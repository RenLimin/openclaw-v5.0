# VERIFICATION — Contract Ontology Bridge v1.0（P1/P2）

> 前置：OUTLINE `ac9faff`、DETAIL `f6ff800`、PLAN `d5c99fc` 均获 Rex 评审通过。
> 实现：P1 `f0a7b57`、P2 `33a5a2a`（均已在远端 `main`）。
> 验收人：Jerry 🦞（独立验收，不依赖子任务自报）· 2026-11-04 · Python 3.14.7 / pytest 9.0.3

## 1. 交付验收 7 步法

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 清空上下文独立审计 | ✅ 不读子任务总结，亲读 `mapper.py`/`cube_provider.py`/`contract_service.py`/`db.py` 增量 + 黄金夹具，对照 DETAIL §2.1-§2.4 逐项核对 |
| 2 | 契约对齐 | ✅ 6+4 文件、表结构、索引、方法签名均与 DETAIL §5 一致；零偏差（见 §4 偏差说明） |
| 3 | 全入口覆盖 | ✅ P1 新增 26 + P2 新增 17（12 单元+5 集成）真实执行；组件全量 152 passed；L3 抽查 73 passed |
| 4 | 黄金基准 | ✅ `card_golden.json`（'人民币 12.5 万元'→125000.0、status draft）集成测试逐字段比对通过 |
| 5 | 幂等性 | ✅ 迁移幂等 ×3、同输入 ×3 一致，有测试锁定 |
| 6 | 调用点扫描 | ✅ 新方法调用点均在组件内；L3 `ApprovalStateMachine` 被 `contract_service` 唯一接入，无重复规则实现 |
| 7 | 回归锁定 | ✅ 新增 43 测试（26+17）；既有 135 单测零回退（147/152 含新增） |

## 2. 测试计数（真实执行）

| 范围 | 结果 |
|---|---|
| P1 新增（test_mapper + test_cube_provider） | **26 passed / 0 failed** |
| P2 新增（test_contract_service 12 + test_bridge_e2e 5） | **17 passed / 0 failed** |
| bangcle-contract unit（既有+新增） | **147 passed** |
| bangcle-contract unit + integration 全量 | **152 passed / 0 failed** |
| L3 contract-management 抽查（零改动） | **73 passed / 0 failed** |

## 3. 关键能力验证点

- 字段映射：别名优先级、缺失字段不抛、金额多形态（12.5万 / ¥1,000,000 / 缺失→0.0）
- OaProvider 适配：`CubeOaProvider` 继承 ABC、`get_contract_attachment` 委托 CubeClient、`query_process` 恒 unknown、写方法 NotImplementedError
- 状态机接线：4 级全生命周期（create→submit→approve×4→sign→archive）+ 3 级路径 + reject 后重提
- 原子性：非法动作抛 `ContractStateError` 且 **count 不变零落库**（draft 上 approve、approved 上 archive、未知 action、合同不存在）
- 持久化：迁移幂等 ×3、`uq_contracts_oa_billid` 部分唯一索引、append-only 接口级断言（dir() 无 update/delete 审计）
- 隔离：全部测试用 tmp_path 临时 DB，不碰真实 `data/bangcle_contract.db`；离线假对象，不连网

## 4. 偏差说明（实现期决策，已在报告中声明的唯一一项）

**合同审计存储位置**：既有 `audit_logs.review_id` 外键指向 reviews(id) 且表结构不可改（红线），
P2 合同审计行 `review_id=NULL`，`contract_id`/`from_status`/`to_status` 放入 detail JSON；
`get_contract_with_history` 按 `review_id IS NULL` + detail.contract_id 过滤。
→ 未动既有表结构与 append-only 性质；不影响 DETAIL 契约（audit_logs 仍只 INSERT）。

## 5. 提交链（全部已推送 `main`）

```
ac9faff OUTLINE v1.0（重做，基于真实代码）
f6ff800 DESIGN-DETAIL v1.0（P1/P2）
d5c99fc IMPLEMENTATION-PLAN v1.0
f0a7b57 P1 只读桥（mapper + CubeOaProvider + 26 测试）
33a5a2a P2 持久化+状态机接线（db V2 + contract_service + 17 测试）
```

## 6. 状态

**✅ P1/P2 验收通过并交付。** P3（审批节点映射 + push_result）/P4（回调/真写回）保持**冻结**，待泛微 workflow 审批流数据源确认 + Rex 单独拍板。
