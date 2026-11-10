# 调研 01：AI Agent 构建参数化企业业务工作流 — 业界最佳实践

> 时间：2026-11-10 ｜ 来源：子代理 56e0d63c（官方文档+社区框架）｜ 状态：done

## 覆盖来源
OpenAI Agents SDK/Cookbook、Anthropic Engineering（Building Effective Agents / Multi-agent Research System / Computer Use）、Google A2A、Microsoft AutoGen、LangGraph、CrewAI Flows、LlamaIndex workflows。

## 10 条可落地模式

| # | 模式 | 适用环节 | 做法 | 来源 |
|---|---|---|---|---|
| 1 | 显式状态机+中心化状态 | 全流程编排 | 代码写死节点/边/分支，强类型全局状态；workflow 骨架+节点内 agent | anthropic.com/research/building-effective-agents |
| 2 | 编排器-工作者（并行取数） | OA/ONES 多源取文件 | 主 agent 拆子任务（目标/输出格式/工具/边界四要素），并行派发，汇总 | anthropic.com/research/multi-agent-research-system |
| 3 | 人在环审批闸门 | 文件齐套确认、对外稿签发 | 不可逆动作前暂停整个 run，从同一断点继续；至少两道闸 | openai.com Agents SDK；LangGraph interrupt()；AutoGen UserProxyAgent |
| 4 | Schema-First 产物契约+校验重试 | 所有结构化产物 | Pydantic/Zod/JSON Schema 定义契约；strict structured outputs 生成层约束；节点出口独立校验，失败回喂重试(上限3)，仍失败升级人工 | platform.openai.com/docs/guides/structured-outputs |
| 5 | 节点级护栏（自动门 vs 人工门分离） | 入口参数、PII/越权 | 护栏=自动二元 allow/block 每次跑；审批=人工暂停；工具级护栏最可靠 | openai.com Agents SDK |
| 6 | 浏览器自动化：Playwright 为主、Computer Use 兜底 | 登录/检索/下载 | 固定流程用确定性 Playwright 脚本；UI 多变才用视觉型；下载即校验（文件名/类型/大小/非空/来源） | docs.anthropic.com tool-use；building-effective-agents |
| 7 | 检查点持久化与断点恢复 | 长流程/跨天审批 | 每节点跃迁持久化全量状态（thread_id 为键）；从最近检查点精确恢复，不重跑 | LangGraph persistence；CrewAI @persist(SQLite)；AutoGen save/load_state |
| 8 | 评估器-优化器自校验 | 条款抽取、汇总成文 | 一个调用生成，另一个按标准评分反馈循环，达上限/人工 | anthropic.com/research/building-effective-agents |
| 9 | 全链路可观测性+时间旅行调试 | 生产监控/审计 | tracing 记录 LLM 生成/工具调用/handoff/护栏；保留「原始文件→结论」血缘 | OpenAI Agents SDK；LangGraph |
| 10 | 标准化 Task/Artifact 建模（A2A） | 模块解耦、产物规范化 | 作业=有生命周期状态的 Task；标准物=Artifact（TextPart/FilePart/DataPart）；结果由 Artifact 承载 | developers.googleblog.com A2A |

## 对本资产启示
1. 定调：确定性 workflow 骨架 + 节点内受限 agent，不做端到端自由 Agent。
2. 流水线：入口护栏 → 并行[OA|ONES]取文件(Playwright) → 文件齐套闸(HITL1) → 解析抽取(structured outputs) → 汇总成文(评估器自校) → 签发闸(HITL2) → 渲染交付；每步写检查点。
3. 三道强校验：原始文件齐套 / 产物 schema / 交付前合规护栏。
4. 契约先行：先冻结三份 JSON Schema 再做提示词。
5. 审批可跨天：状态序列化持久化、断点精确恢复，禁止重跑已取文件。
6. 成本：多智能体 token 消耗可达 15 倍，仅在并行取数+高价值抽取处用。
7. 血缘：保留「原始文件(URI)→抽取字段→汇总结论」链路与 trace。
8. 浏览器稳健性：固定流程固化为可组合工具块；3 次即停、换路径/升级人工。
