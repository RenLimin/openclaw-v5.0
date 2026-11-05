# BDMS 接入运营本体写回层 — 对接建议（仅供建议，不改动 BDMS）

> Jerry 🦞 · 2026-11-01 · v1.0
> 定位：**建议文档**。L2 运营本体（Gen3）已提供写回能力；未来 BDMS 若作为写回源系统接入，
> 本文给出实现路径。**不修改 BDMS 任何资产/代码**，仅描述对接契约与示例。
> 前置：L2 `DESIGN-DETAIL-operational-ontology-v1.0.md`（§3.5 连接器 + P4 多步 Saga）

---

## 1. 对接总览

BDMS 作为**写回目标系统**接入 L2 Proposal Gate，需要实现一个 `WritebackConnector`，
并在装配期注册到 `ProposalService.connectors`。BDMS 侧**零改动**——由连接器封装调用。

```
Agent / 人
  → propose_action（L2，只建 pending）
  → validate（L2 OutputGuard：ABAC→Schema→前置条件→状态机）
  → review（human/auto）
  → commit（L2 事务）
      └─ WritebackConnector.apply(ctx)  →  BDMS API / 数据库（写回）
      失败 → ROLLBACK + connector.compensate(ctx)（逆序补偿）
```

## 2. 实现契约（接口）

```python
from ai_kb.ontology.connectors.base import WritebackConnector, SagaContext

class BdmsConnector(WritebackConnector):
    name = "bdms"  # 写回目标 key，与 ont_action_type.writeback_target / ont_writeback_step.connector_key 一致

    def __init__(self, client):      # client: BDMS 现有 API 客户端（复用，不重造）
        self.client = client

    def apply(self, ctx: SagaContext) -> None:
        """写回 BDMS。失败抛异常 → ProposalService ROLLBACK + 补偿。"""
        # ctx.payloads 里有编排器传入的步骤输入（如变更集）
        # 例：self.client.update_contract_status(contract_no=..., target_state=...)
        # 注意：这里必须是【真实写回】，不是仅标记成功
        self.client.apply_changes(ctx.payloads)
        ctx.mark_success(self.name, {"written_back": True})

    def compensate(self, ctx: SagaContext) -> None:
        """反向补偿。BDMS 不支持反向操作时抛 CompensationUnavailable
        → L2 自动标记人工对账工单（不静默）。"""
        # 例：若 BDMS 支持回滚/作废 → self.client.rollback(...)
        # 若 BDMS 无对应反向能力 → raise CompensationUnavailable("bdms cannot reverse X")
        raise CompensationUnavailable("bdms: reverse not supported for this op")
```

## 3. 注册与多步编排

**单目标**（BDMS 是唯一写回）：

```python
gate.open()
reg.register_action_type(
    "bangcle-contract", "submit_contract", "contract", params_schema,
    precondition={"fn": "validate_submit_state"},
    required_approval="human", writeback_target="bdms",
)
ps = ProposalService(db, reg, connectors={"bdms": BdmsConnector(client)})
```

**多目标**（如 BDMS + OA + 企微，按序写回、失败逆序补偿）——P4 Saga：

```python
aid = reg.register_action_type(..., writeback_target=None)  # 多步时 target 可空
reg.register_writeback_steps(aid, [
    {"seq": 1, "connector_key": "bdms"},    # 先落本地业务系统
    {"seq": 2, "connector_key": "oa"},      # 再推 OA 审批
    {"seq": 3, "connector_key": "wecom"},   # 最后通知企微
])
ps = ProposalService(db, reg, connectors={
    "bdms": BdmsConnector(client),
    "oa": OaConnector(oa_client),
    "wecom": WecomConnector(wecom_client),
})
```

**补偿语义**（L2 已内置，BDMS 连接器只需实现自己的 compensate）：
- 第 3 步失败 → 逆序补偿第 2、1 步；
- 某步不可补偿 → 该步标记 `reconciliation_required`，继续补偿更早步骤（尽量多回滚）；
- 最终全部落到 `ont_decision_record`（result=compensated + 人工对账标记），可回放。

## 4. 对接注意事项

1. **补偿能力先盘点**：BDMS 哪些操作可反向（作废/回滚/冲正），哪些不可——不可者提前
   声明抛 `CompensationUnavailable`，避免静默不一致。
2. **幂等靠 L2**：`idempotency_key` 由 L2 保证；BDMS 连接器内重复写回应自行幂等
   （用 proposal_id 作为业务幂等键）。
3. **权限在 L2**：ABAC 在 OutputGuard 层完成，BDMS 连接器**不自行做授权**，
   只执行已通过的 change_set。
4. **审计闭环**：写回结果会进 `ont_decision_record.evidence.saga_report`，
   BDMS 侧建议保留 `proposal_id` 关联字段，便于双向追溯。
5. **灰度**：首个实例建议先用 NullConnector 跑通全流程（G1–G5 黄金基准），
   再切 BDMS 真实连接器；切真前做补偿演练。

## 5. 明确边界

- 本文档**不修改 BDMS**；BDMS 资产零改动。
- 具体 BDMS API 调用细节（client 方法、鉴权、字段映射）由 BDMS 团队/原型设计确认后，
  在 L4 实例落地时实现 `BdmsConnector`。
- L2 侧接口已冻结（P4 完成）；BDMS 接入只需写一个连接器 + 装配期注册。
