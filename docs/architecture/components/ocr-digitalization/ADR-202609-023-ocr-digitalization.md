---
adr_id: ADR-202609-023
title: L2 OCR 文档数字化组件（OCR-001）建设
status: accepted
date: 2026-09-02
deciders: Rex
layer: L2
component_id: OCR-001
component_name: 文档数字化（OCR）组件
tags: [adr, ocr, document-digitalization, L2, infrastructure, rapidocr, paddleocr]
---

# ADR-023: L2 OCR 文档数字化组件（OCR-001）

## 背景（Context）

系统已具备 **Office 文档生成**（L2, ADR-016）能力，但缺少**对偶能力**——将纸质/扫描件文档数字化为可处理的文本。当前 OCR 代码散落在 L4 `contract-approval` skill 的 `contract_ocr.py` 中，存在以下问题：

1. **层级归属错误**：OCR 是通用基础设施能力，却被封装在销售合同审批（L4 专有业务）内部
2. **不可复用**：知识库导入扫描件、法务审查、其他 L3/L4 业务均需要 OCR，但无法复用
3. **无架构沉淀**：无 ADR、无 DESIGN.md、无四件套规范，能力边界不清
4. **能力薄弱**：仅单引擎（RapidOCR）+ 300DPI，识别精度不足以支撑"完整识别合同文本"的业务目标

**业务需求**（来自 Rex 2026-09-02 测试指令）：针对扫描件合同（如 `~/Downloads/contract/XSZS2603090130北京聚信得仁.pdf`，10 页扫描件），实现**完整、准确**的文本识别，输出可进入审核流水线的结构化文本。

## 决策（Decision）

**建设 L2 OCR 文档数字化组件（OCR-001）**，与 Office 文档生成（ADR-016）形成"一读一写"对偶能力。

**组件标识**：
- 组件 ID：OCR-001
- 组件名称：文档数字化（OCR）
- 目录：`docs/architecture/components/ocr-digitalization/`（设计）+ `skills/contract-approval/scripts/contract_ocr.py`（实现，供 L4 复用）
- ADR：ADR-202609-023

**核心能力**：
1. 扫描件 PDF / 图片 → 高精度文本（多引擎）
2. 图像前处理（600DPI + 多版本预处理 + 版面分析）
3. 合同场景 OCR 错误自动纠错
4. 双引擎投票（RapidOCR + PaddleOCR，取最优）
5. 结构化输出（纯文本 + Markdown + 可选表格还原）

## 理由（Rationale）

### 1. 文档数字化是 L2 基础设施能力
- 与 Office 文档生成（ADR-016）对偶：一个"写"、一个"读"
- 知识库导入、合同审批、法务审查等 L3/L4 业务均依赖
- 符合 L2「基础设施层」定义：封装/适配 L1 能力，提供通用服务

### 2. 为什么从 L4 skill 迁出
- OCR 不属于销售合同专有规则
- 多业务复用需求明确（知识库、法务、档案数字化）
- 层级契约要求：L4 不得直接依赖 L2 实现，应通过 L3 间接获得；但 skill 作为交付形式可承载实现

### 3. 引擎选型
| 引擎 | 中文精度 | 速度 | 依赖 | 结论 |
|---|---|---|---|---|
| tesseract | 差 | 中 | 系统级 | ❌ 中文表格识别差 |
| macOS Vision | 差（中文） | 快 | pyobjc | ❌ 中文不如预期 |
| RapidOCR | 良 | 快 | onnxruntime | ✅ 主引擎（已验证） |
| PaddleOCR | 优 | 中 | paddlepaddle | ✅ 高精度引擎（补充） |

### 4. 双引擎投票策略
- RapidOCR 快、已实测；PaddleOCR 中文精度更高
- 同页两引擎并行识别，按置信度 + 中文字符比例投票取优
- 避免单一引擎的系统性识别错误

## 约束（Constraints）

1. **完整适配 OpenClaw**：输入/输出均为文件，无外部服务依赖；可被 OpenClaw skill / automation 直接调用
2. **避免耦合**：组件仅依赖文件系统 + OCR 引擎库，不依赖具体 L3/L4 业务；L4 通过 CLI/脚本调用
3. **可回滚**：输出文本独立保存，组件升级不影响既有数据

## 影响（Consequences）

### 正面
- L3/L4 业务获得统一的文档数字化能力
- 合同审批（SCA-001）可处理扫描件合同全流程
- 知识库可导入扫描件资料

### 代价
- PaddleOCR 模型较大（约 100MB），首次使用需下载
- 双引擎识别耗时增加（约 2-3 倍单引擎）

### 待办
- [ ] L4 Bangcle 合同模板接入（Rex 提供模板后）
- [ ] 表格结构还原（PP-Structure）作为演进方向

## 相关
- 对偶组件：[ADR-016](./docs/knowledge-base/by-category/project-experience/adr/ADR-202608-016-office-document-generation.md)
- 上游模块：[ADR-018](./docs/knowledge-base/by-category/project-experience/adr/ADR-202609-018-sales-contract-approval.md) (L4 合同审批)
- 知识库工具链：ADR-010
