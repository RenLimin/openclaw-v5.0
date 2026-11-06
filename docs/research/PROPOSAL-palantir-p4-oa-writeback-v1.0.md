# PROPOSAL — Palantir Oncology P4：泛微 OA 真写回 / 回调立项 v1.0

> L4 · bangcle-contract · 归属：Contract Ontology Bridge 的 **P4（边界外立项）**
> 版本 v1.0 · 状态：**立项草案，已立档；真实写回执行需 Rex 针对单据二次授权** · 2026-11-06 · Jerry 🦞
> 上游依据：`L4-.../docs/DESIGN-OUTLINE-contract-ontology-bridge-v1.0.md` §5（P4 明确边界外）
> 关联：RESEARCH-palantir-oncology-v1.1 · MEMORY.md 泛微 OA 环境约束

---

## 1. 为什么有这份文档

P1–P3 用**本地表写回**演示了完整 Saga（commit 事务内真写回 L4 contract 表 + 失败补偿）。但"合同审批最终生效"的真实落点是**泛微 e-cology 9 工作流**（oa.bangcle.com）。P4 要解决的是：把 `approve_contract` / `reject_contract` 的决策**真实写回 OA 工作流节点**，而不只是本地表。

按 OUTLINE §5 红线，P4 属**不可逆外部写操作**，必须单独立项、核实数据源、获得明确授权——故本文档只立档与规划，不擅自执行写回。

---

## 2. 数据源核查结论（2026-11-06 亲查代码，非记忆）

| 能力 | 现状 | 证据 |
|---|---|---|
| OA 合同卡片只读 | ✅ 已固化 | `services/oa/cube.py`（435 行）：`_get_json` 走 **GET + JSON**，`get_contract(billid)` 读卡片 + 附件 |
| OA HTTP 写方法（POST） | ❌ 不存在 | `cube.py` 全文件**无任何 `session.post`**，纯只读客户端 |
| 审批流状态查询 | ❌ 冻结 | `cube_provider.py:query_process` 恒返 `unknown` 信封，"绝不发请求/伪造" |
| 审批结果写回 | ❌ 冻结 | `cube_provider.py:push_result` → `raise NotImplementedError("push_result 在 P4（真写回）前冻结")` |
| OA 事件回调 | ❌ 冻结 | `cube_provider.py:register_callback` → `NotImplementedError("register_callback 在 P4（回调）前冻结")` |
| 审批日志端点 `getRequestLogList` | ⚠️ **未固化进仓库** | 全仓库限定 L3/L4/docs/scripts 搜索 `getRequestLogList` / `RequestLogList` **零命中**；git `-S` 历史亦无。MEMORY 记录 11-04"纯 HTTP 重放已验证"系**手工临时 curl**，代码未落地 |
| 开放平台凭证 | ❌ 不具备 | 普通账号权限，无 WorkflowService / app token（MEMORY 环境约束） |
| 现存 ecology 会话 | ❌ 已超时 | 2026-11-04 起超时；重建需消耗一次真实 IMAP 验证码 |

**核心结论：当前仓库对泛微 OA 是"能只读卡片、不能写、审批流未接"。** 11-04 手工验证过审批日志只读端点的可行性，但那段知识只存在于 MEMORY，**没有可复现的代码**。P4 必须先把它固化，才能谈写回。

---

## 3. P4 范围定义

### 3.1 In-scope（本立项做）

| 阶段 | 内容 | 前置 |
|---|---|---|
| **P4.0 会话与夹具** | 重建 ecology 会话（消耗 1 次 IMAP 验证码，Rex 在场）；固化 `getRequestLogList` / `getRequestLogBaseInfo` 为 `cube.py` 的真实方法 + 黄金夹具（脱敏录制 → 重放） | Rex 提供验证码窗口 |
| **P4.1 审批链读取** | requestid 解析（合同卡片"合同审批流程"字段）→ 节点/处理人/动作/意见完整 loglist；映射到 L3 审批状态机的当前节点 | P4.0 |
| **P4.2 写回可行性验证（只读先行，不写）** | 用**真实 OA 的写接口文档/抓包**确认"同意/驳回"的端点、CSRF/nonce、body 契约；先在**测试流程单据**上验证，绝不在真实在审合同上试 | P4.1 + Rex 指定测试单据 |
| **P4.3 OaWritebackConnector** | 实现 `WritebackConnector` 契约：`apply` 在 commit 事务内调 OA 写接口；`compensate` —— ⚠️ **OA 写操作不可自动回滚**（外部系统已流转），补偿只能记冲销/人工工单，不能像本地表那样还原 | P4.2 |
| **P4.4 回调（可选，建议后置）** | OA 状态变更 → 本地 reconcile（`ont_reconcile`）轮询或 webhook；e-cology 无应用凭证时走定时对账更现实 | P4.3 |

### 3.2 Out-of-scope（红线）

- ❌ 不在真实在审合同上做任何写回试验（只用 Rex 指定的测试流程单据）
- ❌ 不自动补偿 OA 已生效的写操作（外部不可逆，补偿=人工对账/冲销，不伪造回滚）
- ❌ 不存储 OA 凭据/验证码到任何 markdown；不新增第三方依赖
- ❌ 不伪装 agent 可代行 human 审批（审批 human 级动作的越权拒绝在 P2 已固化，P4 保持）

---

## 4. 关键风险与设计影响

| 风险 | 影响 | 对策 |
|---|---|---|
| **Saga 补偿语义变化** | 本地表 `compensate` 可物理还原；OA 写回**不可还原** | P4.3 connector 的 `compensate` 只落"人工冲销工单 + 审计"，Proposal 结果标 `externally_committed`，**不宣称回滚成功**。这是对现有 Saga 契约的增量，需在 DETAIL 升版说明 |
| 会话时效 | ecology 会话数小时即超时，写回可能中途 440 | 写回前 preflight 会话；440 → 中止提案为 failed，不重试写（避免重复提交） |
| 写接口重复提交 | 网络重试可能导致同一审批动作发两次 | OA 侧幂等键 + 写前查询当前节点（已流转则跳过），对齐 P3 幂等语义 |
| 无开放平台凭证 | 只能会话 cookie + SPA 内部接口，脆弱、随版本变 | 黄金夹具 + 端点健康检查；端点变更即降级 unknown，不硬写 |

---

## 5. 前置条件（当前全部未满足 → P4 无法立即执行）

1. Rex 在场，允许消耗一次 IMAP 验证码重建 ecology 会话；
2. Rex 指定一张**测试流程单据**用于写回验证（非真实在审合同）；
3. 拿到写接口真实契约（P4.2 抓包/官方材料）；
4. 明确审批人身份映射（OA 工号 ↔ L3 reviewer）。

---

## 6. 验收标准（P4 全量完成时）

1. 审批链读取：给定 requestid，输出节点/处理人/动作/意见，与 OA 页面人工核对一致（黄金夹具 + 真机会话双验证）；
2. 测试单据写回：`approve` 在测试单据上真实流转，OA 页面可见状态推进 + 本地审计双写；
3. 重复提交防护：同 idempotency_key 重放不产生第二次 OA 动作；
4. 失败不静默：写回失败/会话超时 → proposal failed + 人工工单，**无伪造回滚**；
5. 对账：P4.4 轮询 reconcile 能发现本地与 OA 的状态偏差并报告。

---

## 7. 待 Rex 拍板

1. 本立项的阶段划分（P4.0–P4.4）是否认可；
2. 是否近期提供 IMAP 验证码窗口 + 测试单据（决定 P4 能否启动）；
3. P4.4 回调走"定时对账"还是"webhook"（建议定时对账，因无应用凭证）；
4. 是否同意 Saga 契约为"外部写不可补偿"增量升版（影响 DETAIL）。

> 在以上拍板前，P4 保持**已立档、未执行**；P1–P3 已是独立可交付的完整闭环。
