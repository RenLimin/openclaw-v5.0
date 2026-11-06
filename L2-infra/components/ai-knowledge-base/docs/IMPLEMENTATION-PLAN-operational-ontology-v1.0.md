# L2 运营本体（Operational Ontology）实施计划 v1.0

> L2 · ai-knowledge-base · 阶段 4（Gen3）· INFRA-KB-002
> 版本 v1.0 · 状态：**已验收**（Rex 2026-11-06 授权收口）· 2026-10-31 · Jerry 🦞
> 依据：DESIGN-DETAIL-operational-ontology-v1.0（已通过）
> 说明：本计划仅规划 L2 原语建设；L3/L4 落地在 L2 验收后单独立项。

---

## 1. 总览

| 维度 | 说明 |
|---|---|
| 建设顺序 | P1 身份层 → P2 动力学+注册 → P3 Proposal Gate → P4 连接器+补偿 |
| 交付形态 | `ai_kb/ontology/` 新模块 + `guardrails/output_guard.py` + db migration v8 + MCP/REST 扩展 |
| 兼容策略 | 每 Phase 独立可测、向后兼容；既有只读路径零改动 |
| 进入条件 | 详设已通过（✅）；本计划通过后开工 |
| 编码启动 | **等 Rex 明确指令**（避免与其主会话 BDMS 原型资源冲突） |

每个 Phase 设三道门：**自测通过 → VERIFICATION 文档 → Rex 验收**，过了才进下一 Phase。

---

## 2. Phase 拆分

### P1 权威身份层（Identity）

**目标**：建稳定主键 + 跨源解析 + 软归并，确立封闭世界边界（ADR-008）。

| 任务 | 产出 |
|---|---|
| T1.1 migration v8：`ont_identity` + `ont_identity_alias` 表/索引 | `db.py` DDL + 迁移登记 |
| T1.2 `ontology/identity.py` IdentityService：register/add_alias/resolve/merge/list | 模块 |
| T1.3 CWA 边界与运营/语料对象白名单判定 | domain 配置 + 判定逻辑 |
| T1.4 单元测试：注册/解析/归并/解归并/重复源键冲突 | tests |
| T1.5 product-kb 只读联调（不写业务）：核对自然键唯一性 | 联调记录 |

验收门：resolve 未命中=不存在；归并可逆；现有测试全绿。
**预估：1.5 人日**

### P2 动力学层 + 注册中心（Kinetic & Registry）

**目标**：action/function 原语与注册中心，规则即模型（ADR-007）。

| 任务 | 产出 |
|---|---|
| T2.1 migration：`ont_action_type` + `ont_function_def` | db DDL |
| T2.2 `ontology/actions.py` ActionRegistry：register/get/list | 模块 |
| T2.3 handler_ref 惰性加载（importlib，fail-fast）+ deterministic 校验 | 加载器 |
| T2.4 结构/数据通道分离：register_* 仅装配期可调 | 访问控制 |
| T2.5 单元测试：注册/查询/重复版本冲突/坏 handler 拒绝 | tests |

验收门：运行期无法注册结构；非 deterministic function 不可用于写路径。
**预估：1.5 人日**

### P3 Proposal Gate + 决策对象（核心）

**目标**：两阶段提交 + 输出侧接地 + 决策对象化（ADR-009）。

| 任务 | 产出 |
|---|---|
| T3.1 migration：`ont_proposal` + `ont_decision_record` | db DDL |
| T3.2 `ontology/proposal.py`：propose/validate/review/commit + 快照 + 幂等 | 模块 |
| T3.3 `ontology/decision.py`：record/replay/stats | 模块 |
| T3.4 `guardrails/output_guard.py`：ABAC→Schema→前置条件→状态机 | 校验链 |
| T3.5 commit 事务（validated≠committed）+ audit/decision 双写 | 事务编排 |
| T3.6 MCP 三分类（query_/compute_/propose_）+ REST `/ontology/proposals` | 接口扩展 |
| T3.7 单元 + 集成 + 5 组黄金基准（提交/驳回/越权/重复/补偿） | 测试 |

验收门：全状态机正确；无 execute_*/write_* 泄漏；幂等重复无副作用；拒绝路径留痕。
**预估：3 人日**

### P4 连接器抽象 + Saga 补偿

**目标**：写回源系统的统一契约与补偿（首个实例用 NullConnector 即可闭环）。

| 任务 | 产出 |
|---|---|
| T4.1 `ontology/connectors/base.py`：WritebackConnector + SagaContext | 抽象 |
| T4.2 NullConnector 默认实现 | 模块 |
| T4.3 commit 集成 Saga：失败 ROLLBACK + 反向补偿 | 编排 |
| T4.4 CompensationUnavailable → 人工对账工单记录降级 | 降级路径 |
| T4.5 集成测试：第二步失败 → 回滚 + 工单记录；E2E（真实 HTTP/MCP） | 测试 |

验收门：注入失败可补偿；不可补偿时产生工单而非静默；E2E 全绿。
**预估：1.5 人日**

---

## 3. 工时汇总

| Phase | 人日 | 累计 |
|---|---|---|
| P1 身份层 | 1.5 | 1.5 |
| P2 动力学+注册 | 1.5 | 3.0 |
| P3 Proposal Gate | 3.0 | 6.0 |
| P4 连接器+补偿 | 1.5 | 7.5 |
| **合计** | **7.5 人日** | — |

> 不含 L3 规则 Function 化与 L4 实例适配（后续单独立项）；缓冲建议 +20%（≈9 人日封顶）。

---

## 4. 依赖与里程碑

```
M0 实施计划通过 ──→ M1 P1 身份层 ──→ M2 P2 动力学 ──→ M3 P3 Proposal Gate ──→ M4 P4 连接器
                                          │
                          L2 验收完成后 ──→ L3 规则 Function 化 ──→ L4 bangcle-contract 实例验证
```

- 强依赖：P3 依赖 P1（身份）+ P2（动作/函数）；P4 依赖 P3。
- L3/L4 启动门：L2 四 Phase 全部 Rex 验收通过。

---

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| canonical_key 在 product-kb 实测不唯一 | 中 | P1 先只读核对；自然键失效回退代理键（O2） |
| 与 BDMS 并行资源竞争 | 中 | 编码等 Rex 指令；任务隔离 subagent 执行 |
| handler 注入安全 | 中 | 惰性加载 + 写副作用禁用；必要时子进程隔离（O3） |
| 多源写回不可补偿 | 中 | 人工对账工单降级，不静默（O4） |
| 范围蔓延成全企业本体 | 高 | 严守最小动作集；反模式红线，单域起步 |

---

## 6. 交付物清单

- 代码：`ai_kb/ontology/`（identity/actions/proposal/decision/connectors）、`guardrails/output_guard.py`
- 迁移：db schema v8（5 表 + 索引）
- 接口：MCP 三分类工具 + REST `/ontology/*`
- 测试：单元/集成/E2E + 5 组黄金基准
- 文档：VERIFICATION（每 Phase）+ OPERATIONS 更新

