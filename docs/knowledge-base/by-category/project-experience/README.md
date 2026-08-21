# 经验沉淀模型

> 本系统采用 **双轨制** 经验沉淀：日常用经验卡片，架构级用 ADR。

## 1. 双轨模型

| 维度 | 经验卡片 (EXP) | ADR |
|---|---|---|
| **触发** | 日常/零散工作 | 定期/涉及系统架构设计 |
| **粒度** | 单一问题、单一方案 | 跨模块、跨层级的决策 |
| **结构** | 问题 / 方案 / 教训 | 背景 / 选项 / 决策 / 后果 |
| **频率** | 高（按需） | 低（事件驱动） |
| **可逆性** | 局部、可回滚 | 全局、影响持久 |
| **作者** | 谁踩坑谁记录 | 团队讨论后记录 |
| **模板** | `../../templates/EXPERIENCE-CARD.md` | `../../templates/ADR.md` |

## 2. 何时升级到 ADR

满足以下**任一**条件，必须从经验卡片升级为 ADR：

- [ ] 影响 **≥ 2 个层级** (L1~L4)
- [ ] 涉及 **L1 系统层契约** 或 **L2 基础设施契约**
- [ ] 需要 **多模块/多团队对齐**
- [ ] 决策**不可逆** 或 撤销成本极高
- [ ] 涉及**重大选型**（技术栈、架构风格、平台）
- [ ] 引入**新横切关注点** 或 改变现有横切策略

> 满足条件即升级，不要犹豫——ADR 是"用空间换稳定性"。

## 3. 经验分类

### 3.1 正确的经验 (`correct/`)
- 验证可行的方案
- 性能/可维护性显著改善的做法
- 防止再次踩坑的有效措施

### 3.2 错误的经验 (`incorrect/`)
- 踩过的坑
- 失败方案的原因分析
- 反模式、坑的"触发条件"和"预防措施"

> **错误经验比正确经验更有价值**——它告诉未来"不要做什么"。

## 4. 元数据要求

### 4.1 经验卡片 (EXP)
```yaml
---
type: experience-card
id: EXP-YYYYMMDD-xxx
date: YYYY-MM-DD
layer: [L2, L3]                # 涉及层级
stage: develop                 # design/develop/manage
severity: medium               # low | medium | high | critical
kind: incorrect                # correct | incorrect
tags: [tag1, tag2]
status: active                 # active | superseded
---
```

### 4.2 架构决策记录 (ADR)
```yaml
---
type: adr
id: ADR-YYYYMM-xxx
date: YYYY-MM-DD
status: proposed               # proposed | accepted | deprecated | superseded
deciders: [name1, name2]
layers: [L1, L2]               # 影响层级
tags: [tag1, tag2]
supersedes: ADR-YYYYMM-xxx     # 可选
superseded_by: ADR-YYYYMM-xxx  # 可选
---
```

## 5. 工作流

### 5.1 经验卡片
1. 踩坑/发现好做法 → 立即记录（5 分钟内）
2. 使用 `EXPERIENCE-CARD.md` 模板
3. 放置到 `correct/` 或 `incorrect/`
4. 触发升级条件 → 拷贝核心内容，新建 ADR

### 5.2 ADR
1. 出现重大决策需求 → 创建 `proposed` 状态 ADR
2. 团队讨论、收集反馈
3. 决策 → 改为 `accepted`
4. 实现后 → 补充"实现记录"段
5. 决策失效 → 改为 `deprecated` 或 `superseded`（指向新 ADR）

## 6. 与知识库的关系

经验是知识库的一个**子集**：

```
knowledge-base/by-category/
├── industry-practices/        ← 业界实践
├── theoretical-knowledge/     ← 理论知识
└── project-experience/        ← 项目经验
    ├── correct/               ← 经验卡片(正)
    ├── incorrect/             ← 经验卡片(反)
    └── adr/                   ← 架构决策记录
```

每张经验卡片和每个 ADR 都是知识库的一个**条目**，需要：
- frontmatter 完整
- 可被 `INDEX.md` 索引
- 长期保留（包括 superseded 的，作为决策史）
