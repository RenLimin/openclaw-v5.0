# CLM / AI 合同审批专家 — 业界最佳实践调研

> 调研日期：2026-10-27 | 用途：L3 通用合同管理专家 + L4 Bangcle 合同管理专家设计输入
> 来源总数：28（官方文档 6 + 社区方案 10 + GitHub 开源 8 + OA 集成 4）

---

## 一、摘要结论

1. **合同审批 = 状态机 + 持久化检查点 + 人工闸门（HITL）的长事务 Agent**。OpenAI / Anthropic / Google 三家官方一致：审批从同一 run 的 checkpoint 恢复，而非新会话冷启动。
2. **AI 只做初审（解析/条款抽取/风险建议/法条出处），同意/退回权必须在人**。人工闸门设在「回写 OA / 对外发送」等副作用之前。
3. **框架选型：固定审批链用工作流引擎**（LangGraph HITL 最原生），AutoGen 群聊 / CrewAI 需自写封装，不宜作审批主干。
4. **开源 CLM 普遍不成熟**（多数 <300 star、近一年新建、许可证混杂），只借鉴模块不整套采用；中文场景 `contract-review-pro`（273★）和 `xiaodingfeng/contract-review`（MIT 全栈）最值得参考。
5. **OA 集成三档策略**：API+回调 → 附件授权下载 → RPA 兜底。钉钉接口最全但附件下载属高级版付费；泛微版本碎片化需先确认版本；飞书已有泛微/致远连接器。
6. **条款知识库标配**：条款分类 + 阈值规则 + 语义判断 + 《民法典》引用 + 甲乙方立场 + 版本/反馈闭环；**法条只能来自受控库**，须律师与企业法务共建。
7. **两层分工明确**：L3 沉淀解析/规则引擎/状态机/OA 连接器抽象等通用能力；L4 只放本地产品服务知识库参照、报价 SLA 规则与 OA 实例配置；**严禁重复造轮子、合同原文不发公网模型**。

---

## 二、三类来源发现

### 2.1 AI Agent 官方文档（6 篇）

| 来源 | 核心要点 | 设计启示 |
|---|---|---|
| [OpenAI: A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents) | Agent = 模型+工具+指令；guardrails 一等公民；高影响动作需人工介入；规则型+风险型闸门；记录证据日志 | 审批是高影响动作 → 必须 HITL；风险扫描报告即「证据日志」 |
| [OpenAI Agents SDK: Guardrails](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) | Optimistic execution（乐观执行）+ 并发 guardrail；异常即拦截；guardrails 可以是函数或 agent | 风险扫描与 OCR 可并行；高风险项走拦截模式（fail closed） |
| [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | 长任务需结构化进度文件 + checkpoint + 状态日志；跨会话恢复；脱水/复水（dehydration/rehydration） | 审批流跨多天 → SQLite 状态机 = 天然 checkpoint；审计日志 = 可恢复证据 |
| [Anthropic: Building reliable agents](https://www.anthropic.com/research/building-reliable-agents) | 明确工具边界；输出验证；人工介入点设计 | Agent 只出建议，审批动作由人触发 |
| [Google: Agent Development Kit (ADK)](https://cloud.google.com/products/agent-development-kit) | 工作流 + 人工审批节点是一等公民；状态持久化 + 事件驱动 | 固定审批链用状态机+事件，不做自由对话式审批 |
| [Google ADK: Human-in-the-loop patterns](https://cloud.google.com/vertex-ai/docs/generative-ai/agents/human-in-the-loop) | 审批节点暂停→人工决策→恢复工作流；决策持久化 | 驳回/同意都有明确动作语义；决策原因必填 |

### 2.2 社区方案（10 篇）

| 来源 | 要点 |
|---|---|
| [LangGraph HITL + interrupt + checkpointer](https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt) / [docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) | interrupt() 暂停工作流、checkpointer 存状态、resume 恢复；生产用持久化 checkpointer（类比 BizTalk dehydration/rehydration） |
| [LangGraph Persistent Checkpointer](https://blog.langchain.com/persistent-checkpoints-in-langgraph/) | SQLite/Postgres checkpointer，跨 session 恢复；状态版本化 |
| [LangGraph State Machine Patterns](https://langchain-ai.github.io/langgraph/concepts/low_level/) | 状态图：节点+边+条件边；中断点设计 |
| [飞桨 PactGuard-ERNIE-PP 合同审查落地](https://pfcc.blog/posts/pactguard-ernie-pp) | 分层+解耦+可替换架构（OCR/LLM 可插拔）；工作流引擎；JSON 半残自动修复；版面坐标恢复高亮；缓存/重试/降级 |
| [GraphRAG 合同审查模式](https://microsoft.github.io/GraphRAG/) | 合同知识图谱化，条款关联查询 |
| [通义千问合同审查案例](https://help.aliyun.com/zh/model-studio/) | 模板化审查 + 条款抽取 + 风险分级 |
| [腾讯云智营合同 AI](https://cloud.tencent.com/solution/legal) | 企业级方案：模板库 + 智能审查 + 对比 + 归档 |
| [掘金：企业级合同 AI 审查落地](https://juejin.cn/search?query=合同AI审查) | 与法务共建规则库；灰度上线；人工抽检 |
| [Port.io: HITL 在 AI agent 中的位置](https://www.port.io/blog/human-in-the-loop-for-ai-coding-agents) | 规则型闸门（确定性）+ 风险型闸门（LLM 打分）；统一平台而非每个 workflow 手搓 |
| [LinkedIn: OpenAI agents for workflow automation](https://www.linkedin.com/posts/aagarwal29_openai-agents-activity-7318697440763596831-Lbwi) | KYC/DDQ triage、pre-trade compliance copilot 等高风险场景的 HITL 范式 |

### 2.3 GitHub / 开源项目（8 个）

| 项目 | Stars | 技术栈 | 可借鉴点 |
|---|---|---|---|
| [OpenCLM](https://openclm.ai/open-source-contract-management-software.html) | 商业化开源 | 仓库+审批流+模板条款库+e-sign+提醒+RBAC | 功能全景：contract repository / clause library / approval workflows / audit trail |
| [xiaodingfeng/contract-review](https://github.com/xiaodingfeng/contract-review) | ~ | Vue + PG + Milvus + OnlyOffice | 中文合同审查 Web 应用：AI 预分析、审查点配置、知识库检索 |
| [CSlawyer1985/contract-review-pro](https://github.com/topics/contract-analysis) | 273★ | Python | 中国法律人合同审核 Skill，基于审核方法论体系 |
| [zoharbabin/due-diligence-agents](https://github.com/zoharbabin/due-diligence-agents) | 113★ | 13 个 AI agent 多域交叉审查 | 多 agent 交叉引用，每条发现追溯页码+引用 |
| [jiangnanboy/contract_review](https://github.com/jiangnanboy/contract_review) | ~ | LLM | 条款提取+风险分析+合规检查+审查报告 |
| [thm-msror/Unsupervised-CLM](https://github.com/thm-msror/Unsupervised-CLM) | ~ | Gemini + RAG | RAG 问答 + 风险合规分析 + 摘要 |
| [huggingface: legal-bert-base-chinese](https://huggingface.co/models?search=legal%20chinese) | — | BERT 系列 | 中文法律领域预训练模型（可用于条款分类/风险识别） |
| [LangGraph Checkpointer SQLite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite) | — | Python | 持久化状态 checkpoint 实现参考 |

### 2.4 OA 集成方式（4 篇）

| 平台/方案 | 方式 | 关键能力 | 注意事项 |
|---|---|---|---|
| [钉钉 OA 审批开放平台](https://open.dingtalk.com/document/orgapp/workflow-overview) | 服务端 API | 发起/查询/审批实例；同意/拒绝；**事件订阅回调**（任务变更+实例变更） | 附件下载属高级版付费；第三方企业应用受限 |
| [钉钉审批附件下载流程](https://open.dingtalk.com/document/development/new-version-of-attachment-approval-process) | 附件授权下载 | spaceId 授权 → fileId → downloadUri | 仅企业内部应用可用；需先授权再下载 |
| [飞书集成平台 + 泛微/致远 OA 同步](https://www.feishu.cn/content/7293072844971737089) | 集成平台连接器 | 泛微 OA 数据 → 飞书多维表格；SQL 抽取 | 已有现成连接器，适合数据同步场景 |
| 泛微 e-cology | 接口/DB + RPA | 附件通过 OA 附件表+文档库 API 获取；无 API 时走 RPA | 版本碎片化（e-cology 7/8/9/10），需先确认版本 |

---

## 三、对我们两层架构的设计启示（12 条）

### 3.1 架构分层

1. **L3 纯逻辑核心**：状态机 / 风险规则 / 分级审批 / 金额工具 / 条款解析 / 审核标准库 — 零副作用、可单测（对齐业界共识 + 既有 SCA-001 基础）
2. **L3 连接器抽象**：OaProvider 接口抽象（base class）放 L3 作为"通用模式"，具体厂商实现放 L4（既有依赖注入原则）
3. **L4 只放业务专属**：Bangcle 产品知识库参照 / 报价 SLA / OA 实例配置 / 模板库 / 持久化编排 — 严禁重复造轮子
4. **L3 不引入 LangGraph**：固定审批链用自研状态机 + SQLite 足够（LangGraph 是参考范式，非必选依赖）

### 3.2 审批与 HITL

5. **AI 只做初审，人做决策**：Agent 输出「风险报告 + 修改建议」，同意/驳回由审批人触发（闸门设在副作用前）
6. **持久化 checkpoint**：SQLite 状态机 = 审批流的 checkpointer，跨天/跨会话可恢复（对齐 Anthropic + LangGraph 思想）
7. **审计日志 append-only**：每条发现追溯条款原文 + 法条依据 + 审批决策人 + 时间戳（对齐 due-diligence-agents 交叉引用思想）
8. **幂等键防重**：OA 回调用 `process_id + event_id` 做幂等，重复推送不重复记录（事件驱动标配）

### 3.3 风险与知识库

9. **风险规则双轨**：阈值规则（确定性）+ 语义判断（LLM），规则库受控（法条只能来自受控库）
10. **知识库参照必做**：合同标的 ↔ 本地 SKU 匹配 + 价格偏差 + 折扣红线 — 这是最有价值的"内部增值"
11. **合同原文不发公网模型**：敏感信息本地处理，公网模型只用于通用条款分析或脱敏后调用
12. **条款库版本化 + 反馈闭环**：法务持续迭代规则，版本化管理，每条规则有人负责

---

## 四、风险与注意事项

| 风险 | 缓解 |
|---|---|
| OA 厂商 API 权限/版本/付费差异 | OaProvider 接口隔离 + 模拟实现先行；回调验签；先确认 OA 版本 |
| 合同文本多样性（扫描件/多版本/手改） | 复用 L2 OCR + 版本字段管理；JSON 容错降级 |
| 审批责任边界 | 系统仅辅助分析，审批人实名操作、全程审计；报告标注免责 |
| 折扣红线误判 | 知识库比对结果标记"需人工确认"（product-kb 已有 alert 机制） |
| 数据合规 | 合同数据本地 SQLite；OA 凭据安全存储（不落 markdown/代码）；原文不发公网模型 |
| 规则库质量 | 法务共建；灰度上线；人工抽检反馈闭环 |

---
*来源统计：官方文档 6 · 社区方案 10 · 开源项目 8 · OA 集成 4 = 28 个去重来源*
