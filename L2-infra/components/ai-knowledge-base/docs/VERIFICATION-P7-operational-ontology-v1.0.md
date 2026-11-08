# VERIFICATION-P7-operational-ontology-v1.0

> 验收对象：L2 运营本体 P7（对象级权限 — mandatory Markings / 行级 Visibility）
> 验收方式：全量自动化回归 + L4 黄金用例 + 契约对齐
> 日期：2026-11-08
> 依据：`DESIGN-DETAIL-operational-ontology-p7-v1.0.md` / `DESIGN-OUTLINE-operational-ontology-p7-v1.0.md`

## 0. 结论

**通过**。P7.1（migration + 目录）P7.2（评估器 + claims）P7.3（全入口 enforce）P7.4（黄金用例 + 回归）全部实现、测试全绿。

合计 **548 用例** 回归通过（L2 **175** / L3 **115** / L4 **258** + 3 skip）。
相较 P6 基线 513，净增 **35 个对象级权限用例**（L2 +28 白盒 / L4 +7 黄金），零回归破坏。

- P7.1：migration v13（`ont_marking` / `ont_marking_grant`）+ `MarkingDirectory`（register/grant/revoke/active，授予强制过期、90 天上限）；
- P7.2：单一 `PolicyEvaluator`（mandatory AND + clearance 四级 + deny 优先 + fail-closed + 高敏实时复查），令牌 claims 增 `markings`/`clearance`；
- P7.3：propose / review / commit / MCP query / 动态工具全入口共用同一评估器，无旁路；
- P7.4：L4 region/PII 黄金用例锁定，VERIFICATION 收口。

## 1. 验收矩阵

| Phase | 验收标准（详设 §5/§6） | 实现方式 | 验证结果 |
|---|---|---|---|
| **P7.1** 目录 + 迁移 | v13 建表；register 幂等；grant 强制过期 + ≤90 天；revoke/过期过滤 | `db.py` migration v13 + `markings.py` `MarkingDirectory` | `test_ontology_markings.py` 目录段全绿 |
| **P7.2** 评估器 + claims | AND 缺标 deny（带 code）；clearance 分级；deny 优先/fail-closed；高敏实时；claims 扩展 | `markings.py` `PolicyEvaluator` + `identity_token.py` claims | `test_ontology_markings.py` 评估器段 + 令牌往返全绿 |
| **P7.3** 全入口 enforce | propose 逐对象（不过不建 pending）；review 实时复查；commit 间隙吊销拒；query `found:true,allowed:false`；动态工具同口径 | `proposal.py` + `mcp/server.py` | L4 黄金用例 + MCP query 冒烟全绿 |
| **P7.4** 黄金用例 + 回归 | L4 region/PII 场景锁定；全量 L2/L3/L4 绿；新增测试数 ≥ enforce 分支数 | `test_object_markings.py` 7 例 | **548 passed**（+35），无回归 |

## 2. 关键语义验证（红线）

| 红线 | 验证 |
|---|---|
| **mandatory AND** | ✅ 对象多标须持有全部；缺任一 `Decision(allowed=False, reason='missing_marking:<code>', missing=[...])`（白盒 + 黄金双锁） |
| **deny 优先 / fail-closed** | ✅ metadata 非 dict / markings 非数组 / 未注册 code / claims 属性非法 ⇒ 一律拒；非法 metadata 不回显字段 |
| **全入口单一评估器** | ✅ query / propose / review / commit / MCP 动态工具全部经 `PolicyEvaluator`；不存在绕过路径（冒烟验证动态工具同口径） |
| **写不过不落地** | ✅ propose 逐对象校验在 `INSERT ont_proposal` 之前；缺标 ⇒ `ScopeDenied` 且 `ont_proposal` 计数为 0（DB 计数断言） |
| **reviewer 不能审批看不见的对象** | ✅ review 逐对象 realtime 复查；reviewer 缺标 ⇒ `ScopeDenied`，无法 approve |
| **review→commit 间隙防吊销** | ✅ commit 层 `realtime_assert` 只复查 high-sensitivity marking；间隙 revoke ⇒ ROLLBACK（白盒 + 黄金双锁） |
| **存在性侧信道** | ✅ 读拒统一 `found:true, allowed:false, error:'access denied'`，不回显 metadata/任何字段；缺失 code 仅进 audit |
| **clearance 单字段（D3）** | ✅ `permissions.clearance` 唯一权威；`confidence_level` 仅读别名；claims 缺省 internal（不提权） |
| **授予可治理（D1）** | ✅ grant 强制 `expires_at`、上限 90 天、`source` 枚举、revoke 留痕；过期/吊销 realtime 即失效 |
| **高敏实时复查（D2）** | ✅ sensitivity=high 在 review/commit 实时查 grant 表；normal 敏不实时（claims 判定即可） |
| **渐进启用 / P6 兼容** | ✅ 未注入 directory ⇒ P6 行为完全不变（黄金用例 `test_no_directory_p6_compatible` 锁定）；对象无 marking 退化为只看 clearance |
| **身份权威不变** | ✅ markings/clearance 由签发方写入令牌 claims，agent 不可自报提权；P6「commit 仅 human 令牌」红线延续 |
| **不新增第三方依赖** | ✅ markings/评估器仅标准库（datetime/json/dataclasses） |
| **P4.2 冻结语义不变** | ✅ 黄金用例连接器恒 dry-run；`oa_connector.py` 零改动 |

## 3. 回归清单

```bash
# L2（175 = P6 基线 147 + P7 白盒 28）
cd L2-infra/components/ai-knowledge-base && python3 -m pytest tests/ -q
# L3（115，不变）
cd L3-business/components/contract-management && python3 -m pytest tests/ -q
# L4（258 = P6 基线 251 + P7 黄金 7，+ 3 skip）
cd L4-proprietary/components/bangcle-contract && python3 -m pytest tests/ -q
```

**全部通过。** L2 175 / L3 115 / L4 258+3skip，无回归破坏。

> 注意：`L3-business/components/finance-engine` 的 collection error（`No module named 'finance_engine'`）是该组件自身的 sys.path 装配问题，与 P7 无关；Palantir ontology 回归的 L3 组件为 `contract-management`（115 全绿）。

## 4. L4 黄金用例走查（region/PII）

`test_object_markings.py`（7 例）锁定：

```python
# 1) agent 无 pii 授予 → propose 拒，无 pending 残留
with pytest.raises(ScopeDenied):
    bridge.submit_to_oa_agent(..., directory=d, agent_markings=[])
# SELECT COUNT(*) FROM ont_proposal == 0

# 2) agent 目录授予 pii + claims 带 pii → validated
r = bridge.submit_to_oa_agent(..., directory=d,
        agent_markings=["pii"], agent_clearance="restricted")
assert r["proposal_status"] == "validated"

# 3) reviewer 无 pii → 拒审（不能批自己看不见的）
with pytest.raises(ScopeDenied):
    bridge.submit_to_oa_agent(..., reviewer_operator="rex", reviewer_markings=[])

# 4) reviewer 目录授予 pii + claims 带 pii → commit（dry-run）
r = bridge.submit_to_oa_agent(..., reviewer_operator="rex",
        reviewer_markings=["pii"], reviewer_clearance="restricted")
assert r["proposal_status"] == "committed" and r["reviewer_token_fingerprint"]

# 5) clearance 不足（agent internal < 对象 restricted）→ ScopeDenied
# 6) metadata.markings="pii"（非列表）→ fail-closed
# 7) 不传 directory → P6 兼容路径，正常 commit
```

MCP 读路径冒烟（真实 `call_tool`）：

```python
h.call_tool("ont_query_object", {...})                 # 匿名 → found:true, allowed:false
h.call_tool("ont_query_object", {...,"token":tok})     # 缺标 → found:true, allowed:false
h.call_tool("ont_query_object", {...,"token":tok2})    # 持标 → found:true, allowed:true, 带 canonical_key
```

## 5. 文件清单

**实现（提交 `bcef8de` P7.1/7.2 + `762152a` P7.3）：**

| 层 | 文件 | 改动 |
|---|---|---|
| L2 | `ai_kb/ontology/markings.py` | **新**：MarkingDirectory + PolicyEvaluator + Decision + 常量 |
| L2 | `ai_kb/db.py` | migration v13（`ont_marking` / `ont_marking_grant` 建表 + init 入口） |
| L2 | `ai_kb/ontology/identity_token.py` | claims 增 `markings`/`clearance`；issue 校验 clearance 枚举 |
| L2 | `ai_kb/ontology/proposal.py` | propose/review/commit 逐对象 enforce；commit realtime_assert |
| L2 | `mcp/server.py` | 装配 MarkingDirectory；query mandatory 优先；动态工具透传 |
| L2 | `ai_kb/ontology/agent_toolchain.py` | run_action 加 markings/clearance 透传 |
| L4 | `contract_review/ontology_bridge/bridge.py` | directory 注入 + agent/reviewer 对象级属性透传 |

**测试（2 新文件，+35 例）：**

| 文件 | 用例数 |
|---|---|
| `tests/test_ontology_markings.py`（L2 新，提交 `776f742`） | 28 |
| `tests/unit/test_object_markings.py`（L4 新，提交 `16c4759`） | 7 |

新增 enforce 分支数（missing/clearance/bad_metadata/unregistered/realtime_revoked/bad_claims 等）≤ 新增测试数 35，满足交付 7 步法第 7 条。

## 6. 遗留与非目标

- **非目标（本期不做，详设 §1.3）**：ReBAC 关系图继承；独立授权服务；新第三方依赖（Casbin/OpenFGA adapter 留接口位）；列级 masking；改变 P4.2 冻结语义。
- **P4.2 冻结语义不变**：真实写端点契约（抓包 + Rex 二次授权 + 测试单据）未闭合前连接器恒 dry-run；并入人工验收测试环境执行。
- **marking 挂标/移除治理**：生产挂标与 Expand Access（移除）须走 owner 流程 + 审计；本期提供目录 API，未接 CLI/REST 挂标命令（属装配/治理动作，按需另立）。
- **ClawHub 沉淀**：P7 验证通过后，给 `ontology-identity-gate` skill 增补对象级权限章节（v1.0.0 仍 pending-publication，随平台 moderation 通过后一并处理）。
- **生产 secret / 目录装配**：`MarkingDirectory` 由装配方按 instance 注入；未配置 = P6 兼容（渐进），不回填历史对象。
