# 任务书模板（Standard_Mode_Two / templates）

> 下行协议：指挥官 → 执行层。≤1500 字。五要素齐（目标/已知/死步骤/约束/回执格式）才能下发。
> 纪律（附录 P.1，写进约束节）：①数据优先解释禁止 ②未命中是数据不是失败 ③超长即降载（data>3000 字先落盘，回执写 artifact_path）。

## 通用骨架（4.5）

```
Round: <N> | Domain: <browser|windows|static|explore> | Mode: <Rx+Cx+Px+Tx+Xx>
目标: <一句话,含成功判据>
已知:
- <关键事实1: 函数签名/入口>
- <关键事实2: 已确认机制/反证>
- <关键事实3: 静态快照为何不可用>
第1步: <工具名> <参数> <目的>
第2步: <工具名> <参数> <目的>
第3步: <工具名> <参数> <目的>
只做这N步,不绕圈。用 <指定工具> 返回值汇报,不写文件。
约束: <安全/风控/成本约束>
回执格式: {round_id, domain, status, data, confidence}
```

---

## R1 浏览器攻坚（D1 browser-director）

```
[Round <N> | Domain: browser | Mode: R1+C1+P3+T1]
逆向目标: <捕获/还原 XXX，成功判据一句话>
已知:
- signFn = function(e){return j(12,e,1,void 0,1,void 0)}  <函数签名/入口>
- AES 沙箱纯 JS,不走 WebCrypto（已确认机制/反证）
- 静态快照不可用：运行时被覆盖
第1步: page_eval <脚本> <目的>
第2步: signer_trace <函数名> <目的>
第3步: closure_read <变量名> <目的>
只做这3步,不绕圈。用 page_eval 返回值汇报,不写文件。
约束: 只读 hook,不碰登录;检测到反调试信号立即 status=failed 回报并挂起
回执格式: {round_id, domain, status, data, confidence}
```

## R2 本地二进制攻坚（D2 desktop-worker Frida）

```
[Round <N> | Domain: windows | Mode: R2+C1+P3+T1]
逆向目标: 提取 <目标> 的 <密钥/参数>，使 <解密脚本/验证脚本> 跑通
已知:
- SQLCipher4: AES-256-CBC + HMAC-SHA512, reserve=80, mac_key=PBKDF2-HMAC-SHA512(<KEY>, salt^0x3a, 2, 32)
- 4.1.11 不再内存缓存 x'<hex>' 明文模式（反证）
- key_blob 180B: 头+13B随机+len32+110B密文,算法未逆出
- 内存魔术点 <MAGIC> 已定位（find_keyinfo_mem.py）
第1步: attach <进程名> <目的>
第2步: hook_sqlite3_key 无 <观察是否走标准 SQLCipher API>
第3步: hook_bcrypt_pbkdf2 无 <抓 PBKDF2 输入输出>
第4步: scan_magic <MAGIC> <定位 key_blob 所在内存,回读上下文>
只做这4步,不绕圈。回执格式按协议。
约束: 只读 hook,不碰登录/网络/写内存;测试小号;若检测到反调试信号立即 status=failed 回报
回执格式: {round_id, domain, status, data, confidence}
```

## R3 混合攻坚（D1+D2+D3 按依赖排先后）

```
[Round <N> | Domain: browser|windows | Mode: R3+Cx+P2+T1]
逆向目标: <跨端链路还原 XXX，成功判据一句话>
已知:
- <浏览器侧抓到参数 X，需 Windows 侧验算（跨域协同）>
- <链路依赖顺序：先 A 后 B>
第1步: <域1工具> <参数> <目的>（浏览器侧）
第2步: <域2工具> <参数> <目的>（Windows 侧验算）
第3步: <D3 落地脚本> <参数> <目的>
只做这N步,不绕圈。用指定工具返回值汇报。
约束: 各域各自的安全约束（浏览器只读 hook / Windows 只读 attach）
回执格式: {round_id, domain, status, data, confidence}
```

## R4 纯静态分析（D4 fleet / Ghidra / codegraph-serena）

```
[Round <N> | Domain: static | Mode: R4+C1+P4+T1]
逆向目标: <对 X 做离线分析，成功判据一句话>
已知:
- <密文/样本/二进制来源与结构>
- <已排除的方向与理由>
第1步: <fleet 区域划分：算法区/反调试区/网络区> <目的>
第2步: <codegraph/serena 符号级定位> <目的>
第3步: <Ghidra headless 导出与交叉引用> <目的>
只做这N步,不绕圈。用工具返回值汇报,不写文件。
约束: 只读文件系统,不碰运行时
回执格式: {round_id, domain, status, data, confidence}
```

---

## 取证升格任务书（C4 模式，3.6 三触发条件之一命中时用）

```
[取证实验 | 由 D3 执行 | 触发: 强分歧/软退出/跨域验算]
背景: B 认为 <假设1>, C 认为 <假设2>, 各执一词
实验: 对 <对象> 做 <检测/验算>, 输出每族匹配度与依据
约束: 只读,不触碰目标进程;结果落盘到 <档案目录>/round<N>_experiment/
回执: {hypothesis, evidence, confidence, artifact_path}
```

---

## 探索任务书（E 相位，v1.1）

见 `templates/explore-task-brief.md`（E1 节点分派专用；只读边界 + 出口组合绑定 + 探索卡回报格式）。
E 相位任务书**不适用**本模板的五要素骨架——探索任务书的继承边界与回报格式不同，不得混用。
