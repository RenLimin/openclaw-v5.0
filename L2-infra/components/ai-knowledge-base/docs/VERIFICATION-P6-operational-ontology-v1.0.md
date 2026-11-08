# VERIFICATION-P6-operational-ontology-v1.0

> 验收对象：L2 运营本体 P6（run-scoped 身份令牌 + agent-as-tool 组合消费）
> 验收方式：全量自动化回归 + 黄金用例 + 真实装配走查
> 日期：2026-11-08
> 依据：`DESIGN-DETAIL-operational-ontology-p6-v1.0.md` / `DESIGN-OUTLINE-operational-ontology-p6-v1.0.md`

## 0. 结论

**通过**。P6.1（身份令牌）P6.2（toolchain + L4 首实例）P6.3（回归）全部实现、测试全绿。
合计 **513 用例** 回归通过（L2 147 / L3 115 / L4 251 + 3 skip）。

- P6.1：run-scoped HMAC 令牌，Proposal Gate `propose`/`review` fail-closed，指纹入决策记录（migration v12）；
- P6.2：`OntologyToolchain`（agent 到 validated 即停，commit 仅 human 令牌）+ L4 `submit_to_oa_agent` 黄金链路；
- P6.3：全量回归无破坏；operator 令牌人工路径可用。

## 1. 验收矩阵

| Phase | 验收标准（详设 §5） | 实现方式 | 验证结果 |
|---|---|---|---|
| **P6.1** 身份令牌 | issue→verify 往返；篡改/过期拒；scope 精确/通配/拒绝；enforce fail-closed；claims 冲突拒；指纹落库；逃生口 | `identity_token.py`（HMAC-SHA256，base64url，标准库零依赖）+ migration v12 + `ProposalService.identity/enforce_identity` + MCP 透传 | `tests/test_ontology_identity_token.py` 18 用例全绿 |
| **P6.2** toolchain + 首实例 | discover 无泄漏；run_action 到 validated 不 commit；human 令牌 commit；agent 令牌无法自提 | `agent_toolchain.py` `OntologyToolchain` + L4 `bridge.submit_to_oa_agent` | `tests/test_ontology_toolchain.py` 7 用例 + `test_oa_toolchain_agent.py` 4 黄金用例全绿 |
| **P6.3** 回归 | 全量 L2/L3/L4 绿；operator 令牌兼容人工路径 | L2 147 / L3 115 / L4 251+3skip | 全绿，无回归破坏 |

## 2. 关键语义验证（红线）

| 红线 | 验证 |
|---|---|
| **commit 只由 human 令牌触发** | ✅ toolchain `auto_review` 缺 reviewer_token → `IdentityError`；agent 令牌当 reviewer → 拒绝（L2 单测 + L4 黄金用例双重锁定） |
| **agent 永不代行 human 审** | ✅ human 级 action `review` 校验 `claims.kind=human` + L2 既有 `PermissionError` |
| **fail-closed** | ✅ enforce=True 无 token propose → `IdentityError`；identity 未配置 = 渐进兼容（P5 路径行为不变） |
| **身份冲突即拒** | ✅ 令牌 sub/kind 与自报 caller 冲突 → `InvalidToken` |
| **指纹可审计** | ✅ `ont_decision_record.token_fingerprint` 落库（approve/reject 均验）；L4 决策链双指纹（run + reviewer） |
| **secret 不落盘文档** | ✅ `~/.openclaw/state/ontology-identity.secret`（0600）+ env 覆盖；不进 git/markdown/日志 |
| **P4.2 冻结语义不变** | ✅ `oa_connector.py` 零改动；连接器恒 dry-run；`dry_run=False` 仍抛 RuntimeError |
| **validated ≠ committed** | ✅ toolchain 默认停在 validated；`auto_review=True` 无令牌拒绝 |
| **不新增第三方依赖** | ✅ 全部标准库（hmac/hashlib/base64/json/secrets） |
| **运行期 gate 关闭** | ✅ 结构注册仅装配期；MCP/toolchain 运行期只读 registry |

## 3. 回归清单

```bash
# L2（147）
cd L2-infra/components/ai-knowledge-base && python3 -m pytest tests/ -q
# L3（115）
cd L3-business/components/contract-management && python3 -m pytest tests/ -q
# L4（251 + 3 skip）
cd L4-proprietary/components/bangcle-contract && python3 -m pytest tests/ -q
```

**全部通过。** 无回归破坏。

## 4. 黄金用例走查（L4 首实例）

```python
# agent run 令牌 → validated（不 commit）
r = bridge.submit_to_oa_agent(1, run_id="run-882663", agent="assistant",
                              requestid="882663", action="提交", authority=authority)
assert r["proposal_status"] == "validated"          # agent 永不 commit

# human operator 令牌 → review→commit（dry-run 连接器）
r = bridge.submit_to_oa_agent(1, run_id="run-882663", agent="assistant",
                              requestid="882663", action="提交",
                              reviewer_operator="rex", authority=authority)
assert r["proposal_status"] == "committed"
assert r["run_token_fingerprint"] and r["reviewer_token_fingerprint"]
# 决策链：actor=agent:assistant，review_by=operator:rex，指纹=reviewer 指纹，
# evidence.saga_report.executed_steps=["oa_writeback"]（dry-run 审计写回）
```

## 5. 文件清单

**实现（6 个文件，P6.1 提交 `d27a829` + P6.2 提交 `b2a53d6`）：**

| 层 | 文件 | 改动 |
|---|---|---|
| L2 | `ai_kb/ontology/identity_token.py` | **新**：IdentityAuthority（issue/verify/authorize/fingerprint）+ operator_token + secret 托管 |
| L2 | `ai_kb/ontology/proposal.py` | `identity/enforce_identity` 构造；propose/review 透传 token；claims 冲突校验；指纹进决策记录 |
| L2 | `ai_kb/db.py` | migration v12（`ont_decision_record.token_fingerprint` ALTER 幂等 + 建表原生含列） |
| L2 | `mcp/server.py` | 装配 IdentityAuthority（handler 可注入 secret）；propose/review/动态 propose 透传 token + descriptor 字段 |
| L2 | `ai_kb/ontology/agent_toolchain.py` | **新**：OntologyToolchain（discover/run_action） |
| L4 | `contract_review/ontology_bridge/bridge.py` | `_new_service_oa` 支持 identity 注入；+`submit_to_oa_agent` 首实例 |

**测试（3 新文件 + 2 适配，共 29 新用例）：**

| 文件 | 用例数 |
|---|---|
| `tests/test_ontology_identity_token.py`（L2 新） | 18 |
| `tests/test_ontology_toolchain.py`（L2 新） | 7 |
| `tests/unit/test_oa_toolchain_agent.py`（L4 新） | 4 |
| `tests/test_mcp_dynamic_tools.py`（适配） | 签发真实令牌 |
| `tests/integration/test_ontology_gate_e2e.py`（适配） | 签发真实令牌 |

## 6. 遗留

- **P4.2 冻结语义不变**：`submit_to_oa` 连接器恒 dry-run；真实写端点契约（抓包 + Rex 二次授权 + 测试单据）未闭合前不触碰；已并入人工验收测试环境执行。
- **对象级权限（P7）**：本阶段仅 run/action 级 scope；行级 markings 明确留待 P7。
- **MCP 令牌分发**：`KBMCPHandler` 支持注入 secret；外部 agent 经 MCP 消费时令牌由调用方持有/透传（MCP 层不伪造、不回显完整令牌）。
- **ClawHub 沉淀**：P6 验证通过后按 Rex 拍板沉淀为 ClawHub skill/plugin。
