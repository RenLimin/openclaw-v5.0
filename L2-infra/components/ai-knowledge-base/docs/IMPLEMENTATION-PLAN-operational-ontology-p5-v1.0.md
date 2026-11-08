# L2 运营本体 P5 实施计划 v1.0（IMPLEMENTATION-PLAN）

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）增量 P5
> 组件编码：INFRA-KB-002 · 版本：v1.0 · 状态：**已批准**（Rex 2026-11-08 "通过，继续"；O1–O5 按初版倾向）
> 依据：DESIGN-DETAIL-operational-ontology-p5-v1.0（已通过）
> 作者：Jerry 🦞 · 日期：2026-11-08

---

## 0. 实现前提（代码事实核查，已确认）

| # | 事实 | 影响 |
|---|---|---|
| 1 | `ActionRegistry` 有 `list_actions(domain)`，**无 `list_functions`** | P5.1 需在 L2 新增 `list_functions`（与 `list_actions` 对称，供 MCP 工具发现） |
| 2 | `ProposalService.commit` 组装 `SagaStep(name, connector)` 时**不注入 payload**（`ctx.payloads[step_name]` 不会被自动填充） | P5.2 的 `OaWritebackConnector` 必须走构造注入 `target=` 兜底路径（`_resolve_target` 的 `self.target` 分支）；**不改 L2 commit 的 payload 组装**（避免 L2 理解业务参数，违反 L2 无业务） |
| 3 | `OaWritebackConnector._resolve_target` 两路径：`ctx.payloads[step_name]` → `self.target` → ValueError | 与 #2 结论一致：构造注入即可，`oa_connector.py` 零改动 |
| 4 | `SagaOrchestrator` 已完整：按序 apply、失败逆序补偿、`CompensationUnavailable` → `reconciliation_required` | P5.2 直接复用，无需扩展 |
| 5 | MCP `_call_ontology_tool` 的 `ont_propose_action` 用 `arguments["action"]` 指定动作名 | P5.1 动态工具 `ont_propose_<name>` 是"动作名固化"的便捷入口，背后复用同一 `propose_action`；静态通用工具保留，两者共存 |
| 6 | `scripts/reconcile_oa.py` 的 `local_state` 直接取 `row.get("status")`（L4 表）；`reconcile()` 纯函数接受注入 `local_states` | P5.3 改动点 = runner 构造 `local_states` 处改为决策链推导；`reconcile()` 与测试接口不动 |

---

## 1. Phase 拆分与工时

| Phase | 内容 | 涉及文件 | 依赖 | 预估 |
|---|---|---|---|---|
| P5.1 | MCP 动态工具枚举 + L2 `list_functions` + 冲突检测 + 无 execute 泄漏 | L2 `actions.py`、`mcp/server.py`、新 `tests/test_mcp_dynamic_tools.py` | 无 | 3h |
| P5.2 | `submit_to_oa` 装配 + bridge 编排 + 连接器注入 + 冻结边界 | L3 `register_ontology_functions.py`、L4 `bridge.py`、新 `tests/unit/test_oa_writeback_proposal.py` | 编码可并行；验收依赖 P5.1（工具可见性） | 4h |
| P5.3 | reconcile 权威源统一 | L4 `reconcile.py`、`scripts/reconcile_oa.py`、`tests/unit/test_reconcile_oa_runner.py` | 无 | 2h |
| P5.4 | preflight（`_commit_pipeline` 抽取 + `SagaContext.dry_run`） | L2 `proposal.py`、`connectors/base.py`、新 `tests/test_ontology_preflight.py` | 无 | 3h |

合计约 12h；P5.1/P5.3/P5.4 相互独立可并行，P5.2 编码独立（验收依赖 P5.1）。

---

## 2. P5.1 — MCP 动态工具枚举（L2）

### 任务清单

- [ ] T1.1 `ActionRegistry.list_functions(domain)`：与 `list_actions` 对称（返回 id/name/kind/io_schema/status），按 domain_id 过滤、status=active。
- [ ] T1.2 `mcp/server.py`：
  - `list_tools()`：静态 6 工具 + 动态枚举追加；枚举后**命名冲突检测**（全部工具名 set，重复 → `ValueError`）。
  - 动态枚举规则：
    - 每个 action_type（status=active）→ `ont_propose_<name>`，category=propose_，inputSchema = params_schema + 包装字段（caller_id/caller_kind/rationale/idempotency_key），description 由 object_type/writeback_target 自动生成；
    - 每个 function_def（deterministic=1, status=active）→ `ont_compute_<name>`，category=compute_，inputSchema = io_schema.properties。
  - `call_tool` 分发：`ont_propose_<name>` → `proposals.propose_action(instance_code, name, ...)`；`ont_compute_<name>` → `registry.get_function` + `load_handler` 执行（只产出建议）。
  - 枚举源：`_get_ontology_services()` 的 registry（运行期 gate 关闭，只读）。
- [ ] T1.3 `tests/test_mcp_dynamic_tools.py`：
  - 装配样例 domain（复用 L3 装配脚本或测试内注册）→ 断言 `ont_propose_submit_contract` / `ont_compute_<fn>` 出现、schema 正确；
  - 命名冲突：注册两个同名动作（不同 domain？工具名全局唯一 → 构造冲突场景）→ `list_tools()` 抛 `ValueError`；
  - **无 execute 泄漏**：枚举结果全量断言不存在 `execute_*`/`write_*`/`commit_*` 前缀（含静态 6 工具合计）；
  - 向后兼容：静态 6 工具描述符与旧版逐字段一致。

### 验收标准

1. 新装配任一 action（如测试内注册 `demo_action`）→ `list_tools()` 自动含 `ont_propose_demo_action`，**零代码改动**（除注册本身）。
2. 冲突检测生效（fail-fast）。
3. 全工具集合无 execute/write/commit 泄漏（测试锁定）。
4. 既有 `test_mcp*` 全绿。

---

## 3. P5.2 — `submit_to_oa` 接入 Proposal Gate（L3/L4）

### 任务清单

- [ ] T2.1 L3 `register_ontology_functions.py`：
  - `ACTION_TYPES` 增 `("submit_to_oa", OA_SCHEMA, None, "human", "oa_writeback")`；
  - `OA_SCHEMA`：`{requestid: string, action: string, comment: string?}`，required `[requestid, action]`；
  - `register_all` 中注册后调 `reg.register_writeback_steps(action_type_id, [{"seq":1, "connector_key":"oa_writeback", "payload_schema": OA_SCHEMA}])`；
  - 幂等：`get_action` 判空后注册 + 步骤（重复运行跳过）。
- [ ] T2.2 L4 `bridge.py`：
  - `_ACTIONS` 增 `"submit_to_oa": ("submit_to_oa", "human", "review")`；
  - 新增 `_new_service_oa(contract_id, oa_payload)`：`connectors={"oa_writeback": OaWritebackConnector(dry_run=True, target=oa_payload)}` 注入 ProposalService（**构造注入 target 兜底**，见 §0 #2）；
  - 新增 `_run_oa(...)` 与 `submit_to_oa(contract_id, operator, *, requestid, action="提交", comment="", rationale=None, idempotency_key=None)`：propose（params 含 requestid/action/comment）→ validate（caller_attrs）→ review("approve", operator, reviewer_kind, auto_commit=True) → sync_metadata（不强制本地状态转移，OA 态以对账为准）；
  - `submit_to_oa` 的 caller_kind：**强制 human**（外部写必须 human 发起；agent 经 MCP 只能 propose，review 由人做——L2 已强制 human 审，此处双保险）。
- [ ] T2.3 `tests/unit/test_oa_writeback_proposal.py`：
  - 全链路：`submit_to_oa` → proposal pending → validate ok → human review → commit → decision_record 含 `dry_run: True`、`connector: "oa_writeback"`、result=allowed；
  - 冻结边界：`OaWritebackConnector(dry_run=False)` → `RuntimeError`；`compensate` → `CompensationUnavailable` → proposal failed + 人工对账记录（`reconciliation_required`）；
  - 幂等：同 `idempotency_key` 重放返回既有 proposal；
  - **无真实 HTTP 断言**：注入 spy connector / monkeypatch `CubeClient`，断言 `apply` 未产生网络调用（dry_run 路径只 `ctx.mark_success`）。

### 验收标准

1. `submit_to_oa` 全链路 dry-run 审计闭环（decision_record + audit_log 留痕）。
2. 冻结边界全部锁定（dry_run=False 抛错、补偿恒抛、无 HTTP）。
3. 幂等重放正确。
4. MCP `ont_propose_submit_to_oa` 可见（依赖 P5.1，联调验收）。

---

## 4. P5.3 — reconcile 权威源统一（L4）

### 任务清单

- [ ] T3.1 `reconcile.py` 新增纯函数：

```python
def local_state_from_decisions(decisions, *, default=""):
    """决策记录链 → 本地预期态（与 STATE_ORDER 同尺）。

    取最近一条 committed 记录：
      approve_contract → "approved"; reject_contract → "draft";
      submit_contract → "review"; submit_to_oa → "review";
      无 committed 记录 → default（不伪造 in_sync）。
    """
```

- [ ] T3.2 `scripts/reconcile_oa.py`：`run_reconcile` 中，构造 `local_states` 前先对每个 plan 项按 `contract_no` 调 `bridge.decision_chain(contract_no)`（即 `DecisionService.replay`），经 `local_state_from_decisions` 得预期态；`local_state` 字段语义改为"决策链推导态"（保留原 L4 status 字段作对比参考，输出 `local_state` 与 `source="decision_chain"`）；`reconcile()` 调用与注入接口不变。
- [ ] T3.3 `tests/unit/test_reconcile_oa_runner.py` 增用例：
  - 无决策记录 → default；
  - reject 链 → draft；
  - submit→approve 链 → approved；
  - submit_to_oa 链 → review；
  - runner 集成：fake reader + fake decision_chain 注入 → 四态输出正确。

### 验收标准

1. 黄金 fixture（`oa_log_882663.json` 对应合同）决策链推导态与手工口径一致。
2. 既有 8 个 runner 用例全绿（注入接口未破坏）。
3. 输出含权威源标识（可审计：local_state 来自 decision_chain 而非裸 L4 表）。

---

## 5. P5.4 — preflight 同码试运行（L2）

### 任务清单

- [ ] T4.1 `connectors/base.py`：`SagaContext` 增 `dry_run: bool = False` 字段（commit=False，preflight=True）。
- [ ] T4.2 `proposal.py`：
  - 抽取 `_commit_pipeline(proposal_id, *, dry_run: bool) -> dict`：commit 现有步骤序列（状态/审批校验 → `_apply_change_set` → 写回连接器 → decision_record + audit → 状态更新）整体迁入，`dry_run` 时执行后 ROLLBACK 并返回预演结果（change_set / writeback dry results / risk hints），不落库；
  - `commit(proposal_id)` 改为调用 `_commit_pipeline(proposal_id, dry_run=False)`（行为不变，回归锁定）；
  - 新增 `preflight(proposal_id)`：校验 status=validated → `_commit_pipeline(dry_run=True)` → 返回 `{ok, change_set, writeback_dry_results, risk_hints}`；proposal 状态不变。
- [ ] T4.3 `tests/test_ontology_preflight.py`：
  - 同码断言：preflight 与 commit 共享 pipeline（mock 验证同一函数被调用 / 结果一致性）；
  - 零副作用：preflight 后 proposal 仍 validated、无 decision_record、无 audit 新增（行数不变）；
  - 状态校验：pending/rejected/committed 状态调 preflight → 明确报错。

### 验收标准

1. `preflight` 返回完整预演结果且零副作用（事务回滚验证）。
2. `commit` 行为与重构前完全一致（既有 114 tests 全绿 + 黄金决策 fixture 回归）。
3. `SagaContext.dry_run` 正确传递（preflight 时连接器收到 dry_run=True）。

---

## 6. E2E 与整体验收

- [ ] E2E-1 MCP 真实链路：启动 `KBMCPHandler` → `list_tools()` 含 `ont_propose_submit_to_oa` / `ont_compute_*` → `call_tool("ont_propose_submit_to_oa", {...})` 走全链路（dry-run）→ `ont_get_proposal` 五态可见 → `ont_review_proposal` human 审 → committed。
- [ ] E2E-2 对账真实链路：`scripts/reconcile_oa.py --contract-id <黄金合同>` 输出含 `source=decision_chain`，四态与手工口径一致。
- [ ] 回归：L2 全部 tests + L4 bangcle-contract 全部 tests 绿；只读路径零改动（`AIKBService`/`kb_*` 工具描述符不变）。
- [ ] 文档：`VERIFICATION-operational-ontology-p5-v1.0.md`（L2）+ L4 `VERIFICATION-palantir-p4-reader-v1.0.md` 追加 P5 变更指针（不回改正文）；`OPERATIONS` 增 preflight/MCP 动态工具说明；SKILL 增能力描述；资产清单由 pre-commit 自动重生成。

---

## 7. 风险与回退

| 风险 | 应对 |
|---|---|
| `_commit_pipeline` 抽取破坏 commit 行为 | 抽取前后黄金 fixture 回归 + 全量 tests；行为变更即回退，仅保留 `SagaContext.dry_run` 字段 |
| 动态工具枚举导致 MCP 工具面膨胀 | 只枚举 status=active；冲突 fail-fast；若需收敛（O3 反向），仅保留 propose_* 动态化（代码已按此结构组织） |
| `submit_to_oa` 误触发真实写 | 冻结边界三重锁定（dry_run 默认 + dry_run=False 抛错 + 测试 spy 断言无 HTTP）；P4.2 解锁前绝无真实请求 |
| reconcile 权威源切换引入偏差 | 保留注入接口 + 黄金 fixture 对比 + `source` 字段可审计；偏差时回退 runner 构造处一行 |

---

## 8. 交付顺序

1. P5.1 + P5.3 并行（无依赖）→ P5.2（验收依赖 P5.1）→ P5.4（独立）→ E2E + 回归 → 验收文档 → 推送。
2. 每 Phase 独立 commit；禁止 `git add -A`，只暂存任务相关文件。
