# VERIFICATION — P4 多步 Saga 编排 + 连接器注册（operational-ontology v1.0）

> 日期：2026-11-01 · 对应 IMPLEMENTATION-PLAN P4（T4.1–T4.5）
> 依据：DESIGN-DETAIL-operational-ontology-v1.0 §3.5；前置 P1/P2/P3 全部完成
> 说明：P4 原 subagent 静默失败无产物，由主会话直接落地并验证。

## 1. 改动 / 新增文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `ai_kb/ontology/connectors/saga.py` | 🆕 | SagaOrchestrator / SagaStep / SagaReport / SagaExecutionError（多步顺序执行 + 失败逆序补偿） |
| `ai_kb/ontology/connectors/base.py` | 增量 | SagaContext 增加 `payloads` 字段（步骤输入与连接器输出分离） |
| `ai_kb/ontology/connectors/__init__.py` | 增量 | 导出 saga 组件 |
| `ai_kb/db.py` | 增量 | `init_ontology_saga_tables()`：`ont_writeback_step` 表 + migration **v11**（幂等名 `operational_ontology_saga`）；不动既有表 |
| `ai_kb/ontology/actions.py` | 增量 | `register_writeback_steps()`（装配期，seq 连续校验，先删后插）/ `list_writeback_steps()` |
| `ai_kb/ontology/proposal.py` | 增量 | commit 多步路由（SagaOrchestrator）+ `_writeback_steps()` 向后兼容降级 + evidence 带 saga_report + _mark_failed 系列支持 saga_report |
| `tests/ont_handlers.py` | 增量 | MemoryConnector（测试用内存连接器：fail_on_apply / not_compensable） |
| `tests/test_saga_orchestrator.py` | 🆕 | 9 用例（编排器） |
| `tests/test_ontology_saga_integration.py` | 🆕 | 5 用例（ProposalService 集成） |
| `docs/ADVICE-bdms-connector-integration-v1.0.md` | 🆕 | BDMS 对接建议（不改动 BDMS） |
| `docs/VERIFICATION-P4-saga-v1.0.md` | 🆕 | 本文档 |

红线遵守：未碰 L3/L4（BDMS/product-kb/bangcle-contract）；未修改既有只读 API/MCP；
无新第三方依赖；无凭据；单连接器路径行为不变（向后兼容）。

## 2. 机制

- **SagaOrchestrator.run()**：按声明顺序 apply 各步骤 → 任一步失败，
  对【已成功步骤】逆序 compensate；CompensationUnavailable 该步标记
  `compensation_unavailable` + `reconciliation_required`，**继续补偿更早成功步骤**
  （尽量多回滚）；返回结构化 SagaReport（不静默）。
- **commit 多步路由**：action 有 ont_writeback_step 步骤 → 走 SagaOrchestrator；
  无 → 原单连接器路径（saga_report=None）。表未迁移时优雅降级单步。
- **证据链**：committed 决策记录 evidence 含 `saga_report`（全部执行步）；
  失败补偿记录含 `reconciliation`/`compensated` 标记。

## 3. 测试命令与实际结果

```bash
cd L2-infra/components/ai-knowledge-base
python3 -m pytest tests/ tests/integration/ -q
```

实际结果：**114 passed, 0 failed**
- 新增：test_saga_orchestrator 9 + test_ontology_saga_integration 5 = 14
- 回归：既有 100 全绿（含 P3 黄金基准 G1–G5、P1 身份、P2 动力学）

覆盖项：全成功；第 2 步失败→第 1 步逆序补偿；第 3 步失败→1/2 逆序补偿；
不可补偿→标记对账 + 继续补偿更早步骤；单步失败；步骤顺序；payload 透传；
空步骤拒绝；ProposalService 集成：多步全成功 committed、中间失败 failed+compensated、
不可补偿 reconciliation=manual、单步向后兼容、幂等不重放。

## 4. 遗留 TODO

1. 真实业务连接器（OA/企微/BDMS）实现在 L3/L4 实例落地，L2 只提供能力与契约。
2. `ont_writeback_step.payload_schema` 目前仅存储，未做运行时 payload 校验
   （连接器自行处理；如需 L2 强校验可后补）。
3. JSON Schema 校验器仍为最小实现（复杂关键字 $ref/oneOf 待扩展，P3 遗留）。
4. handler 进程内执行未做子进程沙箱（详设 O3，风险由 L3/L4 实例评估）。
