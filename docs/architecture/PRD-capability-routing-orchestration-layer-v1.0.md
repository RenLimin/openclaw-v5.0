# PRD — 能力路由与编排层（Capability Routing & Orchestration Layer）v1.0

| 项 | 值 |
|---|---|
| 所属层级 | L2 基础设施（横切编排）；L1 agent-registry 作为契约供给方 |
| 版本 | v1.0 |
| 日期 | 2026-11-27 |
| 作者 | Lane D（能力路由与编排层设计） |
| 状态 | **待 Rex 评审** |
| 前置 | `00-system-architecture.md` §1 设计原则 / §3.2 L1 / §3.3 L2；`L1_runtime/components/agent-registry/`；`L2-infra/skills/dag-orchestrator/`；`L0-gateway/DESIGN.md` |
| 关联 | `ADR-202609-031-contract-approval-l3-l4-boundary.md`、`docs/architecture/adr/ADR-035-prompt-rule-system.md`、`L2-infra/components/config/capability-registry/registry.yaml`（84 条目，Lane A/B 处理中） |

> 本文只定义「做什么、做到什么程度算做成」，不含实现结构（见同批 `DESIGN-OUTLINE-*`）与决策留痕（见同批 `ADR-*`）。

---

## 1. 问题陈述

### 1.1 现状事实（实测取证，非推断）

| # | 事实 | 取证方式 | 出处 |
|---|---|---|---|
| P-1 | 自建 skill **28 个**：`L2-infra/skills` 10 + `L3-business/skills` 7 + `L4-proprietary/skills` 11 | `ls` 计数（2026-11-27） | 本仓目录 |
| P-2 | OpenClaw 侧可用 skill 数 **远超自建集**：`openclaw skills list` 返回 **702** 行 | `openclaw skills list \| wc -l`（OpenClaw 2026.9.8 fc23bc8） | CLI 实测 |
| P-3 | 这三个自建 skill 目录被以 `skills.load.extraDirs` **整目录加载**，无逐条准入控制 | `~/.openclaw/openclaw.json` L762-765 | 配置实查 |
| P-4 | OpenClaw **单会话 skill 准入上限 = 64**（超出即截断） | OpenClaw Skills 官方文档 https://docs.openclaw.ai/tools/skills | 官方文档 |
| P-5 | `dag-orchestrator` **无任何生产调用方**：全仓引用仅 11 处，全部落在其自身目录、`registry.yaml` 登记、资产清单/缺陷账本的描述性提及；`L4-proprietary/components/customer-delivery-intelligence/docs/PRD-customer-delivery-intelligence-v1.0.md:100` 明写「编排范式参考（引擎不建，见 §6）」 | `grep -rln dag.orchestrator` 全仓 | 本仓 |
| P-6 | `L0-gateway` 三组件（auth-gateway / channel-router / session-manager）**零业务代码落地**：各组件仅 `README.md` + `DESIGN.md` + `src/` 抽象骨架（合计 1,488 行 Python，其中 `__init__.py` 占 46 行）+ 单测骨架（11+9+8=28 用例，文件名均为 `test_*_skeleton.py`） | `find` + `wc -l` + `grep -c 'def test_'` | 本仓 |
| P-7 | `L1_runtime/components/agent-registry` 为 **骨架阶段 v0.1**：README 自述内存实现 📋 待开发，实际 `src/registry_impl.py` 已实现 `InMemoryAgentRegistry`（注册/注销/按能力标签运行时发现/实例化句柄/健康检查），但**无任何 L2-L4 消费方** | README §3 + `src/registry_impl.py` `grep class/def` | 本仓 |
| P-8 | 现有能力索引 `capability-registry/registry.yaml` 已有 **84 条目**（`- id:` 计数），是「能力 → 入口路径」的既有事实源 | `grep -c '^  - id:' registry.yaml` | Lane A/B 处理中 |
| P-9 | 当前**没有**任何机制在会话启动前把任务意图映射到「该加载哪几个 skill / 该派发给哪个 agent」，skill 选择完全依赖模型自行浏览 skill 列表文本 | 无对应组件/脚本（全仓检索无命中） | 本仓 |

### 1.2 由此产生的四个真实缺口

1. **检索缺口**：702 行 skill 清单进上下文后，模型需在噪声中自选。工具/技能选择（tool selection）在规模上去后会系统性退化——业界实测：584 个工具下 F1 掉 **16.1pp**，且退化模式为 recall-driven（漏选大于多选）。来源：*Scaling Enterprise Agent Routing* https://alphaxiv.org/abs/2606.17519 （已核实可访问）。
2. **上下文缺口**：把「全量目录」塞进 prompt，而不是「检索 top-k 精排后再注入」。Anthropic Tool Search Tool 的核心结论即「工具目录不进上下文，按需检索 top 3–5」（https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview ，Tool Search Tool 章节；已核实可访问）。TrueFoundry 的 agent harness 最佳实践同样要求**延迟加载工具 schema**、上下文做 **compact 而非 truncate**（https://www.truefoundry.com/blog/agent-harness-best-practices ；已核实可访问）。
3. **编排缺口**：`dag-orchestrator` 有完整执行引擎（loader/graph/executor/artifact_store/state/runner/viz + 可插拔 dispatch，默认走 `openclaw` CLI 真实派发），**但没有上游**——没有任何东西替它决定「这个任务该不该走 DAG、走哪张图、初始 inputs 从哪来」。它是孤立的执行器。
4. **契约缺口**：`agent-registry` 定义了 `AgentSpec` / `find_by_capability()` / `instantiate()` 契约，但**从未被调用**（P-7）；`L0-gateway` 定义了认证/路由/会话三段管道，但**零落地**（P-6）。两个「已设计」组件都没有真实消费者，等于能力路由链路两端都断着。

### 1.3 一句话问题

> 系统有能力目录（skill ×28 自建 + registry.yaml ×84 条目）、有能力注册表（agent-registry）、有执行引擎（dag-orchestrator），但**三者之间没有路由与编排层**，导致：技能选择靠运气、上下文靠堆量、编排靠人肉触发、注册表与网关空转。

---

## 2. 目标

| # | 目标 | 判据 |
|---|---|---|
| G-1 | 建立**能力路由**：任务意图 → 精排 top-k skill/agent 清单，替代「全量目录进上下文」 | 检索命中率指标达标（§3.4） |
| G-2 | 建立**编排层**：为 `dag-orchestrator` 提供上游（图选择 + inputs 绑定 + 触发判定），使其成为**被调用方**而非孤立引擎 | `dag-orchestrator` 有 ≥1 个真实生产调用链 |
| G-3 | **激活 `agent-registry`**：路由结果经 `AgentSpec` 契约产出，`find_by_capability()` / `instantiate()` 有真实消费者 | registry 从「骨架」转为「已接线」 |
| G-4 | **给 `L0-gateway` 一个明确归宿**：要么落地、要么正式移交运行时原生通道，终止「设计了但零落地」的长期悬空 | 有 ADR 级处置结论（§4.4 / 同批 ADR 专节） |
| G-5 | **运行时无关**：路由与编排逻辑不 `import openclaw`、不调 `openclaw.*`，全部经 L1 抽象契约（`00-system-architecture.md` §3.2.3 编码规范） | 静态门禁（grep import）+ 审查 |
| G-6 | **演进可逆**：所有新增强制带开关与回滚路径，不改既有 `openclaw.json` / `registry.yaml`（后者由 Lane A/B 持有） | 见 DESIGN-OUTLINE §6 |

---

## 3. 功能清单（Must / Should / Won't）

### 3.1 Must（v1.0 必做）

| ID | 功能 | 输入 → 输出 | 验收挂钩 |
|---|---|---|---|
| F-1 | **能力索引构建器** `capability-index build` | 扫描 28 自建 skill + registry.yaml → 结构化索引（名称/描述/能力标签/入口/运行时要求） | 索引条目数 ≥ 84 且与 registry.yaml 无漂移 |
| F-2 | **意图解析器**（轻量，规则优先） | 用户自然语言请求 → 规范化 intent（能力需求列表 + 槽位） | 覆盖 §3.4 的 20 条基准查询 |
| F-3 | **路由检索器**（top-k 精排） | intent → 排序后的候选（skill 或 AgentSpec），k 默认 5，可调 | 命中率（§3.4 M-1） |
| F-4 | **上下文裁剪注入器** | 仅把 top-k 的**增量**（描述 + 触发条件 + 入口，非全文）注入 prompt | token 降幅（§3.4 M-3） |
| F-5 | **编排决策器** | intent → {直连单 skill / 单 agent / DAG 工作流} 判定 + 选图 | DAG 判定准确率 ≥ 90%（20 条基准） |
| F-6 | **DAG 适配桥** | 决策器 → `dag-orchestrator/scripts/runner.py`（已有 CLI），传 YAML + inputs | 端到端跑通 ≥2 张内置图 |
| F-7 | **registry 接线** | 路由结果写入/读取 `agent-registry` 的 `AgentSpec`，`find_by_capability()` 有消费方 | 新增 ≥1 个 L2 消费者模块 |
| F-8 | **开关与降级** | 路由失败 → 回退到「当前行为」（全量目录注入），不阻断主链路 | 故障演练：索引不可用时主链路可用性 100% |

### 3.2 Should（v1.1，本期不做）

| ID | 功能 | 理由 |
|---|---|---|
| S-1 | 语义向量检索（embedding 召回） | 需评估 embedding 服务（当前 llama.cpp 按需起停）；先用词法+结构召回验证收益 |
| S-2 | 学习式排序（历史成功样本反馈） | 需先积累 v1.0 的真实调用日志 |
| S-3 | 多运行时路由（按 `AgentSpec.runtime` 分流） | 当前唯一运行时 OpenClaw（`00-system-architecture.md` §1.1）；契约预留即可 |
| S-4 | 并发 DAG 的跨层 trace 贯穿 | 等 `telemetry` 组件（✅ 已实现）接入 |

### 3.3 Won't（明确排除）

| ID | 排除项 | 理由 |
|---|---|---|
| W-1 | 不自研底层并发/限流/队列/嵌套深度控制 | **原生优先铁律**（`00-system-architecture.md` §1 / §1.3）：OpenClaw 已有这些原语，L2 只做原生之上的编排 |
| W-2 | 不替换 `openclaw.json` 的 `extraDirs` 加载机制 | 运行时原生能力，改它风险高于收益；本期用「注入」而非「卸载」 |
| W-3 | 不复制 `capability-registry` 已有能力 | 它是索引上游（P-8），本期是消费方 |
| W-4 | 不在本期动 `registry.yaml` / `system_full_audit.py` / `openclaw.json` | 由 Lane A/B 持有，避免并行冲突 |

---

## 4. 可度量验收标准

> 总则：所有指标必须在**真实运行**中采集（真 HTTP / 真 CLI / 真会话），禁止「读代码得出结论」。测试规范见 `00-system-architecture.md` §测试规范。

### 4.1 指标定义

| ID | 指标 | 定义 | 目标值 | 采集方式 |
|---|---|---|---|---|
| **M-1** | 检索命中率（Hit@k） | 20 条预置基准查询，人工标注正确 skill/agent；Hit@5 = 正确项出现在 top-5 的比例 | **≥ 90%**（18/20）；Hit@3 ≥ 75% | 基准集脚本 + 断言 |
| **M-2** | 误召回率 | top-5 中不含正确项的查询占比 | **≤ 10%** | 同上 |
| **M-3** | 上下文 token 降幅 | 同一基准会话，「全量目录注入」vs「top-k 注入」的 prompt token 差 | **≥ 50%** 降幅（相对基线） | tokenizer 计数（确定性、可复现） |
| **M-4** | 编排端到端耗时 | 从 intent 到 DAG 全部任务 success 的墙钟时间（含子 agent 派发） | ≤ 现有「人工描述 + 手动派发」基线的 **70%**，且单任务 P95 ≤ 5 min（对齐 SKILL.md 既有超时口径） | runner 计时埋点 |
| **M-5** | 路由开销 | 单次检索耗时（本地索引，无网络） | **P95 ≤ 200ms** | 计时埋点 |
| **M-6** | 降级可用性 | 人为破坏索引（改名/删除）后主链路仍可完成任一基准查询 | **100%**（必须回退全量目录） | 故障演练脚本 |
| **M-7** | 契约接线 | `agent-registry.find_by_capability()` 的调用点数量 | **≥ 1** 个生产调用点（非测试） | grep + 代码审查 |
| **M-8** | 运行时无关门禁 | L2 新模块中 `import openclaw` / `openclaw.*` 直接调用数 | **0** | 静态扫描门禁 |

### 4.2 基准集（20 条，验收前置产物）

先定验收标准再写实现（`00-system-architecture.md` §资产开发规范）。基准集须覆盖三类，每类至少 5 条：

- **A 类 · 单 skill 直达**：意图清晰、单一 skill 可满足（例：「转写这段会议录音」→ meeting-minutes）
- **B 类 · 多 skill 竞争**：同一意图命中 ≥3 个候选，考精排（例：「生成项目复盘报告」→ bangcle-project-retrospective vs customer-rectification-report vs system-governor）
- **C 类 · 需 DAG 编排**：需 ≥2 步且有依赖（例：「生成交付月报」→ 采集×N → 关联 → 分析 → 报告）

基准集文件：`L2-infra/components/capability-router/tests/fixtures/intent-benchmark-20.yaml`（路径以 DESIGN-OUTLINE 为准），含每条的 `expected_top1` / `expected_set` / `expected_mode`。

---

## 5. 业界最佳实践引用

> 硬性要求（`AGENTS.md`：查找业界最佳实践必须覆盖 AI Agent 官方文档、社区方案、GitHub/Clawhub 等）。以下来源均已核实可访问。

| # | 来源 | 核心结论 | 对本项目的约束 |
|---|---|---|---|
| B-1 | **Anthropic — Tool Search Tool / Tool Discovery**（官方文档）https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview | 工具**目录**不进上下文；按需**检索**最相关的 top 3–5 条再注入模型 | 直接支撑 F-3/F-4 的 top-k 设计，否决「全量注入」 |
| B-2 | **adasci.org — RAG-MCP: How Retrieval Fixes Tool Selection in AI Agents** https://adasci.org/blog/rag-mcp-how-retrieval-fixes-tool-selection-in-ai-agents | 用检索（RAG）做 MCP 工具 shortlisting，把候选集从全量压到少量再让模型选 | 支撑 F-3 的两段式（召回 → 精排）架构 |
| B-3 | **arXiv 2511.01854 — Tool-to-Agent Retrieval**（https://arxiv.org/pdf/2511.01854） | 面向「工具/子 agent 检索」的检索器训练与评测方法，含 Hit@k / MRR 口径 | 支撑 §3.4 的 Hit@k 口径与基准集构造方法 |
| B-4 | **Scaling Enterprise Agent Routing**（alphaXiv）https://alphaxiv.org/abs/2606.17519 | 规模退化实证：**584 工具下 F1 降 16.1pp**，退化模式为 recall-driven（漏选为主） | 量化「为什么必须做路由」；并提示**不能只追 precision**，须保 recall → M-2 设上限而非只设命中率 |
| B-5 | **TrueFoundry — Agent Harness Best Practices** https://www.truefoundry.com/blog/agent-harness-best-practices | 延迟加载工具 schema（lazy-load tool schemas）、上下文 **compact 而非 truncate**、harness 层统一治理 | 支撑 F-4 的「增量注入」；并明确本层属 harness 职责，不越层做压缩算法本身 |
| B-6 | **OpenClaw 官方 Skills 文档** https://docs.openclaw.ai/tools/skills | Skill 组织方式、单会话准入上限 **64**、`openclaw skills` CLI | 硬约束：本层输出必须显式适配 64 上限（P-4） |
| B-7 | **OpenClaw 官方 CLI 文档** https://docs.openclaw.ai/cli/skills | `skills list/info/check/curator` 子命令能力 | F-1 索引构建器可复用 `openclaw skills list --json` 作为数据源之一，避免重复造 |

---

## 6. 备选取舍（≥2，含否决理由）

### 6.1 取 A：top-k 精排注入 —— vs B：全量目录注入（现状）vs C：仅黑名单过滤

| 方案 | 做法 | 优点 | 致命缺点 |
|---|---|---|---|
| **A（采纳）** | 索引 + 召回 + 精排 → top-k 增量注入 | 上下文可控、可度量、与 B-1/B-2 一致 | 需建设索引与基准集，有冷启动成本 |
| B（现状） | 全量 skill 文本进上下文 | 零建设成本 | 规模退化（B-4 实证）；token 不可控；64 上限下更糟 |
| C | 只维护「不加载」黑名单 | 改动最小 | 治不了根本：702 行里仍有大量弱相关项；无正选能力，recall 靠模型自觉 |

**结论**：采纳 A。C 作为 F-8 降级路径的一部分保留（回退时退化为 C 的语义）。

### 6.2 取 A：并入 L2 横切编排 —— vs B：独立新横切层

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A（采纳）** | 作为 L2 组件（`L2-infra/components/capability-router/`），依赖 L1 契约 | 符合 §1 分层；复用 L2 既有测试/门禁；`dag-orchestrator` 本就在 L2 | 需在 L2 内划清与 registry 的边界 |
| B | 新开「L2.5 路由层」 | 边界最干净 | 破坏四层结构（§2）；多一层就多一份契约与文档负担；无收益 |

详细对比与结论见同批 `DESIGN-OUTLINE-*` §1。

### 6.3 取 A：编排器复用 `dag-orchestrator` —— vs B：另建编排引擎

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A（采纳）** | 只做「上游决策 + 适配桥」，执行仍走 `runner.py` | 零重复建设（W-1/W-3）；引擎已过 34 用例；有 VERIFICATION | 受既有 YAML 契约约束 |
| B | 新建轻量编排器 | 可完全贴合路由输出 | 违反「复用优先」（`00-system-architecture.md` §1）；`customer-delivery-intelligence` PRD 已明确「引擎不建」 |

---

## 7. 交付物清单

| # | 交付物 | 路径 |
|---|---|---|
| D-1 | 本 PRD | `docs/architecture/PRD-capability-routing-orchestration-layer-v1.0.md` |
| D-2 | 设计大纲 | `docs/architecture/DESIGN-OUTLINE-capability-routing-orchestration-layer-v1.0.md` |
| D-3 | 架构决策记录 | `docs/architecture/adr/ADR-202611-0NN-capability-routing-orchestration-layer.md`（编号见 ADR） |
| D-4 | 基准集（验收前置） | `L2-infra/components/capability-router/tests/fixtures/intent-benchmark-20.yaml` |
| D-5 | 索引构建器 + 检索器 + 决策器 + 适配桥 | `L2-infra/components/capability-router/` |
| D-6 | 验收文档 | `docs/architecture/VERIFICATION-capability-routing-orchestration-layer-v1.0.md` |

---

## 8. 开放问题（需 Rex 拍板）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| Q-1 | `L0-gateway` 三组件：落地 / 正式移交运行时原生通道 / 维持骨架？ | 决定 ADR 专节结论与后续是否投入 | 建议「正式移交 + 归档为参考设计」（见 ADR） |
| Q-2 | 基准集 20 条由谁定标（含 B 类争议项的系统口径）？ | M-1/M-2 的可信度完全取决于此 | 建议 Rex 指定 1 名业务口径负责人 |
| Q-3 | top-k 的 k 是否按会话类型动态（如 dashboard vs webchat）？ | 影响 F-3 复杂度与 M-3 | 建议 v1.0 固定 k=5，S-2 再谈自适应 |
| Q-4 | 是否允许把自建 28 skill 从 `extraDirs` 中摘除、改为路由后按需注入？ | 会动 `openclaw.json`（本期禁改） | 建议 v1.0 **不动**，仅叠加注入层，v1.1 再评估 |
| Q-5 | `agent-registry` 的持久化后端（当前纯内存）是否需要落地？ | M-7 只要求「有消费者」，未要求持久化 | 建议 v1.0 接受内存态，登记为独立缺口 |
