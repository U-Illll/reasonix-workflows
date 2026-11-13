---
name: Standard_Mode_Three
description: 大型正向工程构建模式（高阶目标 × Gemini 拆分 × 异源批评者池 × 决策函数 × 动态路由修订 × 分域互补验证）：P0a 调研 → P0b 目标卡 → P1 生成 → P1.5 拆分 → P2 六批评者隔离池 → P3 裁决(EIG 决策) → P4 动态路由修订 → P5 分域互补验证 → P6 复盘。触发词：大型工程/正向构建/系统重构/批评者池/边际收益/目标卡/拆分/循环工程化
---

# Skill: Standard_Mode_Three（标准模式三 · 框架/总入口）

> 大型正向工程构建模式。解决大型任务在单 Agent 长会话下的三大死穴：**标准缺失**（验收靠感觉）、**批评失效**（单批评者盲区/自证）、**无终止机制**（烧 token 到天荒地老）。
> 核心思想：**调研定基准 → Gemini 拆子问题 → 异源批评者隔离挑刺 → 决策函数选下一发 → 动态路由修订 → 三执行体分域验证**，每一轮都锚定验收标准，每一次提交都必须换来信息。
> 本 skill 是**唯一被自然语言/`/` 直接触发的入口**；角色、规则、执行域细节分属三个模块 skill，按阶段路由加载。循环工程化细节见 `mode3/docs/loop-engineering-20261017.md`。

---

## 0.0 记忆库闸门（cann-kb · 强制）

进入 P1 之前、以及每次 P3 裁决前，必须先查探索树记忆库，拿到三行契约：

```bash
bash <WORKSPACE>/cann-kb/entry.sh "<P0b 目标卡里的问题/假设/关键字>"
#  → 已知 / 已排除（24h 内不要再试）/ 未测
```

- 三行缺失 ⇒ 不进入 P1 生成与任何真机实验（蓝图 §6 闸门）。
- `已排除` 方向不得重试；确需复测必须在产出里写 `retest_of: <card_id>` + 新条件。
- 每轮 P6 复盘必须回灌：`python3 <WORKSPACE>/cann-kb/ingest_wave.py --wave <W>`（夜间由 `master_wave.sh` 自动执行）。
- 夜间 10-agent 体系：实例任务书 `## 〇、记忆库对照` 与主控 `kb_brief` 字段由编排器自动注入，不要手改。

## 0. 宏观循环 P0-P6(速记)

```
P0a 标准调研 → P0b 目标卡(人工拍板) → P1 生成 → P1.5 拆分(Gemini)
→ P2 批评(子问题 × 角色, 6 通道并发) → P3 裁决(EIG 决策函数)
→ P4 修订(动态路由) → P5 验证(分域互补) → P6 复盘 → 回 P2 或终止
```

- P0a **标准调研**：多 agent 并行调研主流产品 → `benchmark.md` 能力矩阵(每条带来源+日期)，验收标准锚定主流产品实测，不凭感觉定标。
- P0b **目标卡**：主 Agent 依据 benchmark 起草 `goal-card.md`(能力清单+验收判据+范围边界+token 预算) → **人工 X 拍板**(唯一强制人工前置)。拍板后循环内不变更。
- P1 **生成**：主 Agent 蓝图+契约 → Claude Code 铺初版骨架。
- **P1.5 拆分**：Gemini 把「待审产物 + 验收标准」拆成 **3~6 个正交子问题**（每个带 `question/target/acceptance/suggested_roles/priority`），schema 校验不过重拆一次，仍失败则降级为单子问题（不阻塞）。拆分器**不做评审**。
- P2 **批评者池**：`critic_pool.py` 生成「子问题 × 角色」隔离任务书，**异源通道并发**（6 个可用通道，2/4/6 档）。每个批评者只收「本子问题材料片段 + diff + 验收标准」，不收他评、不收其他子问题材料。
- P3 **裁决**：主 Agent 逐条采纳/驳回，写裁决单 `adjudication.json`。**下一发由 `decide_next.py` 排序**：`score = EIG × P_ok / (cost × risk)`，候选必须写"失败能排除什么"（写不出即 EIG=0，停）。
- P4 **修订**：按裁决单动态路由——主 Agent(核心架构，标准模式一执行)/ Claude Code(长链重构)/ codex(批量修改)。单写者。
- P5 **验证**：三执行体分域互补——Claude Code 动态测试 + codex 静态分析 + 主 Agent 独立抽查，**交叉复核冲突**。FAIL_TO_PASS/PASS_TO_PASS 双集回归。失败由 `classify_failure.py` 自动归因。
- P6 **复盘**：批评者贡献热力图(角色/类别/轮次) + `trial_ledger.py` 台账报表 → 下战例重配批评者。

## 1. 红线(违反即失败)

1. **裁决永远在主 Agent**——执行体不互连、不经主 Agent 不直连。
2. **批评者上下文隔离**——不收其他批评者意见(防群体思维)，不收其他子问题材料，不收全部历史(防锚定)。
3. **目标卡拍板后不变更**——范围边界变更 = 重新立项。
4. **单写者原则**——同一 writer_domain 永不并发写。
5. **终止靠可计算条件**——不靠"感觉做完了"：目标达成 / 额度耗尽 / 轮数上限 / 连续 2 发零信息 / 边际收益分档，五类条件由引擎判定。
6. **每发必须换来信息**——决策单上每个候选必须写明"这发失败能排除哪个假设"；写不出来就不发。
7. **拆分正交且可独立评审**——两个子问题指向同一段材料/同一类缺陷 = 不合格；`acceptance` 必须可判定。
8. **拆分失败降级不阻塞**——Gemini 两次失败即降级为单子问题，禁止因拆分环节卡死整条循环。

## 2. 触发与路由

- 大型正向工程任务(目标明确、工期长、token 预算大)→ 直接触发本 skill。
- 按阶段路由加载模块:`mode-three-round`(round 状态机)、`mode-three-roles`(角色决策矩阵)、`mode-three-domains`(执行域工具链)。
- 与模式一关系:模式一是标准模式三的**工作节点**(P1/P4 主 Agent 修订按模式一五步法执行)。
- 与模式二关系:高难度逆向仍走模式二;模式三面向正向构建。

## 3. 落地工程

- 引擎:`<HOME>/reasonix-scripts/mode3/engine/mode3_engine.py`
  (v1.1.0：init/transition/status/check-termination/record-decompose/get-state/journal/ledger/version)
- 拆分器:`mode3/tools/decompose_run.py` + `mode3/skills/gemini-decomposer/SKILL.md`
- 批评者池:`mode3/tools/critic_pool.py`（plan / run / collect / channels）
- 决策:`mode3/tools/decide_next.py`；归因:`mode3/tools/classify_failure.py`；台账:`mode3/tools/trial_ledger.py`
- 参考:`mode3/docs/loop-engineering-20261017.md`（三问答案 + GitHub 借鉴映射 + 通道实测矩阵 + 端到端验收记录）
- 验收脚本:`<HOME>/reasonix-scripts/mode3-scheduler/acceptance/`(S0-S5, 机器判定)
