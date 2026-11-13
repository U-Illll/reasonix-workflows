#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exit_pool.py — 出口资源池（登记 / 分配 / 状态）

定位：D5 探索群的「出口组合」登记处。一个出口组合 = 一个 IP 出口 + 一个账号（可选）。
只登记**引用 ID**，不存 IP / 账号明文——池文件里永远没有可直接使用的凭据。

关键纪律：
  * 同一组合不得被多节点并发复用（alloc 即锁定，release 才释放）。
  * 一个 node 至多持一个组合；重复 alloc 幂等（返回原 exit_ref，不再占用新组合）。
  * 池未就绪时，总可用组合数就是 D5 探索并发上限——宁可少方向，不挤同一出口。

用法（--file 缺省 = 本脚本同目录的 exit_pool.json）：
  python3 exit_pool.py add --tier {L1|L2|L3|L4} --ip-source <ref> [--account-ref <ref>] \\
      [--note <s>] [--exit-ref <name>]        # 登记；exit_ref 缺省自动生成 <tier>-<4位hex>
  python3 exit_pool.py list [--tier X] [--status free|allocated]     # 表格，无明细
  python3 exit_pool.py alloc --node-id <id> [--tier X]               # 分配（幂等）
  python3 exit_pool.py release --node-id <id>                        # 释放租约
  python3 exit_pool.py status                                        # 各 tier 计数 + 并发上限
  python3 exit_pool.py probe --exit-ref <ref> [--dry-run]            # 探活（本轮仅 dry-run）

退出码：0 成功 · 2 输入/状态错误 · 3 功能未实现（实连模式）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

TIERS = ("L1", "L2", "L3", "L4")
STATUSES = ("free", "allocated")
EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_NOT_IMPLEMENTED = 3


class PoolError(Exception):
    """池文件或输入状态错误 → 退出码 2。"""


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


DEFAULT_FILE = os.path.join(script_dir(), "exit_pool.json")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def die(msg, code=EXIT_INPUT_ERROR):
    sys.stderr.write("exit_pool: %s\n" % msg)
    return code


def load_pool(path, create=False):
    """读池。文件不存在：create=True 则初始化为空池，否则按空池处理并提示。"""
    if not os.path.exists(path):
        if create:
            parent = os.path.dirname(os.path.abspath(path))
            if not os.path.isdir(parent):
                raise PoolError("父目录不存在：%s" % parent)
            save_pool(path, {"combos": []})
        else:
            sys.stderr.write("exit_pool: 池文件不存在，按空池处理：%s\n" % path)
        return {"combos": []}
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as exc:
            raise PoolError("池文件不是合法 JSON：%s（%s）" % (path, exc))
    if not isinstance(data, dict) or not isinstance(data.get("combos"), list):
        raise PoolError('池文件结构非法，应为 {"combos": [...]}：%s' % path)
    return data


def save_pool(path, pool):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
        f.write("\n")


def combos_of(pool):
    return pool["combos"]


def find_combo(pool, exit_ref):
    for c in combos_of(pool):
        if c.get("exit_ref") == exit_ref:
            return c
    return None


def gen_exit_ref(pool, tier):
    """自动生成 <tier>-<4位hex>，与现有引用去重。"""
    used = {c.get("exit_ref") for c in combos_of(pool)}
    for _ in range(64):
        ref = "%s-%s" % (tier, os.urandom(2).hex())
        if ref not in used:
            return ref
    raise PoolError("自动生成 exit_ref 失败（碰撞过多），请用 --exit-ref 显式指定")


def lease_node(combo):
    lease = combo.get("lease")
    if isinstance(lease, dict):
        return lease.get("node_id")
    return None


# --------------------------------------------------------------------------- 子命令

def cmd_add(pool, path, tier, ip_source, account_ref, note, exit_ref):
    ref = exit_ref or gen_exit_ref(pool, tier)
    if find_combo(pool, ref) is not None:
        raise PoolError("exit_ref 重复：%s" % ref)
    combo = {
        "exit_ref": ref,
        "tier": tier,
        "ip_source": ip_source,
        "status": "free",
        "lease": None,
    }
    if account_ref:
        combo["account_ref"] = account_ref
    if note:
        combo["note"] = note
    combos_of(pool).append(combo)
    save_pool(path, pool)
    print("%s  free" % ref)
    return EXIT_OK


def cmd_list(pool, tier, status):
    rows = [c for c in combos_of(pool)
            if (tier is None or c.get("tier") == tier)
            and (status is None or c.get("status") == status)]
    if not rows:
        print("(无匹配组合)")
        return EXIT_OK
    w_ref = max([len("exit_ref")] + [len(str(c.get("exit_ref", ""))) for c in rows])
    w_tier = max([len("tier")] + [len(str(c.get("tier", ""))) for c in rows])
    w_st = max([len("status")] + [len(str(c.get("status", ""))) for c in rows])
    print("%-*s  %-*s  %-*s  %s" % (w_ref, "exit_ref", w_tier, "tier", w_st, "status", "lease_node"))
    for c in rows:
        print("%-*s  %-*s  %-*s  %s" % (w_ref, str(c.get("exit_ref", "")), w_tier,
                                        str(c.get("tier", "")), w_st, str(c.get("status", "")),
                                        lease_node(c) or "-"))
    return EXIT_OK


def cmd_alloc(pool, path, node_id, tier):
    # 幂等：该 node 已持有组合 → 直接返回，不再占用新的
    for c in combos_of(pool):
        if c.get("status") == "allocated" and lease_node(c) == node_id:
            print("%s  （幂等：%s 已持有，未新增占用）" % (c["exit_ref"], node_id))
            return EXIT_OK
    free = [c for c in combos_of(pool) if c.get("status") == "free"]
    cand = [c for c in free if tier is None or c.get("tier") == tier]
    if not cand:
        if not combos_of(pool):
            raise PoolError("池未就绪：池内无任何组合（先 add 登记出口组合）")
        if not free:
            raise PoolError("无可用组合：全部已分配（先 release 释放租约）")
        raise PoolError("无可用组合：tier=%s 内无 free 组合（可用池在其它 tier）" % tier)
    combo = cand[0]                       # 按登记顺序取第一个 free
    combo["status"] = "allocated"
    combo["lease"] = {"node_id": node_id, "ts": now_iso()}
    save_pool(path, pool)
    print("%s  -> %s (tier=%s)" % (combo["exit_ref"], node_id, combo.get("tier")))
    return EXIT_OK


def cmd_release(pool, path, node_id):
    held = [c for c in combos_of(pool)
            if c.get("status") == "allocated" and lease_node(c) == node_id]
    if not held:
        raise PoolError("该 node 无租约（无可释放组合）：%s" % node_id)
    for c in held:
        c["status"] = "free"
        c["lease"] = None
    save_pool(path, pool)
    print("released %s -> %s" % (",".join(c["exit_ref"] for c in held), node_id))
    return EXIT_OK


def cmd_status(pool, path):
    print("池文件: %s" % path)
    print("%-6s %-6s %-11s %s" % ("tier", "free", "allocated", "合计"))
    total_free = total_alloc = 0
    for t in TIERS:
        rows = [c for c in combos_of(pool) if c.get("tier") == t]
        f = sum(1 for c in rows if c.get("status") == "free")
        a = sum(1 for c in rows if c.get("status") == "allocated")
        total_free += f
        total_alloc += a
        print("%-6s %-6d %-11d %d" % (t, f, a, len(rows)))
    # 未知 tier（池文件被手工改过时仍如实计数）
    others = [c for c in combos_of(pool) if c.get("tier") not in TIERS]
    if others:
        f = sum(1 for c in others if c.get("status") == "free")
        a = sum(1 for c in others if c.get("status") == "allocated")
        total_free += f
        total_alloc += a
        print("%-6s %-6d %-11d %d" % ("其它", f, a, len(others)))
    print("-" * 34)
    print("组合总数: %d（free %d / allocated %d）" % (len(combos_of(pool)), total_free, total_alloc))
    print("总可用组合数（free）= %d   ← 该值即 D5 探索并发上限" % total_free)
    if total_free == 0:
        print("  ⚠ 池未就绪：探索并发度降级为 0——宁可少方向，不挤同一出口")
    return EXIT_OK


def cmd_probe(pool, exit_ref, dry_run):
    combo = find_combo(pool, exit_ref)
    if combo is None:
        raise PoolError("exit_ref 不存在：%s" % exit_ref)
    if not dry_run:
        print("实连模式待池建立后专项实施（B4-1）")
        return EXIT_NOT_IMPLEMENTED
    acct = combo.get("account_ref") or "(未登记)"
    print("probe 动作计划（--dry-run：不发起任何网络请求）")
    print("  exit_ref  : %s" % combo.get("exit_ref"))
    print("  tier      : %s" % combo.get("tier"))
    print("  ip_source : %s" % combo.get("ip_source"))
    print("  account   : %s" % acct)
    print("  status    : %s（lease=%s）" % (combo.get("status"), lease_node(combo) or "-"))
    print("  ---")
    print("  [1/4] 读取 mihomo 配置端口（只读端口号，不读凭据）")
    print("  [2/4] PUT /proxies/<组> —— 切换到 ip_source 引用对应的组")
    print("  [3/4] GET IP 回显 —— 校验切换已生效")
    print("  [4/4] 聚合输出 —— IP 摘要 + 时延 + 结果（脱敏后写回执）")
    print("  ---")
    print("  本次为 dry-run，以上步骤均未执行；实连模式见 B4-1。")
    return EXIT_OK


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(prog="exit_pool.py", description="出口资源池（登记/分配/状态）")
    p.add_argument("--file", default=DEFAULT_FILE, help="池文件路径（缺省=<脚本目录>/exit_pool.json）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="登记一个出口组合（只存引用 ID）")
    pa.add_argument("--tier", required=True, choices=TIERS)
    pa.add_argument("--ip-source", dest="ip_source", required=True, help="IP 出口引用（非明文地址）")
    pa.add_argument("--account-ref", dest="account_ref", default=None, help="账号引用（可选）")
    pa.add_argument("--note", default=None)
    pa.add_argument("--exit-ref", dest="exit_ref", default=None, help="缺省自动生成 <tier>-<4位hex>")

    pl = sub.add_parser("list", help="列出组合（无明细）")
    pl.add_argument("--tier", default=None, choices=TIERS)
    pl.add_argument("--status", default=None, choices=STATUSES)

    pc = sub.add_parser("alloc", help="给 node 分配一个 free 组合（每 node 至多一个，幂等）")
    pc.add_argument("--node-id", dest="node_id", required=True)
    pc.add_argument("--tier", default=None, choices=TIERS)

    pr = sub.add_parser("release", help="释放 node 的租约")
    pr.add_argument("--node-id", dest="node_id", required=True)

    sub.add_parser("status", help="各 tier 计数 + 总可用组合数")

    pp = sub.add_parser("probe", help="探活（本轮仅 --dry-run 可用）")
    pp.add_argument("--exit-ref", dest="exit_ref", required=True)
    pp.add_argument("--dry-run", dest="dry_run", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    path = args.file
    try:
        if args.cmd == "add":
            pool = load_pool(path, create=True)
            return cmd_add(pool, path, args.tier, args.ip_source,
                           args.account_ref, args.note, args.exit_ref)
        if args.cmd == "list":
            return cmd_list(load_pool(path), args.tier, args.status)
        if args.cmd == "alloc":
            pool = load_pool(path, create=True)
            return cmd_alloc(pool, path, args.node_id, args.tier)
        if args.cmd == "release":
            pool = load_pool(path, create=True)
            return cmd_release(pool, path, args.node_id)
        if args.cmd == "status":
            return cmd_status(load_pool(path), path)
        if args.cmd == "probe":
            return cmd_probe(load_pool(path), args.exit_ref, args.dry_run)
    except PoolError as exc:
        return die(str(exc))
    return die("未知子命令：%s" % args.cmd)


if __name__ == "__main__":
    sys.exit(main())
