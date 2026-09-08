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
**accepted** — 2026-08-31 v1 生效 · 2026-09-07 v2 演进（组件 011 从工具链升级为统一 SDK）

## 2. 背景

系统已有 L2 基础设施组件覆盖配置、可观测、持久化、凭据、工具策略、记忆检索、知识库、沙箱、会话管理、错误处理、模型调度等能力，但缺少**按需求 + 原始数据生成 Office 文档**（Word/Excel/PPT）的标准化能力。

当前 PPT 已有 `pptxgenjs-pro` 技能（Node.js 生态），但 Word 和 Excel 尚未沉淀为可复用的基础设施组件。

业务上存在明确需求：
- 数据报表导出（Excel）
- 报告/合同/邮件模板生成（Word）
- 演示文稿自动生成（PPT）

为避免 L3/L4 业务层重复造轮子、每个场景各自选型，需要将 Office 文档生成能力**正式注册为 L2 基础设施组件**，封装统一的工具链选型、能力边界和最佳实践。

### 调研与实测

2026-08-31 完成深度调研，**6 个库全部实测通过**，输出文件位于 `L2-infra/components/office-generation/research/output/`，详细报告见 `L2-infra/components/office-generation/research/REPORT.md`。

实测样本：
| 格式 | 文件 | 大小 | 验证点 |
|---|---|---|---|
| Word | `sample_word.docx` | 38KB | 标题/段落/表格/样式/列表着色/页眉页脚 |
| Word(模板) | `rendered_working.docx` | 37KB | 变量替换/段落循环/条件渲染 |
| Excel | `sample_excel.xlsx` | 9.7KB | 多sheet/公式/条件格式/图表/样式 |
| Excel(大数据) | `sample_xlsxwriter.xlsx` | 273KB | 10000行×4列/0.05s/数据条/图表 |
| Excel(快速) | `sample_pandas.xlsx` | 6.6KB | DataFrame导出/多sheet |
| PPT | `sample_ppt.pptx` | 42KB | 3页/表格/柱状图/备注 |

---

## v2 演进（2026-09-07）

### 背景变化

v1 上线后，L4 业务组件（BDMS 交付中心、SCA-001 合同审批、Bangcle PPT）各自直调底层库（openpyxl / python-docx / pptxgenjs），存在三个问题：

1. **跨层直调违反架构**：L4 直接依赖 L2 具体实现，绕过 L3（架构明确禁止 L4→L2 直调）
2. **能力零散**：解析（读入）、格式转换、编辑等能力缺失或散落各处
3. **无统一 API**：每个业务组件自己封装一套，接口不统一，复用成本高

v2 目标：从"工具链集合"升级为"统一 SDK"，为 L3 Office 业务维度提供完整的 create / read / update / parse / convert 五件套能力。

### v2 新增决策

#### 决策 1：组件 011 从工具链升级为统一 SDK

| 维度 | v1（工具链） | v2（统一 SDK） |
|---|---|---|
| 形态 | 选型推荐 + 最佳实践 | 可 import 的 Python 包 + 统一 API |
| 能力覆盖 | create（生成） | create / read / update / parse / convert |
| 调用方式 | 业务层自行 import 各库 | `from office_engine import OfficeDocument` |
| 错误处理 | 各库自带异常 | 统一异常体系（OfficeEngineError） |
| 中文支持 | 业务层自行处理 | SDK 内置默认 Microsoft YaHei |
| 文档解析 | ❌ 无 | ✅ 结构化 JSON + Markdown 导出 |
| 格式转换 | ❌ 无 | ✅ docx/xlsx/pptx → PDF（LibreOffice） |

**理由**：
- 符合 L2 "封装外部库 → 提供标准接口 → 上层不直接依赖外部库" 的模式（与持久化适配、知识库能力同构）
- 为 L3 Office 业务维度提供完整底座，L3 只需叠加业务知识和模板资产
- 统一异常 / 统一日志 / 统一字体，业务层不重复踩坑

#### 决策 2：引擎选型不变，新增内部自动切换逻辑

- Word：python-docx（主力） + docxtpl（模板）— 不变
- Excel：openpyxl（读写） + xlsxwriter（高性能写入） + pandas（快速导出）— 不变
  - **新增**：SDK 内部按场景自动切换引擎（读写混合 → openpyxl；纯写入大数据 → xlsxwriter）
- PPT：python-pptx（Python SDK） + pptxgenjs（高品质，通过技能调用）— 不变
  - **新增**：SDK 提供 python-pptx 封装；高品质场景仍通过 pptxgenjs-pro 技能

**理由**：v1 的库选型经过实测验证，能力边界清晰。v2 不换库，只加一层统一封装。

#### 决策 3：文档解析（parse）作为 L2 基础能力

**解析能力清单**：
- **Word**：标题结构 / 段落 / 表格 / 图片 / 样式 / 元数据 → JSON / Markdown
- **Excel**：Sheet 列表 / 数据区域 / 表格 / 公式 / 合并单元格 → JSON / Markdown
- **PPT**：幻灯片大纲 / 文本 / 表格 / 图片 / 图表 / 备注 → JSON / Markdown

**理由**：
- 解析是"读入方向"的基础设施，与"生成"对称
- L3 业务维度（文档审核、数据抽取、内容分析）需要这个底座
- 业务层不应各自写解析逻辑

#### 决策 4：格式转换（convert）基于 LibreOffice，作为可选能力

**转换能力**：
- docx → PDF
- xlsx → PDF
- pptx → PDF
- 旧格式兼容检测（.doc / .xls 警告 + 转换建议）

**实现策略**：
- 检测到 LibreOffice 可用 → 直接转换
- 不可用 → 抛 `OfficeUnsupportedError`，提示安装
- 不强依赖，SDK 核心能力不绑定 LibreOffice

**理由**：
- PDF 导出是高频需求，但实现方式依赖外部工具
- 作为可选能力，不影响核心 SDK 的可移植性
- 与 v1 "不重复造轮子" 原则一致

#### 决策 5：v2 不引入新的业务逻辑，严格保持 L2 纯技术定位

**明确不做的**：
- ❌ 模板资产管理（属 L3 业务维度）
- ❌ 文档审核规则（属 L3 / L4）
- ❌ 业务数据模型（属 L3 / L4）
- ❌ 审批流程（属 L3 / L4）

**理由**：严格遵守架构分层契约，L2 只做技术基础设施，不感知业务含义。

### v2 架构位置

```
L3 Office 业务维度（v3 建设，新 ADR）
    │ 依赖（统一 SDK 契约）
    ▼
L2 Office Engine v2（本组件）
├── WordDocument    ← python-docx + docxtpl
├── ExcelDocument   ← openpyxl + xlsxwriter + pandas
├── PPTDocument     ← python-pptx
├── OfficeConverter ← LibreOffice（可选）
├── OfficeFactory   ← 自动识别 + 统一入口
└── 统一异常 / 日志 / 字体
    │
    ▼
L1 运行时抽象（文件系统 / exec / 沙箱）
```

---

## 3. 考虑的选项（v1 原始选型）

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
- **评估**：✅ 采用（v1 基础）

### v2 新增选项

### 选项 D: v2 升级为统一 SDK — **采用**
- **优点**：
  - 统一 API，业务层 `from office_engine import OfficeDocument` 即可
  - 补齐 parse / convert 能力，覆盖完整生命周期
  - 统一异常 / 字体 / 日志，业务层不重复踩坑
  - 为 L3 Office 业务维度提供清晰的下层契约
- **缺点**：
  - 封装层有一定维护成本
  - 极端场景可能需要绕过 SDK 直接调底层库（预留 escape hatch）
- **评估**：✅ 采用（v2 演进方向）

### 选项 E: v2 新建 L3 组件，L2 保持不变
- **优点**：L2 不膨胀
- **缺点**：
  - L3 做技术封装违反定位（L3 是业务维度）
  - 解析/转换等纯技术能力不该放 L3
- **评估**：❌ 分层定位错误

## 4. 决策

**采用选项 C（v1）+ 选项 D（v2 演进）**：
- v1：将 Office 文档生成能力正式注册为 **L2 基础设施层组件**，组件 ID **011**，多库协同工具链
- v2：从工具链升级为**统一 SDK**，新增 parse / convert / 统一入口，保持引擎选型不变

### 4.1 组件元信息（v2）

| 维度 | 值 |
|---|---|
| 组件名称 | Office 文档引擎（Office Engine） |
| 组件 ID | 011 |
| 层级 | L2 基础设施层 |
| 定位 | 统一 SDK：Word/Excel/PPT 的 create/read/update/parse/convert 五件套，纯技术基础设施，不含业务逻辑 |
| 包名 | `office_engine` |
| 设计文档 | `components/office-generation/DESIGN.md`（v2） |
| ADR | ADR-016（v2） |
| 状态 | ✅ v1 已上线（2026-08-31） · 🚧 v2 升级中（2026-09-07） |

### 4.2 工具链选型（v2，与 v1 一致）

| 格式 | 主力引擎 | 补充引擎 | 选型理由 |
|---|---|---|---|
| **Word** | python-docx | docxtpl | python-docx 程序化构建能力最全；docxtpl 提供 Jinja2 模板渲染 |
| **Excel** | openpyxl + xlsxwriter | pandas | openpyxl 读写双全功能；xlsxwriter 写入性能 + 条件格式/图表最强；pandas 快速导出 |
| **PPT** | python-pptx | pptxgenjs（技能） | python-pptx Python 原生；pptxgenjs 高品质（通过 pptxgenjs-pro 技能调用） |
| **转换** | LibreOffice | — | 业界标准开源方案，格式兼容性最好 |

### 4.3 v2 能力清单

| 能力 | Word | Excel | PPT | 说明 |
|---|---|---|---|---|
| create（创建） | ✅ python-docx | ✅ openpyxl/xlsxwriter | ✅ python-pptx | 程序化构建新文档 |
| read（打开） | ✅ | ✅ | ✅ | 打开已有文档进行编辑 |
| update（编辑） | ✅ | ✅ | ✅ | 查找替换 / 增删内容 / 修改样式 |
| parse（解析） | ✅ | ✅ | ✅ | 结构化 JSON + Markdown 导出 |
| convert（转换） | ✅ → PDF | ✅ → PDF | ✅ → PDF | 基于 LibreOffice，可选 |
| 模板渲染 | ✅ docxtpl | ⚠️ 不支持 | ❌ | Word 模板渲染；Excel/PPT 用程序化构建替代 |

### 4.4 层级归属验证（v2 保持不变）

> 来源：`docs/architecture/00-system-architecture.md` §3.3 — L2 关键约束

| # | L2 约束 | v2 符合情况 | 判定 |
|---|---|---|---|
| 1 | **只依赖 L1 抽象契约** | 依赖文件系统 + exec（LibreOffice）。不调用 OpenClaw 特有 API | ✅ 符合 |
| 2 | **提供给 L3 的接口必须稳定** | 统一 SDK API（OfficeDocument），变更需 ADR | ✅ 符合 |
| 3 | **不感知 L3 / L4 的业务含义** | 纯技术：create/read/update/parse/convert。不知道"合同"或"报表"是什么 | ✅ 符合 |
| 4 | **运行时切换时无需修改** | 换 Agent 运行时，python-docx/openpyxl 等调用不变 | ✅ 符合 |

### 4.5 组件规范检查（v2）

| 规范项 | 状态 |
|---|---|
| ADR | ✅ 本文件（ADR-016 v2） |
| DESIGN.md | ✅ `components/office-generation/DESIGN.md`（v2） |
| 实现 | 🚧 v2 SDK 开发中（src/ + tests/） |
| 验证 | 🚧 单元测试 + 集成测试 + round-trip 验证 |
| 契约 | ✅ 统一 SDK 接口契约 |
| 架构文档同步 | 🚧 v3.4 更新中 |

## 5. 后果

### 5.1 正面（v2 新增）
- 统一 API 大幅降低 L3/L4 使用门槛
- parse 能力补齐"读入方向"，完整覆盖文档全生命周期
- 统一异常 / 字体 / 日志，业务层不重复踩坑
- 为 L3 Office 业务维度提供清晰的下层契约
- LibreOffice 可选依赖，不影响核心 SDK 可移植性

### 5.2 负面（v2 新增）
- 封装层有一定维护成本（库升级时需同步适配）
- 极端场景可能需要绕过 SDK 直接调底层库（已预留 escape hatch：`.native` 属性访问原生对象）

### 5.3 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| v1 业务组件直调底层库 | 架构违规 | v2 上线后 M3 阶段统一迁移到经 L3 调用 |
| LibreOffice 不可用 | PDF 转换失败 | 优雅降级 + 明确错误提示 + 安装指引 |
| 底层库大版本升级 | SDK API 可能受影响 | SDK 隔离层吸收变化，对外保持契约稳定 |
| 中文字体跨平台差异 | 文档显示不一致 | SDK 内置字体检测 + fallback 策略 |

## 6. 实现计划

### v1（已完成）
- [x] 2026-08-31: 深度调研 + 7 库实测
- [x] 2026-08-31: 调研报告
- [x] 2026-08-31: ADR-016 v1 accepted
- [x] 2026-08-31: DESIGN.md v1
- [x] 2026-08-31: 架构文档 v2.7 同步

### v2（进行中）
- [ ] M1: 统一 SDK 实现（Word/Excel/PPT + Factory + Converter）
- [ ] M1: parse 能力（JSON + Markdown）
- [ ] M1: 单元测试 + 集成测试 + round-trip 验证
- [ ] M1: ADR-016 v2 修订
- [ ] M1: DESIGN.md v2 重写
- [ ] M1: 架构文档 v3.4 同步
- [ ] M2: L3 Office 业务维度建设（新 ADR）
- [ ] M3: L4 业务组件迁移（SCA/BDMS 经 L3 调用）
- [ ] M4: Skill 入口 + 模板市场 CLI
