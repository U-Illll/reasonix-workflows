---
name: Standard_Mode_One
description: 标准化五步工作流程（工具增强版）：codegraph/serena 代码智能 + Context7 + GitHub + Worker 派发决策；含运维入口、修改-验证协议（防修复循环）与并发 bug 专项（Specula）
---

# Skill: Standard_Mode_One

> 标准化工作流程：状态检查→计划→依赖检查→分步执行→每步验证。
> 工具增强版：codegraph/serena 代码智能（符号定位/引用/影响面/圈复杂度）+ Context7 获取最新文档 + github-mcp-server 仓库操作。
> 每次非平凡任务按此模式执行。

## 标准模式一：五步工作法（工具增强版）

### 第一步：检查系统当前状态

**目标**：快速理解现状，不遗漏关键上下文。

| 传统方式 | 增强方式（优先） |
|----------|-----------------|
| `read_file` / `grep` 逐文件查看 | `codegraph_symbol_search` / `mcp__serena__find_symbol` 按名称定位符号 |
| `ls` / `glob` 看目录结构 | `codegraph_get_module_summary` 看模块结构 / `mcp__serena__get_symbols_overview` 符号总览 |
| 手动翻代码理解逻辑 | `codegraph_get_ai_context` 全仓图视角 + `mcp__serena__find_symbol` 语义细节 |

**任务入口分叉（三入口，2026-08-11 双工具协同定稿 + 2026-09-13 运维入口）**：
- 从**报错/异常**出发（"这报错哪来的"）→ 先 `codegraph_search_by_error` 反查代码定位 → 再进入下方工具链
- 从**需求/功能**出发（"加个缓存"）→ 直接用下方工具链探路（codegraph 结构 → serena 细节）
- 从**运维/运行态**出发（"服务挂了/守护停了/行为变了"）→ 先收运行态证据定界（`git log --oneline -5` 看最近变更、进程/端口/守护状态、日志尾部）区分「最近改动引入」vs「环境/上游事件」→ 再进入下方工具链；一切修复动作走第四步「修改-验证协议」

**触发条件**：
- 修改已有代码 → `codegraph_analyze_impact` 评估爆炸半径 + `mcp__serena__find_symbol`/`find_referencing_symbols` 语义验证引用面
- 理解不熟悉的模块 → `codegraph_get_module_summary`/`get_ai_context` 全局 + `mcp__serena__get_symbols_overview`/`find_referencing_symbols` 细节

**worker 增强（前置侦察，可选）**：多文件/跨模块/大范围状态收集时，fleet 并行派发侦察 worker（区域划分 R1 记忆 / R2 history / R4 代码，`--model gateway-auto` 或 `gateway`）→ 各 worker 结论三段式回收（带证据引用）→ **理解在主 agent**（worker 结论作候选，主 agent 融合成现状认知）；单文件小任务跳过。

**⚡ 调度决策轴触发（本步特点：理解现状、收集上下文）**：
- 触发 **数据量轴**（多文件/跨模块/大范围状态收集）→ 轴内模式：**① 流水线**（砍量→精炼）、**①' 成本分层**（预处理→执行体）；具体触发条件见下方「调度决策轴」总览
- 触发 **并行轴**（跨区侦察 R1/R2/R4 分区）→ 轴内模式：**④ 探索隔离**（多路并行 + 负结果回报）
- 触发 **工具需求轴**（需真实 grep/read_file 确认符号存在）→ 轴内模式：**⑤ 工具差分**（工具动作→内置 subagent）

### 第二步：制定分步计划

**目标**：列出清晰可执行步骤，标注依赖关系和风险评估。

增强点：
- `mcp__serena__find_referencing_symbols` — 修改/删除/重命名前评估爆炸半径（引用面=影响面）
- `mcp__serena__find_referencing_symbols` + grep 测试命名 — 找到需要同步更新的测试
- `mcp__serena__find_referencing_symbols`（谁引用我）/ `find_declaration`（我引用谁）— 追踪调用链
- `mcp__context7__query-docs`（先 `resolve-library-id`）— 涉及第三方库时获取最新权威 API 示例，计划中标注正确用法（与调用链分析场景不重复，按"查外部库"独立触发）
- `mcp__serena__find_symbol` — 明确新代码的接入点/入口；`find_referencing_symbols` — 明确接入后受影响方（若与上面已有的引用查询重合，合并为一次查询）
- **历史经验检索（默认 worker 外包，P3-0）**：相似案例/踩坑记录检索走检索 worker（区域划分 R1 记忆 / R2 history / R3 ima，派发 `REASONIX_HOME=.reasonix-local reasonix subagent run glm-worker --model gateway-auto "<任务书>"` 或 fleet 并行）→ 结论三段式回收（命中带证据 + 空检索显式回报）→ 与 serena/Context7 内容重合时合并去重；**worker 不可用时回退内联** `mcp__ima__search_notes`（笔记本「代码示例与bug记录」）+ `memory search` + `history search`

**输出格式**：
```
步骤1: xxx  [影响范围: 3个文件, 2个调用者] [关联测试: test_xxx]
步骤2: xxx  [依赖: 步骤1完成] [风险: 低]
...
```

**⚡ 调度决策轴触发（本步特点：方案设计、历史经验检索）**：
- 触发 **决策轴**（架构设计/重构方案需要先想清楚）→ 轴内模式：**⑦ 方案外包**（Claude EnterPlanMode 出方案→主 agent 拍板）
- 触发 **并行轴**（历史经验检索分区 R1/R2/R3）→ 轴内模式：**④ 探索隔离**（多区并行检索 + 空检索显式回报）
- 触发 **数据量轴**（相似案例/踩坑记录量大）→ 轴内模式：**① 流水线**（检索→砍量→精炼）

### 第三步：检查依赖和环境配置

**目标**：逐一验证每步所需的环境、工具、权限、冲突。

在原有检查（工具可用性、端口占用、配置文件）基础上增加：
- `mcp__serena__find_referencing_symbols` 组合 — 改动前人工判环（serena 无专门循环依赖工具）
- `mcp__serena__find_symbol` + `find_referencing_symbols` — 了解文件级依赖关系
- `mcp__serena__get_diagnostics_for_file` — 改动后清理冗余导入（诊断含未用导入告警）

**worker 增强（依赖探测，可选）**：依赖链复杂/需验证多个环境项时，派发只读 worker 核查（端口/服务/配置/权限，任务书约束只读）→ 返回检查清单（每项 通过/失败 + 证据）→ 主 agent 据清单决策；简单依赖检查内联更快，跳过。

**⚡ 调度决策轴触发（本步特点：验证环境、依赖、权限、冲突）**：
- 触发 **并行轴**（依赖链复杂/多环境项核查）→ 轴内模式：**④ 探索隔离**（多路核查 + 每项证据回报）
- 触发 **工具需求轴**（依赖探测需跑命令：端口/服务/配置）→ 轴内模式：**⑤ 工具差分**（工具动作→内置 subagent）

### 第四步：分步执行

**目标**：一次一步，不批量推进。

**编码类步骤在执行前追加**：
1. `mcp__context7__resolve-library-id` → 解析库名
2. `mcp__context7__query-docs` → 获取最新 API 文档和代码示例
3. `codegraph_get_edit_context`（编辑位置图上下文）+ `mcp__serena__find_symbol`/`find_referencing_symbols`/`get_diagnostics_for_file`（引用面+语法诊断）

**写通道分层（2026-08-11 双工具协同定稿）**——修改前先选通道：

| 修改类型 | 通道 | 理由 |
|---|---|---|
| 符号级重构（跨文件重命名/移动/符号体替换） | serena `rename_symbol` / `replace_symbol_body` / `safe_delete_symbol` / `replace_in_files` | 原子、跨文件一致、防漏改 |
| 文本级小改（改一行/调参数/修注释） | 直接 `Edit` / `Write` | 走 serena 多一轮工具调用，纯浪费 |
| 新建文件 / 大段新代码 | 直接 `Write`（serena/codegraph 均无 create 能力，insert_after_symbol 只能往已有符号插） | 无更优通道 |
| 多文件同模式批量替换 | serena `replace_in_files` | 多文件原子替换 |

**修改-验证协议（防"修复→引入新错→再修复"循环，2026-09-13 定稿）**——一切修复类改动（bug 修复/行为调整/运维处置）执行时强制遵守：

1. **先复现再改**：动手前先建立失败复现（最小命令 + 输出落盘）；复现不出来 → 先补观测（日志/探针），禁止凭猜测改码
2. **改后必验**：验证 = 复现用例转绿 + 关联面回归（CodeGraph 影响面 / 关联测试）；"看起来对"不算验证
3. **3-Strike 熔断**：同一问题连续 3 次修复失败 → 停手回报「假设 × 证据 × 失败原因」，**强制换假设/换策略**；禁止第 4 次打补丁式微调
4. **原子回退**：改动前留恢复点（git 副本/stash/备份），只从"已知良好状态"出发；坏状态不带入下一步
5. **循环序列自查**：出现 `read→edit→read→edit` 型工具抖动、或同一报错的措辞级变化而实质未变 → 判定循环信号，停手回报

> 触发：任务进入 ≥2 次修复尝试、或用户反馈"又坏了/还不行"时，逐条对照自查；一次即成的简单修复自然满足 1/2 条，无需额外动作。机制来源：agent-rigor（3-Strike/原子提交）、AgentDebugX（Rerun=验证而非猜测）、loop-guard（循环序列三级检测），2026-09-13 评估引入。

**非编码类步骤**（配置、部署、脚本）：沿用原有方式。

**⚡ 调度决策轴触发（本步特点：实际执行、产出代码/产物）**：
- 触发 **数据量轴**（单批原始数据 > 3 万字符或有效信息密度低）→ 轴内模式：**①' 成本分层**（免费预处理→审阅→执行体）或 **① 流水线**（免费砍量→强模型精炼）
- 触发 **并行轴**（同批 ≥3 个同质子任务可并行）→ 轴内模式：**② 分级路由**（fleet 按复杂度分档混排）
- 触发 **工具需求轴**（长链多步 >10 轮工具操作）→ 轴内模式：**⑥ 深度执行**（claude/codex 整段执行分包）；任务书含工具动作 → **⑤ 工具差分**（内置 subagent）；需观察运行中进程/日志/断点 → **⑥b 调试变体**；产出 UI/视觉产物 → **⑧ 视觉迭代**（执行体写码 + playwright 验证）
- 触发 **专项流程**（并发/状态机类深层 bug，常规复现困难——原子性/锁序/重试窗口/状态机断裂）→ **Specula 并发 bug 挖掘**（TLA+ 规约 → TLC 模型检查 → 代码级复现；重型专项按需启动，见 `specula-concurrency-hunt` skill）
- 触发 **决策轴**（方案执行前需对方案拍板）→ 轴内模式：**③ 审核回炉**（方案审阅）；任务可拆能力差两半 → **⑩ 协调拆分**（主 agent 中转分别派）
- 触发 **并行轴**（长任务 >30 分钟需监控）→ 轴内模式：**⑨ 监督轮询**（claude cron 定时查进度回报）

### 第五步：每步执行后全面检查

**目标**：确保当前步骤生效且不破坏已有功能。

增强点：
- `codegraph_pr_context` / `codegraph_analyze_impact` — 检查分支变更完整影响（blast radius + 测试缺口）
- `codegraph_find_dead_imports` — 清理未使用的导入
- `codegraph_analyze_complexity` — 新增函数圈复杂度 > 10 时考虑重构
- `mcp__serena__get_diagnostics_for_file` — 语法/类型即时诊断
- `mcp__github__get_commit` — GitHub 侧提交核对
- 重构后 `codegraph_reindex_workspace` 同步索引（防"图还是旧的"）

**worker 增强（验证外包，可选）**：验证面广（跑测试/编译/多平台回归）时，派发验证 worker 执行 → 返回结果+证据（测试输出/编译日志）；**验收判定权在主 agent**（worker 结果作证据，主 agent 对照验证清单逐项判定）；单文件小验证内联，跳过。

**验证清单**：
- [ ] 编译/语法通过
- [ ] 调用者不受影响（CodeGraph 验证）
- [ ] 关联测试未破坏
- [ ] 无关功能正常
- [ ] 修复类改动：复现用例转绿 + 无新增回归（对照第四步「修改-验证协议」自查）
- [ ] 调用 `code-review-checklist` 技能做代码审查（15 维度 + 5 跨语言补全）
- [ ] 对比 ima「代码示例与bug记录」笔记本：本次踩坑/经验是否已有记录
      - 已有 → 不重复添加
      - 没有 → `mcp__ima__create_note` 添加，笔记命名格式：`<项目名> - <问题/功能简述>`

**⚡ 调度决策轴触发（本步特点：验证产物、验收判定）**：
- 触发 **工具需求轴**（验证面广：跑测试/编译/多平台回归）→ 轴内模式：**⑤ 工具差分**（验证 worker 执行，主 agent 判定）；UI 产物需截图对比 → **⑧ 视觉迭代**（playwright 截图即证据）
- 触发 **决策轴**（worker 产出进入主 agent / 结论进记忆前）→ 轴内模式：**③ 审核回炉**（默认开启，三段式审阅 + 带反馈补派）

---

## 调度决策轴（四轴，2026-08-09 体系化）

> **轴 = 回答一个调度问题的维度；模式 = 轴内的具体派发策略**。五步中任一步触发某轴（见各步「⚡ 调度决策轴触发」块）→ 进入该轴 → 选择轴内模式（**名称 + 触发条件见下，具体执行内容见 `platform-orchestrator`**）。允许多个步骤触发多个轴（如第四步海量数据 = 数据量轴 + 工具需求轴）。

| 轴 | 回答的问题 | 轴内模式（名称 + 触发条件） |
|----|-----------|---------------------------|
| **数据量轴** | 数据海量、有效信息占比低怎么办 | **① 流水线**（原始数据量大/万级消息/有效信息占比低）/ **①' 成本分层**（单批 >3 万字符或密度低，下游需框架级执行体） |
| **并行轴** | 同批多任务 / 路径分叉 / 长任务监控怎么办 | **② 分级路由**（≥3 同质子任务 + 可预先分档）/ **④ 探索隔离**（路径分叉 ≥2 / 内联探索 >5 轮 / 失败代价低，任一）/ **⑨ 监督轮询**（任务 >30 分钟 / 需无人值守监控 / 失败需及时介入，任一） |
| **工具需求轴** | 任务要不要工具调用、要多深、要视觉验证吗 | **⑤ 工具差分**（任务书含工具动作 vs 纯语义；Kimi 例外不派工具任务）/ **⑥ 深度执行**（长链 >10 轮工具操作，需框架级执行体；含 **⑥b 调试变体**：需观察运行中进程/日志/断点）/ **⑧ 视觉迭代**（产出 UI/页面/视觉产物，需 playwright 验证） |
| **决策轴** | 谁出方案、谁把关、怎么拆 | **⑦ 方案外包**（架构设计/重构方案，Claude plan 出方案）/ **③ 审核回炉**（任何 worker 产出进主 agent 时，默认开启）/ **⑩ 协调拆分**（单一任务可拆能力差两半 + 任一半 >10 轮，主 agent 中转） |

> 模式内容（形态/要点/实例）详见 `platform-orchestrator` 第三章；触发条件速判：数据量大→数据量轴；≥3 并行→并行轴；要工具→工具需求轴；要拍板→决策轴。

---

## Worker 派发决策（免费 vs 强模型 vs 框架级执行体）

> 依据 [[free-worker-capability-boundary]]（2026-08-08 实测）：**免费 worker 适合「执行层」，不适合「决策层」**。派发前先对号入座。
> 2026-08-09 扩展：加入**框架级执行体**（codex-worker / claude-worker）与**成本分层流水线**（模式①'，三方工作流设计见 `Desktop/Reasonix-Codex-ClaudeCode-三方协作工作流设计.md`）。

| 任务性质 | 派发目标 | 说明 |
|----------|----------|------|
| 检索召回（记忆/历史/代码/网页分区并行） | 免费 worker（gateway-glm/kimi/deepseek 免费档） | P3-0 验证通过，成本≈0，多路并行 |
| 候选初筛/砍量 | 免费 worker | 海量候选压到 1/10，缩小强模型输入面 |
| 浅层收集/格式化（抓取/翻译/JSON 提取/清洗） | 免费 worker | 语义判断少、规则明确 |
| 侦察/依赖探测/验证执行 | 免费 worker（read_only） | 返回证据，判定权在主 agent |
| **综合/精炼/判断/编译** | **deepseek-pro 或主模型** | 免费档会把埋在上下文里的真信息判成"无有效信息"（群聊精炼 pilot 翻车实证） |
| 长上下文总结（单批次 > 3 万字符） | 强模型 | 免费档读不全、抓不住重点 |
| 多跳推理 | 强模型 | 免费档推理链易断 |
| **长链多步重构（>10 轮工具操作）** | **框架级执行体（claude-worker 首选）** | 框架能力（Agent 子代理 + 长会话），输入须已砍量 |
| **架构设计/重构方案** | **框架级执行体（claude-worker，EnterPlanMode）** | plan 能力独有，方案回主 agent 拍板 |
| **非交互批量/CI 自动化** | **框架级执行体（codex-worker，exec）** | CI 原生（stdin/退出码），非交互审查用 review |
| **定时巡检/抓取** | **框架级执行体（claude-worker，CronCreate）** | cron 能力独有 |
| **复杂任务（数据量大）** | **免费 worker 预处理 → 主 agent 审阅 → 框架级执行体** | 模式①'成本分层：免费砍量带证据，执行体只接候选集（护栏四条见 platform-orchestrator 模式①'） |

**信任边界（P3-0）**：worker 结论一律视为「候选/证据」——带引用直回收，**写入/编译/验收判定永远在主 agent**（检索直收、编译必审）。框架级执行体的产出（结论三段式）同样必须主 agent 审核回炉后才能进记忆。派发命令与任务书模板见 `platform-orchestrator`（双轨路由 model 表 / 指挥五步 / 五段式任务书）。

**框架级执行体 skill 引用（2026-08-13 实测）**：框架级 worker（claude/codex）的任务书可引 skill 名替代现写五段式规范，省 token 且保证纪律一致：
- 样板 skill `reasonix-worker-brief`（框架级任务书执行规范：执行纪律 + 结论三段式 + 防漂移）已双端落盘。派发时任务书简化为「按 reasonix-worker-brief 执行：<具体目标/死步骤/约束>」。
- **skill 目录**（实测确认）：codex 用户级 = `~/.cache/codex/skills/`（`$CODEX_HOME/skills`）；claude 用户级 = `~/.cache/claude/skills/`（`$CLAUDE_CONFIG_DIR/skills`）。
- **实测三结论**：① claude -p 无头下内置 `Task*` 默认可用、无 permission denied，且 `--allowedTools` 白名单**不影响**内置 Task*（白名单只约束 MCP 工具）→ P0-2/P0-5 无需改 `--allowedTools`；② claude -p 下 `Skill` 工具可加载用户级 skill；③ codex exec 非交互下 skill 自动触发（frontmatter description 匹配），`skill-creator` 可自我 skill 化，但 workspace-write 沙箱写不了 `$CODEX_HOME/skills/`，skill 落盘由主 agent 完成。

### 派发机制与触发条件（②分级路由 / ④探索隔离 / ⑤工具差分）

**② 分级路由式** —— 触发条件（须同时满足）：
- 一批 **≥3 个同质子任务**（同模板、同输入格式、可并行）
- 子任务能**预先按复杂度分档**：单输入 <3 万字符 + 结论可机械提取（列表/关键词/证据引用）+ 无推理链 → 免费 worker；需要综合提炼 / 合并去重 / 模糊判断 → 强模型
- 用法：`fleet` 内 per-item `model` override 混排，一次派完

**④ 探索隔离式** —— 触发条件（任一即可）：
- 方向不确定、**路径分叉 ≥2 条**，不知道哪条通
- 预计内联探索 **>5 轮工具调用**（试错成本高、会污染主 agent 上下文）
- 失败代价低（可重试）
- 用法：免费 worker 多路并行探索，只回收「哪条路通 + 证据」；**失败路径也显式回报**（负结果 = 有效信息，避免下轮重复试错）

**⑤ 工具差分式** —— 触发条件（写入调用规则）：
- 任务书含**必须执行的工具动作**（读写文件 / 跑命令 / 调 MCP / 多步操作）→ **内置 subagent（主模型）**，工具遵循度可靠
- 任务书是**纯语义 / 只读检索**（不碰工具或仅 read-only）→ 免费 worker
- **Kimi 例外**（M1 实测）：Kimi 仅内置工具、不支持函数工具 → 任何需要工具调用的任务都不派 Kimi，只派纯 chat 检索

## 四薄弱场景（已解决，2026-08-09 定案）

> 2026-08-09 全模式实测后识别 4 类无显式模式场景；同日定案方案并纳入四轴体系（platform-orchestrator 有各模式具体内容）。**防递归检查**：四方案均保持"执行体间不直连"，全部经主 agent 中转或单执行体自足。

| # | 场景 | 解决模式 | 归属轴 | 能力依赖 |
|---|------|---------|--------|---------|
| 1 | 交互式 UI/前端迭代（写→浏览器看→改） | **⑧ 视觉迭代式** | 工具需求轴 | playwright（Reasonix 独有）+ 执行体写码 |
| 2 | 运行时调试（attach 进程/实时日志） | **⑥b 调试变体**（模式⑥ 特化） | 工具需求轴 | claude Bash 后台 / codex sandbox |
| 3 | 超长时任务监督（>30 分钟） | **⑨ 监督轮询式** | 并行轴 | claude CronCreate/ScheduleWakeup |
| 4 | 异构跨执行体拆分（能力差两半） | **⑩ 协调拆分式** | 决策轴 | 主 agent 协调（防递归不变） |

> 实测状态：⑧⑨⑩ 定案未实跑（待首次对应任务验证）；⑥b 复用 ⑥ 实测基础。

---

## 工具选择速查表

| 你的需求 | 工具 | 来源 |
|----------|------|------|
| 定位函数/类/变量 | `codegraph_symbol_search`（主）/ `mcp__serena__find_symbol`（补） | codegraph/serena |
| 理解某段代码的上下文 | `mcp__serena__find_symbol` + `get_symbols_overview` | serena |
| 编辑前获取完整上下文 | `mcp__serena__find_symbol` + `find_referencing_symbols` + `get_diagnostics_for_file` | serena |
| 跨文件理解某个概念 | `mcp__serena__find_symbol` + `find_referencing_symbols` | serena |
| 谁引用了这个函数 | `mcp__serena__find_referencing_symbols` | serena |
| 函数实现/声明定位 | `mcp__serena__find_declaration` / `find_implementations` | serena |
| 修改影响范围 | `codegraph_analyze_impact`（主）/ `mcp__serena__find_referencing_symbols`（补） | codegraph/serena |
| 找关联测试 | `mcp__serena__find_referencing_symbols` + grep 测试命名 | serena |
| 变更影响/诊断检查 | `mcp__serena__get_diagnostics_for_file` + `mcp__github__get_commit` | serena/github |
| 查第三方库最新文档 | `resolve-library-id` → `query-docs` | Context7 |
| GitHub 仓库操作（搜代码/取文件/PR/issue） | `mcp__github__*`（search_code / get_file_contents / create_pull_request / add_issue_comment 等 75 工具） | github |
| 检索个人踩坑/经验 | **默认 worker 外包**（P3-0 区域划分 R1-R3，`--model gateway-auto`），回退 `mcp__ima__search_notes` | worker / ima |
| 派发检索/初筛/收集类子任务 | fleet / task + **免费模型**（glm/kimi/deepseek 免费档） | worker |
| 派发精炼/综合/判断类子任务 | task + **deepseek-pro** 或主模型（免费档精炼会误判） | worker |
| 记录踩坑/经验 | `mcp__ima__create_note`（命名 `<项目名> - <简述>`）| ima |
| 并发/状态机类深层 bug 挖掘 | `specula-concurrency-hunt` skill（Specula CLI：TLA+ 规约 → TLC 模型检查 → 代码级复现） | specula |
| 圈复杂度检查 | `code_index` outline 人工评估（serena 无专门工具） | 内置 |
| 循环依赖检测 | `mcp__serena__find_referencing_symbols` 组合人工判环 | serena |
| 清理未用导入 | `mcp__serena__get_diagnostics_for_file`（诊断告警） | serena |

---

## 注意事项

1. **代码智能工具双轨（2026-08-11）**：**codegraph**（42 工具，主选）与 **serena**（23 工具，符号级补充）并存——codegraph 覆盖五步全场景（symbol_search / analyze_impact / find_related_tests / analyze_complexity / find_circular_deps / get_edit_context 等，首次需 `codegraph_index_directory` 建索引）；serena 补充符号级语义（find_referencing_symbols / rename_symbol / get_diagnostics_for_file，首次需 `mcp__serena__activate_project`）；两者不可用时回退 `code_index`/grep/lsp。
2. **Context7 查询限制**：每个问题最多 3 次查询，优先选择高信誉、高代码片段数的来源。
3. **五步框架不动摇**：serena/Context7/github/worker 是工具增强，不是替代。工具不可用（serena 未激活/未加载、ima MCP 未加载、worker 网关 :8080/free_api :8000 未起）时，回退到原有的 `grep`/`read_file`/`lsp_*`/`code_index` / 内联 memory/ima 检索方式。
4. **不被工具裹挟**：对单文件小改动，不需要走完整工具链；对模块级重构或引入新库，必须走完整流程。worker 派发同样遵循此阈值——①②③⑤ 的检索/探测/验证子任务，仅当多文件/跨模块/验证面广时外包，简单情况直接内联（worker 有调度开销）。
5. **ima 笔记本约定**：踩坑/经验统一记入 ima「代码示例与bug记录」笔记本，笔记标题必须带项目名前缀（`<项目名> - <问题/功能简述>`）；写入前先检索去重。

**Why:** 五步法保证推进节奏可控；Context7 消除第三方库 API 幻觉；serena 用符号级语义替代人工 grep（跨文件引用/影响面）；github 补仓库操作——四者合一，既要稳，又要准。

**How to apply:** 每个非平凡任务按此五步推进。编码步骤自动触发 Context7（外部库）或 serena（内部符号/调用链/影响面分析）；涉及 GitHub 操作走 `mcp__github__*`。单步验证时默认跑 serena 诊断 + 引用检查。不适用时跳过相关工具。

## 与其它 skill 的衔接

- **memory-codegraph-collab**：管"记忆检索什么/怎么校验"——记忆全文检索默认 worker 外包（P3-0），本 skill 第二步的历史经验检索子任务按区域划分（R1 记忆 / R2 history / R3 ima / R4 代码 / R5 网页）与结论三段式回收执行；worker 不可用时回退内联混合召回
- **platform-orchestrator**：管"worker 怎么派发/审阅"（双轨路由 model 表/指挥五步/任务书模板/结论审阅）；本 skill 五步中 ①状态检查 ③依赖检查 ⑤验证 的检索子任务可派发 worker（触发条件见注意事项 4）
