# MEMORY.md - 系统级长期记忆

> 主会话专用的长期事实/决策记录。**不**在共享场景（群聊、其他会话）加载。
> 详见 `AGENTS.md` §Memory。

## 系统元数据

- **系统类型**: 综合开放平台
- **架构模式**: 4 层分层（L1 系统层 → L2 基础设施层 → L3 通用业务层 → L4 专有业务层）
- **基座**: OpenClaw（不可改，作为 L1）
- **知识库目标**: 自建系统（人机协作、跨系统移植），当前为 Markdown + 元数据
- **核心约束**: 基础设施层必须适配 OpenClaw 契约；专有业务必须继承通用业务层
- **AI 身份**: Jerry（太空龙虾 🦞），详见 `IDENTITY.md` / `SOUL.md`

## 关键决策

### 2026-08-21: 系统分层架构
- **决策**: 采用 4 层架构
- **理由**: 兼顾 OpenClaw 基座约束、通用能力沉淀、专有业务隔离
- **文档**: `docs/architecture/00-system-architecture.md`
- **相关 ADR**: [ADR-202608-001](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-001-four-layer-architecture.md)

### 2026-08-21: 知识库三维模型
- **决策**: 知识库按 层级(L1~L4) × 阶段(design/develop/manage) × 类别(业界/理论/经验) 三维组织
- **理由**: 支持按视角检索、避免维度混淆、人机共读
- **文档**: `docs/knowledge-base/README.md`
- **ADR**: [ADR-202608-002](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-002-knowledge-base-three-dimensions.md) (accepted)

### 2026-08-21: 经验沉淀双轨制
- **决策**: 日常用经验卡片(EXP)，架构级用 ADR
- **升级触发**: 影响 ≥2 层 / 涉及 L1-L2 契约 / 多模块对齐 / 不可逆
- **文档**: `docs/knowledge-base/by-category/project-experience/README.md`

### 2026-08-21: 知识库承载形式
- **决策**: 当前用 Markdown + 元数据；自建系统作为演进目标
- **理由**: 自建系统是 L2/L3 能力，工作量大；先验证分层与契约
- **迁移策略**: 文件形式作为导出格式保留
- **路径**: 3 阶段 (Markdown 验证期 → 工具链增强期 → 自建系统期) + 7 触发条件
- **ADR**: [ADR-202608-003](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-003-knowledge-base-evolution-path.md) (accepted)
- **层级归属**: 自建系统是 L2 基础设施能力（不是 L3 业务能力）

## 用户偏好

详见 [`USER.md`](./USER.md)。关键点：
- 身份：Rex，全职，全栈+管理，Python 为主
- 语言：中英混合（叙述中文，代码/命令/文件名英文）
- 拍板点：不可逆才停
- 群聊：工作项目可代发，个人项目不可
- Don'ts：凭据不写文件 / 不假设 / 群聊不透露 MEMORY / 不自动对外副作用

## 活跃项目

- [项目 A: 系统初始化] — 当前阶段
  - 状态: **L2 12 组件设计齐备,10 个已上线 + 2 个 cron 驱动型待重建 + L4 首个组件已注册**（08-26 cron 全清）
  - 已上线: 可观测性 004 / 凭据 005 / 持久化 006 / 上下文管理 / 配置管理 007 / 工具策略 008 / 记忆语义检索 009 / 沙箱隔离 / 模型调度 / **Office 文档生成 011**
  - 待重建(cron 已清除,设计保留): 会话生命周期管理(ADR-013) / 错误自动处理(ADR-014)
  - 下一里程碑: **L3 合同管理维度角色完善** —— 合同经理 + 法务审查员角色已定义，可基于 SCA 经验迭代
  - 文档: `docs/architecture/` (v2.7), `docs/knowledge-base/`
  - **已完成**: agent 重建 + cron 全清 + 心跳重建 + 架构文档对齐（v2.4）commit `2c3c138`
  - **已完成**: L3 全量 14 维度 + 跨境电商 + 全量盘点 commit `56b9376`
  - **已完成**: OpenMAIC 迁移至 /Users/bangcle/OpenMAIC（独立项目）
  - **已完成**: **Office 文档生成能力** — 6 库实测 + ADR-016 + DESIGN.md + 架构 v2.7 同步 commit `82739e7` / `b3e6ca8`
  - **已完成**: **L4 Bangcle PPT 模板系统** — 深度解析官方模板 + ADR-017 + DESIGN.md(398行) + skills/bangcle-ppt 技能 + 架构 v2.8 同步 commit `b27c154`
  - **已完成**: **L4 销售合同审批模块 SCA-001** — 分级审批流程 + 风险扫描(民法典13项) + 合同生成(docx) + 审计追踪 + ADR-018 + DESIGN.md(292行) + contract-approval skill + 架构 v2.10 同步 commit `63c3a49`
  - **已完成**: **合同审批报告 Excel v3 优化** — 顶部摘要+颜色标注 / P0-P2三级风险分级 / 整改建议按优先级排序 / Sheet1合同基本信息概览 / Sheet2分类统计 / 集成到 contract-approval skill 可一键生成
  - **已完成**: **合同审批分析文档 v3.1 三件套** — 全文逐字拆解(100%覆盖21段) + 统一审核标准(34项) + 逐条审核整改建议(8高/9中/3低) — generate_full_analysis.py 一键生成，输出到 contracts_output/analysis_v3/
  - **已完成**: **L2 OCR 文档数字化组件 OCR-001** — 扫描件/图片→高精度文本，RapidOCR主+Paddle可选，600DPI+8版本预处理+版面分析+合同40+规则纠错。ADR-023 + DESIGN.md + contract_ocr.py v4 + 架构v2.11。10页扫描件实测通过（聚信得仁采购合同）
  - **已完成**: **FIN-L4 M1-M4 全部里程碑** — M1 骨架+数据层+8服务+Web UI+CLI ✅ / M2 智能分类+预算+CSV导入 ✅ / M3 贷款/保险/投资深度 ✅ / M4 导出+CLI+Skill ✅
  - **当前**: M5 打磨中（全量测试 77/77 通过，待 UI 优化 + 知识库配套文档）
  - **已完成**: **PPT 能力深度调研** — 三项核心能力(表格/流程图/图标)验证通过 + 高级能力(126形状/阴影/透明度)验证 + 业界8方案对比 + EXP-018 commit `9ce3163`
  - **阻塞中**: WeCom 每日观测摘要投递（缺 Agent mode 凭据 corpId/corpSecret/agentId）

## 经验沉淀

_(将由 `docs/knowledge-base/by-category/project-experience/` 自动汇聚)_

## 经验沉淀

### 2026-08-21: Tavily 显式工具解锁
- **方案**: `tools.alsoAllow: ["tavily_search", "tavily_extract"]` — 保留 `profile=coding`，最小变更补充
- **原因**: Tavily plugin 的 `contracts.tools` 与 `Capabilities` 是不同注册路径；alsoAllow 走 tool registry 而非 capability
- **验证**: CLI agent 实际调用成功，advanced 参数被尊重
- **卡片**: `docs/knowledge-base/by-category/project-experience/correct/EXP-20260821-001-tavily-tools-also-allow.md`
- **监控点**: plugin 升级时重新验证 `tavily_search` 可用性 + `openclaw plugins inspect tavily` 检查 capabilities

### 2026-08-21: 凭据管理通用化
- **方案**: 文件存储 + SecretRef provider + 标准生命周期（add/rotate/revoke/audit）
- **原因**: Tavily 和 GitHub 已有不一致的凭据管理方式，需要统一规范
- **关键组件**: `~/.openclaw/secrets/INDEX.md` + `scripts/credentials.sh`
- **ADR**: [ADR-202608-005](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-005-credential-management.md) (accepted)

### 2026-08-21: 持久化适配
- **方案**: SQLite + Repository 模式 + 版本化迁移
- **原因**: L3/L4 业务维度需要结构化数据基础
- **演进路径**: sqlite3 stdlib → SQLAlchemy Core → PostgreSQL
- **ADR**: [ADR-202608-006](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-006-persistence-adapter.md) (accepted + 已实现)

### 2026-08-21: compaction 模型委托（跨模型会话溢出修复）
- **问题**: 会话在 LongCat（1049k）累积 252k 后切到 `ark-code-latest`（200k），对话与 `/compact` 双双死锁
- **方案**: `agents.defaults.compaction.model` + `memoryFlush.model` = `longcat/LongCat-2.0`，`notifyUser: true`
- **原则**: compaction 模型应始终指向全局最大 ctx 模型，与会话模型解耦
- **否决**: 不给 `ark-code-latest` 声明 1049k —— 它是 Auto 调度模式，真实容量取路由池最小值（200k）
- **单点风险**: LongCat key 失效 → compaction 整体失效，备选 `coding-plan/deepseek-v4-flash`（1049k）
- **卡片**: `docs/knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md`

### 2026-08-21: 自动上下文管理配置（系统层）
- **方案**: 三层防线 — auto-compaction + session pruning + mid-turn precheck
- **compaction 配置**: mode=safeguard, keepRecentTokens=30k, maxActiveTranscriptBytes=20mb, midTurnPrecheck=true
- **contextPruning**: mode=cache-ttl, ttl=5m
- **架构文档**: `docs/architecture/00-system-architecture.md` v0.3 新增 L2 上下文管理组件
- **设计原则**: 系统层解决上下文溢出，不依赖人工 /compact 或 /reset
- **模型自治**: 各模型在自身 contextWindow 内独立处理压缩，不委托外部模型（死锁问题通过校准 ctx 解决）

### 2026-08-22: 记忆语义检索 — 本地 GGUF embedding
- **问题**: `memory_search` 静默降级为 keyword-only（`provider: "none"` + `degradedTo`），系统指令强制先搜再答，但它不报错，只是中文同义召回失效
- **方案**: `@openclaw/llama-cpp-provider` + `memory.search.provider: "local"`，模型 `embeddinggemma-300m`（768 维）
- **关键依据**: 官方文档「**显式远程 provider 不可用时 fail closed**」→ 「远程为主 + 本地兜底」是错的（远程挂了比降级更糟），**本地必须是主 provider**
- ~~**火山 embedding 实测不可用**: `/api/v3` 报 `InvalidEndpointOrModel.NotFound`（模型未开通）、`/api/coding/v3` 报 `UnsupportedModel`（**Coding Plan 不含 embedding**，需单独开通+计费）~~ ⚠️ **2026-08-24 证伪，此条为假事实**：Coding Plan **本身就含** embedding，无需单独开通、无额外计费（消耗套餐额度）。唯一可用模型是 `doubao-embedding-vision-251215`（走 `/api/coding/v3/embeddings`，dims=2048，实测 OK）。当时报错是因为**我把模型 ID 写错了**（试的全是 `-text-` 系列文本模型，Coding Plan 内不可用）。真正的阻塞在别处 —— 见下方 2026-08-24 条目
- **验证**: 查「密钥泄露到开源仓库」→ `USER.md#L103` textScore=**0** / vectorScore=0.691，纯向量召回
- **两个禁忌**: ① 模型文件名必须为 `hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf` ② **不可设** `local.modelPath` 绝对路径（否则索引身份与 gateway 永久不匹配）
- **网络**: `huggingface.co` 不可达（HTTP 000）→ 用 `hf-mirror.com`；自动下载会**静默无限挂起**而非报错
- ⚠️ **2026-08-23 修正核心论证**：原写「选 local 就消除了静默降级」**错误**。官方 `concepts/memory-search.md:118-121` 明确 `provider: "local"` 同样会静默退回 keyword-only。风险未消除，只是触发条件从「缺 key/网络」换成「模型文件被改名/插件失效」。ADR-009 新增决策 4（provider 实际值监控）
- **ADR**: [ADR-202608-009](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-009-memory-embedding-provider.md) (accepted + 已实测)

### 2026-08-21: contextWindow 校准
- **问题**: 4 个模型因未显式声明 `contextWindow`，走 OpenClaw 默认 200k，被严重低估
- **调整**: glm-5.3 200k→1M, kimi-k2.7-code 200k→262k, minimax-m3 200k→1M, ark-code-latest 200k→262k
- **依据**: arkcli models search/get + 官方文档（HuggingFace/MiniMax/火山引擎）
- **原则**: 显式声明 ctx 优于依赖默认值；Auto 类模型取路由池最小值

### 2026-08-23: 全盘 review — 选择性引用官方文档导致 ADR 论证错误 ★- **背景**: L2 七组件建成后首次全盘核对，四路并行，发现 13 项偏差
- **关键分类**: 13 项里**只有 2 项是真错误**，其余为结构性漂移（系统在动 4 / 建设快于文档 5 / 官方缺口 2）
- **真错误 A（方法论）**: ADR-009 引用官方时读到支持自己的那句就停了 —— confirmation bias。规则：**引用官方文档作决策依据必须读完相关章节全文**，至少交叉 `concepts/` + `reference/` 两处
- **真错误 B**: 架构文档写「各模型自治」但实配 `compaction.model` 委托 —— 决策反复两次，文档只跟了第一次
- **治理新发现**: self-learning 自动生成 3 个技能未经审批（`autonomous.mode` 与 `approvalPolicy` 官方默认均 `auto`，而 `workspace/skills` 是最高优先级源）
- **`plugins.allow` 是严格白名单**: 设置后 enabled 插件 57→5，改后必须逐项验证依赖能力
- **审计工具有漏报**: `channels.wecom.secret` 不在官方 SecretRef 覆盖矩阵内（第三方插件渠道）
- **卡片**: `EXP-20260823-009-review-selective-citation-and-drift-taxonomy.md`

## 变更历史

- 2026-08-21: 初始化
- 2026-08-21: 补 EXP-20260821-001 经验沉淀
- 2026-08-21: 补 EXP-20260821-002 (GitHub 凭据) + 3 份 ADR accepted + 首次推送 GitHub
- 2026-08-21: 可观测性适配 + 凭据管理通用化 + 持久化适配设计
- 2026-08-21: 补 EXP-20260821-003（compaction 模型委托），修复跨模型会话溢出死锁
- 2026-08-22: L2 建设收官 — 配置管理(007) + 工具策略治理(008) + 记忆语义检索(009)；修复公开仓库归属标识泄漏风险；架构文档 v0.6
- 2026-08-23: 知识库工具链(010) + 阶段 3 评估（0/7 → 暂缓自建）
- 2026-08-23: 5 个孤儿 LaunchAgent 清除（含 2 个存活 16–17 天的幽灵进程），释放 ~858MB；服务层首次入档（架构文档 §8.1.1）
- 2026-08-23: **全盘 review + 14 项修复** — ADR-009 论证纠错、凭据迁 SecretRef（5→1 处明文）、`plugins.allow` 收紧、self-learning 降为 propose、技能四合一；架构文档 v0.8

### 2026-08-23 第二轮 review：用启发式代替证据的三种同源错误 ★★★

- **背景**：Rex「不要留任何潜在隐患」→ 四路并行审计。但**最重要的发现是自查出来的**
- **错误 1（最严重）**：上一轮写进 memory 的「明文 5→1」**有三条是假的** —— 把「讨论过的 5 处」当成「执行过的 5 处」。技术隐患可再修，**假记忆污染后续所有决策**
- **错误 2**：`models.json` 的 apiKey 看长度 17 就判「仍是明文」—— 它**完全等于**官方非密标记 `secretref-managed`（`secretref-credential-surface.md:138` + `concepts/models.md:248-249`）。反而是迁移**生效的证据**，`secrets audit` 属误报
- **错误 3（引入真回归）**：`channels.wecom.secret` 迁 SecretRef —— `dry-run` 通过但运行时报 `account.secret?.trim is not a function`（core `dist/channel-B2DGqAWl.js:1799` 无条件调 `.trim()`），`accounts.default` 被降级判为 unconfigured。**已回退**
- **三者同源**：用启发式（我打算做 / 长度像凭据 / dry-run 通过）代替证据。与 EXP-009（选择性引用）是**同一病灶的更早期形态**
- **官方矩阵的缺席是信号**：wecom 不在 SecretRef 覆盖矩阵内是**有原因的**，不要当成「文档没写但能用」
- **真隐患（公开仓库）**：`snapshot_config.py` 纯 key 名精确匹配，`GROQ_API_KEY` 类命名全漏网（注入测试 6/7 泄漏）。已加值形态兜底，双向测试泄漏 0/8 + 误脱 0/12。当前快照清白是 **SecretRef 侥幸绕开缺陷**，非设计
- **`contextPruning` cache-ttl 是死配置**（dist 源码铁证）：`buildContextPruningFactory` 在 provider 白名单校验处提前 return。三层防线**实为两层**
- **`tools.elevated` 治理前提错**：sandbox 默认 `off` ⇒ elevated 是 **no-op**，exec 本就在 host。真正有效的是 `tools.deny` + `tools.toolsBySender`
- **审计工具自身也误报**：subagent 报「4 个脚本缺 `set -e`」—— 它只 grep 了前 8 行，`set` 在 13~16 行；且两个审计脚本省 `-e` 是**正确设计**（靠 grep 返回码判断检查项）
- **卡片**：`EXP-20260823-010-heuristics-instead-of-evidence.md`
- 2026-08-23: **第二轮 review + 9 项修复 + 2 项误报辨正** — 记录造假纠正、WeCom SecretRef 回退、脱敏值形态兜底、cache-ttl 死配置结案、elevated 前提重写、`group:ui` 三处查清、ADR-005 同步、pre-commit 去吐错
- 2026-08-23: **sandbox.mode 暂缓** — 推荐 `non-main` 但 Docker/openshell/ssh 均不可用，设了反而破坏 WeCom 会话。需先装 backend
- 2026-08-23: commit `0385d47` — 第二轮 review 11 files +567/-49，已 push
- 2026-08-23: **gateway.auth.token → SecretRef** — 最后 1 处可迁明文，`secrets audit: plaintext=0`，commit `6ee998e` 已 push。仅剩 `channels.wecom.secret` 因 core `.trim()` 不兼容留明文
- 2026-08-23: **记忆+技能加密备份** — `~/.openclaw/backups/memory-snapshot/` 2 个 .enc 文件（memory+skills），AES-256-CBC 加密，已验证可解密。40KB 总占用

### 2026-08-24: 上下文压缩失效根因 + 「目录 ≠ 权限」第三次同源错误 ★★★

- **压缩失效四环事故链**（非配置错误）：① sticky model selection 静默把 `agents.defaults.model.primary` 改成 `longcat/LongCat-2.0` ② `compaction.model` **也**指向 LongCat ③ LongCat 网络故障（09:00~09:24 连挂 4 次）④ 显式 `compaction.model` **按官方设计不继承 fallback 链**（`concepts/compaction.md:101`）⇒ 会话与压缩同时死在一个 provider 上且拿不到兜底
- **反模式定案**：`compaction.model` 指向**另一个 provider** 制造「会话活着但压缩死了」的分裂故障。今天 ARK 全程 200 正常、LongCat 挂，整会话卡死。**压缩模型应与主会话同 provider**，共享同一条网络/鉴权命运。修正 EXP-003 的方案
- **`compaction.fallbacks` 是非法字段**（schema 拒绝）—— 官方要它 exact，所以正解是**换掉 model 本身**而非加兜底
- **sticky model selection 机制**（读 dist）：`/model` 切换会写配置文件；agent 无显式 model ⇒ 落 `agents.defaults.model`（全局默认）；有显式 model ⇒ 写 agent 层不碰 defaults（`agent-scope-rpcTIxC8.js:220-248`）。触发条件含 `senderIsOwner` ⇒ Rex 每次切都触发；`BestEffort` 是 fire-and-forget，失败只 `log.warn` ⇒ 静默。**修复：配 `agents.entries.main.model` 隔离**，实测切 minimax-m3 后 defaults 未被改写
- **`memory_search` 会「全面停摆」而非降级**：`disabled:true` + `index sources changed`，而 `memory status --index` **报一切正常**（393 chunks/ready/768 dims）。status 与实际能力不一致，比 ADR-008 三态模型更隐蔽。修复 `memory index --force`
- **★ 「平台目录 ≠ 当前套餐权限」**：`arkcli models search embedding` 列出 3 个 embedding 模型，我据此认定文本模型可用，连试 4 个全 NotFound，两轮结论「Coding Plan 不含 embedding，需单独开通付费」。**真相：Coding Plan 本就含 embedding（消耗套餐额度，非额外计费），但唯一可用模型是 `doubao-embedding-vision-251215`**（`/api/coding/v3/embeddings`，dims=2048，实测 OK，语义自测相关 0.53 vs 不相关 0.18）。套餐可用性只能查**该套餐的专属权益文档**
- **这是与 EXP-009（选择性引用）、EXP-010（启发式代替证据）同源的第三次形态**：拿一个**邻近但不等价**的信息源（全量目录）代替真正的权威源（套餐权益文档），且**未验证等价性**
- **假记忆已纠正**：`MEMORY.md` 曾写「需单独开通+计费」，Rex 澄清后就地标注证伪。按 EXP-010 教训，**假记忆污染后续决策，优先级高于技术隐患**
- **火山 embedding 真实阻塞**：OpenClaw 单请求发 81 条，火山硬上限 10 条。`embedding-provider-DQt_MtNJ.js:24-58` 的 `embedBatch` **原样透传不分片**；`manager-DSpvP_Or.js:3470-3506` 有自动二分机制，但 `:864` 的 `SPLITTABLE_…RE` **只认传输层错误**（ECONNRESET/EPIPE/socket hang up），HTTP 400 不匹配 ⇒ 不分片直接抛。全局 grep **无任何 `batchSize`/`maxInputsPerRequest` 配项** ⇒ 无配置可解。**已回退本地，Rex 拍板保持现状**
- **供应链**：4/4 插件钉版本 + integrity 全绿。审计读的是 **SQLite `installed_plugin_index` 表的 `spec` 字段**（不是 package.json，后者本就精确），修法 `plugins install <pkg>@<exact> --force`。`openclaw-weixin` 已卸载（先确认 WeCom 跑的是 `wecom-openclaw-plugin`）
- **卡片**：`EXP-20260824-011-catalog-is-not-entitlement.md`
- 2026-08-24: **上下文压缩失效根因定案** — compaction 跨 provider 单点 + sticky 静默改全局默认；改同 provider `deepseek-v4-flash`、加 fallbacks、cron 钉模型（force run ok）、`pruneAfter=48h`、会话 19→6；commit `f03c464`
- 2026-08-24: **sticky 隔离 + 供应链加固** — `agents.entries.main.model` 实测阻断 defaults 污染；4/4 插件钉版本+integrity；卸载 `openclaw-weixin`；security audit 3 WARN→1；commit `2cc185e`
- 2026-08-24: **火山 embedding 结案（保持本地）** — Coding Plan 本就含 embedding（未单独付费），唯一可用 `doubao-embedding-vision-251215` 实测 dims=2048 语义正常，但 OpenClaw 发 81 条/火山限 10 条且无配项可解，已回退 `provider: local`（406 chunks / vectorScore 0.691 验证通过）

## Promoted From Short-Term Memory (2026-08-26)

<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:30:48 -->
- **核对 01-asset-inventory.md**: 8 cron / 5 agent / 4 plugins / 14 ADR / 12 EXP / 504 chunks 记忆检索 / 24 记忆文件全部对得上。 - **memory_search 健康**: local provider, 504 chunks / 768 dims / FTS ready / Dirty: no。 - **git**: 最新 commit `71c75d9`,已 push 待确认。 - **备份**: memory-snapshot 2 个 .enc 加密备份在 `~/.openclaw/backups/memory-snapshot/`。 - **配置快照**: 已重新生成,含 model-scheduling auto model contextWindow=229376 + agents.entries.main.model.primary=model-scheduling/auto。 - **已解决(09-04)**: "每日观测摘要投递" cron 任务已不存在；WeCom 报告由其他 4 个 cron 承担（错误扫描/健康探测/错误自动处理/生命周期管理），投递到 wecom:1313 正常。原"缺 Agent mode 凭据"记录已过时。... [score=0.843 signals=12 recalls=12 avg=0.756 source=memory/2026-08-25.md:30-39] <!-- trigger: backup, backups, 备份 --> <!-- importance: 8 --> <!-- project: github.com/RenLimin/openclaw-v5.0 -->
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:130:148 -->
- **核对 01-asset-inventory.md**: 8 cron / 5 agent / 4 plugins / 14 ADR / 12 EXP / 504 chunks 记忆检索 / 24 记忆文件全部对得上。 - **memory_search 健康**: local provider, 504 chunks / 768 dims / FTS ready / Dirty: no。 - **git**: 最新 commit `71c75d9`,已 push 待确认。 - **备份**: memory-snapshot 2 个 .enc 加密备份在 `~/.openclaw/backups/memory-snapshot/`。 - **配置快照**: 已重新生成,含 model-scheduling auto model contextWindow=229376 + agents.entries.main.model.primary=model-scheduling/auto。 - **已解决(09-04)**: "每日观测摘要投递" cron 任务已不存在；WeCom 报告由其他 4 个 cron 承担（错误扫描/健康探测/错误自动处理/生命周期管理），投递到 wecom:1313 正常。原"缺 Agent mode 凭据"记录已过时。... [score=0.822 signals=8 recalls=8 avg=0.753 source=memory/2026-08-25.md:130-139] <!-- trigger: backup, backups, 备份 --> <!-- importance: 8 --> <!-- project: github.com/RenLimin/openclaw-v5.0 -->
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:190:206 -->
- **已解决(09-04)**：每日观测摘要投递已不存在，WeCom 报告由其他 cron 承担。L3/L4 业务层暂缓；自建知识库系统 0/7 暂缓。 ## DESIGN.md 状态统一 + cron 重跑机制 + 备份机制落地（14:00-14:30） [score=0.793 signals=6 recalls=6 avg=0.695 source=memory/2026-08-25.md:190-193] <!-- trigger: network, 备份, l3/l4 --> <!-- importance: 8 --> <!-- project: github.com/RenLimin/openclaw-v5.0 -->
### 2026-08-26: 配置安全写入保护机制 ★★★
- **背景**：全盘审计发现 2 个🔴危险点——`adapter.py config_set()` 无保护写入 + `setup_agents.sh` 回退文件过时
- **修复 1**：`adapter.py config_set()` — 加 dry-run 预检 + 写入后 validate + 读回确认 + 失败自动回退到 .bak
- **修复 2**：`setup_agents.sh` — 加幂等检查（检测到已有 ms-* entries 则跳过）+ 动态 rollback 快照（每次执行前保存当前全量配置）
- **修复 3**：`config.sh apply` — 深层读回（递归提取所有叶子路径逐键验证）+ 失败自动回退 + 自动保存带时间戳的 rollback 快照
- **修复 4**：`probe_context_window.py` — 加容错加载（json 损坏时尝试 .bak 恢复）
- **修复 5**：新增 `scripts/config_safe_write.sh` — 统一安全写入通道（5 步保护：回退点→dry-run→写入→validate→读回）
- **核心原则**：所有写 openclaw.json 的操作必须经过保护通道，禁止裸写入
- 2026-08-26: **配置安全保护机制落地** — 5 项修复全部实测通过
### 2026-09-04: ms-* agent 记忆索引排查 ★★
- **背景**：系统检测发现 ms-reasoning/ms-chat 索引 0 chunks，原记录为"blocked by gateway bug"
- **排查过程**：
  1. `openclaw memory status --agent ms-*` — ms-coding/research 各 929 chunks，ms-reasoning/ms-chat 各 0 chunks
  2. `openclaw memory index --force --agent ms-reasoning/ms-chat` — 进程被 SIGTERM，索引仍为空
  3. Store 文件对比：ms-coding/research=73M，ms-reasoning/ms-chat=628K（仅空表结构）
  4. strings 检查：ms-chat/reasoning 有 `memory_index_chunks` 表定义但无数据行
  5. `openclaw sessions list --agent ms-*` — 全部 0 sessions（从未被实际使用过）
  6. 所有 ms-* agent 的 memory/memorySearch 配置均为 "not set"（与 main 一致）
- **结论**：ms-reasoning/ms-chat 索引为空**不是 bug**——它们从未有过会话，没有记忆数据可索引。628K store 文件 = 空表结构（正常初始状态）
- **影响范围**：ms-reasoning/ms-chat 的 `memory_search` 返回空结果，但**不影响模型调度功能**（调度由 model-scheduling 路由引擎处理，不依赖记忆索引）
- **依赖环境**：OpenClaw 2026.8.1 (ea80657)，嵌入模型 doubao-embedding-vision-251215 (2048 dims)
- **后续建议**：当 ms-reasoning/ms-chat 被实际使用后，索引会自动构建。无需特殊处理
- **教训**：排查前先确认"问题是损坏还是未初始化"——0 chunks ≠ 索引损坏

### 2026-08-27: model-scheduling 守护进程冲突分析 ★★
- **验证项**：独立启停 / Gateway 重启自动恢复 / 守护进程冲突
- **结论**：仅 KeepAlive（当前）= 安全，LaunchAgent 单层守护无冲突
- **独立启停命令**：`launchctl unload/load ~/Library/LaunchAgents/ai.openclaw.model-scheduling.plist`
- **KeepAlive 自动恢复**：kill proxy.py 后 8 秒内自动重启（实测 PID 20767→21223）
- **看门狗（service_guardian）**：未安装，不安装，避免与 KeepAlive 产生竞态冲突
- **核心原则**：自定义服务守护用 LaunchAgent KeepAlive 单层即可，禁止多层守护叠加
- **端口冲突事件**：OpenMAIC 原定 3000 与 model-scheduling 冲突，改为 3002。已建立端口分配表和校验规则（AGENTS.md）
<!-- openclaw-memory-promotion:memory:memory/2026-08-25.md:14:32 -->
- ## model-scheduling 切换成功 + 三处 bug 修复 [score=0.789 signals=5 recalls=5 avg=0.779 source=memory/2026-08-25.md:14-15] <!-- trigger: model-scheduling, 15-10, 127.0.0.1 --> <!-- importance: 8 --> <!-- project: github.com/RenLimin/openclaw-v5.0 -->
