# VERIFICATION-P5-operational-ontology-v1.0

> 验收对象：L2 运营本体 P5（MCP 工具自动生成 + submit_to_oa 接入 + 对账权威源统一 + preflight dry-run）
> 验收方式：全量自动化回归 + 真实装配走查
> 日期：2026-11-08
> 依据：`DESIGN-DETAIL-operational-ontology-p5-v1.0.md` / `IMPLEMENTATION-PLAN-operational-ontology-p5-v1.0.md`

## 0. 结论

**通过**。四个 Phase 全部实现、测试全绿、真实装配验证幂等且 writeback_steps 落库。合计 **440 用例** 回归通过（L2 122 / L3 115 / L4 单测 191 / L4 集成 12）。

## 1. 验收矩阵

| Phase | 验收标准（详设） | 实现方式 | 验证结果 |
|---|---|---|---|
| **P5.1** MCP 工具自动枚举 | active action → `ont_propose_<name>`；deterministic function → `ont_compute_<name>`；命名冲突 fail-fast；无 execute_* 泄漏 | `ActionRegistry.list_functions` + `mcp/server.py` `_dynamic_ontology_tools()` + 冲突检测 | `tests/test_mcp_dynamic_tools.py` 8 用例；全工具集无 `execute_*/write_*/commit_*` 泄漏测试锁定 |
| **P5.2** submit_to_oa 接入 | L3 装配注册 action + writeback_steps；L4 bridge `_new_service_oa` 注入 `oa_writeback` 连接器；human 级动作 | `register_ontology_functions.py` OA_SCHEMA + ACTION_TYPES + 幂等 writeback 注册；bridge `_run_oa`/`submit_to_oa` | 装配走查：首次注册 + 幂等跳过 + `(4, 1, 'oa_writeback')` 落库；`test_oa_writeback_proposal.py` 6 用例 |
| **P5.3** 对账权威源统一 | `local_state_from_decisions` 纯函数；runner 通过 `bridge.decision_chain` 推导；单合同降级 | `reconcile.py` ACTION_TO_STATE 映射 + `reconcile_oa.py` 决策链注入 + `no_decision_source` 降级 | `test_reconcile_oa_runner.py` 14 用例（8 既有适配 + 6 新增四态） |
| **P5.4** preflight dry-run | `SagaContext.dry_run`；preflight 复用 Saga 编排零副作用 | `proposal.py` `preflight()` + `SagaContext(dry_run=True)` | `test_ontology_preflight.py` 5 用例；spy 断言连接器感知 dry_run、无 HTTP、无决策记录、无 change_set |

## 2. 关键语义验证（红线）

| 红线 | 验证 |
|---|---|
| `oa_connector.py` **零改动** | ✅ 未触碰该文件；dry_run 冻结语义不变（`dry_run=False` 仍抛 RuntimeError） |
| `validated ≠ committed` | ✅ preflight 要求 validated；preflight 后保持 validated、不写决策记录 |
| 写回不可物理补偿 | ✅ `compensate` 恒抛 `CompensationUnavailable` → `reconciliation_required`（两步 Saga 测试锁定） |
| 幂等 | ✅ 装配二次跳过；`idempotency_key` 重放返回既有提案（`test_submit_to_oa_idempotent_replay`） |
| agent 永不代行 human 审 | ✅ L2 review 内置 `PermissionError`（`test_submit_to_oa_agent_review_permission_error`） |
| 对账只读 | ✅ `local_state_from_decisions` 纯函数；runner 决策链只读；单合同降级不中断整批 |
| 不新增第三方依赖 | ✅ 全部标准库/既有依赖 |
| 运行期 gate 关闭 | ✅ 装配期开启、运行期 `AssemblyGate(open_by_default=False)`；MCP 动态枚举只读 registry |

## 3. 回归清单

```bash
# L2（122）
cd L2-infra/components/ai-knowledge-base && python3 -m pytest tests/ -q
# L3（115）
cd L3-business/components/contract-management && python3 -m pytest tests/ -q
# L4 单测（191）
cd L4-proprietary/components/bangcle-contract && python3 -m pytest tests/unit/ -q
# L4 集成（12）
cd L4-proprietary/components/bangcle-contract && python3 -m pytest tests/integration/ -q
```

**全部通过。** 无回归破坏。

## 4. 真实装配走查

```bash
python3 L3-business/components/contract-management/scripts/register_ontology_functions.py <tmp>/ai_kb.db
# 首次：act registered:submit_to_oa + writeback_steps:submit_to_oa->oa_writeback
# 二次：act skipped(dup):submit_to_oa（幂等）
# bindings validated: 4 action types
# ont_writeback_step 落库：(4, 1, 'oa_writeback', 'submit_to_oa')
```

## 5. 文件清单

**实现（10 个文件，+657/-29）：**

| 层 | 文件 | 改动 |
|---|---|---|
| L2 | `ai_kb/ontology/actions.py` | +`list_functions`（MCP 发现） |
| L2 | `ai_kb/ontology/connectors/base.py` | `SagaContext.dry_run` 字段 |
| L2 | `ai_kb/ontology/proposal.py` | +`preflight()`（dry-run 编排） |
| L2 | `mcp/server.py` | +`_dynamic_ontology_tools()` + 冲突检测 + 分发 |
| L3 | `scripts/register_ontology_functions.py` | +OA_SCHEMA/`submit_to_oa`/writeback 注册 |
| L4 | `contract_review/ontology_bridge/bridge.py` | +`_new_service_oa`/`_run_oa`/`submit_to_oa` |
| L4 | `contract_review/ontology_bridge/reconcile.py` | +`local_state_from_decisions`/ACTION_TO_STATE |
| L4 | `scripts/reconcile_oa.py` | 决策链权威源 + `no_decision_source` 降级 |

**测试（3 个新文件 + 2 个适配，共 33 新用例）：**

| 文件 | 用例数 |
|---|---|
| `tests/test_mcp_dynamic_tools.py`（L2 新） | 8 |
| `tests/unit/test_oa_writeback_proposal.py`（L4 新） | 6 |
| `tests/unit/test_ontology_preflight.py`（L4 新） | 5 |
| `tests/unit/test_reconcile_oa_runner.py`（L4 适配+新增） | 14 |
| `tests/test_ontology_l2_integration.py`（L3 适配） | 2 断言更新 |

## 6. 遗留

- **P4.2 冻结语义不变**：`submit_to_oa` 连接器恒 dry-run；真实写端点契约（抓包 + Rex 二次授权 + 测试单据）未闭合前不触碰。
- OA 写回后本地状态机不强制转移（OA 态以 P4.4 对账为准）。
- 动态 MCP 工具目前仅供 MCP 客户端发现；AI agent 端到端消费验证留待 P6（agent-as-tool 组合）。
