---
type: adr
id: ADR-202610-035
date: 2026-10-30
title: Agent Prompt 规则体系（P0-P3 纵切层）与应答契约治理
status: accepted
deciders: [Rex]
layers: [L0, L1, L2, L3, L4]
stage: develop
tags: [prompt, governance, answer-spec, adr]
supersedes: null
superseded_by: null
---

# ADR-035：Agent Prompt 规则体系（P0-P3 纵切层）与应答契约治理

> 状态：accepted
> 日期：2026-10-30
> 决策人：Rex

## 背景

2026-10-30 茅台项目/合同双域分析暴露 4 类输出偏移：

1. **数据源时效偏移**：首轮从 memory/本地文件得出"茅台只有 1 个项目"，实时 ONES 实际 7 个——无"数据源优先级+时效标注"规则。
2. **客户实体归一偏移**："贵州茅台酒股份有限公司"与"贵州爱茅台数字科技有限公司"双甲方口径差点混统，无实体映射规则。
3. **分析维度临时定**："汇总分析""进度风险"该覆盖哪些维度、风险 🔴/🟡 怎么定级，全由 Agent 临场发挥，无标准件。
4. **降级静默**：contractctl 缺合同原文跑不通时静默降级用 9-28 旧审批报告，无"降级必须显式声明"规则。

根因排查（对 6 个子 skill + 3 个入口 skill 全量扫描）：

- Prompt 指令资产（SOUL/AGENTS/USER/90+ SKILL.md）在四层架构（L1~L4）中**无归属**——既非代码组件、也非知识库数据，无治理机制。
- 证据分级在子 skill 中零散自发出现（出现次数 3~8 次不等，标准不一）；数据时效、风险定级口径几乎全缺。
- 22 条风险规则（确定性、可测试的代码）与"输出必含维度"（约束生成的指令）**混写在 SKILL.md**，无边界。

## 决策

### 1. Prompt 规则作为正交纵切层

Prompt 规则**不构成独立层**，而是贯穿 L0~L4 的纵切约束（与 §4 横切关注点同性质，新增一行）。纵切内部自分四级：

| 层 | 内容 | 对应资产 | 治理规则 |
|---|---|---|---|
| **P0 身份宪法** | 人格、全局红线、用户偏好 | SOUL.md / AGENTS.md / USER.md | 全局唯一，跨所有 agent，变更走配置流程 |
| **P1 通用应答契约** | 数据源优先级与时效、证据三档、降级规则、落盘与副作用、客户实体归一 | `L2-infra/prompts/answer-spec-base.md` | 跨域复用，一处维护，single source |
| **P2 域应答契约** | 项目/合同/产品三类的固定分析维度、风险定级矩阵 | `L3-business/prompts/project-answer-spec.md` / `contract-answer-spec.md` / `L4-proprietary/prompts/product-answer-spec.md` | 同类全部子 skill 强制引用 |
| **P3 能力技能** | 路由表、操作流程、工具用法 | 现有各 SKILL.md | 只讲"怎么做"，不自定义口径 |

### 2. "规则即代码"与"规则即指令"边界（强制）

| 类别 | 归属 | 特性 |
|---|---|---|
| **规则即代码**（22 条 CHECK_RULES、风险引擎、金额计算、状态机） | 留在 L3 `contract-management` 等代码层 | 确定性、可测试、黄金基准比对；版本随代码 |
| **规则即指令**（证据分级、输出维度、定级矩阵、实体映射） | 进 P1/P2 Prompt 层 | 约束生成；变更不动代码 |

两者**禁止混写**——这是当前 SKILL.md 越写越臃肿、口径却不统一的根因。

### 3. 物理位置与引用机制

- P1 → `L2-infra/prompts/`；P2 按域 → `L3-business/prompts/`（项目/合同）、`L4-proprietary/prompts/`（产品）。
- 子 skill 在 SKILL.md 增加「应答规范」节，以绝对路径强制引用所属 spec；同类全部子 skill 同一事实来源。
- 新增技能必须声明所属域并引用对应 spec（验收条件之一）。

## 理由

- **为什么纵切层而非新层**：横切关注点 §4 已有先例（安全/可观测贯穿各层不构成独立层）；Prompt 治理同性质，避免架构膨胀。
- **为什么 P1/P2 分离**：跨域通用规则（证据三档/时效/降级）与域特定维度（合同主体/金额/付款节点）变更频率不同，一处维护各自演进。
- **为什么规则即代码**：22 条风险规则需确定性、可测试、rule_id 100% 匹配黄金基准，LLM 生成不稳定。
- **备选否定**：C 方案（每次提问由用户带口径）——正是本次偏移来源，且与 Rex 短指令提问习惯冲突。

### 4. 数据闭环层：交付质量反馈 → 反哺契约/技能（2026-10-30 增补）

Prompt 治理不能只靠前置闸门，还需从真实交付的**用户纠正**中持续学习。新增 L2 组件 `delivery-quality`：

- `feedback.jsonl`（git-tracked JSONL）**默认记录** Rex 对交付结果的反馈/纠正（规则写入 AGENTS.md P0）。
- **事件驱动（无 cron）**：每次确认反馈（`record.py` 记录）后立即自动跑 `review.py`：按维度/域/严重度聚类、复发根因检测（≥2 次）、高危单次项（high 首次即评估）。批量导入用 `--no-review`。
- review **只生成报告与建议**，不改核心文件；Rex 拍板后收紧 P2「维度合格判据」+ checker、加黄金 fixture、或沉淀 KB。
- 选 JSONL 而非 SQLite：需 git 版本化/diff/grep/不丢，规避「DB 重制全丢」教训。

闭环：`用户反馈 → feedback.jsonl → 确认即 review（事件驱动）→ (P2/checker/fixture/KB) → 更高返回准确率`。

### 5. 输出格式契约：统一信封 + 域内固定内页（2026-10-30 增补）

内容契约只规定维度，导致报告结构跨任务漂移。新增格式治理：

- **P1 `format-spec-base.md`**：报告型（H1+≥2 章节）必须套统一信封 F1–F5（H1/元信息块含生成·契约版本·归属/数据基准/§0溯源链/质量信号章节）；操作回执豁免。
- **P2 三域各加 §4**：域内固定章节标题与表格列（如项目清单列 编号·主体·类型·状态·结项·完成率；合同审查列 rule_id·原文片段·法条·整改）。
- checker 升级为内容+格式双层，信封缺件 fail-closed；新增正反 report fixture（共 3 PASS/3 BLOCK）。
- 硬校验只管稳定的通用信封；域内章节作指令模板不做脆弱逐标题正则。一处升级，12 技能自动获得格式约束。

## 影响与落地

1. `00-system-architecture.md`：§4 横切关注点新增 Prompt 治理行；§8 ADR 表补 ADR-035；§12 变更历史 v5.9 → v6.0。
2. `01-asset-inventory.md`：新增「Prompt 资产」分类登记 P0~P3 全部文件；ADR 清单补 ADR-035。
3. 新建 4 个 spec 文件（P1×1 + P2×3）。
4. 6 个子 skill（bangcle-project-summary / obligation-summary / project-retrospective / customer-profile / contract-approval / product-kb）+ 3 个入口 skill（PJME/CME/PME）加「应答规范」引用节。
5. 用茅台案例回跑验证口径一致性。
6. 新建 L2 `delivery-quality`（feedback.jsonl + record.py + review.py + README/SCHEMA），反馈确认后即时 review（事件驱动，无 cron）；AGENTS.md 增「默认记录反馈」铁律。

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-30 | 1.0 | 初始 accepted |
| 2026-10-30 | 1.1 | 增数据闭环层 delivery-quality（默认记录+反哺） |
| 2026-10-30 | 1.1a | 优化时机由每周 cron 改为反馈确认后即时执行（事件驱动） |
| 2026-10-30 | 1.2 | 增输出格式契约 format-spec-base + P2 §4 域内模板（v1.3） |
