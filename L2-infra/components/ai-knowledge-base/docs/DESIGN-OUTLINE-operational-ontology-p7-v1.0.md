# L2 运营本体 P7 设计大纲：对象级权限（Markings / 行级 Visibility）v1.0

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）后续
> 组件编码：INFRA-KB-002
> 版本：v1.0 · 状态：**待评审**（Rex 拍板后才进入详设）
> 日期：2026-11-08 · 作者：Jerry 🦞
> 依据：`../../../../memory/research-p7-object-level-security.md`（四类来源调研）；`DESIGN-OUTLINE-operational-ontology-p6-v1.0.md` §1.3（P7 为明确预留项）；`VERIFICATION-P6-operational-ontology-v1.0.md` §6 遗留
> 前置：P1–P6 已交付（`7c52a3c`，513 tests 绿）

---

## 1. 背景与目标

### 1.1 背景

P6 把 caller 身份从 fail-open 收敛为 **run-scoped HMAC 令牌**，Proposal Gate 的 `propose`/`review` 校验令牌 scope（`<verb>:<action>:<domain>`）。但这是**调用级 / action 域级**控制——令牌只能表达"谁能对**哪个域的哪类动作**"，无法回答：

1. **行级可见性**：同一域内，agent/human 只能看见部分运营对象（如某区域、PII、财务敏感对象）。
2. **写路径无对象门槛**：`propose_action` 只校验动作 scope，不校验调用方对**具体目标对象**是否可见——有 `propose:submit_to_oa:bangcle-contract` 就能对该域**任意**合同提提案。
3. **审批者可见性未约束**：reviewer 理论上能审批自己无权可见的对象。

现状里有一个**文档级** `ai_kb/permissions.py`（clearance 四级 + role/dept/user allowlist），但 MCP 只在 `ont_query_object` 单一读路径接入，**写路径未接、也未与 P6 令牌打通**。

Palantir 的对应机制是 **Markings**（mandatory control）：对象可挂多个 marking，主体须持有**全部** marking（AND）才能访问，marking 随数据派生传播，deny 优先、跨 project 生效。

### 1.2 目标（本期范围）

1. **Marking 注册 + 授予**：marking 注册表 + 主体→marking 授予（含来源/有效期/审计）；集中托管，可对应 Palantir Expand Access 治理"谁能加/移除"。
2. **对象挂标**：运营对象（`ont_identity.metadata`）挂 `markings`（多标签 AND）+ 复用既有 `clearance` 四级。
3. **令牌 claims 扩展**：P6 令牌新增 `markings` / `clearance`，**签发时由权威目录写入，agent 不可自报**（沿用 claims 权威原则）。
4. **全入口对象级 enforce（fail-closed）**：读（query）、写（propose 逐对象）、审/提（review/commit 要求 reviewer 可见）、MCP 动态工具，同一 `PolicyEvaluator`，无旁路。
5. **首个黄金用例**：bangcle-contract 域——带 region/PII marking 的合同，未授予对应 marking 的 agent 无法 propose、无法在 query 看见字段。

### 1.3 非目标（本期不做）

- ❌ 不做跨对象**关系图继承**（ReBAC / Zanzibar userset rewrite / 父子文件夹继承）——marking 保持扁平 AND；关系需求出现再评估 Casbin。
- ❌ 不引入独立授权服务（OpenFGA/SpiceDB/Keto/Cerbos）——违背嵌入式零外部服务。
- ❌ 不引入新第三方依赖（延续 P1–P6 标准库红线）；仅定义 `PolicyEvaluator` 接口为未来 Casbin/Cedar adapter 预留。
- ❌ 不做属性级（property/列级）masking（只做对象/行级可见性）；列级留待后续。
- ❌ 不改变 P4.2 冻结语义（OA 连接器仍恒 dry-run）。

---

## 2. 设计原则

1. **mandatory + AND**：对象多个 marking，主体须持有全部；任一不满足即拒。
2. **deny 优先 / fail-closed**：marking 不满足、metadata 非法、令牌缺 claims 一律拒；无 fail-open 口子。
3. **claims 权威**：主体 markings/clearance 只信令牌 claims（签发时写入），自报仅核对、不可提权。
4. **全入口单一评估器**：读/写/审/MCP 共用 `PolicyEvaluator`，杜绝"只在一条路径校验"的旁路。
5. **渐进启用**：未配置 marking 目录 = P6 兼容行为；一旦启用，enforce 默认 fail-closed；`enforce=False` 仅测试逃生口且 audit 标注。
6. **授予可治理**：marking 授予有来源/有效期/审计，不做无限期静态白名单（离职/调岗 stale 授予是主要风险）。

---

## 3. 整体架构

```
                  ┌──────────────────── PolicyEvaluator（新增，单一评估器）┐
                  │  check(claims, object_metadata, verb) -> Decision      │
                  │   · 持有对象全部 markings?（AND）                        │
                  │   · clearance claims ≥ 对象 clearance?                 │
                  │   · deny 优先 / 非法 metadata => deny（fail-closed）    │
                  └───────────────▲────────────────▲──────────────▲───────┘
                                  │                │              │
   读 ont_query_object ───────────┘                │              │
   （不可见 => found:true,allowed:false，不泄字段）  │              │
                                                    │              │
   写 propose_action ───────────────────────────────┘              │
   （对 snapshot 中【每个】目标对象校验，不过则连提案都不能建）        │
                                                                   │
   审/提 review / commit ──────────────────────────────────────────┘
   （reviewer 必须能看见对象；否则拒绝审批）

   数据层：
   ┌────────────────┐  grant   ┌──────────────────┐  marking  ┌────────────────────┐
   │ ont_subject    │─────────▶│ ont_marking_grant│◀─────────│ ont_marking（注册） │
   │ (human/agent)  │          │ subject,marking, │           │ id,name,owner,...  │
   └────────────────┘          │ source,expires_at│           └────────────────────┘
                               └──────────────────┘
   对象：ont_identity.metadata = { "markings": [...], "permissions": {...}, ... }
   令牌：P6 claims += { "markings": [...], "clearance": "..." }
```

**新增/改动模块：**

| 模块 | 文件 | 职责 |
|---|---|---|
| marking 目录 | `ai_kb/ontology/markings.py`（新） | marking 注册、主体授予/吊销、对象挂标；`PolicyEvaluator` 评估 |
| 迁移 | `ai_kb/db.py` | migration v13：`ont_marking` / `ont_marking_grant` 表 + 索引；授予幂等 |
| 令牌 | `ai_kb/ontology/identity_token.py` | claims 增 `markings`/`clearance`；issue 从目录解析；verify 透传 |
| 写治理 | `ai_kb/ontology/proposal.py` | propose 逐对象 + review/commit reviewer 可见性校验 |
| MCP | `mcp/server.py` | query 扩展 markings；动态 propose 走同一评估器 |

---

## 4. 关键设计取舍

1. **扁平 marking AND vs ReBAC 图**：只做 mandatory 标签 AND，不做关系继承。换取零依赖/可预测；放弃"父文件夹继承"等表达力（调研 §5.6，需求出现再引 Casbin）。
2. **自研评估器 vs 直接引 Casbin**：核心自研以紧耦合 P6 令牌、零新依赖；但抽 `PolicyEvaluator` 接口，未来 Casbin/Cedar 可作 adapter，不锁死。
3. **claims 携带 markings vs 实时查目录**：markings 在**签发时**写入令牌（无状态、无额外查询），代价是授予吊销有最长令牌有效期延迟 → 用短令牌 + `expires_at` 控制；高敏场景可在 review 层实时复查。
4. **不可见对象的响应语义**：query 返回 `found:true, allowed:false`（不回显任何字段/metadata），避免通过"存在性差异"侧信道；写路径直接抛 `ScopeDenied`，不建提案、不留 pending。
5. **授予治理**：授予需 `source`（目录/人工/工单）+ 可选 `expires_at`；加/移除对象 marking 需 marking 的 Expand Access 角色（集中托管），对应 Palantir。

---

## 5. Phase 拆分（建设计划，详设细化）

- **P7.1 marking 目录 + 迁移**：`ont_marking` / `ont_marking_grant`（migration v13，幂等）；注册/授予/吊销/对象挂标 API；clearance 复用。
- **P7.2 令牌 claims + PolicyEvaluator**：claims 扩展；`markings.py` 评估器（AND/clearance/deny 优先/fail-closed）；单测覆盖。
- **P7.3 全入口 enforce**：query（不泄字段）、propose 逐对象、review/commit reviewer 可见、MCP 动态工具；L4 黄金用例（region/PII）。
- **P7.4 回归 + 验收**：全量 L2/L3/L4 回归；渐进启用/逃生口验证；VERIFICATION-P7。

每阶段独立可测、向后兼容。

---

## 6. 风险与开放问题（评审重点）

1. **授予数据同步**：离职/调岗后 stale 授予是真实风险（Zanzibar 社区共识）——是否强制 `expires_at` 上限？默认是否拒绝无过期日授予？
2. **claims 时效 vs 即时吊销**：签发后吊销有延迟——高敏 marking 是否在 review/commit 层强制实时查目录（放弃纯无状态）？
3. **存在性侧信道**：`found:true,allowed:false` 是否足够，还是写路径报错文本会区分"对象不存在/无权"——需统一错误口径。
4. **clearance 双源**：既有 `permissions.py` 的 `confidence_level` 与新 `clearance` 是否合并为单一字段（建议合并，避免双轨）。
5. **marking 命名/层级**：是否允许 marking 之间层级/互斥（本期倾向不做，保持独立标签）。

---

## 7. 验收标准（概要）

- P7.1：marking 注册/授予/吊销/挂标幂等；migration v13 老库升级一致。
- P7.2：AND 语义（缺一 marking 即拒）、clearance 分级、deny 优先、非法 metadata fail-closed；claims 不可被自报提权。
- P7.3：未授予 agent 无法 propose（连 pending 都不留）、query 不见字段、无法审批不可见对象；MCP 无旁路；L4 region/PII 黄金用例通过。
- P7.4：全量回归无破坏；渐进启用 + enforce 逃生口行为正确并 audit 留痕。

---

## 变更历史

- v1.0（2026-11-08）：初版大纲，待 Rex 评审。
