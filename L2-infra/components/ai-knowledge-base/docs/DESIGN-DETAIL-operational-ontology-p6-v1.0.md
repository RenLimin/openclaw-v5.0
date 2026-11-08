# L2 运营本体 P6 详细设计：身份令牌 + Agent 组合消费 v1.0

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）后续
> 组件编码：INFRA-KB-002
> 版本：v1.0 · 状态：**OUTLINE 已通过（Rex 2026-11-08），本详设待评审**
> 日期：2026-11-08 · 作者：Jerry 🦞
> 前置：`DESIGN-OUTLINE-operational-ontology-p6-v1.0.md`（`101824a`）；P1–P5（`9f92ba5`）

---

## 1. 范围与目标

闭合 P5 两条开放项：**caller 身份 fail-open（O4）** 与 **动态 MCP 工具未被 agent 真实消费（VERIFICATION-P5 §6）**。

| 子阶段 | 交付 |
|---|---|
| P6.1 | run-scoped 身份令牌：签发/校验（HMAC + scope），Proposal Gate `propose`/`review` 接入，fail-closed；`token_fingerprint` 入决策记录 |
| P6.2 | agent-as-tool 编排助手：发现→组合→调用→审计；L4 `submit_to_oa` 首实例端到端黄金用例 |
| P6.3 | operator 兼容路径 + 全量回归 + 验收文档 |

**非目标**：不引入 OAuth/IdP/第三方依赖；不做对象级（行级 markings）权限（P7）；不膨胀 MCP 工具三分类。

---

## 2. 数据模型契约

### 2.1 新增 migration v12：decision_record 增列

`ont_decision_record` 增加令牌指纹列（ALTER TABLE，向后兼容，老记录为 NULL）：

```sql
ALTER TABLE ont_decision_record ADD COLUMN token_fingerprint TEXT;
```

- `token_fingerprint`：令牌的**非可逆指纹**（SHA-256 of canonical token，hex 前 16 位），用于把决策记录关联到已验证身份而**不存令牌明文**。
- 老记录 NULL 表示"v12 前历史决策"；不回填。
- `ont_proposal` 不增列——提案的 caller_id 仍保留（人读），但信任来源变为令牌；新增的令牌指纹随 commit 进入 decision_record 即闭环。

> 增量加列由新方法 `init_ontology_identity_token_tables()` 执行（幂等：检查 `PRAGMA table_info` 是否已含列），登记 migration v12。`init_ontology_tables()` 末尾调用。

### 2.2 令牌载荷（claims）

| claim | 含义 | 示例 |
|---|---|---|
| `run_id` | agent run 实例 id | `"run-7f3a..."` |
| `sub` | 主体（调用者身份） | `"agent:contract-worker"` / `"operator:1313"` |
| `kind` | human \| agent | `"agent"` |
| `scopes` | 授权范围列表 | `["propose:submit_to_oa:bangcle-contract"]` |
| `iat` | 签发时间（epoch 秒） | `1794190000` |
| `exp` | 过期时间（epoch 秒） | `1794193600` |
| `jti` | 令牌唯一 id（防重放审计） | `"tok-..."` |

**scope 语法**：`<verb>:<action>:<domain>`
- `verb`：`propose` | `review` | `*`
- `action`：action_type name 或 `*`
- `domain`：domain code（如 `bangcle-contract`）或 `*`
- 通配 `*:*:*` 仅 operator 令牌可用。

### 2.3 令牌编码

紧凑 JSON（`separators=(",",":")`，`sort_keys=True`）→ base64url payload；签名 = `HMAC-SHA256(secret, payload_b64)` base64url；令牌串 = `<payload_b64>.<sig_b64>`。

- **secret 托管**：`~/.openclaw/state/ontology-identity.secret`，权限 `0600`；首次签发时若不存在则 `secrets.token_bytes(32)` 生成（与 state 目录 `drwx------` 一致）。可被环境变量 `OPENCLAW_ONTOLOGY_SECRET`（hex/base64）覆盖（多机部署）。**secret 永不落 markdown/日志/git。**
- **指纹**：`sha256(payload_b64 + "." + sig_b64)` hex `[:16]`。

---

## 3. 模块接口契约

### 3.1 `ai_kb/ontology/identity_token.py`（新）

```python
class IdentityError(Exception): ...          # 校验失败基类
class TokenExpired(IdentityError): ...
class InvalidToken(IdentityError): ...
class ScopeDenied(IdentityError): ...

class IdentityAuthority:
    def __init__(self, secret: Optional[bytes] = None,
                 secret_path: Optional[Path] = None,
                 default_ttl: int = 3600) -> None: ...

    def issue(self, *, run_id: str, subject: str, kind: str,
              scopes: List[str], ttl: Optional[int] = None) -> str: ...

    def verify(self, token: str) -> Dict[str, Any]:
        """验签 + 过期 → claims；失败抛 InvalidToken/TokenExpired。"""

    def fingerprint(self, token: str) -> str: ...

    def authorize(self, claims: Dict[str, Any], verb: str,
                  action: str, domain: str) -> bool:
        """scope 匹配（支持 * 通配）；不匹配抛 ScopeDenied。"""

def operator_token(authority: IdentityAuthority, operator_id: str,
                   domain_code: str = "*") -> str:
    """签发 local operator 令牌（全 scope），人工 REST/CLI 兼容路径。"""
```

**校验规则**：
1. 签名不符 / 结构错 → `InvalidToken`；
2. `exp < now` → `TokenExpired`；
3. scope 三段逐一匹配（精确或 `*`），无任一 scope 命中 → `ScopeDenied`；
4. `kind` 必须 ∈ {human, agent}。

### 3.2 ProposalService 接入（`proposal.py` 改）

构造函数新增可选依赖（向后兼容）：

```python
def __init__(self, ...,
             identity: Optional[IdentityAuthority] = None,
             enforce_identity: bool = True) -> None
```

- `enforce_identity=False`：**仅测试/历史兼容**，跳过令牌校验（等同现状 fail-open），但 audit details 标 `"identity_enforced": false`。生产路径恒 True。
- `propose_action(...)` 新增关键字参数 `token: Optional[str] = None`：
  1. `enforce_identity=True` 且无 token → `IdentityError`（fail-closed）；
  2. `verify(token)` → claims；`authorize(claims, "propose", action_name, domain_code)`；
  3. **claims.sub / kind 为准**：`caller_id = claims["sub"]`、`caller_kind = claims["kind"]`（入参 caller_id/caller_kind 若与 claims 冲突 → `InvalidToken`，杜绝自报与令牌不一致）；
  4. audit details 增 `token_fingerprint`、`run_id`。
- `review(...)` 新增 `token: Optional[str] = None`：
  1. enforce 下必须有 token；`authorize(claims, "review", action_name, domain)`；
  2. human 级 action 要求 `claims["kind"]=="human"`（与现有 reviewer_kind 校验叠加）；
  3. reviewer 以 `claims["sub"]` 为准。

### 3.3 commit → decision_record 带指纹

`commit()` 在调用 `decisions.record_no_commit(...)` 处传入 `token_fingerprint`。`DecisionService._record` 增参 `token_fingerprint: Optional[str] = None`，INSERT 增列。reject 路径的 decision_record 同样带 review 令牌指纹。

### 3.4 MCP server 接入（`mcp/server.py` 改）

- `ont_propose_<name>` / `ont_propose_action` 工具 schema 增可选参数 `token`；
- 调用时透传 token；无 token 时由 ProposalService 判 fail-closed（MCP 层不伪造）；
- 工具返回体不回显完整 token，仅回 `token_fingerprint`。

### 3.5 `ai_kb/ontology/agent_toolchain.py`（新，P6.2）

```python
class OntologyToolchain:
    """高层 agent 的运营本体消费助手（进程内直调 + 可经 MCP 暴露）。"""

    def __init__(self, proposals: ProposalService,
                 registry: ActionRegistry,
                 authority: IdentityAuthority) -> None: ...

    def discover(self, domain: Union[int, str]) -> List[Dict[str, Any]]:
        """列可用 ont_propose_* / ont_compute_* 工具（复用 ActionRegistry）。"""

    def run_action(self, *, run_id: str, domain: str, action: str,
                   object_refs: List[str], params: Dict[str, Any],
                   scopes: List[str], subject: str, kind: str,
                   auto_review: bool = False,
                   reviewer_token: Optional[str] = None) -> Dict[str, Any]:
        """issue run 令牌 → propose → validate →（可选 review+commit）→ 审计摘要。

        返回：{proposal_id, status, token_fingerprint, decision_record?}。
        """
```

- 默认 `auto_review=False`：agent 只到 validated，**commit 永远由 human 令牌触发**（不破红线）。
- L4 首实例：用 `OntologyToolchain` 对 `submit_to_oa` 跑通 issue→propose→validate；再由 human operator 令牌 review→commit（dry-run 连接器），全程审计可查。

---

## 4. 关键取舍（OUTLINE 开放问题的回答）

1. **secret 托管**：`~/.openclaw/state/ontology-identity.secret`（0600），可 env 覆盖；不进 git/markdown。
2. **对象级权限**：本阶段仅 run/action 级 scope；对象级 markings 明确 P7。
3. **MCP vs 进程内**：`OntologyToolchain` 进程内直调（省传输），MCP 工具并存供外部 agent；两者共用同一 ProposalService，身份校验逻辑唯一。
4. **审批跨 run 的令牌过期**：run 令牌 TTL 默认 1h；**review 阶段用独立的 reviewer/operator 令牌**（review 时现场签发），不依赖原 run 令牌续命——天然解耦 run 生命周期与人工审批节奏。

---

## 5. 测试方案（黄金基准）

### P6.1（identity_token + Gate 接入）
1. issue→verify round-trip；claims 完整。
2. 篡改签名/载荷 → `InvalidToken`。
3. 过期令牌 → `TokenExpired`。
4. scope 精确命中 / `*` 通配 / 不匹配 → `ScopeDenied`。
5. enforce=True 无 token propose → `IdentityError`（fail-closed 锁定）。
6. 令牌 sub/kind 与自报 caller 冲突 → `InvalidToken`。
7. agent 令牌 review human 级 action → 拒绝（叠加现有 PermissionError）。
8. commit 后 decision_record.token_fingerprint 非空且 = 令牌指纹；reject 同。
9. `enforce_identity=False` 历史路径可用（仅测试），audit 标未强制。

### P6.2（toolchain + L4 首实例）
10. discover 列出 submit_to_oa 等工具，无 execute_*/write_* 泄漏。
11. run_action 走通 issue→propose→validate 到 validated；auto_review=False 不 commit。
12. L4：agent run 令牌到 validated + human operator 令牌 review→commit（dry-run），审计含两条指纹、oa_submitted_at 落库。

### P6.3（回归）
13. 全量 L2/L3/L4 回归绿（现有 agent-caller 测试适配 enforce 或显式关闭）。
14. operator 令牌兼容：CLI/REST 人工路径全 scope 可用。

> 现有 6 个测试文件用 `caller_kind="agent"`：适配方式 = 测试内用 `IdentityAuthority` 签发对应 run/operator 令牌传入（真实路径），或对纯历史行为用例显式 `enforce_identity=False`。优先前者。

---

## 6. 风险

1. **secret 丢失 → 旧令牌全失效**：可接受（令牌短命，重签）；多机用 env 对齐。
2. **迁移锁**：ALTER TABLE 在大库短暂锁；decision_record 体量小，无虞。
3. **fail-closed 误伤历史调用方**：`enforce_identity=False` 逃生口仅限受控；OPERATIONS 明确标注不得用于生产。
4. **时钟偏移**：iat/exp 校验预留 60s leeway。

---

## 变更历史

- v1.0（2026-11-08）：初版详设，待 Rex 评审。
