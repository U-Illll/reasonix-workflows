---
name: mode-three-roles
description: 标准模式三 agent 角色模块（由 Standard_Mode_Three 路由加载）：指挥官/拆分者(Gemini)/批评者池(6 通道)/修订者/验证者职责与决策权限矩阵。勿直接作为任务入口
---

# mode-three-roles — 标准模式三 Agent 角色

> 由 `Standard_Mode_Three` 路由加载。本节定义模式三各 Agent 角色的职责边界与决策权限。

## 1. 角色全景

| 角色 | 执行者 | 职责 | 决策权限 |
|---|---|---|---|
| 指挥官(主 Agent) | Reasonix 主会话 | P0b 目标卡起草、P1 蓝图、P3 裁决、P4 路由、P6 复盘 | **唯一裁决权**；终止判定；目标卡提交人工 |
| 人工 X | 用户 | P0b 目标卡拍板；HUMAN_HOLD 介入 | 目标卡唯一批准权；每战例 ≤5 次介入 |
| **拆分者** | **Gemini（`:7790`）** | P1.5 把大问题/待审产物拆成 3~6 个正交子问题 | **无裁决权**；只产子问题，不做评审、不给修复方案 |
| 批评者池 | `critic_pool.py` 子代理（异源 6 通道） | P2 隔离挑刺，结构化回执 | 无裁决权；只给意见+严重级 |
| 决策函数 | `decide_next.py`（主 Agent 执行） | P3 给候选排序与"下一发" | 无裁决权；输出排序与 EIG，主 Agent 采信或覆盖并记录理由 |
| 修订者(动态路由) | 主 Agent / Claude Code / codex | P4 按裁决单修改 | 无裁决权；单写者执行 |
| 验证者(分域) | Claude Code / codex / 主 Agent | P5 动态测试/静态分析/独立抽查 + 失败归因 | 无裁决权；报告+冲突标记 |

## 2. 拆分者（P1.5，本版新增）

| 项 | 约定 |
|---|---|
| 通道 | `:7790/v1`，`gemini-4-argon-contributor`（实测 3.1s） |
| skill 注入 | `mode3/skills/gemini-decomposer/SKILL.md` 全文作为 system prompt |
| 输入 | 目标卡 + 待审产物快照 + 本轮 diff（截断到 24KB） |
| 输出 | 严格 JSON：`subtasks[3~6]{id,title,question,target,acceptance,suggested_roles,priority,depends_on}` + `coverage` + `split_quality` |
| 硬约束 | 正交、可独立评审、可验收；`question` 必须是判断句；`acceptance` 禁止主观词 |
| 失败处理 | 1 次修复重试（错误回灌）→ 仍失败降级为单子问题（`status=degraded`） |
| 禁止 | 输出评审意见、修复方案、代码质量结论（越界即整份作废） |

- 拆分器**不是批评者**：它回答"怎么切"，不回答"好不好"。
- 拆分质量自检由机器做（数量/字段/角色/依赖），语义质量由 `split_quality` 字段与 P6 复盘回溯。

## 3. 批评者池（默认 6 角色，可配）

| 角色 | 关注点 | 类别标签 |
|---|---|---|
| 架构批评者 | 模块划分/依赖方向/扩展性 | architecture |
| 安全对抗批评者 | 对抗视角/攻击面/绕过(网安场景必带) | security |
| 代码正确性批评者 | 崩溃/逻辑错误/边界条件 | correctness |
| 性能批评者 | 复杂度/资源/并发/访存 | performance |
| 规范接口批评者 | 命名/接口一致性/文档 | convention |
| 对比批评者 | 与目标/benchmark 逐项对比，输出差距 | benchmark_gap |

**异源通道矩阵（2026-10-17 实测）**：

| 通道 | 模型 | 延迟 | 备注 |
|---|---|---|---|
| `gemini` | gemini-4-argon-contributor | 3.1s | 同时是拆分器 |
| `dsv4pro` | deepseek-v4-pro | 2.3s | thinking，max_tokens ≥4096 |
| `kimi` | kimi-k3 | 1.8s | 快 |
| `flash 模型` | 强模型 | 8.8s | thinking |
| `gw-dsv4pro` | deepseek-v4-pro（`:8080`） | 1.8s | 异源网关 |
| `glm` | glm-4-flash | 1.3s | ⚠️ 长任务书易上游超时，仅补充 |
| `gw-kimi` | kimi-k2d6（网页版） | 1 次 200 | ⚠️ 网页版限长，长任务书 503 |

- **稳定集 = 5 个**（kimi / dsv4pro / gemini / flash 模型 / gw-dsv4pro），`critic_pool.py` 默认只用这 5 个；`glm`、`gw-kimi` 需 `--channels` 显式启用。
- **全强模型**；角色库可扩展至 10，战例启动时按子问题 `suggested_roles` 选。
- **上下文隔离（三级）**：① 不收他评 ② 不收其他子问题的材料（`pick_material` 按 target 切片）③ 不收全部历史（只给本轮 diff + 目标卡）。
- 并发：默认 `--parallel 4`，上限 6（每通道 1 并发，防限流）。**不要用 `fleet` 4 并发跑批评者**（历史卡死）。
- 盲评：加权随机抽 1 批评者（marginal_gain 第二评分源）。

## 4. 修订者动态路由

| 修订类型 | 路由到 | 理由 |
|---|---|---|
| 核心架构/跨模块 | 主 Agent（模式一五步法） | 全局视野 |
| 长链重构(单文件大改) | Claude Code | 长上下文擅长 |
| 批量小改/机械替换 | codex | 批量效率 |

- 单写者：同一 writer_domain 永不并发写。
- 修订回执带 diff 摘要+受影响文件。

## 5. 验证者分域

| 域 | 执行者 | 内容 |
|---|---|---|
| 动态测试 | Claude Code | 跑测试套件/单测，FAIL_TO_PASS 转绿 |
| 静态分析 | codex | lint/类型检查/依赖审计，PASS_TO_PASS 不回归 |
| 独立抽查 | 主 Agent | 随机抽查关键路径，交叉复核前两域冲突 |
| 失败归因 | `classify_failure.py` | 把平台 msg/逐 case 映射为 9 类 + 建议动作 |

- 测试生成端与生成端隔离（防自证清白）。
- 冲突由主 Agent 复核定案。

## 6. 记忆分层

- S0 会话记忆、S1 项目记忆（工程档案）、S2 档案（战例终局报告+热力图）。
- headless 会话不写记忆，一切落盘文件。
