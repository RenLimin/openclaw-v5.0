---
title: "Subagent 输出截断问题的规避方案"
description: "subagent 通过 sessions_history 返回大文本时被 display-cap 截断，改用'写文件+主agent读取'模式规避"
source: "OpenClaw sessions_history 工具 + subagent 实测"
version: "2026"
category: "project-experience"
type: "correct"
tags: ["subagent", "truncation", "display-cap", "workflow"]
last_reviewed: "2026-09-02"
---

# EXP-001: Subagent 输出截断问题的规避方案

## 背景

在合同审批模块建设过程中，使用 subagent 并行读取 OpenClaw 官方文档。
subagent 成功完成任务并通过 `sessions_history` 返回结果，但输出被截断。

## 问题

### 现象
- `sessions_history` 返回 `contentTruncated: true` + `truncated: true, reason: "display-cap"`
- 大段文本在 display-cap 处被截断，丢失后续内容
- 两个 subagent 都受到影响：
  1. CLM 生命周期读取（7 阶段）— 实际未截断（stopReason=stop，内容完整）
  2. OpenClaw 文档研究 — Skills/自动化部分丢失

### 根因
`sessions_history` 工具有**显示截断上限**（display-cap），超过字节限制的输出会被截断。
这不是模型输出截断（`stopReason: "stop"` 表示模型正常结束），而是**传输层的显示截断**。

### 影响
- 方案设计层面：不影响（CLM 完整、Agent 架构核心已拿到）
- 具体实现层面：部分影响（Skills 详细机制、自动化文档未完整获取）

## 解决方案

### 方案 1：写文件 + 主 agent 读取（推荐）

在 subagent 的 task 中明确要求将结果写入文件，主 agent 直接 `read` 文件：

```
task: "读取文档并将结果写入 /workspace/tmp/xxx.md"
```

优点：
- 完全不依赖 sessions_history 的传输
- 文件内容无截断
- 主 agent 可按需读取

缺点：
- 需要额外的文件清理

### 方案 2：拆分更细粒度的 subagent

每个 subagent 只读 2-3 个文件，减少单次输出量。

### 方案 3：主 agent 直接读关键文件

对于路径已知的文件，主 agent 直接 `read` 或 `exec + head`，不派 subagent。

## 决策

**采用方案 1 为主、方案 3 为辅的混合策略**：
- 大量文档汇总 → subagent 写文件
- 关键文件（<200 行）→ 主 agent 直接读
- 并行任务 → 每个 subagent 聚焦单一领域

## 验证

合同审批模块建设过程中，通过 `exec + head` 直接读取 OpenClaw 官方文档，
成功获取 Skills/Automation/Hooks/Tool Plugins 等核心内容，未再出现截断。

## 教训

1. **subagent 不是万能的**：大文本输出场景，写文件比返回 history 更可靠
2. **display-cap ≠ 模型截断**：`stopReason: "stop"` + `truncated: true` 是传输层问题，不是模型问题
3. **粒度控制**：单个 subagent 任务不要太大，聚焦 2-3 个文件为宜
4. **验证先行**：拿到 subagent 结果后，先确认 `stopReason` 和 `truncated` 字段，判断是否需要补读

## 相关

- OpenClaw 官方文档：`/opt/homebrew/lib/node_modules/openclaw/docs/`
- 合同审批模块：`skills/contract-approval/`
- ADR-018：`docs/knowledge-base/by-category/project-experience/adr/ADR-202609-018-sales-contract-approval.md`
