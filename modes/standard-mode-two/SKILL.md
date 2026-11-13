---
name: Standard_Mode_Two
description: 高难度逆向任务多 Agent 协作体系（讨论层+静默执行层分离）：任务形态判定、T0-T6 逆向循环总览、探-收双相位模型（E/D5 探索树，v1.1）、模块路由（角色/规则/执行域）、三级终止、生态衔接。触发词：高难度逆向/混淆JS/反调试/加密参数还原/JSVMP/Frida hook/动态取证/多轮试错/探索树/广度枚举
---

# Skill: Standard_Mode_Two（标准模式二 · 框架/总入口）

> 高难度逆向任务的多 Agent 协作体系。解决单一 Agent 在逆向任务上的双死穴：**上下文爆炸**（历史尝试-报错挤占窗口）+ **策略单一**（钻牛角尖反复走同一死路）。
> 核心思想：**讨论层（只动脑）与静默执行层（只动手）严格分离**，多个能力互补的 Agent 围绕同一逆向目标迭代收敛，三级终止条件系统防无限循环。
> 本 skill 是**唯一被自然语言/`/` 直接触发的入口**；角色、规则、执行域细节分属三个模块 skill，按阶段路由加载。

---

## 0.1 逆向方法论五则（操作顺序速记，完整版见计划书 §1.5）

```
M1 观察优先  → M2 Hook 优先  → M3 断点最后  → M4 面向重建  → M5 证据优先
（M6 纯提取：收敛后必做，见 T6+）
```

一句话约束：**同一执行体在一个 round 内不得跳过 M1/M2 直接上 M3**；指挥官在 T3 回执检查时核对是否遵守（是否先侦查再动手、是否 hook 优先于断点、是否每步有 artifact）。

- M1 **Observe-first**：先全面侦查（scripts_list / net_capture 含发起者栈 / scripts_save 落源码 / page_info），确认目标来源再动手。
- M2 **Hook-preferred**：最小侵入采样——引擎层旁观（signer_trace / closure_read / webapi_trace，**零页面注入最不触发反调试**）→ 页面包装（page_eval）→ document-start 注入（hook_inject）递进。
- M3 **Breakpoint-last**：仅 Hook 不够才进引擎层深调试（jsvmp_trace dump / whitebox_diff）。
- M4 **Rebuild-oriented**：目标=Node 本地复现（scripts_save → npm_install → run_node），浏览器只取证，产物不依赖浏览器。
- M5 **Evidence-first**：每步沉淀 artifact（回执带落盘路径+round_id，>3000 字先落盘），决策靠证据不靠记忆。
- M6 **Pure-extraction-after-pass**：收敛后提取参数蓝图 [templates/param-blueprint.md] + 纯净实现，与过程产物分离归档。

---

## 0. 模块结构与加载方式（先读这一节）

本体系由 **1 个入口 + 3 个模块 skill** 组成，遵循单一事实源：每个概念只在归属模块定义一次，其余模块只引用不重述。

| 模块 | 内容 | 何时加载（run_skill / read_skill） |
|---|---|---|
| **本 skill（框架）** | 入口判定 / T0-T6 总览 / 路由表 / 生态衔接 / 术语 | 任务入口判定命中模式二即加载 |
| `mode-two-roles` | A 指挥官 / B/C 顾问 / D1-D4 执行体 / X 人工的角色边界与决策权限 | 进入循环前（T0 之前）加载一次 |
| `mode-two-round` | round 状态机 / 故障处置 / 五轴 / 回执五关 / 探索树协议 / 三级终止 / 记忆流程 | 每个 round 的 T0 选型与 T6 终止判定时加载 |
| `mode-two-domains` | 三执行域工具链（browser-director / desktop-worker / 静态分析）/ 调用序列 / 会话管理 | 轴1 选定 domain 后加载对应域 |

**共享资源**（`Standard_Mode_Two/` 目录内，模块 skill 按需引用，不重复内嵌）：

```
Standard_Mode_Two/templates/
    task-brief.md        # 任务书模板（R1/R2/R3/R4 四套）
    explore-card.md      # 探索卡模板（E 相位，v1.1）
    explore-task-brief.md # 探索任务书模板（E 相位，v1.1）
    receipt-schema.json  # 回执 JSON Schema（附录 B）
    advisor-prompt.md    # B/C 顾问 Prompt（附录 F.4）
    adjudicate-prompt.md # 指挥官裁决 Prompt（附录 F.2）
    review-prompt.md     # 复盘 Prompt（附录 F.3）
Standard_Mode_Two/scripts/
    round_engine.py      # LangGraph round 状态机引擎（13.1 落地，用法见 mode-two-round §12）
    drift_scan.py        # 漂移/净化规则检测（观测模式，v1.1；用法见 mode-two-round §5）
    requirements.txt     # 依赖清单（langgraph 全家桶）
```

---

## 1. 入口判定（任务形态分叉，与模式一的边界）

收到任务先做形态判定，**判定只做一次**，命中模式二后整条战例走模式二循环：

```
任务形态判定（附录 F.1）:
- 目标含以下任一特征 → 模式二（本 skill）
    混淆JS / 反调试 / 动态取证 / 需要 attach 进程 / 多轮试错 / 加密参数还原 / 运行时覆盖
- 或：探索面不明 / 多候选路径 / 需要广度枚举（探索型任务） → 模式二从 E 相位起步（§2.5）
- 否则（常规工程任务：改代码/部署/整理） → 标准模式一（`Standard_Mode_One`）
- 模式二内部执行动作（砍量/派发/验证） → 复用模式一四轴（见 `platform-orchestrator`）
```

**关键心态**：逆向的第一步不是"开始逆向"，而是"确认目标真的需要逆向"——flash 模型 Chat API 战例证明"服务端不校验签名"时整套攻坚可省。启动前先做附录 U 启动检查（见 §6）。

**简单取证不进化模式二**：单次浏览器取证（怎么 hook/怎么抓包）直接走 `trace` skill；只有多轮试错、混淆、反调试这类高难度取证才升级进模式二循环。

---

## 2. T0-T6 循环总览（单轮时间线）

每轮 round 是一趟完整的"下发→执行→讨论→裁决→落盘→判定"：

```
T0 选型:   五轴速判 → Mode 组合（如 R1+C1+P3+T1+X1），写本轮 round_id    [加载 mode-two-round §6]
T1 任务书: 按模板写任务书（已知/目标/死步骤/约束/回执格式），下发执行层   [templates/task-brief.md]
T2 执行:   执行层静默执行（可含多个 turn），指挥官不介入
T3 回执:   执行层返回结构化 JSON；过三关检查（schema/纯度/锚定）        [mode-two-round §6]
T4 讨论:   把 data + 30字前情提要分发 B/C，并行挑刺（parallel_tasks 只读）[mode-two-roles §3]
T5 裁决:   对照 B/C 论点 + S1 记忆检索 top-5 → 拍板下一轮方向 → 落盘 S1
T6 判定:   三级终止条件 → 收敛(结束) / 继续(回 T0, round_id+1) / 换基底 [mode-two-round §8]
T6+ 纯提取: 收敛后必做——验证通过 → 参数蓝图 [templates/param-blueprint.md] + 纯净实现 → 与过程产物分离归档；未完全收敛但结论稳定 → 产出"结论+证据链"档案（复盘四问回答）
```

- round = 一轮完整 T0-T6；turn = 执行层单次工具调用；budget = 每 round token 预算（执行层 80 turn / 讨论层 2 次 subagent / 裁决 1 次）。
- 单轮典型耗时：浏览器域 20-30 分钟（agent_wait_for_stop timeoutSec≥900）；讨论层 T4-T6 5 分钟内。
- 完整示例（桌面目标 round 1 全流程）见计划书附录 E，浓缩走查见 mode-two-round §11。

---

## 2.5 探-收双相位模型（E↔C，v1.1 新增）

T0-T6 是收敛式循环（每轮挑一个方向深挖，防兔子洞）——它强于深挖已验证的突破口，但找突破口是谁的串行试错。**E 相位（探索/发散）补上这个缺口**，形成逆向任务的探-收双相位：

```
【E 相位 · 探索/发散】只读、并行、广度优先
  E0 探索地图:  A 画探索维度（端点枚举 / 校验路径 / 权限面 / 隐藏功能 / 参数族…）
  E1 节点分派:  每维度一个探索任务书 + 绑定出口组合 → D5 群并行（模板 templates/explore-task-brief.md）
  E2 节点存档:  每节点产出探索卡（双段式；协议见 mode-two-round §6.5）
  E3 分向批评:  每方向独立配对 B_i/C_i（每方向一对，见 mode-two-roles §3）；A 收齐合并去重 → 候选路径清单+证据分级
  E4 移交检查:  高价值路径 → 入 C 相位任务书；全死路 → 终局/换探索字典

【C 相位 · 收敛/深挖】现有 T0-T6 循环——一字不改，作为深挖引擎
【相位切换】E→C 高价值路径出现即可切换；C→E 遇分叉/阻塞/连续死路时回探（软退出换基底升级为回 E 相位换视线）
```

**入口判定扩展**：任务形态含探索面不明/多候选路径/需要广度枚举 → 从 E 相位起步（轴5 X1/X2）；目标明确只是难 → 直接 C 相位（现状）。
**编号纪律**：T0-T6 编号为 C 相位专属；E 相位用 E0-E4 独立编号（防混淆）。

---

## 3. 五层架构（L0-L4，快速定位角色）

| 层 | 名称 | 组成 | 职责 |
|---|---|---|---|
| L0 | 执行层 | browser-director worker / desktop-worker(Frida) / Codex / Claude Code / 本地 subagent | 只执行命令返回结构化结果，不决策 |
| L1 | 工具层 | 浏览器 44 工具、Frida hook、文件系统工具、MCP server | 能力原子，单次调用输入输出明确 |
| L2 | 讨论层 | 指挥官 A + 顾问 B/C（并行只读 subagent） | 提假设、质疑、裁决、写任务书 |
| L3 | 记忆层 | Reasonix memory + reasonix-memory MCP + 档案目录 + ima | 跨轮持久化，检索即决策依据 |
| L4 | 调度层 | **主 Agent 的执行循环**（T0-T6）+ 五轴分支 + 探-收双相位（E/C）切换 | 控制循环、触发分支、相位切换、执行终止条件 |

**铁律**：L0 与 L2 之间只通过"任务书（下行）+ 回执（上行）"两个文档对象通信，禁止直接对话。讨论层每轮基于同一份结构化证据；执行体不携带个人观点。

**LangGraph 定位（路线二定案）**：`round_engine.py` 只实现 13.1 round 状态机的**状态跟踪/超时/故障分支/持久化**，是 L4 的辅助工具，**不是 L4 本身**——循环推进、裁决、落盘永远在主 Agent（指挥官）手里。状态机只回答"当前在哪、该往哪迁、超时没有"，不回答"为什么、下一步派谁"。

---

## 4. 数据流与状态流（一句话各流）

- **下行**：指挥官 → 执行层，单条任务书（≤1500 字，含已知/目标/死步骤/约束/回执格式）。
- **上行**：执行层 → 指挥官，单条回执 JSON（round_id/domain/status/data/confidence，见 templates/receipt-schema.json）。
- **讨论流**：指挥官把回执 data（砍量后）分发给 B/C，收回两条极简批评（≤100 字 + 候选方向）。
- **记忆流**：指挥官每轮结束把踩坑/反证/成功摘要写入 S1（按 domain tag 分域）。
- **状态流**：执行层浏览器 tab / hook 会话 / 调试器 attach 是唯一"活状态"，**单例串行**；讨论层与记忆层是"死状态"，随时可重建。

---

## 5. 生态衔接（依赖的既有资产，全部已核实存在）

| 资产 | 位置 | 在本体系中的作用 |
|---|---|---|
| `Standard_Mode_One` skill | <REASONIX_HOME>/skills/Standard_Mode_One/ | 入口分叉 + 四轴派发复用（附录 H 五步对照） |
| `platform-orchestrator` skill | 同上目录 | 10 派发模式（①流水线/①'成本分层/④探索隔离/⑥深度执行/⑨监督轮询等）用于执行层任务分发与成本分层 |
| `frx-dual-agent-reverse` skill | 同上目录 | 浏览器域骨架（任务书模板/阶段门审阅/防漂移三板斧），模式二是其"加讨论层"的升级 |
| `trace` skill | 同上目录 | 单次浏览器取证的方法论，作为 R1 模式执行层"操作手册"（附录 W.1） |
| `memory-codegraph-collab` skill | 同上目录 | 记忆写入/检索协作守则（S1 落盘时遵循其 remember 三步与链式复核） |
| browser-director MCP | <HOME>/<WORKSPACE>/agent-start/tools/browser-mcp/ | 域1 执行层（44 工具，待注册本会话 MCP） |
| 桌面执行体工具集 | <HOME>/wxd/ | 域2 初版能力（find_all_keys/find_keyinfo_mem/mcp_server.py 等） |
| 解密脚本 | <WORKSPACE>/decrypt.py | 域2 成功判据载体 |
| WEB-SIGN 档案 | <HOME>/flash 模型-chat/web-sign-archive/ | S2 档案样板 + 跨域经验 |
| claude/codex worker 脚本 | <WORKSPACE>/scripts/ | D3 执行通道（L0 通道：claude-worker.sh / codex-worker.sh） |
| ima 知识库 | ima MCP | S2 归档（附录 O 归档映射） |

**生态总关系**：

```
tech-research-plan ──选型报告──→ Standard_Mode_Two ──任务形态判定──→ Standard_Mode_One
        ▲                                    │ 高难度逆向                   │ 常规工程
        │                                    ▼                             ▼
        └── 沉淀 ── trace / frx-dual-agent-reverse / platform-orchestrator（执行层与派发）
        └── 归档 ── ima 知识库 / S2 档案目录 / S1 记忆
```

**待建设项**（计划书 10.2，按优先级）：P0 desktop-worker(frida_server.py) + browser-director 注册进本会话 MCP；P1 Ghidra headless(WSL 侧) + 本 skill 集评审固化；P2 统一执行协议校验器 + 战例档案模板化。

---

## 6. 启动检查表（新战例十分钟进入 T1，附录 U）

每次新会话启动一个逆向战例，按此表执行，**不带着"我觉得应该从 X 开始"直接发任务书**：

| 步 | 动作 | 工具/命令 | 判定 |
|---|---|---|---|
| 1 | 恢复战例上下文 | `memory search`（战例名）+ read S2 档案 SUMMARY.md | 拿到"已知/已排除/未解"三件套 |
| 2 | 确认执行层就绪 | frx_status（浏览器域）/ wx_status（Windows 域） | 未就绪 → 请用户启动浏览器/目标进程 |
| 3 | 确认预算与风控 | 核对战例预算表 + 人工 X 确认测试号放行 | 预算不足 → 转 R4 纯静态降级 |
| 4 | 五轴速判 | 附录 F.1 Prompt（见 mode-two-round §6） | 输出 Mode 组合（含轴5 X0-X2） |
| 5 | 检索跨域同构经验 | `memory search`（"沙箱绕过"/"hook 0 命中"/"死路"） | 命中 → 写进任务书"已知"节 |
| 6 | 写首轮任务书 | templates/task-brief.md | 五要素齐 → 过自检 → T1 |
| 7 | 进入 T0-T6 循环 | 见 §2 | 直到三级终止条件 |

步骤 2 未就绪时，宁可用步骤 6 的时间先把任务书写完待命，也不空等。

---

## 7. 术语表（共享协议层，全模块唯一版本）

| 术语 | 释义 |
|---|---|
| round / turn / budget | 循环单元与预算：round=一轮 T0-T6；turn=执行层单次工具调用；budget=每 round token 预算 |
| 域(domain) | browser / windows / static 三个执行域 |
| 基底策略 | 当前主攻路线，软退出时可整体切换 |
| 前情提要 | 30 字摘要，补偿 B/C 弱记忆的上下文锚点 |
| 取证升格 | C4 模式：派执行体做取证实验，证据（而非人）进讨论 |
| driftHint | browser-director 漂移核查字段（finishReason/likelyDrift） |
| 活状态 | 浏览器 tab / hook 会话等不可并发的单例状态 |
| 死路证明 | 高置信度排除某假设的记录，防重复踩坑 |
| 降载通道 | 大数据先落盘 + 回执只带路径摘要，防上下文爆炸 |
| 探索卡 | E 相位节点压缩存档（双段式：事实段+裁决摘要）；协议见 mode-two-round §6.5 |
| 出口组合 | 探索节点的资源绑定单元（IP 出口+账号）；一节点一组合，不得并发复用 |
| 相位切换 | E↔C 切换：E→C 高价值路径出现即切；C→E 分叉/阻塞/连续死路时回探 |
| 回执五关 | schema/纯度/锚定/净化解/漂移关（v1.1，协议见 mode-two-round §5） |

---

## 8. 版本与变更登记

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.1 | 2026-09-12 | 探索树融合（阶段 A）：探-收双相位模型（E0-E4）+ 五轴（轴5 探索广度 / P5 节点并行）+ 回执五关（净化解/漂移关）+ D5 探索群 + 免费层准入条件化 + 探索卡/探索任务书模板 + drift_scan 检测脚本。依据《模式二演进评审与融合设计 v1.3》（Desktop） |
| v1.0 | 2026-08-11 | **评审门通过，正式固化**（附录 N 三条件全满足）：①P0 动工三项完成——browser-director 接入（MCP+marionette 3928 桥+worker key deepseek-v4-flash+37 工具）/ key_blob 静态分析（验收记录 wxd/P0-2-acceptance.md，5 命中点全误报）/ WEB-SIGN 战例 3 轮循环（round-state.db 全历史至 TERMINATED）；②真实战例 3 轮完整循环走通（web-sign-archive：轮1 侦察/轮2 定向/轮3 验证）；③复盘四问有实际答案（flash 模型-chat/web-sign-archive/R1-R3-rounds-review.md）。计划书全文归档 ima 与档案目录 |
| v0.2 | 2026-08-11 | 由计划书附录 N"单一 SKILL.md"演进为**模块 skill 集**（本框架 + `mode-two-roles` + `mode-two-round` + `mode-two-domains`）；新增 scripts/round_engine.py（LangGraph round 状态机，计划书 13.1 落地，路线二定案） |
| v0.1 | 2026-08-11 | 对应计划书 v0.1 讨论稿（尚未固化） |

**评审门**（已于 2026-08-11 通过，见 v1.0）：①P0 动工项完成（browser-director 接入 / key_blob 纯静态分析 / WEB-SIGN 战例验证讨论层）；②真实战例至少走完 3 轮完整循环；③复盘 Prompt 四问全部有实际答案。
