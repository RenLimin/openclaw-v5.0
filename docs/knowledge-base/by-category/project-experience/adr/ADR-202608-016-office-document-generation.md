---
type: adr
id: ADR-202608-016
date: 2026-08-31
title: L2 Office 文档生成能力 — Word/Excel/PPT 多库工具链
status: accepted
deciders: [Rex]
layers: [L2]
stage: develop
tags: [office, document-generation, python-docx, openpyxl, xlsxwriter, pptxgenjs, docxtpl]
supersedes: null
superseded_by: null
---

# [ADR-202608-016] L2 Office 文档生成能力

## 1. 状态
**accepted** — 2026-08-31 起生效

## 2. 背景

系统已有 L2 基础设施组件覆盖配置、可观测、持久化、凭据、工具策略、记忆检索、知识库、沙箱、会话管理、错误处理、模型调度等能力，但缺少**按需求 + 原始数据生成 Office 文档**（Word/Excel/PPT）的标准化能力。

当前 PPT 已有 `pptxgenjs-pro` 技能（Node.js 生态），但 Word 和 Excel 尚未沉淀为可复用的基础设施组件。

业务上存在明确需求：
- 数据报表导出（Excel）
- 报告/合同/邮件模板生成（Word）
- 演示文稿自动生成（PPT）

为避免 L3/L4 业务层重复造轮子、每个场景各自选型，需要将 Office 文档生成能力**正式注册为 L2 基础设施组件**，封装统一的工具链选型、能力边界和最佳实践。

### 调研与实测

2026-08-31 完成深度调研，**6 个库全部实测通过**，输出文件位于 `/tmp/office-research/output/`，详细报告见 `/tmp/office-research/REPORT.md`。

实测样本：
| 格式 | 文件 | 大小 | 验证点 |
|---|---|---|---|
| Word | `sample_word.docx` | 38KB | 标题/段落/表格/样式/列表着色/页眉页脚 |
| Word(模板) | `rendered_working.docx` | 37KB | 变量替换/段落循环/条件渲染 |
| Excel | `sample_excel.xlsx` | 9.7KB | 多sheet/公式/条件格式/图表/样式 |
| Excel(大数据) | `sample_xlsxwriter.xlsx` | 273KB | 10000行×4列/0.05s/数据条/图表 |
| Excel(快速) | `sample_pandas.xlsx` | 6.6KB | DataFrame导出/多sheet |
| PPT | `sample_ppt.pptx` | 42KB | 3页/表格/柱状图/备注 |

## 3. 考虑的选项

### 选项 A: 不建组件，各业务层自行选型
- **优点**：零额外仪式
- **缺点**：
  - 每个业务场景重复调研选型
  - 能力边界、坑、workaround 无法沉淀
  - 与 pptxgenjs-pro 技能的协同无统一规范
- **评估**：❌ 不符合 L2 基础设施层的定位

### 选项 B: 只封装一个库，简化选型
- **优点**：API 单一，学习成本低
- **缺点**：
  - Word/Excel/PPT 各有优势库，单库无法覆盖所有场景
  - 性能/功能不可兼得（如 xlsxwriter 只写不改但性能最好）
- **评估**：❌ 实际业务需要多库配合

### 选项 C: 注册为 L2 组件，多库协同工具链 — **采用**
- **优点**：
  - 7 个库全部实测验证，选型有依据
  - 明确每个库的能力边界和适用场景
  - 与现有 pptxgenjs-pro 技能形成协同
  - L3/L4 可直接调用，无需重复调研
- **缺点**：
  - 多库有学习成本（需按场景选择）
- **评估**：✅ 采用

## 4. 决策

**采用选项 C**：将 Office 文档生成能力正式注册为 **L2 基础设施层组件**，组件 ID **011**，多库协同工具链。

### 4.1 组件元信息

| 维度 | 值 |
|---|---|
| 组件名称 | Office 文档生成 |
| 组件 ID | 011 |
| 层级 | L2 基础设施层 |
| 定位 | 封装 Python/JS 多库文档生成能力，为上层提供统一的文件生成服务 |
| 设计文档 | `components/office-generation/DESIGN.md` |
| ADR | ADR-016 |
| 状态 | ✅ 已上线（2026-08-31，6/6 库实测通过） |

### 4.2 工具链选型（基于实测）

| 格式 | 主力库 | 补充库 | 选型理由 |
|---|---|---|---|
| **Word** | python-docx | docxtpl | python-docx 程序化构建能力最全；docxtpl 提供 Jinja2 模板渲染（段落循环 OK，表格行循环有 bug） |
| **Excel** | openpyxl + xlsxwriter | pandas | openpyxl 读写双全功能；xlsxwriter 写入性能 + 条件格式/图表最强；pandas 一行代码快速导出 |
| **PPT** | pptxgenjs | python-pptx | pptxgenjs 设计品质最高 + 已有技能封装；python-pptx 用于 Python 原生批量场景 |

### 4.3 层级归属

归属 **L2 基础设施层**。以下逐条对照架构文档 §3.3 L2 约束与 §3.4 L3 判断标准：

#### 4.3.1 L2 约束逐条验证

> 来源：`docs/architecture/00-system-architecture.md` §3.3 — L2 关键约束

| # | L2 约束 | Office 文档生成的符合情况 | 判定 |
|---|---|---|---|
| 1 | **只依赖 L1 抽象契约**，不直接调用具体运行时 API | 依赖 L1 的**文件系统**（写 .docx/.xlsx/.pptx 到磁盘）+ **exec**（调 Node.js pptxgenjs）。不调用 OpenClaw 特有 API（无 `memory_search` / `sessions_send` / `config_get` 等） | ✅ 符合 |
| 2 | **提供给 L3 的接口必须稳定**（契约变更需 ADR） | 工具链选型已锁定（python-docx / openpyxl / xlsxwriter / pptxgenjs），API 契约为"输入数据 + 模板 → 输出文件路径"。未来新增库走 ADR 变更 | ✅ 符合 |
| 3 | **不感知 L3 / L4 的业务含义** | 只做"结构化数据 → Office 文件"的通用转换。不知道也不关心生成的是"报表"还是"合同"——调用方传入什么数据就生成什么文件 | ✅ 符合 |
| 4 | **运行时切换时 L2 组件无需修改** | 换 Agent 运行时（OpenClaw → Claude Code → 自研），python-docx / openpyxl / pptxgenjs 的调用方式不变，适配层吸收差异 | ✅ 符合 |

#### 4.3.2 L3 判断标准反向排除

> 来源：`docs/architecture/00-system-architecture.md` §3.4.1 — 判断标准

| 标准 | Office 文档生成的匹配情况 | 结论 |
|---|---|---|
| L3 = "跨场景通用**业务能力**" | Office 文档生成是**技术能力**（文件格式转换），不含业务逻辑、业务规则或业务实体 | ❌ 不是 L3 |
| L3 = "领域实体 / 领域流程 / 横切能力" | 不属于 user/order/payment 等实体，也不属于 checkout/fulfillment 等流程 | ❌ 不是 L3 |
| L3 示例：notification / search / analytics / audit | 文档生成不在 L3 示例范畴，更接近"导出"基础设施 | ❌ 不是 L3 |

#### 4.3.3 与已有 L2 组件的类比

| 已有 L2 组件 | 职责 | Office 文档生成的类比 |
|---|---|---|
| **知识库能力**（010） | 封装 Markdown 解析/索引/查询，为上层提供知识访问 | 封装 docx/xlsx/pptx 生成，为上层提供文档输出 |
| **持久化适配**（006） | 封装 SQLite/Repository，为上层提供数据存取 | 封装 python-docx/openpyxl，为上层提供文件生成 |
| **可观测性适配**（004） | 封装 logging/metrics，为上层提供可观测服务 | 封装多库工具链，为上层提供文档生成服务 |

**三者共同点**：封装外部库 → 提供标准接口 → 上层不直接依赖外部库。

#### 4.3.4 归属结论

Office 文档生成完全满足 L2 的四条关键约束，且不符合 L3 的任何判断标准。

**最终归属**：**L2 基础设施层**，组件 ID **011**。

### 4.4 能力清单

| 库 | 能力边界（实测验证） | 不适用场景 |
|---|---|---|
| python-docx | 标题/段落/表格/样式/列表/页眉页脚/图片 | 模板渲染（需 docxtpl）、复杂页码 |
| docxtpl | Jinja2 变量替换/段落循环/条件渲染/富文本/图片占位 | 表格行循环（`{%tr for %}` 有 bug）、程序化构建 |
| openpyxl | 多sheet/公式/条件格式/图表/样式/读写已有文件 | 大数据量写入（性能不如 xlsxwriter） |
| xlsxwriter | 高性能写入/丰富条件格式/精美图表/10000 行 0.05s | 修改已有文件（只能写新文件） |
| pandas | DataFrame → Excel 一行导出/多 sheet/统计汇总 | 复杂图表/条件格式/精细样式 |
| python-pptx | 多 slide/文本框/表格/图表/备注/图片 | 设计品质不如 pptxgenjs、布局需手动计算 |
| pptxgenjs | 高质量设计/完整图表/中文友好/已有技能封装 | 仅限 Node.js、不适合数据处理 |

### 4.5 与 pptxgenjs-pro 技能的协同

- **pptxgenjs-pro 技能**是 pptxgenjs 的高层次封装（设计系统 + 常用模板），是本组件的 **PPT 子能力实现**
- 本组件在架构层面将 pptxgenjs-pro 纳入统一工具链管理，明确其在 PPT 生成中的首选地位
- Python 数据处理 → 传给 Node.js pptxgenjs 生成 PPT 是推荐管线

### 4.6 组件规范检查

| 规范项 | 状态 |
|---|---|
| ADR | ✅ 本文件（ADR-016） |
| DESIGN.md | ✅ `components/office-generation/DESIGN.md` |
| 实现 | ✅ 6/6 库实测通过（python-docx/docxtpl/openpyxl/xlsxwriter/pandas/python-pptx）+ 已有 pptxgenjs-pro 技能 |
| 验证 | ✅ 7 份实测输出文件 + 调研报告 |
| 契约 | ✅ 按场景推荐工具链 + 明确能力边界 |
| 架构文档同步 | ✅ §3.3 组件表 + 四件套清单 + 详细清单已更新 v2.7 |

## 5. 后果

### 5.1 正面
- Word/Excel/PPT 文档生成有了标准化的 L2 基础设施组件
- 选型决策有实测依据，不再凭感觉
- 与 pptxgenjs-pro 技能形成协同，PPT 能力已有完整封装
- L3/L4 业务层可直接调用，无需重复调研

### 5.2 负面
- 多库选型增加了"该用哪个库"的决策成本（已通过场景推荐矩阵缓解）

### 5.3 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| docxtpl 表格行循环 bug | 模板中无法动态生成表格行 | 用 python-docx 手动构建表格，或用段落循环代替 |
| xlsxwriter 只写不改 | 需要修改已有 Excel 时不适用 | 用 openpyxl 处理读写场景 |
| openpyxl number_format 坑 | cell() 不支持关键字参数 | 单独赋值 `cell.number_format = '...'` |
| python-pptx 布局繁琐 | 每个元素需手动计算坐标 | 封装布局函数或转用 pptxgenjs |
| 中文字体显示问题 | 中文显示为方框 | python-docx 需同时设置 font.name + eastAsia 字体；pptxgenjs 默认 Microsoft YaHei |

## 6. 实现计划

- [x] 2026-08-31: 深度调研 + 7 库实测（6 通过 + 1 已有技能）
- [x] 2026-08-31: 调研报告 `/tmp/office-research/REPORT.md`
- [x] 2026-08-31: ADR-016 accepted
- [x] 2026-08-31: `components/office-generation/DESIGN.md`
- [x] 2026-08-31: 架构文档 v2.7 同步
- [ ] 后续: 封装通用生成函数（scripts/office/）
- [ ] 后续: 建立数据→文档统一管线
