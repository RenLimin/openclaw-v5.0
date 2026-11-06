# L2 运营本体（Operational Ontology）详细设计 v1.0

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）
> 组件编码：INFRA-KB-002 · 版本：v1.0 · 状态：**已验收**（Rex 2026-11-06 授权收口）
> 日期：2026-10-31 · 验收：2026-11-06 · 作者：Jerry 🦞
> 依据：DESIGN-OUTLINE-operational-ontology-v1.0（已通过）+ ADR-007/008/009
> 本文档定义：接口契约、数据模型 DDL、模块/类设计、安全、测试方案。

---

## 1. 范围与约定

- 本期新增 **4 模块 + 5 表 + MCP 扩展**，全部向后兼容（migration 增量），不修改既有只读路径。
- 遵循既有风格：Python 3.11+、SQLite 先行、`CREATE TABLE IF NOT EXISTS` + `kb_migration` 版本号、PascalCase 类、snake_case 方法。
- 业务规则不落 L2：function handler 由上层注入，L2 只持有注册表与调用契约。

---

## 2. 数据模型（DDL 细化）

> 每个表 `CREATE TABLE IF NOT EXISTS`，schema 版本通过 `apply_migration(version, name)` 登记。
> 本期 migration 版本号：**v8**（在现有 v7 之后，含 5 张新表 + 索引）。

### 2.1 ont_identity（权威身份，对应 OUTLINE §5.1）

```sql
CREATE TABLE IF NOT EXISTS ont_identity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id       INTEGER NOT NULL REFERENCES domain(id),
    object_type     TEXT NOT NULL,             -- 运营对象类型（如 contract/product）
    canonical_key   TEXT NOT NULL,             -- 稳定权威主键，一经 commit 不可变
    system_of_record TEXT NOT NULL,            -- 源系统标识（如 oa/erp/product_kb）
    display_name    TEXT,
    status          TEXT DEFAULT 'active',     -- active | merged | retired
    merged_into     INTEGER REFERENCES ont_identity(id),  -- 软归并指针，不物理删除
    metadata        TEXT,                      -- JSON：SoR 字段映射、抽取规则等
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    UNIQUE (domain_id, object_type, canonical_key)
);
CREATE INDEX IF NOT EXISTS idx_ont_identity_sor ON ont_identity(system_of_record);

CREATE TABLE IF NOT EXISTS ont_identity_alias (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id   INTEGER NOT NULL REFERENCES ont_identity(id),
    source_system TEXT NOT NULL,
    source_key    TEXT NOT NULL,
    confidence    REAL,                        -- 解析置信度
    created_at    DATETIME NOT NULL,
    UNIQUE (source_system, source_key)         -- 同一源键唯一
);
```

- **canonical_key 策略（评审开放问题 O2 的初版决策）**：优先**自然业务键**（合同号、SKU 码），无自然键才用代理键；生成规则在 domain 配置（`metadata`）声明，由 L3/L4 装配期注入。
- 归并：`merged_into` 指向吸收方；被归并方 `status='merged'`，alias 全部转移；可审计、可回滚（解归并仅改指针）。

### 2.2 ont_action_type / ont_function_def（动力学层）

```sql
CREATE TABLE IF NOT EXISTS ont_action_type (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id       INTEGER NOT NULL REFERENCES domain(id),
    name            TEXT NOT NULL,             -- 如 submit_contract
    object_type     TEXT NOT NULL,             -- 作用于哪类对象
    params_schema   TEXT NOT NULL,             -- JSON Schema（参数校验）
    precondition    TEXT,                      -- JSON：前置条件（引用 function）
    required_approval TEXT NOT NULL DEFAULT 'none',  -- none | auto | human
    writeback_target TEXT,                     -- 写回源系统标识（连接器 key）
    version         INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'active',
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    UNIQUE (domain_id, name, version)
);

CREATE TABLE IF NOT EXISTS ont_function_def (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id    INTEGER NOT NULL REFERENCES domain(id),
    name         TEXT NOT NULL,                -- 如 validate_submit_state
    kind         TEXT NOT NULL,                -- rule | state_machine | risk | compute
    handler_ref  TEXT NOT NULL,                -- 上层注入的可调用标识（L3 提供实现）
    io_schema    TEXT,                         -- JSON：入参/出参 schema
    deterministic INTEGER DEFAULT 1,           -- 可被写流程调用的必须 =1
    version      INTEGER DEFAULT 1,
    status       TEXT DEFAULT 'active',
    created_at   DATETIME NOT NULL,
    updated_at   DATETIME NOT NULL,
    UNIQUE (domain_id, name, version)
);
```

### 2.3 ont_proposal / ont_decision_record（写治理 + 决策对象）

```sql
CREATE TABLE IF NOT EXISTS ont_proposal (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id        INTEGER NOT NULL REFERENCES domain(id),
    action_type_id   INTEGER NOT NULL REFERENCES ont_action_type(id),
    caller_id        TEXT NOT NULL,            -- 发起人/Agent 标识
    caller_kind      TEXT NOT NULL,            -- human | agent
    params           TEXT NOT NULL,            -- JSON：动作参数
    target_snapshot  TEXT NOT NULL,            -- JSON：目标对象变更前快照
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending|validated|rejected|committed|failed
    validation_result TEXT,                    -- JSON：校验明细（命中规则/违规）
    review_by        TEXT,
    review_at        DATETIME,
    idempotency_key  TEXT UNIQUE,              -- 幂等键（重试/重复提交防护）
    created_at       DATETIME NOT NULL,
    committed_at     DATETIME
);
CREATE INDEX IF NOT EXISTS idx_ont_proposal_status ON ont_proposal(status);

CREATE TABLE IF NOT EXISTS ont_decision_record (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id  INTEGER REFERENCES ont_proposal(id),   -- 可空：人工直录决策
    domain_id    INTEGER NOT NULL REFERENCES domain(id),
    action_type  TEXT NOT NULL,
    object_refs  TEXT NOT NULL,               -- JSON：受影响对象 [canonical_key...]
    actor_id     TEXT NOT NULL,
    actor_kind   TEXT NOT NULL,               -- human | agent
    rationale    TEXT,                        -- 决策理由（Agent 填的说明）
    change_set   TEXT NOT NULL,               -- JSON：实际变更（before/after）
    evidence     TEXT,                        -- JSON：依据（命中规则/来源/模型输出）
    result       TEXT NOT NULL,               -- allowed | rejected | compensated
    ts           DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ont_decision_ts ON ont_decision_record(ts);
```

- 与 `kb_audit_log` 关系：audit_log 记"发生过的操作"（运维/安全视角，已有）；decision_record 记"做了什么决策及其依据"（业务/学习视角）。两者经 `proposal_id` 关联（在 audit `details` 中写 proposal_id）。

---

## 3. 模块/类设计（新增 4 模块）

```
ai_kb/ontology/
├── identity.py      # IdentityService
├── actions.py       # ActionRegistry
├── proposal.py      # ProposalService
├── decision.py      # DecisionService
├── connectors/
│   └── base.py      # WritebackConnector（抽象）+ SagaContext
ai_kb/guardrails/output_guard.py   # OutputGuard（输出侧符号校验）
```

### 3.1 IdentityService

| 方法 | 签名 | 说明 |
|---|---|---|
| `register_identity(domain, object_type, canonical_key, sor, display_name=None)` | → int | 建权威身份，主键唯一冲突即报错 |
| `add_alias(identity_id, source_system, source_key, confidence)` | → int | 绑定跨源标识 |
| `resolve(source_system, source_key)` | → Optional[int] | 按 (源,键) 解析到权威 identity |
| `merge(from_id, into_id, actor)` | → decision_record | 软归并，alias 转移，留决策记录 |
| `list_identities(domain, object_type, status=None)` | → List[dict] | 管理/联调用 |

**CWA 边界实现**：`resolve()` 命中即"存在"；未命中即"不存在"（封闭世界），调用方据此可拒绝操作。运营对象与语料实体分离判定：`entity.status` + 新 `ont_identity.object_type` 白名单（domain 配置声明哪些 type 进封闭世界）。

### 3.2 ActionRegistry

| 方法 | 签名 | 说明 |
|---|---|---|
| `register_action_type(domain, name, object_type, params_schema, precondition, required_approval, writeback_target)` | → int | 装配期调用；Agent 运行期不可注册（结构/数据通道分离） |
| `register_function(domain, name, kind, handler_ref, io_schema, deterministic=True)` | → int | 同上 |
| `get_action(domain, name)` / `get_function(domain, name)` | → dict | 读注册表 |
| `list_actions(domain)` | → List[dict] | MCP 工具发现用 |

- `handler_ref` 解析：模块路径 + 可调用名（如 `"contract_management.validators:validate_submit"`）；L2 用 `importlib` 惰性加载，加载失败即注册失败（fail-fast）。
- **安全边界**：handler 只在 `validate()` 时以**调用者权限**执行；handler 本身视为可信（来自 L3/L4 装配），但其副作用受限——写流程只允许 handler 返回校验结果，不允许 handler 直接写库（写必须走 ProposalService）。

### 3.3 ProposalService（核心）

| 方法 | 签名 | 说明 |
|---|---|---|
| `propose_action(domain, action_name, object_refs, params, *, caller_id, caller_kind, rationale, idempotency_key)` | → proposal_id | 只建 pending + 快照，零写 |
| `validate(proposal_id)` | → {ok, violations[]} | 调绑定 deterministic function（OutputGuard 内执行） |
| `review(proposal_id, decision, reviewer)` | → proposal_id | human 审：approve/reject；auto 审由策略决定 |
| `commit(proposal_id)` | → decision_record | 单事务：应用变更集 → 写回连接器 → 生成决策记录；失败走 Saga 补偿 |
| `get(proposal_id)` | → dict | 状态查询 |

**commit 事务时序（关键不变量：validated ≠ committed）**：
```
BEGIN
  1) 校验 idempotency_key（重复 → 返回既有结果，不重放）
  2) 校验 proposal.status == 'validated' 且 required_approval 已满足
  3) 对目标对象执行 change_set（apply edits）
  4) 调用 writeback_target 连接器（写回源系统；失败抛异常）
  5) 写 ont_decision_record + 更新 kb_audit_log（含 proposal_id）
COMMIT  -- 任一步失败 → ROLLBACK + Saga 补偿（见 §3.5）
```

**幂等**：`idempotency_key` 唯一约束兜底；网络重试返回已提交的 decision_record，不重复副作用。

### 3.4 DecisionService

| 方法 | 签名 | 说明 |
|---|---|---|
| `record(...)` | → int | 写决策对象（commit 内调用 / 人工直录） |
| `replay(domain, object_type, canonical_key, since=None)` | → List[dict] | 按对象回放决策链 |
| `stats(domain, action_type=None, result=None, since=None)` | → dict | 学习语料统计（后续风险规则迭代/微调用） |

### 3.5 WritebackConnector 抽象 + Saga 补偿

```python
class WritebackConnector(ABC):
    name: str
    @abstractmethod
    def apply(self, ctx: SagaContext) -> None: ...   # 写回源系统
    @abstractmethod
    def compensate(self, ctx: SagaContext) -> None: ... # 反向补偿（可空实现）

class SagaContext:
    steps: list          # 已成功步骤
    results: dict        # 各步骤输出
    def add_step(self, name): ...
    def mark_success(self, name, result): ...
    def mark_failed(self, name, error): ...
```

- 默认实现 `NullConnector`（无源系统写回，本地库内事务即可）——首个实例可用。
- 补偿降级：连接器不支持反向操作时（如 OA 审批已发起无法撤回），`compensate()` 抛出 `CompensationUnavailable`，ProposalService 标记 `status='failed'` + 生成**人工对账工单记录**（决策对象里留 `result='compensated'` + 说明），不静默。

### 3.6 OutputGuard（输出侧接地）

- 复用现有 `guardrails/` 目录风格，新增 `output_guard.py`：
  - `validate_proposal(proposal, caller_attrs)` → 依次执行：ABAC 权限（复用 `PermissionChecker`）→ 参数 Schema → 前置条件（调用 deterministic function）→ 状态机约束（若 action 绑定 state_machine 类 function）。
  - 与现有 `output.py` 的关系：`output.py` 管**回答文本**（反幻觉/脱敏）；`output_guard.py` 管**动作输出**（写治理）。两条线并行，互不干扰。

---

## 4. 接口/API 扩展（MCP 三分类）

`api.py` 新增 `OntologyAPI`（新类，与 `AIKB` 并列；`AIKB` 保持只读不动）：

| MCP 工具 | 分类 | 对应方法 | 说明 |
|---|---|---|---|
| `ont_query_object` | query_ | IdentityService.resolve + 对象读 | 读时按 ABAC 过滤 |
| `ont_compute_risk` | compute_ | ActionRegistry.get_function → 执行 | 只产出建议，零写 |
| `ont_propose_action` | propose_ | ProposalService.propose_action | 只建 pending |
| `ont_list_actions` | query_ | ActionRegistry.list_actions | 工具发现 |
| `ont_get_proposal` | query_ | ProposalService.get | 状态查询 |
| `ont_review_proposal` | propose_(human) | ProposalService.review | 仅 human 角色可调 |

**硬约束**：MCP 工具集中**不存在** `execute_*`/`write_*`/`commit_*` 的直接工具。commit 只由 ProposalService 内部（经 human review 或 auto 策略）触发，Agent 不可直接调用。
REST 侧同理：新增 `/ontology/proposals`（POST propose / GET 查询 / POST review），**不暴露**直接写端点。

---

## 5. 安全与权限设计

1. **ABAC 集成**：proposal 的 validate 阶段复用 `PermissionChecker.can_access_doc` 同款属性判定；运营对象权限存 `ont_identity.metadata.permissions`（JSON），读/写分别过滤。
2. **结构与数据通道分离**：`register_*` 仅装配期（CLI/配置）可调；运行期（MCP/REST）只有 query/compute/propose。对标 Palantir MCP（只能改结构、需提审）与 OMCP（只能读写数据）的硬分割。
3. **幂等与重放防护**：`idempotency_key` 唯一；commit 事务内再校验状态，防 TOCTOU。
4. **审计闭环**：所有 validate/review/commit/merge 都写 `kb_audit_log` + `ont_decision_record`；拒绝路径同样留痕（含被拒原因，供 Agent 学习）。
5. **无 LLM 直写**：任何路径都不存在"LLM 输出 → 直接 SQL/API"；LLM 只能产生 proposal 参数与 rationale。

---

## 6. 测试方案（要点，VERIFICATION 文档再细化）

- **单元**：IdentityService（注册/解析/归并/回滚）、ActionRegistry（注册/查/重复注册冲突）、ProposalService（pending→validated→rejected/committed 全状态机、幂等、快照）、DecisionService（回放）、OutputGuard（ABAC/参数/前置条件拒绝）。
- **集成**：Proposal 全链路（propose→validate→review→commit→写回 NullConnector→决策记录）；Saga 补偿（模拟第二步失败 → 回滚 + 工单记录）。
- **黄金基准**：人工构造 5 组典型决策（提交/驳回/越权/重复/补偿），断言决策记录字段完整性与状态迁移，作为回归锁定。
- **E2E（真实 HTTP/MCP）**：走 MCP 工具描述符注册，验证三分类存在、无 execute_* 泄漏；验证 human review 流程经 REST 可完成。
- **兼容性**：既有 tests（test_db/test_parsers/integration）全部通过，只读路径零改动。

---

## 7. 开放问题与风险（评审重点）

| # | 问题 | 初版倾向 | 需要拍板 |
|---|---|---|---|
| O1 | 运营对象边界判据 | domain 配置白名单 object_type 进封闭世界 | 首个实例（contract/product）名单由 L3/L4 确认 |
| O2 | canonical_key 生成 | 自然业务键优先（合同号/SKU） | 需结合 product-kb 实测校验唯一性 |
| O3 | function handler 沙箱 | L2 惰性加载 + 只读副作用约束，不做进程沙箱 | 是否需进一步隔离（如子进程）由风险等级定 |
| O4 | OA 不支持反向操作的补偿降级 | CompensationUnavailable → 人工对账工单记录 | 首个实例验证时确认 |
| O5 | required_approval 分级 | none/auto/human 三级，action_type 声明 | 分级阈值（金额/风险）由 L3 规则定 |

---

## 8. 与既有文档/代码的衔接

- 新增表走 `apply_migration`（v8）；`db.py` 只加 DDL + 迁移登记，不改既有表。
- `ai_kb/api.py` 新增 `OntologyAPI` 类；`AIKB` 类保持只读，不破坏既有 MCP 工具（`kb_query` 等）。
- 新模块目录 `ai_kb/ontology/` + `guardrails/output_guard.py`，遵循既有 import 风格（`from ai_kb.ontology.identity import IdentityService`）。
- 文档：本详设通过后，进入 `IMPLEMENTATION-PLAN`（P1-P4 拆分 + 工时）→ 建设 → `VERIFICATION`。
