# L2 运营本体 P7 详细设计：对象级权限（Markings / 行级 Visibility）v1.0

> L2 Infrastructure Component · ai-knowledge-base · INFRA-KB-002
> 版本：v1.0 · 状态：**待 Rex 评审**（评审通过后才编码）
> 日期：2026-11-08 · 作者：Jerry 🦞
> 上承：`DESIGN-OUTLINE-operational-ontology-p7-v1.0.md`（已通过）
> 调研：`memory/research-p7-object-level-security.md`（四类来源）
> 前置：P1–P6 已交付（`d8b7e79`，513 tests 绿）

---

## 1. 范围与拍板项

### 1.1 本期范围

在运营本体上新增 **mandatory marking + clearance** 对象级权限层，并把 enforce 铺到读/写/审/MCP 全入口。

### 1.2 Rex 已拍板（2026-11-08 OUTLINE 评审）

| # | 决策 |
|---|---|
| D1 | marking 授予**强制 `expires_at`**，默认上限 **90 天**（`MARKING_MAX_GRANT_DAYS` 可配）；无过期日的授予一律拒。目录（`source='directory'`）来源可在续期时刷新。 |
| D2 | **双保险**：`propose` 用令牌 claims 评估；`review`/`commit` 对对象上**任一 high-sensitivity marking** 额外**实时查 `ont_marking_grant` 表复查**（claims 与实时表都满足才放行）。 |
| D3 | 既有 `permissions.py` 的 `confidence_level` 与新 `clearance` **合并为单一 `clearance`**（四级 public/internal/confidential/restricted）；`confidence_level` 作为读别名兼容、不再写入。 |

### 1.3 非目标

ReBAC 关系图继承、独立授权服务、新第三方依赖、列级 masking、改变 P4.2 冻结语义。

---

## 2. 数据模型（migration v13）

### 2.1 新增表 DDL

```sql
-- marking 注册（集中托管）
CREATE TABLE IF NOT EXISTS ont_marking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id   INTEGER NOT NULL REFERENCES domain(id),
    code        TEXT NOT NULL,          -- 域内稳定标识，如 'pii' / 'region-eu'
    name        TEXT NOT NULL,
    sensitivity TEXT NOT NULL DEFAULT 'normal',  -- normal | high（high 触发实时复查）
    owner       TEXT,                   -- Expand Access 责任主体（角色/人）
    created_at  TEXT NOT NULL,
    UNIQUE(domain_id, code)
);

-- 主体 → marking 授予（强制过期，审计可追溯）
CREATE TABLE IF NOT EXISTS ont_marking_grant (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    marking_id  INTEGER NOT NULL REFERENCES ont_marking(id),
    subject     TEXT NOT NULL,          -- 与令牌 claims.sub 同口径
    source      TEXT NOT NULL,          -- directory | manual | ticket
    granted_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,          -- NOT NULL（D1）
    revoked_at  TEXT,                   -- 非空 = 已吊销
    granted_by  TEXT,
    UNIQUE(marking_id, subject)
);

CREATE INDEX IF NOT EXISTS idx_ont_grant_subject
    ON ont_marking_grant(subject);
CREATE INDEX IF NOT EXISTS idx_ont_grant_marking
    ON ont_marking_grant(marking_id);
```

### 2.2 对象挂标位置（不加新列）

运营对象标记写在既有 `ont_identity.metadata`：

```json
{
  "markings": ["pii", "region-eu"],
  "permissions": { "clearance": "confidential", "allowed_roles": ["..."] }
}
```

- `markings`：域内 marking `code` 的数组（扁平 AND）。
- clearance 统一读 `metadata.permissions.clearance`；历史 `confidence_level` 仅读兼容。
- metadata 非法 JSON / `markings` 非数组 / 引用未注册 code → 评估器按 **fail-closed 处理（deny）**；其中"引用未注册 marking code"同时在挂标 API 层拒绝写入。

### 2.3 迁移与装配

- `db.py` 新增 `init_ontology_marking_tables()`，`CREATE TABLE IF NOT EXISTS` + 索引；幂等登记 migration v13（`object_level_markings`）。
- 加入 `init_ontology_tables()` 依赖顺序末尾（v13）。
- 老库升级：不回填、不改动任何既有 `ont_identity` 行；无 marking 数据时全系统行为与 P6 一致（渐进启用）。

---

## 3. 模块与接口契约

### 3.1 新模块 `ai_kb/ontology/markings.py`

```python
CLEARANCE_LEVELS = ["public", "internal", "confidential", "restricted"]
MAX_GRANT_DAYS = 90

class MarkingError(Exception): ...
class MarkingNotFound(MarkingError): ...

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str                 # 短英文 code，如 'missing_marking:pii'
    missing: List[str]          # 缺失的 marking code（供审计，不回显敏感字段值）

class MarkingDirectory:
    def __init__(self, db: AIKB) -> None: ...

    # 注册 / 查
    def register(self, domain, code, name, *, sensitivity='normal', owner=None) -> int
    def get(self, domain, code) -> Optional[Dict]
    def list(self, domain) -> List[Dict]

    # 授予 / 吊销（强制 expires_at；幂等）
    def grant(self, domain, code, subject, *, source, granted_by=None,
              ttl_days: Optional[int] = None, now=None) -> int
    def revoke(self, domain, code, subject, *, now=None) -> None

    # 主体【当前有效】marking 集合（实时查，过滤过期/吊销）
    def active_markings(self, subject, *, domain=None, now=None) -> Set[str]
    def has_high_sensitivity(self, domain, codes) -> bool

class PolicyEvaluator:
    """单一对象级评估器：读/写/审/MCP 共用。"""
    def __init__(self, db: AIKB, directory: Optional[MarkingDirectory] = None) -> None: ...

    def evaluate(
        self,
        subject_claims: Dict,          # 令牌 claims（含 markings/clearance）
        object_metadata: Dict,
        *,
        verb: str,                     # read | propose | review | commit
        domain=None,
        realtime: bool = False,        # True = review/commit 高敏实时复查（D2）
        now=None,
    ) -> Decision: ...
```

### 3.2 `PolicyEvaluator.evaluate` 判定顺序（deny 优先 / fail-closed）

1. **元数据非法** ⇒ deny(`bad_metadata`)。
2. **clearance**：`claims.clearance` 序位 < 对象 `clearance` ⇒ deny(`clearance`)。claims 缺 clearance ⇒ 视为 `internal`（最低可用默认，不自动提权）。
3. **markings AND**：对象 `markings` 中，claims.markings 未覆盖者 ⇒ deny(`missing_marking:<code>`)。
4. **realtime 复查**（`realtime=True` 且对象含任一 high-sensitivity marking）：
   `directory.active_markings(claims.sub)` 必须覆盖对象**全部** marking，否则 deny(`realtime_revoked:<code>`)。
5. 全过 ⇒ allow。

> discretionary 部分（role/dept/user allowlist）仍由 `permissions.py` 负责；`ont_query_object` 先走 `PolicyEvaluator`（mandatory），再走 `PermissionChecker`（discretionary）。**mandatory 不过直接拒，不再进入 discretionary。**

### 3.3 令牌 claims 扩展（`identity_token.py`）

- `issue(...)` 新增可选参数 `markings: Optional[List[str]] = None`、`clearance: Optional[str] = None`；写入 claims：
  ```json
  { ..., "markings": ["pii"], "clearance": "confidential" }
  ```
- `markings` 默认 `[]`；`clearance` 默认 `"internal"`；`clearance` 非法值 ⇒ `InvalidToken`。
- **agent 不能自报**：markings/clearance 只由签发方（装配目录/权威源）传入；`verify` 原样透传，不接受调用时覆盖。
- `verify` 对新字段做类型校验（list/str），缺失时补默认（向后兼容旧令牌）。
- `operator_token(...)` 增可选 `markings`/`clearance`；local operator 默认 `markings=[]` + `clearance='restricted'`（人工全 clearance，但 marking 仍需显式授予，不天然豁免 mandatory）。

### 3.4 ProposalService 接入（`proposal.py`）

构造器新增 `directory: Optional[MarkingDirectory] = None`、`enforce_object_security: bool = True`。

- **propose_action**：身份校验后、建 pending 前，对 snapshot 中**每个 identity**：
  ```python
  decision = evaluator.evaluate(claims, identity['metadata'], verb='propose',
                                domain=domain_code, now=now)
  if not decision.allowed: raise ScopeDenied(...)
  ```
  任一对象不过 ⇒ 抛 `ScopeDenied`，**不建提案、不留 pending**（在 INSERT 之前）。
- **review**：身份校验后，对目标对象逐个 `verb='review', realtime=True`；不过 ⇒ 拒（reviewer 无权可见则不能审批）。
- **commit**：作为 review 的内部延续，已在 review 层复查；commit 内对 high-sensitivity 再断言一次（防 review→commit 间隙吊销），失败 ⇒ ROLLBACK。
- **兼容路径**：`directory=None` ⇒ 对象级安全未启用（仅 P6 action scope），audit 标 `object_security_enforced=false`；注入 directory 后默认 fail-closed；`enforce_object_security=False` 仅测试逃生口，audit 显式标注。

### 3.5 MCP 接入（`mcp/server.py`）

- `ont_query_object`：
  - claims：若传 `token` 则 `verify` 取 claims；否则由 `caller_attrs` 映射（兼容旧形态）。
  - 先 `PolicyEvaluator.evaluate(..., verb='read')`；不过 ⇒ `{"found": true, "allowed": false}`，**不回显任何 metadata/字段**。
  - 再过 `PermissionChecker`（discretionary）。
- 动态 `ont_propose_<name>` / `ont_propose_action` / `ont_review_proposal`：透传 `token`，由 ProposalService 统一 enforce，无旁路。
- 服务装配 `_get_ontology_services`：构造 `MarkingDirectory` + 传入 `ProposalService(directory=...)`。

### 3.6 错误口径（存在性侧信道，开放项 3）

- 读路径：对象不存在 ⇒ `{"found": false}`；存在但无权 ⇒ `{"found": true, "allowed": false}`。保留 found 以维持现有契约，但**不泄露任何字段**。
- 写路径：统一抛 `ScopeDenied`（`IdentityError` 子类），reason 只含缺失 marking code，不区分"对象不存在/无 clearance"的细节文案给 agent；详细区分只进 audit。

---

## 4. 关键时序

### 4.1 propose（写）

```
caller ─token─▶ verify ─authorize(action scope)
              ─▶ snapshot（CWA，逐对象）
              ─▶ PolicyEvaluator(propose) 每个对象   ← 不过：ScopeDenied，无 INSERT
              ─▶ INSERT ont_proposal(pending) + audit
```

### 4.2 review + commit（审/提）

```
reviewer ─token─▶ verify ─authorize(review scope)
                 ─▶ PolicyEvaluator(review, realtime=True) 逐对象
                        · claims markings AND
                        · high-sensitivity ⇒ 实时查 ont_marking_grant
                 ─▶ approve ─▶ commit
                        · commit 再断言 high-sensitivity（防间隙吊销）
                        · change_set + 连接器 + decision_record + audit（单事务）
```

---

## 5. Phase 拆分（编码）

| Phase | 内容 | 产出 |
|---|---|---|
| **P7.1** | migration v13 + `MarkingDirectory`（register/grant/revoke/active） | 目录 API + 迁移测试 |
| **P7.2** | `PolicyEvaluator`（clearance/AND/deny/fail-closed/realtime）+ claims 扩展 | 评估器单测 |
| **P7.3** | ProposalService（propose/review/commit）+ MCP query/动态工具接入 | 全入口 enforce |
| **P7.4** | L4 region/PII 黄金用例 + 全量回归 + VERIFICATION-P7 | 验收 |

---

## 6. 测试设计

### 6.1 单元（白盒）

**目录 / 迁移**
- register 幂等（同 domain+code 重复不新增）；grant 无 `expires_at`/超 90 天 ⇒ 拒；revoke 后 active 不含；过期授予 active 不含。

**PolicyEvaluator**
- 对象无 markings ⇒ 只看 clearance；
- AND：缺任一 marking ⇒ deny，reason 标注缺失 code；
- clearance：claims 低一级 ⇒ deny；缺 claims.clearance ⇒ internal 默认；
- 非法 metadata / markings 非数组 / 未注册 code ⇒ deny（fail-closed）；
- realtime：claims 有 marking 但 grant 表已 revoke/过期 ⇒ deny；normal sensitivity 不触发实时、high 触发。

**claims**
- agent issue 时不能注入越权 markings（由签发方控制）；verify 不接受覆盖；clearance 非法值 ⇒ InvalidToken。

### 6.2 集成 / E2E（真实 HTTP / MCP call_tool，不用 TestClient）

- propose：未授予 marking 的 agent ⇒ `ScopeDenied`，且 `ont_proposal` 无新 pending 行（用 DB 计数断言）。
- query：带 PII 对象，未授予 agent ⇒ `found:true,allowed:false`，返回体无 metadata/字段。
- review：reviewer 缺 marking ⇒ 拒，无法 approve；reviewer 授予后可 approve→commit。
- commit 间隙吊销：review 通过后、commit 前 revoke high marking ⇒ commit ROLLBACK。
- MCP 动态 `ont_propose_submit_to_oa` 走同一 enforce，无旁路。
- 幂等：同一 propose 连跑 3 次，拒绝结果稳定（且不产生 pending 垃圾）。

### 6.3 L4 黄金基准（bangcle-contract）

构造两个合同对象：
- `HT-2026-普通`：clearance=internal，无 marking；
- `HT-2026-PII-EU`：markings=[`pii`,`region-eu`]，clearance=confidential。

断言：
1. 仅授 `pii` 的 agent：两合同都无法 propose（EU 缺 region-eu；且 PII-EU clearance 不足）；
2. 授 `pii`+`region-eu` + clearance=confidential 的 human reviewer：可 query 见字段、可 review→commit；
3. agent 令牌不能当 reviewer（延续 P6）；
4. 普通合同对内部 agent 正常可见可提案（不误伤）。

### 6.4 回归

全量 L2（147）/ L3（115）/ L4（251）+3 skipped 必须全绿；新增测试数 ≥ 新增 enforce 分支数（交付 7 步法第 7 条）。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| stale 授予（离职/调岗） | 强制 expires_at + 90 天上限 + high-sensitivity 实时复查（D1/D2） |
| claims 时效导致吊销延迟 | review/commit 实时复查 + 短 TTL；propose 层不做高敏放行单点 |
| mandatory 挂错阻断合法业务 | 挂标/移除走 owner（Expand Access）；默认从严，误挂可经 owner 移除并留审计 |
| 侧信道泄露存在性 | 统一错误口径，不回显字段；细节只进 audit（§3.6） |
| clearance 双轨混乱 | 单字段合并，confidence_level 只读别名（D3） |
| 误锁老数据 | 不回填、无 marking 时退化为 P6 行为；逃生口仅测试并 audit |

---

## 8. 交付物清单

- 新增：`ai_kb/ontology/markings.py`；migration v13（`db.py`）
- 修改：`identity_token.py`、`proposal.py`、`mcp/server.py`
- 测试：评估器/目录单测 + 集成 + L4 黄金用例
- 文档：本 DETAIL + `VERIFICATION-P7-operational-ontology-v1.0.md`
- 技能/资产：`ontology-identity-gate` SKILL 增补对象级权限章节；资产清单自动重生成

---

## 变更历史

- v1.0（2026-11-08）：初版详设，固化 D1–D3，待 Rex 评审。
