#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""explore_ledger.py — 探索节点树 ledger（JSONL 单调追加 + 链式完整性校验）

三条纪律：
  1. 单调追加：只 append 新行，历史行永不改写（没有 update/delete 子命令）。
  2. 链式校验：每行带 prev_hash = 前一整行原始文本（不含换行）的
     sha256(...).hexdigest()[:16]；首行固定 "GENESIS"。
     任何对历史行的篡改都会让下一行的 prev_hash 失配 —— 篡改不可隐藏。
  3. 序列化固定为 json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
     紧凑无空格，保证哈希可逐字节复算。

用法（--file 必须置于子命令之前）：
  python3 explore_ledger.py --file <ledger.jsonl> root [--name <探索地图名>]
      # 追加根行：node_id="root", parent=null, status="running"
  python3 explore_ledger.py --file <ledger.jsonl> append --node <id> --parent <id> --status <s> \
      [--card <path>] [--exit-ref <ref>]
  python3 explore_ledger.py --file <ledger.jsonl> tree      # 缩进树（2 空格 × 深度）
  python3 explore_ledger.py --file <ledger.jsonl> verify    # 完整性校验

退出码：0 正常 / 1 verify 发现完整性问题 / 2 输入或状态错误（含文件不存在）。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

STATUSES = ("running", "done", "dead_end", "uncertain")
GENESIS = "GENESIS"
REQUIRED_FIELDS = ("ts", "node_id", "parent", "status", "prev_hash")
EXIT_OK = 0
EXIT_VERIFY_FAIL = 1
EXIT_INPUT_ERROR = 2


def now_iso():
    """当前时间，ISO8601 带时区偏移（秒精度）。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dumps(obj):
    """ledger 的唯一合法序列化形式。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def line_hash(raw_line):
    """前一整行原始文本（不含换行）的 sha256，取前 16 位。"""
    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()[:16]


def die(msg, code=EXIT_INPUT_ERROR):
    sys.stderr.write("explore_ledger: %s\n" % msg)
    return code


def read_lines(path):
    """按字节读入，返回 [(行号, 不含换行的原始行文本)]。

    容忍 CRLF：若行尾是 \\r 则剥掉（视作换行的一部分，不属于行内容）。
    文件末尾的那个终止换行不产生额外一行。
    """
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        return []
    text = data.decode("utf-8")
    out = []
    for i, raw in enumerate(text.split("\n"), 1):
        if raw.endswith("\r"):
            raw = raw[:-1]
        out.append((i, raw))
    if out and out[-1][1] == "" and text.endswith("\n"):
        out.pop()
    return out


def parse_ledger(path):
    """解析 ledger，返回 (entries, raws, problems)。

    problems: [(行号, 原因)]；无法解析的行在 entries 中占位 None。
    """
    lines = read_lines(path)
    entries, raws, problems = [], [], []
    for lineno, raw in lines:
        raws.append(raw)
        try:
            obj = json.loads(raw)
        except Exception as exc:
            problems.append((lineno, "JSON 非法：%s" % exc))
            entries.append(None)
            continue
        if not isinstance(obj, dict):
            problems.append((lineno, "顶层不是 JSON 对象"))
            entries.append(None)
            continue
        entries.append(obj)
    return entries, raws, problems


def append_line(path, obj):
    """单调追加一行。"""
    line = dumps(obj)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    return line


def check_parent_dir(path):
    """目标父目录必须已存在（工具不自建目录）。"""
    d = os.path.dirname(os.path.abspath(path))
    return d if os.path.isdir(d) else None


def known_ids(entries):
    """从已解析行中取 node_id 列表；若有行缺 node_id 返回 None。"""
    ids = []
    for e in entries:
        nid = e.get("node_id")
        if not isinstance(nid, str) or not nid:
            return None
        ids.append(nid)
    return ids


def verify_lines(lines):
    """对 [(行号, 原始行)] 做完整性校验，返回 [(行号, 原因)]（空列表 = 全过）。

    检查项：JSON 合法、字段齐全、status 枚举、node_id 唯一、parent 引用存在、
    prev_hash 链完整。只输出行号与原因，不回显整行内容。
    """
    problems = []
    entries = []
    seen = set()
    prev_raw = None
    prev_lineno = None
    for lineno, raw in lines:
        # 1) JSON 合法
        try:
            obj = json.loads(raw)
        except Exception as exc:
            problems.append((lineno, "JSON 非法：%s" % exc))
            entries.append(None)
            prev_raw, prev_lineno = raw, lineno
            continue
        if not isinstance(obj, dict):
            problems.append((lineno, "顶层不是 JSON 对象"))
            entries.append(None)
            prev_raw, prev_lineno = raw, lineno
            continue
        entries.append(obj)
        # 2) 字段齐全
        missing = [f for f in REQUIRED_FIELDS if f not in obj]
        if missing:
            problems.append((lineno, "字段缺失：%s" % ",".join(missing)))
        # 3) status 枚举
        if "status" in obj and obj["status"] not in STATUSES:
            problems.append((lineno, "status 非法：%r" % (obj["status"],)))
        # 4) node_id 唯一
        nid = obj.get("node_id")
        if isinstance(nid, str):
            if nid in seen:
                problems.append((lineno, "node_id 重复：%s" % nid))
            seen.add(nid)
        # 6) prev_hash 链完整
        want = GENESIS if prev_raw is None else line_hash(prev_raw)
        if "prev_hash" in obj and obj["prev_hash"] != want:
            if prev_raw is None:
                problems.append((lineno, 'prev_hash 应为 "GENESIS"，实际 %r' % (obj["prev_hash"],)))
            else:
                problems.append((lineno, "prev_hash 链断裂：应为 %s（第 %d 行哈希），实际 %r"
                                 % (want, prev_lineno, obj["prev_hash"])))
        prev_raw, prev_lineno = raw, lineno
    # 5) parent 引用存在
    for idx, obj in enumerate(entries):
        if obj is None or "parent" not in obj:
            continue
        par = obj["parent"]
        if par is not None and par not in seen:
            problems.append((lines[idx][0], "parent 引用不存在：%s" % par))
    problems.sort(key=lambda t: t[0])
    return problems


# --------------------------------------------------------------------------- 子命令

def cmd_root(path, name):
    if os.path.isdir(path):
        return die("--file 指向的是目录：%s" % path)
    if os.path.exists(path):
        lines = read_lines(path)
        problems = verify_lines(lines)
        if problems:
            return die("ledger 完整性受损，拒绝写入（先跑 verify 定位）：line %d %s" % problems[0])
        raws = [raw for _lineno, raw in lines]
        ids = known_ids([json.loads(raw) for raw in raws])
        if ids is None:
            return die("ledger 已有行缺少 node_id，先跑 verify：%s" % path)
        if "root" in ids:
            return die("根行已存在（node_id=root 重复）：%s" % path)
        prev_hash = line_hash(raws[-1]) if raws else GENESIS
    else:
        d = check_parent_dir(path)
        if d is None:
            return die("父目录不存在：%s" % os.path.dirname(os.path.abspath(path)))
        prev_hash = GENESIS
    obj = {"ts": now_iso(), "node_id": "root", "parent": None, "status": "running"}
    if name:
        obj["name"] = name
    obj["prev_hash"] = prev_hash          # 字段顺序固定：prev_hash 恒为末位
    append_line(path, obj)
    print("root 已追加 -> %s（prev_hash=%s）" % (path, prev_hash))
    return EXIT_OK


def cmd_append(path, node, parent, status, card, exit_ref):
    if not os.path.exists(path):
        return die("ledger 不存在：%s（先用 root 创建）" % path)
    if status not in STATUSES:
        return die("status 非法：%s（允许：%s）" % (status, "|".join(STATUSES)))
    lines = read_lines(path)
    chain_problems = verify_lines(lines)
    if chain_problems:
        return die("ledger 完整性受损，拒绝在断链上追加（先跑 verify 定位）：line %d %s"
                   % chain_problems[0])
    raws = [raw for _lineno, raw in lines]
    ids = known_ids([json.loads(raw) for raw in raws])
    if ids is None:
        return die("ledger 已有行缺少 node_id，先跑 verify：%s" % path)
    if node in ids:
        return die("node_id 重复：%s" % node)
    if parent not in ids:
        return die("parent 不存在：%s" % parent)
    prev_hash = line_hash(raws[-1]) if raws else GENESIS
    obj = {"ts": now_iso(), "node_id": node, "parent": parent, "status": status}
    if card:
        obj["card_path"] = card
    if exit_ref:
        obj["exit_ref"] = exit_ref
    obj["prev_hash"] = prev_hash          # 字段顺序固定：prev_hash 恒为末位
    append_line(path, obj)
    print("append %s -> %s（status=%s parent=%s）" % (node, path, status, parent))
    return EXIT_OK


def cmd_tree(path):
    if not os.path.exists(path):
        return die("ledger 不存在：%s" % path)
    entries, _raws, problems = parse_ledger(path)
    if problems:
        return die("ledger 已损坏，先跑 verify：line %d %s" % problems[0])
    if not entries:
        print("(空 ledger)")
        return EXIT_OK
    nodes = {}
    for e in entries:
        nodes.setdefault(e["node_id"], e)
    children = {}
    for e in entries:
        children.setdefault(e.get("parent"), []).append(e["node_id"])
    visited = set()
    out = []

    def walk(nid, depth):
        if nid in visited or nid not in nodes:
            return
        visited.add(nid)
        e = nodes[nid]
        extra = []
        if e.get("card_path"):
            extra.append("card=%s" % e["card_path"])
        if e.get("exit_ref"):
            extra.append("exit_ref=%s" % e["exit_ref"])
        suffix = ("  " + " ".join(extra)) if extra else ""
        out.append("%s%s (%s)%s" % ("  " * depth, nid, e.get("status"), suffix))
        for c in children.get(nid, []):
            walk(c, depth + 1)

    for e in entries:                      # parent=null 的按根渲染（含多根）
        if e.get("parent") is None:
            walk(e["node_id"], 0)
    for e in entries:                      # 兜底：悬空 parent / 环，按根渲染不静默丢行
        if e["node_id"] not in visited:
            walk(e["node_id"], 0)
    print("\n".join(out))
    return EXIT_OK


def cmd_verify(path):
    if not os.path.exists(path):
        return die("ledger 不存在：%s" % path)
    lines = read_lines(path)
    problems = verify_lines(lines)
    if problems:
        print("verify: FAIL（%d 行，%d 处问题）" % (len(lines), len(problems)))
        for lineno, reason in problems:
            print("  line %d: %s" % (lineno, reason))
        return EXIT_VERIFY_FAIL
    print("verify: ok（%d 行）" % len(lines))
    return EXIT_OK


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(prog="explore_ledger.py",
                                description="探索节点树 ledger（JSONL 单调追加 + 链式校验）")
    p.add_argument("--file", required=True, help="ledger JSONL 路径")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("root", help="追加根行 node_id=root / parent=null / status=running")
    pr.add_argument("--name", default=None, help="探索地图名（仅根行）")

    pa = sub.add_parser("append", help="追加一个探索节点")
    pa.add_argument("--node", required=True)
    pa.add_argument("--parent", required=True)
    pa.add_argument("--status", required=True, help="|".join(STATUSES))
    pa.add_argument("--card", default=None, help="探索卡路径")
    pa.add_argument("--exit-ref", dest="exit_ref", default=None, help="软退出/死路凭证引用")

    sub.add_parser("tree", help="打印缩进树")
    sub.add_parser("verify", help="校验 ledger 完整性")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "root":
        return cmd_root(args.file, args.name)
    if args.cmd == "append":
        return cmd_append(args.file, args.node, args.parent, args.status,
                          args.card, args.exit_ref)
    if args.cmd == "tree":
        return cmd_tree(args.file)
    if args.cmd == "verify":
        return cmd_verify(args.file)
    return die("未知子命令：%s" % args.cmd)


if __name__ == "__main__":
    sys.exit(main())
