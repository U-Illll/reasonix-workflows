---
name: mode-three-domains
description: 标准模式三执行域模块（由 Standard_Mode_Three 路由加载）：P0a 调研/P1.5 拆分/P2 批评/P3 决策/P4 修订/P5 验证与归因六执行域工具链全景。勿直接作为任务入口
---

# mode-three-domains — 标准模式三执行域

> 由 `Standard_Mode_Three` 路由加载。本节定义模式三各执行域的工具链与调用序列。

## 1. P0a 标准调研域(基准锚定)

- 派发: `parallel_tasks`，每个 subagent 调研一个主流产品(同领域 3-5 个)。
- 工具: web_fetch/web_search/gh(官方文档/评测/源码)。
- 产出: `benchmark.md` 能力矩阵(产品 × 能力条目)，每条带来源+调研日期。
- 质量门: 每条能力必须多源交叉；无来源条目标"待验证"；不产优劣结论。
- 复用: 同领域跨战例复用，仅增量更新。

## 2. P1.5 拆分域(Gemini 子问题分解)

```bash
# 输入: 目标卡 + 待审产物快照 + 本轮 diff
# 输出: subtasks.json（3~6 个正交子问题 + coverage + split_quality）
python3 mode3/tools/decompose_run.py \
  --goal goal-card.md --snapshot snapshot.md --diff diff.txt \
  --out subtasks.json --channel gemini-7790 \
  --db campaign.db --campaign <name> --round-no 3
```

- skill: `mode3/skills/gemini-decomposer/SKILL.md`（作为 system prompt 注入；改 skill 立即生效）。
- 校验门（机器）：数量 3~6、id 唯一、`question/target/acceptance` 必填、`acceptance` 可判定、`suggested_roles` 合法、`depends_on` 只引用更小 id。
- 修复重试: 校验错误回灌 1 次；仍失败 → **降级**为单子问题（`status=degraded`），不阻塞下游。
- 落盘: `record-decompose` 写 `events`，`get-state` 可见 `last_decompose`；断点续跑直接复用，**不要重调 Gemini**。
- 判定"要不要拆"：跨 ≥2 模块 / ≥2 类验收维度 / 产物 >300 行或 >12KB / 已知失败模式分属不同根因 → 满足任意 2 条才拆；否则 `--allow-single`。

## 3. P2 批评域(子问题 × 角色，异源并发)

```bash
# 生成任务书矩阵（每子问题取 suggested_roles 前 N 个）
python3 mode3/tools/critic_pool.py plan \
  --subtasks subtasks.json --snapshot snapshot.md --diff diff.txt --goal goal-card.md \
  --outdir ./critic --roles-per-subtask 2 --max-tasks 6 --parallel 6

# 并发执行（2/4/6 档；每通道 1 并发）
python3 mode3/tools/critic_pool.py run --jobs ./critic/jobs.json --parallel 4 \
  --ledger ./critic/ledger.jsonl --summary-out ./critic/run-summary.json

# 汇总
python3 mode3/tools/critic_pool.py collect --dir ./critic/outs \
  --out ./critic/summary.md --json ./critic/summary.json
```

- 输入包（每份任务书）: `子问题陈述 + 该子问题材料片段 + 本轮 diff + 验收标准(goal-card)`。
- 材料切片: `pick_material(snapshot, target)` 按 target 里的文件名/函数名匹配段落，匹配不到取头部 8KB —— **这是"隔离"的物理实现**。
- 回执 schema: `{role, subtask, verdict: pass|fail|unknown, findings:[{severity: P0|P1|P2|P3, category, location, summary, suggestion}], summary}`。
- 纪律: 不串通、不锚定（只给本轮 diff）、不越界（只答本子问题）。
- 故障: 空正文/非 JSON/HTTP 非 200 → 重试 ≤2（指数退避）→ 写 `.fail.json` 并标 `fault_round=1`。

## 4. P3 裁决与决策域(EIG 排序)

```bash
# 下一发排序（读批评者池汇总 + 历史台账 + 剩余额度）
python3 mode3/tools/decide_next.py \
  --findings ./critic/summary.json --history trial-ledger.jsonl \
  --quota-left 37 --local-minutes 25 \
  --out decisions.md --json decisions.json
```

- 公式: `score = EIG × P_ok / (cost × risk)`。
  - `EIG = |失败可排除的开放假设| / |开放假设总数|`
  - `P_ok = 0.5 + 0.3 × (同类历史成功率 − 0.5)`（无历史 = 0.5）
  - `cost = 1 + 本地估时(分钟)/60`；`risk = 1 + 0.5 × 未验证路径数`
- 硬纪律: 候选必须写 `falsifies`；写不出 ⇒ EIG=0；最高 EIG < `--min-eig`(默认 0.1) ⇒ `HUMAN_HOLD`（零信息 streak +1）。
- 输出: `decisions.md`（裁决单附录）+ `decisions.json`（`{decision, next, zero_info_streak, candidates}`）。
- 主 Agent 可覆盖排序，但必须在裁决单写明覆盖理由（否则 P6 复盘无法归因）。

## 5. P4 修订域(动态路由)

| 路由 | 工具链 |
|---|---|
| 主 Agent | read/edit/multi_edit + 模式一五步法(状态检查→计划→依赖→执行→自验) |
| Claude Code | `claude -p` 长链重构(单文件大改/跨模块) |
| codex | `codex exec` 批量修改(机械替换/重复模式) |

- 修订后必跑: `git diff` 摘要 + 受影响文件清单 + 自验(编译/单测)。

## 6. P5 验证与归因域(分域互补)

| 域 | 工具链 | 判定 |
|---|---|---|
| 动态测试 | pytest/仿真主程序 | FAIL_TO_PASS 转绿(必过) |
| 静态分析 | lint/类型检查/依赖审计 | PASS_TO_PASS 不回归 |
| 独立抽查(主 Agent) | 随机路径代码阅读 + 冲突复核定案 | 抽查无 P0 |
| 失败归因 | `classify_failure.py` | 9 类映射 + 建议动作 |

```bash
python3 mode3/tools/classify_failure.py --msg msg.txt --cases cases.json --json
# → {class, confidence, evidence, action, next_probe}
```

- 归因类别: `rate_limit / batch_missing_profiling / compile / precision_gate / pass / numeric / crash_early_return / timeout_or_perf / unknown`。
- 失败归因进入台账后，"同类历史成功率"反哺 `decide_next` 的 `P_ok`。
- 双集回归: `verify_gate.py --f2p` + `--p2p`，两集全绿才 DONE。
- 测试生成端与生成端隔离（防自证清白）。

## 7. 提交台账域(可复现)

```bash
# 追加一次提交（自动归一化平台返回 + 自动归因）
python3 mode3/tools/trial_ledger.py append --file trial-ledger.jsonl \
  --campaign lstsq --round 4 --variant qr-v1 --result sub_detail.json \
  --quota-before 20 --quota-after 19 --decision "C2 实现 QR 主体" --outcome fail

# 报表（按变体 / 按归因）
python3 mode3/tools/trial_ledger.py report --file trial-ledger.jsonl --md report.md
```

- 一行一提交: `ts / round / variant / submission_id / source_md5 / quota / verdict / cases / attribution / decision / outcome`。
- 用途: 终止判定的 gains 序列、决策函数的同类成功率、P6 复盘的变体效率表。

## 8. 工具脚本一览

| 脚本 | 职责 |
|---|---|
| `decompose_run.py` | P1.5 Gemini 拆分（schema 校验 + 修复重试 + 降级） |
| `critic_pool.py` | P2 子问题×角色任务书 + 异源并发 + 汇总 |
| `decide_next.py` | P3 EIG 决策函数 |
| `classify_failure.py` | P5 失败归因（9 类） |
| `trial_ledger.py` | 提交台账（JSONL + 报表） |
| `p0a_survey.py` | P0a 调研任务书生成 + benchmark 质量门 |
| `p2_critics.py` | 旧版 6 角色任务书（保留兼容） |
| `verify_gate.py` | 双集回归（F2P/P2P） |
| `heatmap.py` / `ledger.py` | 批评者贡献热力图 / 成本记账 |

## 9. 环境

- venv: `<REASONIX_HOME>/skills/Standard_Mode_Two/scripts/venv/`
- 引擎: `<HOME>/reasonix-scripts/mode3/engine/mode3_engine.py`（v1.1.0）
- 通道: `:7790` gemini / `:7789` go 池（dsv4pro、kimi、flash 模型）/ `:8080` free-api gateway（gw-dsv4pro、glm、gw-kimi）；稳定集 5 个，矩阵见 `mode3/docs/loop-engineering-20261017.md`
- 参考: `mode3/docs/loop-engineering-20261017.md`（三问答案 + 调研映射 + 实测 + 验收）
