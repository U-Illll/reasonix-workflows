#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
round_engine.py — Standard_Mode_Two 的 LangGraph round 状态机引擎

计划书 13.1 / 13.2 / 18.2 的落地实现（路线二定案）。
职责：round 状态跟踪 / 迁移合法性校验 / 终止判定辅助 / 持久化（SQLite checkpointer）/ 多战例隔离（thread_id）。

⚠️ 红线（与 `Standard_Mode_Two` 框架 skill §3 一致）：
  本引擎是 L4 调度层的【辅助记录器/校验器】，不是循环主控。
  - 只回答"当前在哪、该往哪迁、是否合法、终止建议"
  - 不写任务书、不调用执行层、不裁决（裁决权唯一在指挥官 = 主 Agent）

用法（venv 内，依赖见 requirements.txt）：
  python round_engine.py transition --campaign campaign-desktop --round 5 --to EXECUTING [--mode R2+C1+P3+T1 --domain windows --note "任务书已下发"]
  python round_engine.py status      --campaign campaign-desktop --round 5
  python round_engine.py check-termination --campaign campaign-desktop --round 5 --receipts receipts.json
  python round_engine.py reset       --campaign campaign-desktop --round 5
  python round_engine.py list        --campaign campaign-desktop
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, Literal, Optional, TypedDict

# ── LangGraph ────────────────────────────────────────────────────────────────
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

# ── 状态定义（13.1 round 状态机）──────────────────────────────────────────────
StateName = Literal[
    "IDLE",
    "DISPATCH",
    "EXECUTING",
    "RETURNED",
    "DISCUSSING",
    "ADJUDICATED",
    "TERMINATED",
    "BASE_SWITCH",
]

STATE_NODES: list[str] = [
    "IDLE",
    "DISPATCH",
    "EXECUTING",
    "RETURNED",
    "DISCUSSING",
    "ADJUDICATED",
    "TERMINATED",
    "BASE_SWITCH",
]

# 合法迁移表（13.1 迁移图 + 8.1 终止出口）
VALID_TRANSITIONS: dict[str, list[str]] = {
    "IDLE": ["DISPATCH"],                                   # 新轮开始
    "DISPATCH": ["EXECUTING"],                              # 任务书下发 → 执行
    "EXECUTING": ["RETURNED"],                              # 执行 → 回执
    "RETURNED": ["DISCUSSING"],                             # 回执 → 讨论
    "DISCUSSING": ["ADJUDICATED"],                          # 讨论 → 裁决
    "ADJUDICATED": ["IDLE", "TERMINATED", "BASE_SWITCH"],   # 裁决后：下一轮 / 终止 / 换基底
    "BASE_SWITCH": ["IDLE"],                                # 换基底重置计数 → 下一轮
    "TERMINATED": [],                                       # 终局，无出边
}

DEFAULT_STATE = "IDLE"


# ── LangGraph State ───────────────────────────────────────────────────────────
class RoundState(TypedDict, total=False):
    current: str                 # 当前状态
    to: str                      # 目标状态（本次迁移）
    final: bool                  # 是否已到达目标状态（一次 invoke 迁移一步）
    error: Optional[str]         # 非法迁移的错误信息
    campaign: str                # 战例名
    round: int                   # round_id（全局递增）
    mode: Optional[str]          # 四轴组合，如 "R2+C1+P3+T1"
    domain: Optional[str]        # browser / windows / static
    note: Optional[str]          # 阶段备注（如 "任务书已下发"）
    timestamp: str               # 最近一次迁移时间（UTC ISO）
    history: Annotated[list[dict[str, Any]], add]  # 迁移日志（增量累积）


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 节点与边 ──────────────────────────────────────────────────────────────────
def _make_node(name: str):
    """每个状态一个节点：若自己是本次迁移目标 → 落定并返回 final；否则途经继续路由。"""

    def node(state: RoundState) -> dict[str, Any]:
        # 节点收到的是"迁移前的状态"，目标迁移由条件边完成。
        # 条件边已按合法性路由到目标节点；此处若 to==name 说明刚落定。
        if state.get("to") == name:
            return {
                "current": name,
                "final": True,
                "timestamp": _now(),
            }
        return {}

    return node


def _invalid_node(state: RoundState) -> dict[str, Any]:
    cur = state.get("current", DEFAULT_STATE)
    to = state.get("to")
    valid = VALID_TRANSITIONS.get(cur, [])
    return {
        "final": True,
        "error": f"非法迁移: {cur} → {to}（合法目标: {valid or '无（终局）'}）",
        "timestamp": _now(),
    }


def _router(state: RoundState) -> str:
    """条件边：已落定 → END；未落定 → 校验后路由到目标节点或 INVALID。"""
    if state.get("final"):
        return END
    cur = state.get("current", DEFAULT_STATE)
    to = state.get("to")
    if cur in VALID_TRANSITIONS and to in VALID_TRANSITIONS[cur]:
        return to
    return "INVALID"


def build_graph() -> StateGraph:
    """构建 round 状态机图（未编译）。调用处 compile 并注入 checkpointer。"""
    builder = StateGraph(RoundState)

    for s in STATE_NODES:
        builder.add_node(s, _make_node(s))
    builder.add_node("INVALID", _invalid_node)

    builder.add_edge(START, "IDLE")

    # 每个节点（含 IDLE 入口）都用同一条件边路由
    for s in STATE_NODES + ["INVALID"]:
        builder.add_conditional_edges(
            s,
            _router,
            {"IDLE": "IDLE", "DISPATCH": "DISPATCH", "EXECUTING": "EXECUTING",
             "RETURNED": "RETURNED", "DISCUSSING": "DISCUSSING",
             "ADJUDICATED": "ADJUDICATED", "TERMINATED": "TERMINATED",
             "BASE_SWITCH": "BASE_SWITCH", "INVALID": "INVALID", END: END},
        )

    return builder


# ── 终止判定辅助（18.2，仅建议，最终判定权在指挥官）─────────────────────────
def check_termination(
    receipts: list[dict[str, Any]],
    rounds_no_progress: int = 0,
    total_rounds: int = 0,
    turn_budget: int = 80,
    max_idle_rounds: int = 6,
) -> dict[str, Any]:
    """对最近几轮回执做三级终止建议。

    receipts: 最近 ≤3 轮回执（按 round_id 升序）。每项含 status/data/drift_hint。
    返回: {verdict, reason, matched_rule}
      verdict ∈ {continue, soft_exit_dead_end, soft_exit_budget, terminated_success,
                 terminated_infeasible, human_interrupt, t4_downgrade}
    """
    result: dict[str, Any] = {"verdict": "continue", "reason": "", "matched_rule": None}

    if not receipts:
        result["reason"] = "无回执，无法判定"
        return result

    last = receipts[-1]

    # 硬退出-成功
    if last.get("status") == "success":
        result.update(verdict="terminated_success",
                      reason="回执 status=success：成功判据达成",
                      matched_rule="hard_exit_success")
        return result

    # 硬退出-不可行（status=dead_end 且置信度 > 0.9）
    if last.get("status") == "dead_end" and last.get("confidence", 0) > 0.9:
        result.update(verdict="terminated_infeasible",
                      reason="dead_end + confidence>0.9：高置信不可行证明",
                      matched_rule="hard_exit_infeasible")
        return result

    # T4 信任降级信号：drift 回执不计入"一致报错"
    drift_count = sum(1 for r in receipts if r.get("drift_hint") == "drift")
    if drift_count >= 2:
        result.update(verdict="t4_downgrade",
                      reason=f"最近 {len(receipts)} 轮回执中 {drift_count} 条 drift_hint=drift：模型漂移，先 T4 降级再谈方向",
                      matched_rule="t4_trust_downgrade")
        return result

    # 软退出-死胡同：连续 3 轮回执 status 与 data 完全一致（且均非 drift）
    if len(receipts) >= 3:
        clean = [r for r in receipts if r.get("drift_hint") != "drift"][-3:]
        if len(clean) == 3:
            s0, s1, s2 = clean
            if s0.get("status") == s1.get("status") == s2.get("status") and \
               s0.get("data") == s1.get("data") == s2.get("data"):
                result.update(verdict="soft_exit_dead_end",
                              reason="连续 3 轮回执 status+data 完全一致：死胡同，触发换基底策略",
                              matched_rule="soft_exit_identical_error")
                return result

    # 软退出-预算：80 turn 耗尽 或 6 轮无进展
    if last.get("turns", 0) >= turn_budget:
        result.update(verdict="soft_exit_budget",
                      reason=f"执行层 turn 数 {last.get('turns')} ≥ {turn_budget}：预算耗尽",
                      matched_rule="soft_exit_budget_turns")
        return result
    if rounds_no_progress >= max_idle_rounds or total_rounds >= 12:
        result.update(verdict="soft_exit_budget",
                      reason=f"无进展 {rounds_no_progress} 轮 / 总轮数 {total_rounds}：预算软退出，收敛为阶段性结论落盘",
                      matched_rule="soft_exit_budget_rounds")
        return result

    result["reason"] = "无终止条件命中，继续下一轮（round_id+1）"
    return result


# ── SQLite checkpointer 上下文 ───────────────────────────────────────────────
def _db_path(db: str) -> str:
    return os.path.abspath(db)


# ── CLI ───────────────────────────────────────────────────────────────────────
def _thread_id(campaign: str, round_id: int) -> str:
    return f"{campaign}:{round_id}"


def cmd_transition(args) -> int:
    thread = _thread_id(args.campaign, args.round)
    db = _db_path(args.db)

    with SqliteSaver.from_conn_string(db) as saver:
        graph = build_graph()
        graph = graph.compile(checkpointer=saver)

        config = {"configurable": {"thread_id": thread}}

        # 读取当前状态（首次 = IDLE 默认）
        cur = "IDLE"
        snap = saver.get_tuple(config)
        if snap is not None and snap.checkpoint is not None:
            cur = snap.checkpoint.get("channel_values", {}).get("current", "IDLE")
        else:
            # 首次：需要先建立 IDLE 基线
            graph.invoke(
                {"current": "IDLE", "to": "IDLE", "campaign": args.campaign,
                 "round": args.round, "timestamp": _now(),
                 "history": [{"from": None, "to": "IDLE", "ts": _now(), "note": "初始化"}]},
                config=config,
            )

        # 校验本次迁移
        if cur not in VALID_TRANSITIONS or args.to not in VALID_TRANSITIONS.get(cur, []):
            print(f"[非法] {cur} → {args.to}（合法目标: {VALID_TRANSITIONS.get(cur, []) or '无（终局）'}）", file=sys.stderr)
            return 2

        # 执行迁移：一次 invoke 走 START→cur(途经)→目标(落定)→END
        # 注意：invoke 输入是部分更新，必须显式重置 final=False（否则 checkpoint 残留 final=true 直接走 END）
        result = graph.invoke(
            {
                "current": cur,
                "to": args.to,
                "final": False,
                "campaign": args.campaign,
                "round": args.round,
                "mode": args.mode,
                "domain": args.domain,
                "note": args.note,
                "timestamp": _now(),
                "history": [{"from": cur, "to": args.to, "ts": _now(), "note": args.note}],
            },
            config=config,
        )

        print(json.dumps({
            "campaign": args.campaign,
            "round": args.round,
            "transitioned": f"{cur} → {args.to}",
            "current": result.get("current"),
            "error": result.get("error"),
            "history_len": len(result.get("history", [])),
        }, ensure_ascii=False, indent=2))
        return 0 if not result.get("error") else 3


def cmd_status(args) -> int:
    thread = _thread_id(args.campaign, args.round)
    db = _db_path(args.db)

    with SqliteSaver.from_conn_string(db) as saver:
        graph = build_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread}}
        state = graph.get_state(config)

        if state is None or state.values is None or not state.values:
            print(json.dumps({"campaign": args.campaign, "round": args.round,
                              "current": "IDLE", "history": []}, ensure_ascii=False, indent=2))
            return 0

        vals = state.values
        print(json.dumps({
            "campaign": vals.get("campaign"),
            "round": vals.get("round"),
            "current": vals.get("current", "IDLE"),
            "mode": vals.get("mode"),
            "domain": vals.get("domain"),
            "last_ts": vals.get("timestamp"),
            "error": vals.get("error"),
            "history": vals.get("history", []),
        }, ensure_ascii=False, indent=2))
        return 0


def cmd_list(args) -> int:
    db = _db_path(args.db)
    import sqlite3
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serializer = JsonPlusSerializer()
    prefix = f"{args.campaign}:"
    with sqlite3.connect(db) as con:
        # 每个 thread 取最新 checkpoint（checkpoint_id 降序第一行）；checkpoint 列为 msgpack
        rows = []
        seen = set()
        for tid, cid, ctype, blob in con.execute(
            "SELECT thread_id, checkpoint_id, type, checkpoint FROM checkpoints ORDER BY checkpoint_id DESC"
        ):
            if not str(tid).startswith(prefix) or tid in seen:
                continue
            seen.add(tid)
            try:
                cp = serializer.loads_typed((ctype or "json", blob)) if blob else {}
                vals = cp.get("channel_values", {}) if isinstance(cp, dict) else {}
            except Exception:
                vals = {}
            rows.append({"thread": tid, "round": vals.get("round"),
                         "current": vals.get("current"), "last_ts": vals.get("timestamp")})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0


def cmd_check_termination(args) -> int:
    with open(args.receipts, encoding="utf-8") as f:
        receipts = json.load(f)
    verdict = check_termination(
        receipts,
        rounds_no_progress=args.no_progress,
        total_rounds=args.total_rounds,
        turn_budget=args.turn_budget,
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


def cmd_reset(args) -> int:
    thread = _thread_id(args.campaign, args.round)
    db = _db_path(args.db)
    with SqliteSaver.from_conn_string(db) as saver:
        config = {"configurable": {"thread_id": thread}}
        snap = saver.get_tuple(config)
        if snap is None:
            print(f"thread {thread} 不存在，无需重置", file=sys.stderr)
            return 1
        saver.delete_thread(thread)
        print(f"已重置 thread {thread}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="round_engine", description="Standard_Mode_Two round 状态机引擎（LangGraph）")
    parser.add_argument("--db", default="round-state.db", help="SQLite checkpointer 路径（默认 ./round-state.db）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("transition", help="登记一次状态迁移")
    p.add_argument("--campaign", required=True)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--to", required=True, choices=STATE_NODES)
    p.add_argument("--mode")
    p.add_argument("--domain", choices=["browser", "windows", "static"])
    p.add_argument("--note")
    p.set_defaults(fn=cmd_transition)

    p = sub.add_parser("status", help="查询当前状态与迁移历史")
    p.add_argument("--campaign", required=True)
    p.add_argument("--round", type=int, required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("list", help="列出战例所有 round 状态")
    p.add_argument("--campaign", required=True)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("check-termination", help="终止判定辅助（18.2，仅建议）")
    p.add_argument("--campaign", required=True)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--receipts", required=True, help="最近 ≤3 轮回执 JSON 文件路径")
    p.add_argument("--no-progress", type=int, default=0)
    p.add_argument("--total-rounds", type=int, default=0)
    p.add_argument("--turn-budget", type=int, default=80)
    p.set_defaults(fn=cmd_check_termination)

    p = sub.add_parser("reset", help="重置某 round 的状态")
    p.add_argument("--campaign", required=True)
    p.add_argument("--round", type=int, required=True)
    p.set_defaults(fn=cmd_reset)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
