---
name: mode-two-domains
description: 标准模式二执行域模块：执行域工具链全景（浏览器 browser-director 44 工具分组与调用序列 / Windows desktop-worker Frida 接口与脚本设计 / 静态分析链 / v1.1 explore 探索域 D5）、执行层会话生命周期、模型档位与免费层准入（v1.1 条件化）。由 Standard_Mode_Two 框架路由加载，勿直接作为任务入口
---

# Skill: mode-two-domains（标准模式二 · 执行域与工具链）

> 定义"三个执行域各自的工具面、怎么调、什么顺序、怎么管会话"。由 `Standard_Mode_Two` 框架 skill 在轴1 选定 domain 后加载。
> 单一事实源：工具清单、调用序列、会话生命周期只在本模块定义；执行体角色边界见 `mode-two-roles`。

---

## 1. 三域总览（2.1）

| 域标识 | 名称 | 执行体 | 工具面 | 典型战例 |
|---|---|---|---|---|
| browser | 浏览器执行域 | D1 browser-director worker | 44 引擎级工具 + 浏览器指纹 | Web 签名参数、Web 签名战例 |
| windows | Windows 执行域 | D2 desktop-worker（Frida，待建） | Frida hook / Stalker / 内存只读 | 示例目标 A（桌面应用） <KEY> |
| static | 静态分析域 | D4 subagent fleet + Ghidra + codegraph/serena | 文件系统只读分析 | key_blob 密文族检测 |
| explore（v1.1） | 探索域 | D5 探索群：deepseek 网页号池（文本探索）+ 内置 subagent（工具型探索，强模型） | 只读探索（源码/文档/数据/枚举） | E 相位探索树 |

三个域共用同一套"任务书 → 静默执行 → 双顾问并行挑刺 → 指挥官裁决"循环，差别只在工具面。域标识写进任务书与回执，讨论层靠它区分上下文。**v1.1 增补**：explore 探索域（D5）按探-收双相位模型在 E 相位运行（框架 skill「探-收双相位模型」节），只读边界/出口组合绑定/准入四条件见 `mode-two-roles` D5 节；探索卡协议见 `mode-two-round` §6.5。

---

## 2. 浏览器域（D1，browser-director worker）

### 2.1 接入步骤（4.2 实测修订版，2026-08-12）
1. 启动 browser-automation：`powershell Start-Process '<HOME>\tools\browser AI\firefox.exe' -ArgumentList '-marionette','-remote-allow-system-access','-no-remote','-profile','<HOME>\AppData\Roaming\Mozilla\Firefox\Profiles\ds01hysb.default'`。**端口 3928**（不是 2828）；**必须带 -profile**；启动失败先删 profile 下 parent.lock。
2. 用户在 Firefox 窗口的 Agent 设置里配 worker key（唯一需要用户动手的环节；director 不碰 key，只校验 hasKey）。
3. 把 browser-director 注册进本会话 MCP（.mcp.json 或等价注册），frx_status 确认就绪；**MCP 代码改动后需重启 Reasonix**。
4. 之后每次会话：先 frx_status 探活，未连接则请用户重启浏览器。
5. **workspace 双视角**：workspaceRoot 下行给浏览器必须是 **Windows 路径**（默认 `<HOME>\firefox-reverse-ws`），MCP 侧自动 toPosix 转换；显式传时不可用 <HOME> 或 /mnt/...。
6. **run_node 前置**：profile prefs.js 已配 `extensions.firefox-reverse.agent.exec.node = D:\download\node.exe`（绕过系统 PATH `?` 脏条目导致的 _resolveExe 崩溃）；换机/重装需重配。

### 2.3 44 工具按逆向阶段分组（15.1，2026-08-12 修正实际工具名）

| 阶段 | 工具组 | 典型工具（实际名） | 用途 |
|---|---|---|---|
| 侦察 | 页面观测 | page_info / page_snapshot / net_capture / scripts_list | 看页面状态、抓请求（net_capture 含发起者调用栈） |
| 定位 | 函数追踪 | signer_trace / closure_read / code_search | 找到签名函数与闭包变量 |
| 深挖 | 字节码层 | jsvmp_trace / jsvmp_disassemble / whitebox_diff | JSVMP 解释器指令流、白盒差分 |
| 篡改 | 运行时 | hook_inject（document-start 注入）/ page_eval 包装 / cookies_set | hook 原型链、patch 环境（**引擎层 signer_trace 零注入优先**） |
| 反制 | 反调试 | 引擎层旁观（零页面注入，天然不触发）+ page_eval 探测 | 绕过检测 |
| 收尾 | 取证 | page_eval 返回值 / fs_write 落盘 / net_capture（WS 帧） | 抓最终参数与状态 |

### 2.4 典型调用序列（15.2，R1 模式默认骨架，指挥官按战例增删）

```
round 1: page_eval(检查 window.signFn 是否存在) → net_capture(定位含签名的请求)
round 2: signer_trace(signFn 函数入口) → closure_read(抓闭包中的密钥/IV)
round 3: jsvmp_trace(4786-case 解释器) → jsvmp_disassemble(字节码反汇编)
round 4: page_eval 环境替换(WebCrypto 等) → page_eval(验证参数是否变化)
round 5: hook_inject(document-start 跨刷新) → net_capture(抓 WebSocket 侧信道)
```

每个序列的每一步对应任务书里的一行"第 N 步"，执行层照单执行，不发明路线。

### 2.5 会话生命周期管理（附录 L，继承 frx-dual-agent-reverse）

| 动作 | 工具 | 时机 |
|---|---|---|
| 开会话 | agent_start（assist=true 默认阶段门停，maxRounds=80，model=flash 档，targetUrl，task=任务书） | T1 下发 |
| 阻塞等待 | agent_wait_for_stop 默认 timeoutSec=5400（⚠️ MCP 层硬限制 300s，长任务等不到阶段门；实测变通：`agent_state` 轮询 running/settled，settled 才是阶段结束唯一信号） | T2 等待执行 |
| 存活探针 | agent_state（查 running/nSteps/likelyDrift/recentToolCalls） | 等待超时但未停时 |
| 阶段审阅 | agent_read（①确认发现②候选方向③推荐；**必须核查 driftHint+finishReason**） | T3 回执前 |
| 方向纠正 | agent_send（一句话纠正，写得像真人：具体/有序/防兔子洞） | 阶段门内发现跑偏 |
| 截停 | agent_stop（进展已落盘不丢） | 冲向错误路线时 |
| 无人值守收尾 | agent_set_mode auto | 收敛后收尾 |

**会话与 round 映射（L.2）**：推荐每 round 一个会话（任务书独立、回执独立、round_id 锚定干净）。会话结束但结论可疑：agent_runlog 查 finishReason——drift/idle-timeout ≠ 路线走不通，是模型没调工具，先 T4 降级再决定重派。

**共享状态纪律（L.3）**：同一 tab / hook 会话内串行禁止并发（已实测串味）；不同域活状态天然隔离可 P2 并行；指挥官直驱（agent_call_tool）必须等 worker 会话停之后（共享 tab 状态会串味）。

---

## 3. Windows 域（D2，desktop-worker，Frida，待建）

### 3.1 接口清单草案（4.3，对齐 browser-director 工具风格，首批 11 个）

| 工具 | 输入 | 输出 |
|---|---|---|
| wx_status | - | 目标进程/已 attach/关键模块列表 |
| attach | pid / 进程名 | attach 成功/失败 |
| hook_sqlite3_key | 无 | 命中回调（sqlite3_key_v2 参数） |
| hook_bcrypt_pbkdf2 | 无 | 命中回调（参数+派生输出） |
| hook_dpapi | 无 | CryptProtectData/Unprotect 回调 |
| hook_pbkdf2_sha512 | 无 | mac_key 派生点回调 |
| wx_stalker_trace | 起始地址/范围 | 指令流（过滤后） |
| wx_read_mem | 地址/长度 | 十六进制 dump（只读） |
| scan_magic | 魔术字节（如 <MAGIC>） | 命中地址列表 |
| wx_regions | - | 可读内存区域清单 |
| wx_run_script | JS 脚本 | 执行结果（预置脚本模板） |

### 3.2 开发路径（4.3 + 附录 G.1）
- wxd/mcp_server.py 已证明 FastMCP stdio 模式可行；新增 frida_server.py 挂同配置链（env→~/.config/ima/→~/.cache/ima/ 同款零配置思路），Windows Python 侧运行。
- 架构：读 config.json → 连接 frida 到 TargetApp.exe（attach 模式）→ 按工具名加载预置 JS 脚本片段（scripts/ 目录）→ 事件回调 → 结构化 JSON 回执。

## 4. 静态分析域（D4，域3）

- **抓回的 JS**：本地 subagent fleet 并行分析（区域划分：算法区/反调试区/网络区），codegraph/serena 做符号级定位。
- **Windows 二进制**：WSL 侧 Ghidra（headless）分析 TargetApp.exe / wx_key.dll 的导出与交叉引用，产出静态候选 hook 点清单，供 D2 动态验证。
- **触发条件**：≥3 个本地文件/样本需独立分析 → P4 静态 fleet 并行（写隔离：各 worker 只读自己分区）。
- **工具衔接**：符号级检索用 codegraph（42 工具）/ serena（23 工具），协作守则见 `memory-codegraph-collab`。

### D3 文件系统执行体（Codex/Claude Code，2026-08-13 补）

D3 是跨域文件系统执行体（角色边界见 mode-two-roles §3.6），经 L0 worker 脚本（claude-worker.sh / codex-worker.sh）调用，非对话式。工具面与会话生命周期：

- **skill 目录（实测）**：codex 用户级 `~/.cache/codex/skills/`、claude 用户级 `~/.cache/claude/skills/`。样板 `reasonix-worker-brief`（框架级任务书执行规范）已双端落盘，任务书可引 skill 名替代现写五段式。
- **会话生命周期（对齐 D1）**：claude 内置 Task* 在 -p 无头下默认可用（`--allowedTools` 白名单只约束 MCP 工具），可用 TaskList 探活、结构化回执当阶段审阅、追加任务书轮当方向纠正；Task* 不可用时回退 CronCreate 定时盲查。
- **codex 沙箱限制**：workspace-write 沙箱写不了 `$CODEX_HOME/skills/`（只允许写 cwd + /tmp），skill 落盘由主 agent 完成；skill-creator 可自我 skill 化（读规范→创建→quick_validate 校验）。
- **内置子代理**：D3 分析大段 JS/静态样本时可用 Agent:Explore 内部再分工，减指挥官往返；严禁用 Agent 子代理充当 B/C 顾问（见 mode-two-roles §3）。

---

## 5. 执行层模型档位与工具可达性（15.3）

- **flash 档（默认）**：deepseek-v4-flash / flash 档模型 / glm。适合"照任务书执行工具、返回原始数据"。**别选推理档**——推理档在长工具循环里易漂移成纯文字不调工具（已实测）。
- **强模型直驱（T2）**：仅最后收口。agent_call_tool 直驱烧的是指挥官 token，单步操作可控。
- **工具落盘失败时**（fs/run_node 故障）：页面侧观测（page_eval/signer_trace）通常仍可用；落盘需求改在文件系统侧用 D3/D4 干。
- **免费层准入（附录 Q，v1.1 条件化改写）**：免费层允许进入执行层，**仅限"只读探索类"任务**（任务书声明 mode: explore 且工具面白名单化）：
  - ✅ 文本型探索（源码分析、文档检索、数据初筛、候选枚举）——免费 worker 擅长区
  - ✅ **模型范围收紧（v1.1）**：仅 free_api **deepseek 网页号池**——当前唯一免费旗舰级通道；glm_api / kimi / 其他免费档维持"预处理/初筛/检索辅助"既有定位，**不进探索执行层**
  - ❌ 工具型动作（浏览器操作、发请求、hook、文件写）——仍禁止；此类探索由内置 subagent（强模型）在 D5 中承担
  - ❌ B/C 讨论层（假阴性污染裁决）、裁决与终止判定（指挥官唯一）——维持禁止
  - 依据：原"适合执行层（收集/检索/初筛）"针对只读探索；"禁止执行层"针对工具型执行——两条并存不矛盾，v1.1 把"只读探索"从执行层拆出单列。

---

## 6. 战例 runbook（S2 档案 + 跨战例经验）

- **desktop-app.md**：示例目标 A（桌面应用） 战例（域2 主战例）——已知/已排除/未解三件套、Frida 三连 hook 顺序、成功判据（decrypt.py 跑通）。
- **web-sign.md**：Web 签名战例 / Web 签名参数 战例（域1 主战例）——字节码虚拟机、AES 沙箱纯 JS、C2 分治爆破的 IV 派生攻坚。
- **新战例接入**（9.3）：先对照附录 I 常见死路清单 → 跨域检索同构经验（memory search）→ 按 runbook 结构建档案目录 → 进 T0。

**跨域同构经验迁移表（K.4，检索记忆时优先命中）**：

| 经验 | 来源战例 | 可迁移到 |
|---|---|---|
| hook 全 0 命中 = 路径被绕过，换路径 | WEB-SIGN（WebCrypto 全 0） | 桌面目标（若 sqlite3_key 0 命中 → 转 Stalker） |
| 沙箱/自实现是绕过 hook 的惯用手法 | WEB-SIGN（纯 JS 沙箱） | 桌面目标（自实现 SQLCipher 路径） |
| 死路证明要落盘，防下个战例重踩 | WEB-SIGN / flash 模型（IV 阻塞） | 所有新战例 |
| 运行时证据优于静态快照 | WEB-SIGN（快照失真） | 桌面目标（内存布局以运行时为准） |
| "不可行"结论本身是成功交付物 | flash 模型（套壳证明） | 所有高难度目标 |

---

## 7. 与其它模块的引用关系

- 执行体角色边界与决策权 → `mode-two-roles`
- 调用序列对应的任务书写法、回执协议 → `mode-two-round`
- 浏览器域骨架/防漂移 → `frx-dual-agent-reverse`
- 单次浏览器取证方法论 → `trace`
- 执行层派发模式 → `platform-orchestrator`
- D5 探索域（explore）：角色边界 → `mode-two-roles` D5 节；探索卡协议 → `mode-two-round` §6.5
