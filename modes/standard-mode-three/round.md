---
name: mode-three-round
description: 标准模式三 round 状态机模块（由 Standard_Mode_Three 路由加载）：P0-P6 节点迁移、DECOMPOSE 拆分节点、四档终止判定、零信息 streak、超时/故障分支、持久化。勿直接作为任务入口
---

# mode-three-round — 标准模式三 Round 状态机

> 由 `Standard_Mode_Three` 路由加载。本节定义 round 循环的状态机语义与终止判定，是模式三的"时钟与刹车"。

## 1. 节点迁移表(引擎 `mode3_engine.py transition` 校验)

```
主链: GOAL → P0A → P0B → GENERATE → DECOMPOSE → CRITIQUE → ADJUDICATE
      → REVISE → VERIFY → RETRO → CRITIQUE | TERMINATED
任意态可入: HUMAN_HOLD / TERMINATED
HUMAN_HOLD 可回: GOAL / TERMINATED / HUMAN_HOLD(人工介入后重启)
内环: REVISE ⇄ VERIFY ≤3 次(第 4 次拒绝, 防死循环)
```

| 迁移 | 语义 |
|---|---|
| `GENERATE → DECOMPOSE` | **默认路径**：产物交给 Gemini 拆子问题 |
| `DECOMPOSE → CRITIQUE` | 拆分成功（或降级成功），进批评者池 |
| `DECOMPOSE → GENERATE` | 拆分不成立（子问题不可独立评审）→ 退回重做蓝图 |
| `GENERATE → CRITIQUE` | 兼容直连：产物不可拆 / 小任务（`--no-decompose`） |
| `ADJUDICATE → DECOMPOSE` | 裁决发现"问题本身要重拆"，不重跑生成 |

非法迁移示例: `P0A → REVISE` 拒绝; `GOAL → GENERATE` 拒绝。

## 2. 终止判定(`check-termination` 四档 + 三类硬条件)

输入: 近 N 轮 `marginal_gain` + `goal_gap` + `f2p_green` + `no_info_streak` + `quota_left` + `round`。

判定顺序 = 强约束优先：

| 序 | 条件 | 判定 | trigger |
|---|---|---|---|
| 1 | f2p 全绿 且 gap ≥0.95 | TERMINATED | `goal_reached` |
| 2 | 剩余额度 = 0 | TERMINATED | `quota_exhausted` |
| 3 | 当前轮 ≥ `--max-rounds`(默认 12) | TERMINATED | `round_cap` |
| 4 | 连续 2 发零信息增益 | HUMAN_HOLD | `zero_info` |
| 5 | 加权收益 <5 且无 P0 | HUMAN_HOLD | `low_gain` |
| 6 | 加权收益 <15 | CONFIRM | `diminishing` |
| 7 | 加权收益 ≥15 | CONTINUE | `healthy` |

- 加权: 近 3 轮 `[0.5, 0.3, 0.2]`, 近者权重最大。
- `--json` 输出 `{verdict, reason, weighted, trigger}`，供脚本消费；纯文本输出供验收 grep。
- **零信息增益定义**：一发提交后没有排除任何开放假设（`decide_next` 的 `falsifies` 全落空），或除限流/编译错外没有产生新归因类别。由 `trial_ledger` + `decide_next` 判定后传入 `--no-info-streak`。
- 外部终止：存在 `STOP` 文件即停机（调用方检查，优先级最高）。
- 确认轮计入轮数上限，但触发 CONFIRM 时引擎先豁免当前轮。

## 3. 故障分支

| 故障 | 处置 |
|---|---|
| 拆分超时/无正文（Gemini） | `decompose_run.py` 内置 2 轮修复重试；仍失败降级为单子问题（`status=degraded`），**不阻塞** |
| 拆分产物 schema 不过 | 带错误回灌重拆 1 次；仍不过即降级 |
| 批评者超时(>15min) | 标记 `fault_round=1`，不计入终止序列，继续其他批评者 |
| 批评者空正文 / JSON 不合规 | 重试 ≤2（指数退避）；仍失败写 `.fail.json`，`collect` 标 `json_ok=false` |
| 修订者断链 | 跳过该验证域，记录，裁决单注明 |
| 双写冲突 | 单写者原则已防；发生则回滚 + 重启该轮 |
| 引擎非法迁移被拒 | 说明状态机漂移，检查 round 状态，修正后重试 |

## 4. 持久化

- `campaigns`（战例主表/当前状态/内环计数/hold 计数）、`events`（journal 回放）、`ledger`（成本台账）、`critique_log`（批评回执/热力图源）。
- 拆分结果落 `events(event_type='decompose', meta={subtasks,status,out,channel,round})`；`get-state` 返回 `last_decompose`，断点续跑直接复用 `subtasks.json`，**不要重新调 Gemini**。
- 引擎 `--db` 参数指定库；中断后 `get-state` 恢复。

## 5. 人工介入纪律

- 每战例人工介入 ≤5 次(`hold_count` 计数, 超限自动 TERMINATED)。
- HUMAN_HOLD >24h → 自动写阶段性结论并 TERMINATED。
- 目标卡变更 = 新战例, 不走 HUMAN_HOLD。
