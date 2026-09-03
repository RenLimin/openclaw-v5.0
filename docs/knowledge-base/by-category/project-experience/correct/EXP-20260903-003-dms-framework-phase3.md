---
title: "DMS 框架 Phase 3 知识库建设经验"
id: EXP-20260903-003
date: 2026-09-03
type: correct
project: delivery-management-framework
tags: [dms, framework, phase3, knowledge-base, documentation]
---

# DMS 框架 Phase 3 知识库建设经验

## 背景
Phase 2 完成 5 个通用模块后，Phase 3 建设交付管理知识库，为框架提供知识底座。

## 成果
65 个文件，5,611 行文档。

| 类别 | 文件数 | 说明 |
|------|--------|------|
| 能力知识 | 12 | 12 个能力原子的知识卡片 |
| 方法论 | 13 | PMBOK + 敏捷 + RACI + ITIL |
| 角色模板 | 24 | 6 角色 × (SOUL + AGENTS + IDENTITY + capability-map) |
| 交付物模板 | 8 | 项目章程/RACI/里程碑/风险/状态报告/检查单/变更/经验 |
| 数据模型 | 3 | ER图 + 状态机 + schema.sql |
| 外部参考 | 3 | OpenProject + Plane + GitHub Projects |
| 索引 | 2 | README + INDEX |

## 4 批并行开发的教训

### 1. 方法论 subagent 输出为空（幻觉）
- **问题**：methodologies subagent 报告"13 篇完成"，但实际文件目录全空
- **根因**：subagent 可能把"写好了"当成"完成了"，但实际没写文件
- **教训**：
  - 每批 subagent 任务必须包含**明确的验证命令**
  - 主 agent 必须**逐条验证文件存在**，不能信汇报
  - 写文件任务要给具体的 `cat > file << EOF` 式指令，而不是"写一篇文档"
- **修复**：主 agent 直接补写，比重新 spawn 更快

### 2. 内容质量可控
- 能力知识 12 篇：87-126 行，结构统一，质量好
- 角色 24 个：每个角色有差异化 SOUL，不重叠
- 数据模型 3 篇：基于实际代码，不是编造
- 参考 3 篇：与 DMS 框架的对比有深度

### 3. frontmatter 规范
- 能力知识/方法论/参考/数据模型：有完整 YAML frontmatter
- 角色文件：SOUL/AGENTS/IDENTITY 结构（与系统风格一致）
- 模板文件：填写指南 + 表格模板形式

## 知识库价值
1. **可检索**：可被 memory_search 语义检索
2. **可扩展**：L4 专有业务可以在 L3 基础上叠加
3. **可交付**：随框架一起交付，开箱即用
4. **人机共读**：既给 AI 读，也给人读

## 下一步
Phase 4：端到端框架验证，用一个示例交付项目跑通全流程。

## 参考
- [EXP-001](EXP-20260903-001-dms-framework-phase1.md)
- [EXP-002](EXP-20260903-002-dms-framework-phase2.md)
- [ADR-025](../../adr/ADR-202609-025-delivery-management-framework.md)
