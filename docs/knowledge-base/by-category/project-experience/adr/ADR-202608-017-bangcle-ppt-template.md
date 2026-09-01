---
adr_id: ADR-202608-017
title: 将 Bangcle 官方 PPT 模板注册为 L4 专有业务层组件
status: accepted
date: 2026-09-01
deciders: Rex
layer: L4
component_id: CPT-012
component_name: Bangcle PPT 模板系统
tags: [adr, design-system, ppt, bangcle-vi, L4]
---

# ADR-017: 将 Bangcle 官方 PPT 模板注册为 L4 专有业务层组件

## 背景（Context）

Rex 提供了梆梆安全官方 PPT 模板两套：

1. **浅色系模板**（19 页）：`【PPT】2025梆梆安全模板（浅色系）.pptx`
2. **深色系模板**（15 页）：`【PPT】2025梆梆安全模板（深色系）.pptx`

两套模板包含完整的 Bangcle VI 规范：
- 品牌主色（`#2D74BB` 梆梆蓝）
- VI 辅助色（7 色标准色卡）
- 官方字体（思源黑体 Heavy / Medium）
- Logo 组合形态（横版/竖版/方形/全字）
- 标准布局模式（封面/目录/章节页/内容页/结尾）

模板作为公司级品牌资产，需要在架构中拥有明确的层级定位，以便后续生成 Bangcle PPT 时可以复用统一的设计规范。

## 决策（Decision）

**将 Bangcle 官方 PPT 模板注册为 L4 专有业务层组件**，组件 ID 为 `CPT-012`，组件名称为「Bangcle PPT 模板系统」。

**配套技能**: 在 `skills/bangcle-ppt/` 创建可复用技能文件，封装设计规范和 pptxgenjs 代码模板。

## 理由（Rationale）

### 1. 专有品牌资产 → 归属 L4
- 模板内含 Bangcle 注册商标、VI 配色、官方字体规范
- 属于梆梆安全专有，不具备通用复用性
- 仅用于 Bangcle 业务场景的 PPT 生成
- 符合 L4「专有业务层」的定义：业务专属、品牌相关、不可通用

### 2. 运行时无关 → 不占 L1/L3
- 设计规范本身不依赖运行时（静态知识）
- 具体生成能力由 L2 pptxgenjs-pro 提供
- 本组件是「设计规范 + 代码模板」，属于配置层而非能力层

### 3. 与 L2 pptxgenjs-pro 的清晰分工
| 层级 | 组件 | 职责 |
|------|------|------|
| L2 | pptxgenjs-pro (CPT-004) | 通用 PPT 生成能力（形状/文本/图表/模板修改） |
| L4 | Bangcle PPT 模板系统 (CPT-012) | Bangcle 专属设计规范 + 页面类型模板 + VI 约束 |

**调用方向**: L4 → L2（业务层调用通用能力层）

### 4. 收益
- 统一 PPT 输出的品牌一致性
- 后续生成 Bangcle PPT 无需重复设计规范
- 设计系统有版本管理，模板更新时可同步升级
- 技能化后 Jerry 可直接调用生成符合规范的 PPT

## 后果（Consequences）

### 正面
- ✅ 品牌一致性：所有自动生成的 PPT 符合官方 VI
- ✅ 复用性：页面类型模板可直接组合使用
- ✅ 可维护性：设计规范集中管理，更新只需改一处
- ✅ 与 L2 解耦：pptxgenjs-pro 保持通用，不掺杂业务品牌

### 负面
- ⚠️ L4 层组件数量增加，需要维护
- ⚠️ 模板更新时需要同步更新 DESIGN.md 和技能文件
- ⚠️ 仅适用于 Bangcle 业务，其他客户无法复用

### 应对
- 通过 ADR 记录决策，保持可追溯
- 建立模板版本与组件版本的对应关系
- 模板更新时遵循语义化版本号

## 备选方案（Alternatives Considered）

### 方案 A：放在 L2 pptxgenjs-pro 中作为预设
- ❌ 违反 L2 通用层定位
- ❌ 将专有品牌资产混入通用组件
- ❌ 其他项目使用 pptxgenjs-pro 时会携带无关的 Bangcle 模板

### 方案 B：作为项目文档，不注册为架构组件
- ❌ 缺乏明确层级定位，后续易遗忘
- ❌ 无法被技能系统索引和调用
- ❌ 不具备版本管理和变更追踪

### 方案 C（选中）：L4 专有业务层 + 独立技能文件
- ✅ 层级清晰（专有资产归属 L4）
- ✅ 技能可直接被 Jerry 调用
- ✅ 与 L2 协同关系明确
- ✅ 设计规范有集中存放处

## 技术详情

### 色彩体系
- **主色**: `#2D74BB`（梆梆蓝）
- **辅助色**: `#3FA1DA`、`#27AABF`、`#33ADA0`、`#EFBA20`、`#00122B`、`#595757`
- **浅色系背景**: `#FFFFFF`
- **深色系背景**: `#00122B`

### 字体
- 中文/英文统一使用「思源黑体」（Source Han Sans）
- 字重：Heavy（标题）、Medium（正文）
- Fallback：Microsoft YaHei

### 页面类型
- 封面页 × 2（浅/深）
- 目录页 × 2（浅/深）
- 章节过渡页 × 2（浅/深）
- 内容页（图文混排、三卡片、时间轴、数据图表、纵向时间轴、放射结构等）× 10+
- 结尾页（二维码）× 1

## 参考资料

- 设计规范文档: `docs/architecture/components/bangcle-ppt-template/DESIGN.md`
- 技能文件: `skills/bangcle-ppt/SKILL.md`
- 依赖组件: L2 pptxgenjs-pro (CPT-004)
- 模板源文件: `/Users/bangcle/Bangcle Workspace/00. Bangcle Manual/02. Bangcle Template/`
