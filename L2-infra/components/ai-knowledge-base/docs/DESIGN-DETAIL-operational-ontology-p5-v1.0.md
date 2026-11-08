# L2 运营本体 P5：OA 写回接入 Proposal Gate + MCP 工具自动生成（v1.0）

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）增量 P5
> 组件编码：INFRA-KB-002 · 版本：v1.0 · 状态：**待评审**（2026-11-08）
> 作者：Jerry 🦞 · 依据：RESEARCH-palantir-agent-application-v1.2（§4.2 差距 ① ② ③）、DESIGN-DETAIL-operational-ontology-v1.0（已验收）
> 范围：L2 原语扩展（P5.1/P5.4）+ L4 bangcle-contract 首个实例接入契约（P5.2/P5.3）
> 前置：operational-ontology v1.0（P1–P4 已验收，`ae3a1b9`）；P4.3 bangcle-contract 连接器（`b32cb1f`）

---

## 1. 范围与目标

### 1.1 背景（现状核查，基于真实代码）

v1.0 已交付 L2 运营本体全部原语；P4.3 已把 bangcle-contract 作为首个实例接入（`ContractOntologyBridge` 直接调用 L2 `ProposalService`/`ActionRegistry`/`DecisionService`，三个动作 submit/approve/reject 走两阶段提交）。调研 v1.2 发现三处与业界最佳实践的差距：

| # | 差距 | 现状（代码事实） | 目标 |
|---|---|---|---|
| ① | **OA 外部写未进 Proposal Gate 链路** | `OaWritebackConnector`（`oa_connector.py`）已实现 L2 接口（dry-run 审计、补偿恒抛 `CompensationUnavailable`），但**未注册**为任何 action 的 writeback step，无动作编排走它；`reconcile.py` 的本地预期态由调用方注入，**未以 `DecisionService` 为权威源** | OA 写回成为受治理动作（propose→validate→human review→commit），对账权威源统一到决策记录 |
| ② | **MCP 工具非自动生成** | `mcp/server.py` 手工 6 个 ontology 工具（`ont_query_object`/`ont_compute_risk`/`ont_propose_action`/`ont_list_actions`/`ont_get_proposal`/`ont_review_proposal`），action_type 新增**不会自动暴露** | 从 `ont_action_type`/`ont_function_def` 自动枚举生成工具描述符，新动作零代码暴露（移植 operational-ontology `buildMcpServer` 模式） |
| ③ | **无 preflight（dry-run 同码试运行）** | dry-run 是连接器内分支（`oa_connector.py`），非"提交同码在回滚事务里试跑" | 新增 `preflight()`：在回滚事务内执行完整 commit 流水线，供审批人审前预览 |

### 1.2 目标（本期）

1. **P5.1** L2 MCP 工具自动生成：action_type/function_def → 工具描述符自动枚举，命名冲突 build 时检测，硬约束（无 execute_*/write_*/commit_*）保持。
2. **P5.2** L4 实例：`submit_to_oa` 动作注册（required_approval=human，writeback step → `oa_writeback`），`ContractOntologyBridge.submit_to_oa()` 编排走 L2 全链路；**真实写冻结语义不变**（dry_run 默认、dry_run=False 抛 RuntimeError、补偿恒抛）。
3. **P5.3** L4 实例：`reconcile` 本地预期态改为由 `DecisionService.replay` 推导（决策记录 → 预期态映射），保持只读、保留注入接口兼容测试。
4. **P5.4** L2 `preflight()`：回滚事务内试运行 commit 流水线（含写回连接器），返回将发生的变更集/风险，零副作用。

### 1.3 非目标（本期不做，明确列出）

- ❌ 不解锁 P4.2 真实写：`dry_run=False` 仍抛 `RuntimeError`（需测试单据 + Rex 二次授权 + 增量文档 p4-write-v1.1）。
- ❌ 不做调用者身份签名校验（caller_id 仍由调用方声明；fail-open 风险记录为 P6 开放项）。
- ❌ 不做运营对象级权限 enforce（metadata.permissions 已有字段，enforce 留 P6）。
- ❌ 不自动生成 execute 类工具；MCP 三分类（query_/compute_/propose_）边界不破。
- ❌ 不引入新第三方依赖（preflight 用现有事务机制实现）。

---

## 2. 总体设计

### 2.1 分层与依赖

```
接入层  MCP server（P5.1：list_tools 动态枚举 action/function → 工具描述符）
        │
服务层  ProposalService
        ├─ preflight(proposal_id)      （P5.4 新增）
        ├─ commit 既有流水线（P5.2 复用：writeback_steps → SagaOrchestrator）
        ├─ connectors 表注入
        │    └─ "oa_writeback" → OaWritebackConnector（P4.3 产物，零改动复用）
        └─ DecisionService.replay      （P5.3：对账权威源）
        │
L4 实例 bangcle-contract
        ├─ L3 装配脚本：register submit_to_oa（action_type + writeback step）
        ├─ ContractOntologyBridge.submit_to_oa()（propose→validate→review→commit）
        └─ scripts/reconcile_oa.py：local_states 改为 replay 推导
```

依赖方向不变：接入层 → 服务层 → 注册表/决策；L2 不持有业务规则，`submit_to_oa` 的具体 schema/审批语义由 L3/L4 装配注入。

### 2.2 关键设计决策

| 议题 | 决策 | 理由 |
|---|---|---|
| OA 写回与本地状态变更的关系 | **独立动作** `submit_to_oa`（不并入 submit_contract） | submit_contract 是本地库写回（ContractWritebackConnector 单连接器路径）；OA 是外部不可逆写，独立动作便于 human 审、审计分离、对账映射 |
| commit 内步骤顺序 | 保持 v1.0：应用 change_set → 写回连接器 → 决策记录，单事务 | 外部写失败 → 整体 ROLLBACK → 本地零残留（干净失败）；外部成功 → COMMIT → 一致。残余风险（外部成功但本地 COMMIT 失败）由 reconcile 兜底，与 P4.3 语义一致 |
| 补偿语义 | `OaWritebackConnector.compensate` 恒抛 → SagaOrchestrator 记 `compensation_unavailable` + `reconciliation_required`，标 `externally_committed` | P4.3 已拍板：外部写不可物理补偿，只记录人工冲销工单 |
| preflight 实现 | 回滚事务内跑完整 commit 流水线（含连接器 apply），结尾 ROLLBACK | 同码试运行 = 与真实提交共享同一代码路径，杜绝"预演与真跑不一致"（operational-ontology #preflight 模式） |
| MCP 自动生成的命名 | `ont_propose_<action_name>` / `ont_compute_<function_name>`；跨 domain 冲突 build 时报错 | 工具名全局唯一；冲突检测在装配/首次枚举时 fail-fast（operational-ontology 命名冲突检测模式） |

---

## 3. P5.1 MCP 工具自动生成（L2）

### 3.1 现状

`mcp/server.py`：
- `ontology_tool_descriptors()` 静态返回 6 个工具描述符（含 category 字段）；
- `_call_ontology_tool()` 手工分发。

### 3.2 设计

新增 `_dynamic_ontology_tools(db)`（或 `ActionRegistry.list_actions` + `list_functions` 的封装）：

```
list_tools() =
    静态 6 工具（保留，向后兼容）
  + 动态枚举（每 action_type status=active）:
      ont_propose_<name>      # category=propose_
        inputSchema: params_schema(JSON Schema) 的 properties
                      + caller_id/caller_kind/rationale/idempotency_key 包装
        description: 由 action 的 object_type + writeback_target 自动生成
  + 动态枚举（每 function_def deterministic=1）:
      ont_compute_<name>      # category=compute_
        inputSchema: io_schema.properties
```

`call_tool` 分发：
```
ont_propose_<name>  → ProposalService.propose_action(domain, name, ...)
ont_compute_<name>  → ActionRegistry.get_function → 执行（只产出建议，零写）
```

**硬约束（不变量，测试锁定）**：动态枚举**只**生成 `propose_*`/`compute_*`；任何 `execute_*`/`write_*`/`commit_*` 名称出现在枚举结果 → 测试断言失败（`test_no_execute_tools_leak`）。commit 仍只由 `review(auto_commit=True)` 内部触发。

**命名冲突检测**：`list_tools()` 枚举时收集全部工具名，发现重复 → 抛 `ValueError`（装配期/联调期 fail-fast；运行期 MCP server 启动即校验）。

**兼容性**：静态 6 工具描述符不变（既有 client 不破）；新增工具仅追加。

### 3.3 数据模型

无新表。复用 `ont_action_type.params_schema` / `ont_function_def.io_schema`（均为 JSON Schema 文本）。

### 3.4 文件变更

| 文件 | 变更 |
|---|---|
| `mcp/server.py` | `list_tools` 增动态枚举；`call_tool` 增 `ont_propose_<name>`/`ont_compute_<name>` 分发；启动时命名冲突校验 |
| `mcp/__init__.py` | 导出新增 helper（如需） |
| `tests/test_mcp_dynamic_tools.py` | 新增：枚举正确性、冲突检测、无 execute 泄漏、向后兼容 |

---

## 4. P5.2 OA 写回接入 Proposal Gate（L4 实例）

### 4.1 连接器复用（零改动）

`OaWritebackConnector`（P4.3）已满足全部要求：
- `name = "oa_writeback"` → 作为 connectors 表 key；
- `apply(ctx)`：dry_run 下只 `ctx.mark_success` 落审计（含 requestid/action/comment/recorded_at）；`dry_run=False` 抛 `RuntimeError`（P4.2 冻结）；
- `compensate(ctx)`：恒抛 `CompensationUnavailable`。

**P5.2 不修改 `oa_connector.py`。**（若未来 P4.2 解锁，改动仅限该文件 + 授权文档。）

### 4.2 L3 装配扩展（`register_ontology_functions.py`）

新增（幂等，装配期，AssemblyGate 开启时执行）：

```python
# submit_to_oa：OA 外部写，必须 human 审
reg.register_action_type(
    DOMAIN_CODE, "submit_to_oa", "contract",
    params_schema={
        "type": "object",
        "properties": {
            "requestid": {"type": "string"},   # OA 流程单据 id
            "action": {"type": "string"},      # 流转动作（提交/退回等）
            "comment": {"type": "string"},
        },
        "required": ["requestid", "action"],
    },
    precondition=None,
    required_approval="human",
    writeback_target="oa_writeback",
)

# 写回步骤（有序，seq 从 1）
steps = [{"seq": 1, "connector_key": "oa_writeback",
          "payload_schema": {
              "type": "object",
              "properties": {
                  "requestid": {"type": "string"},
                  "action": {"type": "string"},
                  "comment": {"type": "string"},
              },
              "required": ["requestid", "action"],
          }}]
reg.register_writeback_steps(action_type_id, steps)
```

绑定校验：`validate_action_bindings(DOMAIN_CODE)` 覆盖新动作（connector_key 注册期不做存在性校验——连接器由 ProposalService 注入，运行时缺失 → 明确报错，不静默）。

### 4.3 Bridge 编排（`bridge.py`）

新增方法：

```python
def submit_to_oa(
    self,
    contract_id: int,
    operator: str,
    *,
    requestid: str,
    action: str = "提交",
    comment: str = "",
    rationale: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """OA 外部写：draft/review → OA 流转（human 审，dry-run 审计）。"""
    return self._run_oa(
        contract_id, operator, requestid=requestid,
        action=action, comment=comment, rationale=rationale,
        idempotency_key=idempotency_key,
    )
```

`_run_oa` 与 `_run` 同构，差异点：
- `_ACTIONS` 增 `"submit_to_oa": ("submit_to_oa", "human", "review")`（target_state 仅作 metadata 提示，不强制本地状态机转移——OA 态以对账为准）；
- `_new_service_oa()`：构造 ProposalService 时注入 `connectors={"oa_writeback": OaWritebackConnector(dry_run=True, target=oa_payload)}`；
- 调用 `svc.review(proposal_id, "approve", operator, reviewer_kind=caller_kind, auto_commit=True)` —— human 审 + auto_commit，SagaOrchestrator 编排 oa_writeback step；
- commit 成功后 `registry.sync_metadata`（若本地状态机允许）或仅记 decision record（OA 态交由对账）。

**提交 payload 约定**：propose 的 params 含 requestid/action/comment；`SagaContext.payloads["oa_writeback"]` 由 ProposalService commit 的 writeback step 组装（若 v1.0 未自动填充，bridge 在 propose 后、commit 前经 `_new_service_oa` 注入——实现细节以代码评审为准，契约不变：连接器 `_resolve_target` 优先读 `ctx.payloads[step_name]`）。

### 4.4 冻结边界（不变量，测试锁定）

| 路径 | 行为 |
|---|---|
| `dry_run=True`（默认） | 仅审计，无 HTTP；`ctx.results["oa_writeback"]` 含 `dry_run: True` |
| `dry_run=False` | `RuntimeError`（P4.2 未闭合）；测试断言不出现任何真实请求 |
| `compensate` | 恒抛 `CompensationUnavailable` → proposal `failed` + 人工对账记录 |
| 幂等 | 同 `idempotency_key` 重放返回既有 proposal，不重复副作用 |

### 4.5 文件变更

| 文件 | 变更 |
|---|---|
| `L3-business/components/contract-management/scripts/register_ontology_functions.py` | 增 `submit_to_oa` action + writeback step（幂等） |
| `L4 .../ontology_bridge/bridge.py` | 增 `_run_oa` + `submit_to_oa()`；`_ACTIONS` 扩展 |
| `L4 .../ontology_bridge/oa_connector.py` | **零改动** |
| `L4 .../tests/unit/test_oa_writeback_proposal.py` | 新增：全链路（propose→validate→human review→commit dry-run 审计）、冻结边界、补偿路径 |

---

## 5. P5.3 对账权威源统一（L4）

### 5.1 现状

`reconcile.py` 的 `local_states` 由调用方注入（`scripts/reconcile_oa.py` 构造），未读 `DecisionService`。`decision_chain()` 已存在（bridge 内 DecisionService.replay）。

### 5.2 设计

新增纯函数（放 `reconcile.py`，保持无副作用）：

```python
def local_state_from_decisions(
    decisions: List[Dict[str, Any]],
    *,
    default: str = "",
) -> str:
    """决策记录链 → 本地预期态。

    映射（与 STATE_ORDER 同尺）：
    - 最近一条 committed 的 action_type == approve_contract → approved
    - reject_contract → draft
    - submit_contract → review
    - submit_to_oa → 以对账语义为准（OA 态权威），本地预期 = review
    - 无决策记录 → default（空 = 未登记，reconcile 保守归 local_ahead 由
      上层处理；不伪造 in_sync）
    """
```

`scripts/reconcile_oa.py`：构造 local_states 时改用 bridge `decision_chain(contract_no)`（内部即 `DecisionService.replay`）→ `local_state_from_decisions`；**保留 `local_states` 注入参数**（测试/降级兼容）。对账结果四态语义、`oa_unknown` 降级、不自动触发写回——全部不变。

### 5.3 一致性验证

黄金 fixture：对 `oa_log_882663.json`（10 条）对应合同，断言 replay 推导的预期态与手工报表口径一致（复用既有 fixture，不新增）。

### 5.4 文件变更

| 文件 | 变更 |
|---|---|
| `reconcile.py` | 增 `local_state_from_decisions()` |
| `scripts/reconcile_oa.py` | local_states 改由 replay 推导（注入参数保留） |
| `tests/unit/test_reconcile_oa_runner.py` | 增推导用例（含无决策/拒绝/提交三类） |

---

## 6. P5.4 preflight（L2，可裁剪项）

### 6.1 设计

```python
def preflight(self, proposal_id: int) -> Dict[str, Any]:
    """回滚事务内试运行完整 commit 流水线（含写回连接器）。

    - 校验状态 == validated（未审/未过审 → 明确报错，不试跑）；
    - BEGIN → 执行与 commit 完全相同的步骤序列
      （_apply_change_set → writeback steps → 决策记录写入）
      → 在 COMMIT 前 ROLLBACK；
    - 返回 {"ok", "change_set", "writeback_dry_results", "risk_hints"}，
      零副作用（连接器在 preflight 中收到 dry_run 标记）。
    """
```

- **同码保证**：preflight 复用 commit 的步骤函数（抽公共 `_commit_pipeline()`，commit 与 preflight 共享），杜绝"预演与真跑分叉"；
- 连接器感知：`SagaContext` 增 `dry_run: bool = True` 标记；连接器 apply 时若 `ctx.dry_run` 则只记录不真正外发（`OaWritebackConnector` 本就 dry_run，天然兼容；`ContractWritebackConnector` 为库内写回，preflight 中经 ROLLBACK 自然撤销）；
- 用途：human 审批人在 review 前调用（MCP `ont_preflight`？——**不新增 MCP 工具**，避免扩大攻击面；仅 REST/CLI/内部 API 暴露，评审确认）。

### 6.2 文件变更

| 文件 | 变更 |
|---|---|
| `ai_kb/ontology/proposal.py` | 抽 `_commit_pipeline()`；新增 `preflight()` |
| `connectors/base.py` | `SagaContext` 增 `dry_run` 字段（默认 False，commit 为 False、preflight 为 True） |
| `tests/test_ontology_preflight.py` | 新增：同码断言（preflight 与 commit 共享 pipeline）、零副作用（事务回滚后行数不变）、状态校验 |

---

## 7. 安全与不变式（全部测试锁定）

1. **validated ≠ committed** 不破；preflight 不改变 proposal 状态。
2. **MCP 无 execute/write/commit 工具**：动态枚举 + 静态 6 工具合计断言。
3. **结构/数据通道分离**：`submit_to_oa` 注册仅装配期（AssemblyGate）；运行期只有 propose/review。
4. **外部写冻结**：`dry_run=False` 抛 RuntimeError；preflight 亦不真发（ctx.dry_run=True）。
5. **补偿纪律**：OA 补偿恒抛 → 只记录工单 + `externally_committed`，绝不宣称回滚。
6. **幂等**：idempotency_key 唯一；重放返回既有结果。
7. **对账只读**：reconcile 不触发任何写。

---

## 8. 测试方案（要点）

- **P5.1**：`test_mcp_dynamic_tools.py` —— 枚举正确性（submit_contract → ont_propose_submit_contract；function → ont_compute_*）、命名冲突 fail-fast、无 execute 泄漏、静态工具兼容。
- **P5.2**：`test_oa_writeback_proposal.py` —— 全链路状态迁移（pending→validated→committed，decision_record 含 `externally_committed` 语义）；`dry_run=False` 抛 RuntimeError；补偿 → failed + 工单；幂等重放；**断言无真实 HTTP**（连接器注入 spy）。
- **P5.3**：`test_reconcile_oa_runner.py` 增推导用例 + 黄金 fixture 一致性。
- **P5.4**：`test_ontology_preflight.py` —— 同码、零副作用、状态不变。
- **E2E（真实 HTTP/MCP）**：启动 MCP server → `list_tools()` 含动态工具 → `call_tool("ont_propose_submit_to_oa")` 走全链路（dry-run）→ `ont_get_proposal` 五态可见。
- **回归**：既有 114 tests 全绿；只读路径零改动。

---

## 9. 开放问题（评审重点）

| # | 问题 | 初版倾向 | 需要拍板 |
|---|---|---|---|
| O1 | preflight 是否纳入本期 | 纳入（P5.4，可裁剪） | Rex 决定保留/裁剪；若裁剪，`SagaContext.dry_run` 字段仍加（P5.2 连接器兼容） |
| O2 | `submit_to_oa` 的 target_state 是否驱动本地状态机转移 | 不强制；OA 态以对账为准（保守） | 若业务要求本地同步显示"已提交OA"，需 L3 规则 function 定义转移条件 |
| O3 | 动态 MCP 工具是否也覆盖 function（compute_*） | 覆盖（与 propose_* 对称） | 若担心工具面膨胀，可仅 propose_* 动态化 |
| O4 | caller 身份 fail-open | 本期保持现状，P6 立项 | 是否 P6 一并做 run-scoped 身份（Sixb 模式） |
| O5 | preflight 的暴露面 | 仅 REST/CLI/内部 API，不加 MCP 工具 | 若 Rex 希望审批人经 agent 触发 preflight，再加 MCP（需评审） |

---

## 10. 实施计划（Phase 拆分，逐项可测）

| Phase | 内容 | 依赖 | 产出 |
|---|---|---|---|
| P5.1 | MCP 动态枚举 + 冲突检测 + 无 execute 断言 | 无 | `mcp/server.py` 扩展 + 测试 |
| P5.2 | L3 装配 + bridge.submit_to_oa + 连接器注入 | P5.1（工具可见性） | 全链路 dry-run 审计 + 测试 |
| P5.3 | reconcile 权威源统一 | 无（独立） | 推导函数 + runner 切换 + 测试 |
| P5.4 | preflight（同码 pipeline 抽取） | 无（独立，可裁剪） | `_commit_pipeline` + `preflight()` + 测试 |

每 Phase 独立向后兼容；P5.2 依赖 P5.1 仅因"工具自动暴露"是验收点，编码可并行。

---

## 11. 与既有文档/代码的衔接

- 文档：本详设通过后 → `IMPLEMENTATION-PLAN-operational-ontology-p5-v1.0.md` → 建设 → `VERIFICATION-operational-ontology-p5-v1.0.md`；L4 侧 `VERIFICATION-palantir-p4-reader-v1.0.md` 追加 P5 变更指针（不回改正文）。
- 代码：不修改 v1.0 已验收模块的既有方法语义（只新增方法/字段）；`oa_connector.py` 零改动。
- 审计链：propose/validate/review/commit/preflight 全部留痕（`kb_audit_log` + `ont_decision_record`）。
