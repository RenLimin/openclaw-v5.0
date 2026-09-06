---
id: METHODOLOGY-003
title: "建设经验沉淀"
description: "L3 业务层建设过程中验证过的正确做法与踩过的坑，持续更新"
source: "L3 维度建设实证（DMS 框架/OCR/合同审批/交付报表）"
version: "1.0"
dimension: "methodology"
sub_area: "lessons-learned"
stage: "manage"
tags: ["l3", "methodology", "lessons-learned", "experience"]
last_reviewed: "2026-09-06"
---

# 建设经验沉淀

> L3 业务层建设过程中验证过的正确做法与踩过的坑。每个维度建设完成后更新本文件。

## 2026-09-06: 方法论知识库建设启动

**背景**：按 L3 架构文档 v1.5 阶段 0 建设方法论知识库（6 篇文档）。
**问题**：已有 3 篇（README/role-definition/knowledge-authoring）缺少 `id`/`stage` 字段，且 README 引用 3 个尚不存在的文档（dimension-design/quality-standard/lessons-learned），校验产生断链与缺字段警告。
**根因**：早期建设只填了架构文档要求的字段，未对照 `kb_index.py --validate` 的 schema 补齐 id/stage；文档先有索引引用、后补实体。
**修复**：新增 3 篇缺失文档，并为已有 3 篇补齐 id/stage/last_reviewed，消除断链与缺字段。
**预防**：建设任何业务文档后立即跑 `python3 scripts/kb_index.py --validate`，以校验结果为准闭环；索引文档（README）只在实体文档落地后才引用。

## 2026-09-03: 方法论 subagent 输出为空（幻觉）

**背景**：DMS 框架 Phase 3 建设交付管理知识库，4 批并行 subagent。
**问题**：methodologies subagent 报告"13 篇完成"，但实际文件目录全空。
**根因**：subagent 把"写好了"当成"完成了"，实际没写文件。
**修复**：主 agent 逐条验证文件存在性，直接补写；不轻信 subagent 汇报。
**预防**：批量 subagent 任务必须含**明确验证命令**（如 `ls` + `wc -l`），主 agent 逐文件核对。详见 [EXP-20260903-003-dms-framework-phase3](../../project-experience/correct/EXP-20260903-003-dms-framework-phase3.md)。

## 2026-09-03: 对比验证必须到单元格级

**背景**：交付月报统计 Sheet 差异修复。
**问题**：原始数据差异允许但汇总差异过大，之前只看行数/列数归因"日期差"就结束。
**根因**：简化版统计逻辑（按部门 groupby count）≠ 参考实现的复杂透视表格式；`build_stat_sheets.py` 写好了但没集成到主生成脚本。
**修复**：逐 Sheet 逐单元格对比，区分"结构差异 / 数值差异 / 显示风格差异"三类；统计类 Sheet 验证表头结构、数据布局、单元格值分布。
**预防**：任何"对比验证"必须到单元格级，不能以行数/列数/概要结论收尾。详见 [EXP-20260903-002-audit-scope-filter](../../project-experience/correct/EXP-20260903-002-audit-scope-filter.md) 的同类精神。

## 2026-09-03: 知识库建设质量可控的做法

**背景**：DMS 框架 Phase 3 完成 65 个文件、5,611 行文档。
**问题**：如何保证批量知识文档质量统一？
**根因**：无统一模板时各写各的，结构漂移。
**修复**：能力知识 12 篇统一 87-126 行、结构统一；角色 24 个每个差异化 SOUL 不重叠；数据模型基于实际代码不编造。
**预防**：批量文档用统一 frontmatter + 标准结构模板；知识内容以真实代码/真实来源为锚，不凭空编造。

## 2026-09-03: OCR 坐标系统一陷阱

**背景**：OCR 签名/印章检测开发。
**问题**：bbox 偏移导致检测框错位。
**根因**：DPI 不一致，不同来源图片坐标基准不同。
**修复**：统一坐标系统一换算基准。
**预防**：跨来源数据处理先统一基准坐标系再开发算法。详见 [EXP-20260903-001-ocr-coordinate-system](../../project-experience/correct/EXP-20260903-001-ocr-coordinate-system.md)。

## 2026-09-03: 合同审核 scope 防误报

**背景**：合同风险扫描规则开发。
**问题**：关键词匹配误报高。
**根因**：审核规则缺少"位置意识"，只看关键词不看上下文。
**修复**：给审核规则加位置/上下文过滤（scope filter）。
**预防**：规则引擎类能力必须考虑误报率，加位置/范围约束。详见 [EXP-20260903-002-audit-scope-filter](../../project-experience/correct/EXP-20260903-002-audit-scope-filter.md)。

## 2026-09-03: 分层验证优于空谈（DMS 端到端）

**背景**：DMS 框架 Phase 4 端到端验证。
**问题**：如何证明框架"能跑"而非"应该能跑"。
**根因**：无端到端验证则交付物停留在"设计可用"。
**修复**：用一个示例交付项目跑通全流程，46 个单测 + 端到端全过。
**预防**：每个 L3 维度交付前必须有端到端测试证据，见 [quality-standard.md](./quality-standard.md) §3。

## 变更历史

- 2026-09-06: 初始版本（收录 2026-08-25 ~ 2026-09-06 L3 建设实证经验）
