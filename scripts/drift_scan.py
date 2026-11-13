#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""drift_scan.py — 漂移/净化规则检测（观测模式，v1.1 阶段 A）

用途：回执五关的第 4/5 关规则部分（mode-two-round §5）。
  观测模式 = 只记不拦：默认只输出命中类别/计数/行号，退出码恒 0。
  --block：cleanse 类命中时退出码 1（净化解=硬线，命中即阻断）。
输出纪律：绝不打印命中原文——只打印类别、计数、行号（防翻转泄漏）。

用法：
  python3 drift_scan.py <file>            # 文本报告（观测）
  python3 drift_scan.py <file> --json     # JSON 报告（观测）
  python3 drift_scan.py -                 # 从 stdin 读
  python3 drift_scan.py <file> --block    # cleanse 命中 → 退出码 1
  python3 drift_scan.py <file> --append <obs.jsonl>
      # 追加一行观测记录（ts/source/bytes/命中数/类别聚合）；
      # 不影响上面的 stdout 报告与退出码语义。obs.jsonl 不存在则创建。
"""
import datetime
import json
import re
import sys

# (类别, 级别, 正则)  级别：drift=漂移关 / cleanse=净化解（硬线）
RULES = [
    ('drift:fullwidth-pipe', 'drift', re.compile(r'[\uFF5C]')),
    ('drift:dsml-residual', 'drift', re.compile(r'DSML', re.I)),
    ('drift:think-leak', 'drift', re.compile(r'<\s*think', re.I)),
    ('drift:latex-residual', 'drift', re.compile(r'\\text\{|\\!')),   # 合法打散语境请人工豁免
    ('cleanse:key-like', 'cleanse', re.compile(r'\bsk-[A-Za-z0-9_\-]{8,}')),
    ('cleanse:bearer', 'cleanse', re.compile(r'[Bb]earer[ \t]+[A-Za-z0-9\-_.=]{16,}')),
    ('cleanse:private-key', 'cleanse', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('cleanse:proxy-uri', 'cleanse', re.compile(r'\b(vmess|vless|trojan|ss|ssr|hysteria2?|tuic)://', re.I)),
    ('cleanse:long-b64', 'cleanse', re.compile(r'[A-Za-z0-9+/]{120,}={0,2}')),
]


def scan(text):
    hits = []
    lines = text.splitlines()
    for name, level, rx in RULES:
        ln = []
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                ln.append(i)
        if ln:
            hits.append({'rule': name, 'level': level, 'count': len(ln), 'lines': ln[:20]})
    # JSON 合法性（当文本看起来应是一段 JSON 时）
    t = text.strip()
    if t[:1] in ('{', '['):
        try:
            json.loads(t)
        except Exception:
            hits.append({'rule': 'drift:bad-json', 'level': 'drift', 'count': 1, 'lines': [1]})
    return hits


def short_name(rule):
    """'drift:fullwidth-pipe' -> 'fullwidth-pipe'（冒号后段为类别短名）。"""
    return rule.split(':', 1)[1] if ':' in rule else rule


def aggregate_categories(hits):
    """按类别短名累计命中数；无命中 -> {}。"""
    cats = {}
    for h in hits:
        name = short_name(h['rule'])
        cats[name] = cats.get(name, 0) + h.get('count', 0)
    return cats


def append_observation(path, source, nbytes, drift_n, cleanse_n, hits):
    """向 obs.jsonl 追加一行观测记录。

    纪律：只落计数与类别短名，绝不落命中原文（防翻转泄漏）。
    返回写入的 dict。
    """
    rec = {
        'ts': datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds'),
        'source': source,
        'bytes': nbytes,
        'drift_hits': drift_n,
        'cleanse_hits': cleanse_n,
        'categories': aggregate_categories(hits),
    }
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
    return rec


def take_option(args, name):
    """从参数字表里摘出 `--opt <value>`（就地删除），返回其值；未出现返回 None。"""
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        raise ValueError('%s 需要一个取值' % name)
    val = args[i + 1]
    del args[i:i + 2]
    return val


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    try:
        obs_path = take_option(args, '--append')
    except ValueError as exc:
        sys.stderr.write('drift_scan: %s\n' % exc)
        return 2
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    as_json = '--json' in args
    block = '--block' in args
    if path == '-':
        text = sys.stdin.read()
    else:
        text = open(path, encoding='utf-8', errors='replace').read()
    hits = scan(text)
    drift_n = sum(h['count'] for h in hits if h['level'] == 'drift')
    cleanse_n = sum(h['count'] for h in hits if h['level'] == 'cleanse')
    if as_json:
        print(json.dumps({'file': path, 'bytes': len(text.encode('utf-8', 'replace')),
                          'drift_hits': drift_n, 'cleanse_hits': cleanse_n, 'hits': hits},
                         ensure_ascii=False, indent=2))
    else:
        print('file=%s | bytes=%d | drift_hits=%d | cleanse_hits=%d' % (
            path, len(text.encode('utf-8', 'replace')), drift_n, cleanse_n))
        for h in hits:
            print('  [%s] %s x%d @lines %s' % (h['level'], h['rule'].split(':', 1)[1], h['count'],
                                               ','.join(str(x) for x in h['lines'][:10])))
        if not hits:
            print('  （干净）')
    if obs_path:
        try:
            append_observation(obs_path, 'stdin' if path == '-' else path,
                               len(text.encode('utf-8', 'replace')), drift_n, cleanse_n, hits)
        except OSError as exc:
            sys.stderr.write('drift_scan: 观测记录写入失败：%s\n' % exc)
            return 2
    if block and cleanse_n > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
