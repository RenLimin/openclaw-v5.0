# VERIFICATION — Contract Ontology Bridge（L4 bangcle-contract × L2 运营本体）v1.0

> 日期：2026-11-05 · 对应 DESIGN-OUTLINE-contract-ontology-bridge-v1.0（待 Rex 评审）
> 执行：主会话真实落地，全部命令真实运行。
> 关联：L2 运营本体 P1–P4（`ae3a1b9`）· L3 contract-management P1/P2（`f654958` 等）

## 1. 交付文件

| 路径 | 说明 |
|---|---|
| `contract_review/ontology_bridge/__init__.py` | 包导出（registry/connector/bridge/assemble） |
| `contract_review/ontology_bridge/registry.py` | ContractRegistry：登记合同为 L2 运营对象（P1） |
| `contract_review/ontology_bridge/connector.py` | ContractWritebackConnector / NotifyConnector：真写回 + 补偿（P2） |
| `contract_review/ontology_bridge/bridge.py` | ContractOntologyBridge：propose→validate→review→commit 编排（P2） |
| `contract_review/ontology_bridge/assemble.py` | 装配逻辑单一来源（L3 脚本 importlib 绝对路径加载，幂等） |
| `contract_review/ontology_bridge/_assembly.py` | L3 装配脚本绝对路径加载（规避 L4/L3 `scripts/` 包名冲突） |
| `scripts/register_contract_ontology.py` | CLI 装配入口（薄封装 assemble） |
| `repository/db.py` | + `get_contract_row_by_no`（登记幂等查询） |
| `cli/contractctl.py` | + `ontology` 子命令（register/submit/approve/reject/status/proposals） |
| `tests/integration/test_ontology_bridge.py` | 7 组黄金基准 pytest |

## 2. 关键设计决策落地

| 决策（OUTLINE D1–D4） | 实现 |
|---|---|
| D1 L4 contract 表为 source of truth | L2 `ont_identity` 只做运营索引/快照；metadata 镜像 status/amount/title |
| D2 真写回连接器 | `ContractWritebackConnector`：commit 事务内 L3 状态机计算 next_status → 写回 L4 表；compensate 用 before 快照还原 |
| D3 review 与运营对象解耦 | 本期不自动建合同；登记走 `ontology register` 显式命令 |
| D4 canonical_key 规范化 | NFKC + 去空白标点 + 小写；`HT-2026-001` → `ht-2026-001`，保留编号语义 |

## 3. 黄金基准 7 组（pytest 固化）

命令：
```bash
cd L4-proprietary/components/bangcle-contract
python3 -m pytest tests/integration/test_ontology_bridge.py -q
```

结果：**7 passed in 0.41s**

| # | 基准 | 断言要点 | 结果 |
|---|---|---|---|
| 1 | 提交闭环 | submit → committed → L4 status=review1 + L2 metadata_status=review1 + 决策记录 result=allowed/connector=contract_writeback | ✅ |
| 2 | 越权拒绝 | agent 审 human 级 approve → PermissionError("human approval") | ✅ |
| 3 | 非法转移 | 未 submit 直接 approve → ok=False + illegal_transition 违规痕，提案留 pending，L4 状态不被污染 | ✅ |
| 4 | 幂等重放 | 同 idempotency_key 重复 submit → 返回既有提案（idempotent_replay=True），决策链仅 1 条 submit | ✅ |
| 5 | Saga 补偿回滚 | 多步写回第二步 notify 注入失败 → executed=[contract_writeback,notify] / failed=notify / compensated=[contract_writeback]，L4 回 draft，审计含 ontology_submit+ontology_compensate，决策 result=compensated，proposal=failed | ✅ |
| 6 | CWA 未登记拒绝 | 未登记合同 submit → ValueError("not registered as operational object") | ✅ |
| 7 | CLI 冒烟 | contractctl ontology register/submit/status 真实子进程可跑 | ✅ |

## 4. 手工走查（真实命令与输出）

### 4.1 装配脚本（临时目录）

```bash
python3 scripts/register_contract_ontology.py \
  --db /tmp/ont-smoke.XXX/contract.db \
  --ai-kb /tmp/ont-smoke.XXX/ai_kb.db \
  --register "HT-2026-001:100000,HT-2026-002:3000000"
```

输出（节选）：
```
domain_id   : 1
  fn  registered:validate_submit_state ... (9 个 deterministic function)
  act registered:submit_contract / approve_contract / reject_contract
bindings validated: 3 action types
  reg HT-2026-001 -> identity 1 (canonical=ht-2026-001, created=True)
  reg HT-2026-002 -> identity 2 (canonical=ht-2026-002, created=True)
```

### 4.2 完整生命周期（bridge 编排）

```
submit  HT-2026-001 (10万, 2级)   → review1  (auto 审, committed)
approve ×2                        → review2 → approved (human 审)
status  双视角: contract_status=approved metadata_status=approved decisions=3
```

### 4.3 越权 + 非法转移

```
agent 审 human approve → PermissionError ✅ (this action requires human approval; agent may not review)
未 submit 直接 approve  → ok=False + illegal_transition (L3 状态机拒绝)
未登记对象 submit       → ValueError (CWA 封闭世界)
```

### 4.4 Saga 补偿回滚

```
executed:   ['contract_writeback', 'notify']
failed:     notify
compensated:['contract_writeback']
L4 status after saga: draft (补偿回滚)
audit trail: ['ontology_submit', 'ontology_compensate']
decision stats: {'total': 1, 'by_result': {'compensated': 1}}
proposal status: failed
```

## 5. 回归结果

| 套件 | 结果 |
|---|---|
| L4 bangcle-contract 全量 | **194 passed, 3 skipped**（新增 7 黄金基准，零破坏） |
| L3 contract-management | **115 passed** |
| 既有集成 test_bridge_e2e | 包含在全量内（300 万四级/80 万三级生命周期不变） |

## 6. 与 DESIGN-OUTLINE §7 验收标准对照

| 验收标准 | 状态 |
|---|---|
| 提交闭环（双写 + evidence 完整） | ✅ 黄金基准 #1 |
| 越权拒绝（PermissionError + 审计留痕） | ✅ 黄金基准 #2 |
| 非法转移（L3 状态机拒绝 + 违规痕） | ✅ 黄金基准 #3 |
| 幂等重放（无二次副作用） | ✅ 黄金基准 #4 |
| 补偿回滚（ROLBACK + failed + 人工对账记录） | ✅ 黄金基准 #5（NotifyConnector 可逆故无对账单；不可逆场景由 CompensationUnavailable 路径覆盖） |

## 7. 未做 / 边界

- ❌ 未改 L2 ai-knowledge-base 源码/测试（只调用）
- ❌ 未改 L3 contract-management 源码（复用装配脚本与 handler）
- ❌ 未做泛微 OA 真写回（P2 连接器立项；本立项本地表写回演示 Saga，接口按 WritebackConnector 契约预留）
- ⚠️ `Local embedding not available: No module named 'llama_cpp'` 为 ai_kb 导入期提示噪音（stdout），不影响功能；CLI 测试已过滤

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-05 | v1.0 | 初版：P1–P3 全量验证（装配/编排/写回/Saga/CLI/黄金基准） |
