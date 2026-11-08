# L2 运营本体 P6 设计大纲：身份治理 + Agent 组合消费 v1.0

> L2 Infrastructure Component · ai-knowledge-base · 阶段 4（Gen3）后续
> 组件编码：INFRA-KB-002
> 版本：v1.0 · 状态：**待评审**（Rex 拍板后才进入详设）
> 日期：2026-11-08 · 作者：Jerry 🦞
> 依据：`RESEARCH-palantir-agent-application-v1.2.md` §4.2 差距 ③⑥ + §5 路径 A/B；`DESIGN-DETAIL-operational-ontology-p5-v1.0.md` 开放项 O4/O5；`VERIFICATION-P5-operational-ontology-v1.0.md` §6 遗留
> 前置：P1–P5 已交付（`9f92ba5`，440 tests 绿）

---

## 1. 背景与目标

### 1.1 背景

P5 已交付：MCP 动态工具自动枚举（`ont_propose_*`/`ont_compute_*`）、`submit_to_oa` 接入 Proposal Gate、对账权威源统一、preflight dry-run。**但两条已知开放项未闭合**：

1. **caller 身份 fail-open（P5 详设 O4）**：`caller_id` 仍由调用方声明，无签名/作用域校验——任何 agent 可自称任意身份发提案。Palantir 的做法是 OAuth 2.0 作用域 + 每 agent 服务主体 + **run-scoped 权限**（Sixb 模式：权限来自 run 而非 agent 视图）。
2. **动态 MCP 工具未被 agent 真实消费（VERIFICATION-P5 §6）**：工具已暴露给 MCP 客户端，但高层 agent 尚无"发现→组合→调用→审计"的端到端通路（Palantir 的 agent-as-tool：AIP Logic 函数经 MCP 暴露，高层 agent 调用底层）。

### 1.2 目标（本期范围）

1. **run-scoped 身份**：每个 agent run 实例持独立身份令牌（scope 绑定 caller + action 类型 + 对象域），Proposal Gate 的 `propose`/`review` 校验令牌而非信任自报 `caller_id`；越权 fail-closed。
2. **agent-as-tool 端到端**：高层 agent 经 MCP 发现 `ont_propose_*` → 发起提案 → 人工 review → commit 的完整闭环，含身份注入与审计留痕；首个真实消费实例（bangcle-contract 的 submit_to_oa 场景）。

### 1.3 非目标（本期不做）

- ❌ 不引入 OAuth 2.0 服务器/IdP（无第三方依赖铁律）；用轻量 HMAC 签名 + scope 令牌，可平滑升级。
- ❌ 不做对象级权限 enforce（markings/行级 visibility）——那是 P7 范围，本 OUTLINE 只做调用级（run）身份。
- ❌ 不把 MCP 工具面膨胀（保持 query_/compute_/propose_ 三分类）。
- ❌ 不引入 Sixb 代码（仅借鉴 run-scoped 模式）；不引入 OWL/SHACL。

---

## 2. 设计原则

1. **fail-closed**：身份令牌缺失/过期/scope 不符 → 拒绝提案，不留 fail-open 口子（现状是 fail-open）。
2. **零信任自报**：`caller_id` 不再可信，一律经令牌验证。
3. **最小改动 L2 核心**：Proposal Gate 的 validate 增加令牌校验步骤；其余原语不动。
4. **审计不可降级**：每次提案附带令牌指纹，`decision_record` 增加 `token_fingerprint` 字段（append-only）。
5. **向后兼容**：REST/CLI 人工调用走"本地 operator 令牌"（等效现状），agent 调用走 run 令牌；两类都有明确身份。

---

## 3. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│ 高层 Agent（run 实例）                                       │
│  ┌─────────────┐  MCP 发现 + 调用   ┌─────────────────────┐ │
│  │ agent-as-   │ ─────────────────▶ │ L2 MCP 动态工具      │ │
│  │ tool 编排    │                    │ ont_propose_*/      │ │
│  └─────────────┘                    │ ont_compute_*        │ │
│         │ run 身份令牌               └──────────┬──────────┘ │
│         ▼                                       ▼           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ L2 Proposal Gate（P3/P5 已有）                       │   │
│  │  propose → [NEW] 令牌校验（scope 匹配）→ validate     │   │
│  │  → review（human）→ commit → decision_record          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**新增两个 L2 模块：**

| 模块 | 文件 | 职责 |
|---|---|---|
| 身份令牌 | `ai_kb/ontology/identity_token.py` | 签发/校验 run 令牌（HMAC + scope），指纹提取 |
| 代理编排 | `ai_kb/ontology/agent_toolchain.py` | 高层 agent 的发现→组合→调用→审计助手（首个实例） |

---

## 4. 关键设计取舍

1. **HMAC 令牌 vs 自报**：令牌 = `run_id + caller + scopes + exp` 的 HMAC（secret 由 gateway 持有）；scope 形如 `propose:submit_to_oa:bangcle-contract`。校验失败 → `IdentityError`（fail-closed），审计留痕。
2. **operator 兼容**：人工 REST/CLI 调用默认注入 `local-operator` 令牌（拥有全部 scope），等效现状但身份可审计。
3. **scope 收敛**：agent run 的 scope 由 spawning 方声明（最小权限原则），不得声明未授权 action。
4. **agent-as-tool 首个实例**：bangcle-contract 场景——高层 agent 发现 `ont_propose_submit_to_oa` → 带 run 令牌 propose → 人工 review → commit；端到端黄金用例锁定。

---

## 5. Phase 拆分（建设计划，详设细化）

- **P6.1 身份令牌原语**：HMAC 签发/校验 + scope 解析 + `decision_record.token_fingerprint`；Proposal Gate validate 接入；fail-closed 测试。
- **P6.2 agent-as-tool 编排**：`agent_toolchain.py` 发现→组合→调用→审计；L4 首实例端到端黄金用例（submit_to_oa 场景）。
- **P6.3 兼容与回归**：operator 令牌兼容路径；全量回归（L2/L3/L4）；验收文档。

每阶段独立可测、向后兼容。

---

## 6. 风险与开放问题（评审重点）

1. run 令牌的 secret 托管位置（gateway state vs 环境变量）——不落 markdown/凭据文件铁律。
2. scope 表达力是否够（action 级 + 对象域级）——对象级权限仍是 P7。
3. agent-as-tool 的"高层 agent 发现工具"是否真走 MCP 协议，还是内部函数直调（避免 MCP 传输开销）——倾向内部直调 + MCP 暴露并存。
4. 令牌过期窗口（run 时长 vs 审批时长）——review 可能跨 run，需令牌续期或 review 期独立授权。

---

## 7. 验收标准（概要）

- P6.1：无令牌 → 拒绝；scope 不符 → 拒绝；伪造令牌 → 拒绝（HMAC 校验）；`token_fingerprint` 入审计。
- P6.2：agent 端到端 propose→review→commit 黄金用例跑通；审计链完整。
- P6.3：全量回归无破坏；operator 兼容路径可用。

---

## 变更历史

- v1.0（2026-11-08）：初版大纲，待 Rex 评审。
