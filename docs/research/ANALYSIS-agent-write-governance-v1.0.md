# Palantir 对 AI Agent 的核心增益与架构落地（机制分析）

> Jerry 🦞 · 2026-10-31 · v1.0 · 作为 bangcle-contract 后续 DESIGN-DETAIL 输入
> 关联：docs/research/RESEARCH-palantir-oncology-v1.1.md

## 1. 核心增益（一句话）
把 LLM 从"直接读写世界"降级为"只能申请调用受治理能力"，使会幻觉/越权的 LLM 能安全对真实业务系统做写操作。
通用框架给"自由组合"，Palantir 给"约束"。设计哲学：determinism where possible, autonomy where necessary, constraint everywhere.

## 2. 六个关键零件（官方机制）
1. Read-time enforcement：工具由 AIP Logic 在调用者权限内执行，LLM 无直接权限。
2. 三类工具分离：Object(读)/Function(逻辑)/Action(写)，写单独隔离。
3. 只提议不提交：Logic 产生 proposed edits，必须被 Action/Automation 调用才落库。
4. ACID 跨系统事务：多 API 全成功或全回滚，杜绝半脏。
5. Persistent Sandbox/Scenarios：隔离试算、可回滚仿真。
6. Propose→Review→Merge：高风险走人审合并（同 git PR）。

铁律：Don't let the LLM guess the rules —— 规则封装为 Function，LLM 调用而非推理。
结构/数据双通道：Palantir MCP 只能改类型定义、不能写数据，且需提审；OMCP 才能读写数据，受 OAuth/应用策略约束。

来源：palantir.com/docs/foundry/logic/blocks、/getting-started；zerofuturetech 五层长文；ernestchiang 五层框架。

## 3. 与我们系统对照
已有（bangcle-contract 设计原则）：L4 只编排调 L3 状态机(=Function 隔离)；OA 双向回写(=connector)；append-only 审计(=action_log)。
缺口：ContractService→OaProvider 写路径缺 pending proposal 中间态；Agent 接入后，"LLM 调用"与"状态机提交"之间无隔离闸门。

## 4. 落地（裁剪为三改造）
- P0 Proposal 闸门：Agent 仅 propose_action()→pending(带快照)；L3 状态机确定性校验；review→commit 才回写 OA。规则只在 L3 一处，人与 Agent 同一 commit 路径。
- P1 MCP 三分类：query_*(读/ABAC 过滤)、compute_*(逻辑/只产出建议)、propose_*(写/只生成 proposal)；不暴露任何 execute_*/write_*。
- P2（可选）Saga 补偿事务：OA+企微+本地多步写，失败补偿回滚+告警，防半脏。
- 暂不建：Persistent Sandbox（流程场景非仿真，价值最低）。

## 5. 结论
增益在"写治理结构"而非模型/名词；不采购、不上重架构；核心=Proposal 闸门 + MCP 三分类；首个落点 bangcle-contract 合同提交/审批。
