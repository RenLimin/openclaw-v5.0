# VERIFICATION — P3 Proposal Gate + 决策对象（核心）v1.0

> L2 · ai-knowledge-base · 阶段 4 · INFRA-KB-002
> 日期：2026-10-31 · 执行：subagent
> 依据：DESIGN-DETAIL-operational-ontology-v1.0 §2.3/§3.3/§3.4/§3.6/§4
>       + IMPLEMENTATION-PLAN T3.1–T3.7

---

## 1. 改动 / 新增文件

### 1.1 修改（纯增量）

| 文件 | 改动 |
|---|---|
| `ai_kb/db.py` | 新增 `init_ontology_proposal_tables()`；migration **v10**（幂等名 `operational_ontology_proposal`）；建 `ont_proposal` / `ont_decision_record` 两表 + `idx_ont_proposal_status` / `idx_ont_decision_ts`。未改既有表与只读路径 |
| `ai_kb/ontology/identity.py` | 补齐 merge 的 TODO(P3)：经 `DecisionService.record` 实写 `ont_decision_record`（result='allowed'，完整 change_set/evidence），audit details 关联 decision_record_id；表未迁移时回退占位（P1 环境兼容） |
| `ai_kb/ontology/actions.py` | 新增 `validate_action_bindings()` + `_iter_precondition_refs()`：装配期校验 precondition 引用的 function 存在、deterministic=1、state_machine kind 匹配 |
| `ai_kb/ontology/__init__.py` | 导出 DecisionService / ProposalService / 连接器 |
| `mcp/server.py` | 注册 6 个本体工具（描述符含 category 三分类）；新增 `_get_ontology_services` / `_call_ontology_tool` / `ontology_tool_descriptors`；运行期 gate 关闭；close 清理 |
| `api/server.py` | 新增 3 个 REST 端点与请求模型、`_get_ontology_service`（懒装配，gate 关闭） |

### 1.2 新增

| 文件 | 内容 |
|---|---|
| `ai_kb/ontology/proposal.py` | **ProposalService**：propose_action / validate / review / commit / get / list_proposals |
| `ai_kb/ontology/decision.py` | **DecisionService**：record / record_no_commit / replay / stats / get |
| `ai_kb/guardrails/output_guard.py` | **OutputGuard**（动作输出，区别于 output.py 回答文本）：ABAC→参数 Schema→前置条件→状态机；内置最小 JSON Schema 校验器（无第三方依赖） |
| `ai_kb/ontology/connectors/base.py` | WritebackConnector 抽象 + SagaContext + NullConnector + CompensationUnavailable |
| `ai_kb/ontology/connectors/__init__.py` | 连接器导出 |
| `tests/ont_handlers.py` | 确定性 handler fixtures（rule/state_machine/risk/raise/false） |
| `tests/test_ontology_proposal.py` | 24 测试（含 5 黄金基准） |
| `tests/test_ontology_decision.py` | 10 测试 |
| `tests/test_output_guard.py` | 14 测试 |
| `tests/integration/test_ontology_gate_e2e.py` | 6 E2E（真实 HTTP uvicorn + 真实 MCP 分发） |

---

## 2. 新增表（DDL 严格按详设 §2.3）

- **ont_proposal**：五态状态机 `status DEFAULT 'pending'`
  （pending|validated|rejected|committed|failed）；`idempotency_key TEXT UNIQUE`；
  `target_snapshot NOT NULL`；`review_by/review_at/committed_at`；
  FK domain / action_type；`idx_ont_proposal_status`。
- **ont_decision_record**：FK proposal（可空，人工直录/归并用）/ domain；
  object_refs、change_set NOT NULL；result（allowed|rejected|compensated）；
  `idx_ont_decision_ts`。

## 3. 新增方法 / 工具 / 端点

- ProposalService：propose_action（只建 pending+快照，零写）、validate
  （OutputGuard 内执行，产出 violations）、review（human approve/reject）、
  commit（§3.3 事务时序，失败 ROLLBACK + Saga 补偿）、get / list_proposals。
- DecisionService：record / record_no_commit / replay(domain, object_type,
  canonical_key, since) / stats / get。
- MCP 工具（§4 三分类）：
  - query_：`ont_query_object` `ont_list_actions` `ont_get_proposal`
  - compute_：`ont_compute_risk`
  - propose_：`ont_propose_action` `ont_review_proposal`
- REST：`POST /ontology/proposals`（propose）、`GET /ontology/proposals`
  （查询）、`POST /ontology/proposals/review`（human review）。

**硬约束（已断言）**：工具集与端点中不存在任何 `execute_*`/`write_*`/
`commit_*`；commit 仅由 ProposalService 内部经 review/auto 策略触发。
既有 `kb_query` 等只读工具与端点保持不动。

---

## 4. 关键不变量验证

- **validated ≠ committed**：validate 仅写 validation_result 与状态，
  反复执行对象 metadata 无 applied_changes；commit 要求 status='validated'
  且审批满足（review_by 已写），事务内再校验防 TOCTOU。
- **幂等**：idempotency_key UNIQUE 兜底 + 提交前查重 + INSERT 异常并发
  兜底；重复提交返回既有结果（idempotent_replay=True），commit 后重复
  不产生第二条 decision_record。
- **拒绝留痕**：reject 写 rejected 决策记录 + audit；ABAC 越权 validate
  尝试同样写 audit；commit 失败写 result='compensated' 记录；补偿不可用
  时置 failed + 高风险人工对账 audit（不静默）。

---

## 5. 测试命令与实际结果

```bash
cd L2-infra/components/ai-knowledge-base
python3 -m pytest tests/ tests/integration/ -q
# => 100 passed in ~2.2s
```

| 文件 | 测试数 |
|---|---|
| test_ontology_proposal.py | 24 |
| test_ontology_decision.py | 10 |
| test_output_guard.py | 14 |
| integration/test_ontology_gate_e2e.py | 6 |
| test_ontology_identity.py（回归） | 12 |
| test_ontology_actions.py（回归） | 24 |
| test_db.py / test_parsers.py | 3 / 2 |
| integration/test_pipeline_e2e.py（回归） | 5 |
| **合计** | **100 全绿** |

权限/访问路径均经真实 HTTP（uvortex 后台线程 + requests）与真实 MCP
分发验证，未用 FastAPI TestClient 测权限；服务内部逻辑正常单测。

## 6. 黄金基准（5 组，全部通过）

| # | 场景 | 断言要点 | 结果 |
|---|---|---|---|
| G1 | 提交 | pending→validated→committed，决策记录全字段非空，evidence.review_by=rex，audit 关联 | ✅ |
| G2 | 驳回 | rejected 终态 + rejected 决策记录，对象无 applied_changes | ✅ |
| G3 | 越权 | ABAC 拒绝并留痕，对象未变更 | ✅ |
| G4 | 重复 | 同幂等键 1 提案 1 决策记录，返回既有结果 | ✅ |
| G5 | 补偿 | 连接器失败→ROLLBACK→failed→compensated 记录 | ✅ |

---

## 7. 遗留 TODO

1. **P4**：真实业务 WritebackConnector 与完整 Saga 多步补偿；
   CompensationUnavailable 当前只落人工对账 audit/决策记录，工单系统
   对接在 L3/L4。
2. change_set 的本地应用目前统一写 `ont_identity.metadata.applied_changes`
   （L2 不持业务表）；L3/L4 可注入/覆盖 `_apply_change_set` 实现具体字段落库。
3. JSON Schema 校验器为最小实现（覆盖本期关键字），非完整草案；如后续
   schema 复杂（$ref/oneOf 等）需扩展或评估引入依赖。
4. required_approval=auto 的自动审批策略阈值（金额/风险）由 L3 规则决定，
   L2 只提供 reviewer_kind='agent' 的 review 通道。
5. handler 进程内执行（惰性 import + 只读副作用约束），未做子进程沙箱（详设 O3）。

**红线遵守**：未碰 L3/L4 业务数据；未新增第三方依赖；未写凭据；
既有只读 API/MCP 工具零破坏。
