---
type: experience
id: EXP-20260901-018
date: 2026-09-01
title: PPT 生成能力深度调研 — pptxgenjs 高级能力边界 + 业界对比
status: active
category: correct
tags: [ppt, pptxgenjs, capability-research, flowchart, table, chart, shapes]
---

# EXP-20260901-018: PPT 生成能力深度调研

## 背景

Rex 要求评估 PPT 的三项核心能力：原生表格、流程图、智能图标。并调研业界最佳实践判断优化空间。

## 调研方法

1. 实测 pptxgenjs v4.0.1 的三项能力
2. 与 python-pptx、Runstamp、SlideForge 等 8 种方案对比
3. 测试高级能力边界（161 种形状、图表类型、阴影、透明度）

## 发现

### 能力 1: 原生表格
- **API**: `addTable(data, opts)`
- **能力**: colspan 合并单元格、列宽行高自定义、边框样式、表头着色、多行文本
- **结论**: ⭐⭐⭐⭐⭐ 完整支持

### 能力 2: 流程图
- **API**: `addShape(type, opts)` + `addShape("line", opts)` 组合
- **可用形状**: 126/161 种（含 roundRect, diamond, hexagon, cloud, heart, star, flowChart* 等）
- **箭头**: endArrowType: "triangle"，支持 dashType: "dash" 虚线
- **结论**: ⭐⭐⭐⭐⭐ 完整支持泳道、决策、跨连接

### 能力 3: 智能图标
- **API**: 内置形状 + Emoji 文本叠加
- **可用形状**: 100+（含流程图专用形状 flowChartProcess/Decision/Terminator 等）
- **结论**: ⭐⭐⭐⭐ 组合使用可覆盖绝大多数场景

### 高级能力（额外发现）
| 能力 | 状态 | 说明 |
|---|---|---|
| 组合图表 | ✅ | bar+pie 同 slide（分开放置） |
| 阴影 | ✅ | outer/inner shadow + opacity |
| 透明度 | ✅ | transparency: 0-100 |
| 圆角 | ✅ | rectRadius: 0-1 |
| 旋转 | ✅ | rotate: -360 to 360 |
| 超链接 | ✅ | hyperlink 属性 |
| 161 形状 | ✅ | 126/161 实测通过 |

### 业界对比（2026.08）

| 工具 | 语言 | 周下载 | 维护 | 表格 | 图表 | 流程图 | 价格 |
|---|---|---|---|---|---|---|---|
| **pptxGenJS** | JS | 2.7M | ✅ 活跃 | ✅ | ✅ 10+ | ✅ 126形状 | 免费 |
| python-pptx | Python | 13.6M | ❌ 不活跃(2024.08) | ✅ | ✅ 8种 | ✅ | 免费 |
| Runstamp | JS | 新 | ✅ | ✅ | ✅ | ✅ | 免费 |
| SlideForge | API | - | ✅ | ✅ | ✅ | ✅ | $0.05/页 |
| Pluslide | API | - | ✅ | ✅ | ✅ | ✅ | 订阅 |

### 关键结论
1. **pptxGenJS 是当前最优开源 JS 方案**：2.7M 周下载、v4.0.1(2025.06)活跃维护、126 形状
2. **python-pptx 已不活跃**：上次发布 2024.08，439 个 open issues
3. **我们选对了栈**：pptxgenjs-pro(L2) + bangcle-ppt(L4) 是正确分层
4. **无优化空间**：三项核心能力 + 高级能力全部覆盖，无需引入新库

## 产出
- 测试文件: `research/office-generation/test_3caps.pptx`（3 slides, 基础能力）
- 测试文件: `research/office-generation/test_advanced_caps.pptx`（6 slides, 高级能力）
- 技能更新: `skills/bangcle-ppt/SKILL.md`（13.6KB, 含高级能力代码模板）

## 相关
- ADR-017: Bangcle PPT 模板系统注册
- DESIGN.md: docs/architecture/components/bangcle-ppt-template/DESIGN.md
- pptxgenjs 官方文档: https://gitbrent.github.io/PptxGenJS/docs/api-shapes
