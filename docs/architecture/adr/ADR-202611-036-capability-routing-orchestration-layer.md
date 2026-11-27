# ADR-036：能力路由与编排层（Capability Routing & Orchestration Layer）

> 状态：**proposed**
> 日期：2026-11-27
> 决策人：Rex（待拍板）
> 提案人：Lane D

## 背景

### 1. 实测现状（2026-11-27，全部可复核）

| # | 事实 | 取证 |
|---|---|---|
| C-1 | 自建 skill **28 个**（L2-infra 10 + L3-business 7 + L4-proprietary 11） | `ls` 目录计数 |
| C-2 | OpenClaw 可用 skill 清单 **702 行**（OpenClaw 2026.9.8 fc23bc8） | `openclaw skills list \| wc -l` |
| C-3 | 三个自建 skill 目录经 `skills.load.extraDirs` **整目录加载**，无逐条准入 | `~/.openclaw/openclaw.json` L762-765 |
| C-4 | OpenClaw **单会话 skill 准入上限 = 64** | 官方文档 https://docs.openclaw.ai/tools/skills |
| C-5 | `dag-orchestrator` **无生产调用方**：全仓 11 处引用全在自身目录、registry 登记或描述性提及；`customer-delivery-intelligence` PRD:100 明写「编排范式参考（引擎不建）」 | `grep -rln dag.orchestrator` |
| C-6 | `L0-gateway` 三组件**零业务落地**：仅 README+DESIGN+`src/` 骨架（1,488 行 Python，含 46 行 `__init__.py`）+ 单测骨架（28 用例，文件均 `test_*_skeleton.py`） | `find` + `wc -l` |
| C-7 | `agent-registry`（L1）为**骨架阶段 v0.1**，`InMemoryAgentRegistry` 已实现但**无任何 L2-L4 消费方** | `src/registry_impl.py` + README §3 |
| C-8 | 能力索引上游已存在：`capability-registry/registry.yaml` **84 条目** | `grep -c '^  - id:'`（Lane A/B 处理中） |

### 2. 结构性问题

**系统有能力目录、有能力注册表、有执行引擎，但三者之间没有「路由」与「编排」层。** 表现为四个缺口：

1. **检索缺口**：全量目录进上下文，模型在噪声中自选。业界实证：584 工具下 F1 降 **16.1pp**，退化模式为 **recall-driven**（漏选为主）— *Scaling Enterprise Agent Routing* https://alphaxiv.org/abs/2606.17519 （已核实）。
2. **上下文缺口**：堆量而非精排注入。Anthropic Tool Search Tool 结论为「工具目录不进上下文，按需检索 top 3–5」（https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview ，已核实）；adasci.org RAG-MCP 亦主张用检索做 shortlisting（https://adasci.org/blog/rag-mcp-how-retrieval-fixes-tool-selection-in-ai-agents ，已核实）。
3. **编排缺口**：`dag-orchestrator` 有完整引擎（loader/graph/executor/artifact_store/state/runner/viz + 可插拔 dispatch）但**没有上游**——无人替它决定「该不该走 DAG、走哪张图」。
4. **契约缺口**：`agent-registry` 定义了 `AgentSpec`/`find_by_capability()`/`instantiate()` 却从未被调用；`L0-gateway` 三段管道零落地。链路两端都断着。

### 3. 架构约束（决策必须满足）

- **原生优先铁律**（`00-system-architecture.md` §1 / §1.3）：运行时已有的并发/限流/队列/嵌套深度/会话管理一律复用，L2 只做原生之上的编排。
- **分层自治**（§1）：L2 依赖 L1 + 其他 L2，禁止跨层。
- **运行时抽象**（§1 / ADR-012）：L2-L4 禁 `import openclaw`、禁调 `openclaw.*`（§3.2.3 编码规范）。
- **治理横切不是独立层**（§1 / §4）。
- **演进可逆**（§1）。

## 决策

### 决策 1：新建 L2 基础设施组件 `capability-router`（层归属）

**采纳**：作为 **L2 基础设施组件**落地于 `L2-infra/components/capability-router/`，与 `dag-orchestrator`（L2 skill）同层；对 L3/L4 暴露查询契约。

**理由**：

1. 被编排对象 `dag-orchestrator` 已在 L2（其 SKILL.md 头部明写「层级：L2 基础设施层」）。放 L1 会反向依赖 L2，违反分层自治；放独立层会新增跨层契约。
2. 「治理横切」性质上贯穿各层而非独立成层（§1/§4）；路由属「原生之上的编排逻辑」，正属 L2 职责（§1.3）。
3. 最小变更：不改动四层结构，只在 §3.3 组件表补一行。

**模块划分**（outline 级，详细设计另出 `DESIGN-v1.0.md`）：

| 模块 | 职责 |
|---|---|
| `index_builder` | 扫描 28 自建 skill front-matter + registry.yaml → 归一化 `CapabilityRecord` 索引 |
| `intent` | 自然语言 → 能力需求列表 + 槽位（规则优先） |
| `retriever` | 召回 + 精排 → top-k（默认 k=5） |
| `injector` | 把 top-k **增量**渲染进上下文（不做 truncate） |
| `planner` | mode ∈ {skill, agent, dag} 判定 + 选图 |
| `dag_bridge` | plan → 调 `dag-orchestrator/scripts/runner.py`（现有 CLI，不改） |
| `registry_client` | 读写 `AgentSpec`，调 `find_by_capability()`/`instantiate()` |

**核心抽象**：`CapabilityRecord`（运行时中立）——`id/name/description/capability_tags[]/trigger_hints[]/entry_ref/runtime_requirement/source`。字段不含任何运行时专有概念；切换运行时只需新增 adapter。

### 决策 2：编排器复用 `dag-orchestrator`，不自建引擎

**采纳**：本层只提供**上游**（意图 → 选图 + inputs 绑定），执行仍走既有 `runner.py`。

**理由**：零重复建设（原生优先铁律 + 复用优先原则）；引擎已过 **34 用例** 且有 VERIFICATION v1.1；`customer-delivery-intelligence` PRD 已明确「引擎不建」。违反将直接触发 W-1/W-3 排除项。

### 决策 3：降级回退到现状行为（安全网）

**采纳**：`index_builder` 失败 / 检索异常 / 命中为空 → 一律回退「全量目录注入」= 当前生产行为，主链路不中断。总开关在 `config/router-policy.yaml`。

**理由**：新层不允许把主链路变成单点故障；这是「可逆性」的硬要求（PRD M-6 要求降级可用性 100%）。

## 备选方案

| # | 备选 | 否决理由 |
|---|---|---|
| A1 | **独立「L2.5 路由层」** | 制造第五层，破坏 §2 全景图；把横切关注点误当独立层；多一层即多一套契约/门禁/文档，无收益 |
| A2 | **下沉为 L1 组件** | 需反向依赖 L2 的 `dag-orchestrator`，违反 L1 只依赖自身抽象契约的定位（§3.2.5）；L3/L4 直连 L1 组件不合分层 |
| A3 | **维持全量目录注入 + 黑名单过滤** | 治不了根本：702 行清单中仍有大量弱相关项；无正选能力，recall 无法保障（B-4 实证 recall 才是退化主因） |
| A4 | **另建轻量编排引擎** | 违反复用优先（§1）；重复造轮子；与 `customer-delivery-intelligence` PRD 的明确口径冲突 |
| A5 | **直接修改 `openclaw.json` 摘除 28 个自建 skill 的 `extraDirs`** | 会动运行时配置（本期禁改）；且丢失 fallback 通路，不可逆风险高；建议 v1.1 再评估（PRD Q-4） |
| A6 | **语义向量检索（embedding 召回）一步到位** | 需引入 embedding 服务（当前 llama.cpp 按需起停，运行时不确定）；先用词法+结构召回验证收益，v1.1 再做（S-1） |

## 后果

### 正面

- 技能选择从「模型自觉」变为**可度量工程**（Hit@k / token 降幅 / 端到端耗时）。
- `dag-orchestrator` 获得真实上游，结束空转（C-5）。
- `agent-registry` 获得生产消费者，结束骨架态（C-7）。
- 上下文成本可控，规避 584+ 工具规模的 recall 退化区间。

### 负面 / 代价

1. **新增一条冷启动链路**：索引构建 + 基准集定标（20 条）需要人工投入，且基准集质量直接决定 M-1/M-2 可信度。
2. **召回精度是新风险面**：若精排把正确项挤出 top-k，会比现状更糟（漏选不可逆）。→ 由 M-2 误召回率上限 + F-8 降级共同约束。
3. **增加一跳延迟**：本地检索 P95 ≤ 200ms（M-5），相比纯静态注入有少量开销。
4. **索引漂移维护负担**：skill 增减后需重建索引。→ 复用 `gen_asset_inventory.py` 漂移检查口径（AGENTS.md 单一事实源红线：资产文档判定统一复用 `capability_registry._asset_docs()`，禁自造匹配规则）。

### 不做的事（明确留待后续）

S-1 语义检索 / S-2 学习式排序 / S-3 多运行时路由 / S-4 trace 贯穿 —— 全部 v1.1+，见 PRD §3.2。

---

## 专门一节：L0-gateway 处置建议

> 对应 PRD 开放问题 Q-1、DESIGN-OUTLINE §4。

### 现状

`L0-gateway` 设计了三段入站管道（`auth-gateway` / `channel-router` / `session-manager`），但**只有 README + DESIGN + 骨架代码**（C-6）。而 OpenClaw 原生已实现等价能力，`00-system-architecture.md` §3.2.3 映射表逐条标注 ✅：通道接入、凭据管理、沙箱隔离、会话生命周期均为运行时原生。

### 选项对比

| 选项 | 内容 | 评估 |
|---|---|---|
| **A（建议）** | **正式移交运行时原生通道** + L0-gateway 归档为「参考设计」，状态改 📋 架构预留 | 消除悬空态；遵守原生优先铁律（不自建与运行时重叠的认证/限流/会话控制，避免两层控制打架）；`DEFECT-LEDGER` 同类「设计了没做」噪音随之收敛 |
| B | 落地三组件（1,488 行骨架生产化） | 需实现认证签发、通道适配器、会话持久化——全部与原生能力重叠；成本高、收益负、长期双轨维护 |
| C | 维持现状 | 持续产生审计噪音与误导（下游读者会以为存在可用网关） |

### 建议

**采纳 A：正式移交运行时原生通道，L0-gateway 归档为参考设计。**

**理由**：① 原生优先铁律的直接适用（W-1）；② 分层定位上，入站管道本就属运行时职责，L0 自建等于重复造轮子；③ 消除 C-6 这类「长期悬空」状态，让资产清单与实际能力一致。

### 与本层的关系

**无运行期耦合**。本层的路由发生在 **agent 会话内的 prompt 组装阶段**（出站方向），L0-gateway 处理的是 **入站认证/限流/路由**，两者正交。唯一潜在交集是「按会话类型调整注入量」，属 v1.1 自适应范畴（Q-3），本期明确不做。

### 执行前提

移交动作涉及 `L0-gateway/README.md` / `DESIGN.md` 状态标记与 `00-system-architecture.md` §3.1 表格，**须 Rex 单独确认后由 Lane 执行**，本 ADR 提案阶段不动这些文件。

---

## 生效条件

- 状态 **proposed** → Rex 拍板后置 **accepted**。
- 若 accepted：先落 `tests/fixtures/intent-benchmark-20.yaml`（验收前置）+ 基准定标（阻塞项，PRD Q-2），再写实现（`00-system-architecture.md` §7.2 强制 8 步，禁止跳步）。
- 若 rejected：保持现状（全量目录注入 + dag-orchestrator 孤立），缺口以缺陷账本条目追踪。

## 相关文档

- PRD：`docs/architecture/PRD-capability-routing-orchestration-layer-v1.0.md`
- DESIGN-OUTLINE：`docs/architecture/DESIGN-OUTLINE-capability-routing-orchestration-layer-v1.0.md`
- 上游约束：`docs/architecture/00-system-architecture.md` §1 / §3.2 / §3.3 / §4 / §7
- 业界依据：Anthropic Tool Search Tool、adasci.org RAG-MCP、arXiv 2511.01854（Tool-to-Agent Retrieval）、alphaXiv 2606.17519（Scaling Enterprise Agent Routing）、TrueFoundry Agent Harness Best Practices、https://docs.openclaw.ai/tools/skills （均已于 2026-11-27 核实可访问）
