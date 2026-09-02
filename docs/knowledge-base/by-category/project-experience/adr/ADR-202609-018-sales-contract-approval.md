---
adr_id: ADR-202609-018
title: 销售合同审批模块（SCA-001）建设与层级归属
status: accepted
date: 2026-09-02
deciders: Rex
layer: L4
component_id: SCA-001
component_name: 销售合同审批模块
tags: [adr, contract, approval, sales, L4, skill]
---

# ADR-018: 销售合同审批模块（SCA-001）建设与层级归属

## 背景（Context）

Rex 提供了实际销售合同（信创-技术服务合同，梆梆安全移动应用安全合规检测平台续费升级服务，金额 ¥90,000），要求基于当前系统资产和知识库，搭建合同审批工作流/功能模块。

**核心约束**：
1. 独立且可扩展（单独使用 + 未来整合至自建系统）
2. 目前仅针对销售合同
3. 基于《民法典》及相关法律法规
4. 缺失能力按系统架构补到对应层级
5. 完全符合 AI Agent 官方文档描述

**现有资产盘点**：
- L3 合同管理维度：CLM 7 阶段知识库（7 篇）、中国民法典合同编、合同经理 + 法务审查员角色
- L2 基础设施：持久化适配（SQLite）、Office 文档生成（python-docx/docxtpl）、凭据管理、可观测性、知识库工具链
- L1 运行时：OpenClaw Agent Loop / Tools / Memory / Automation

## 决策（Decision）

**建设销售合同审批模块（SCA-001）**，归属 L4 专有业务层，以 OpenClaw Skill 形式交付。

**模块标识**：
- 组件 ID：SCA-001
- 模块名称：销售合同审批模块（Sales Contract Approval）
- 目录：`skills/contract-approval/`

## 理由（Rationale）

### 1. 销售合同 = 专有业务 → 归属 L4
- "仅针对销售合同" = 专有业务规则，不具备跨业务复用性
- 包含销售侧特化的审批阈值、风险评估规则、模板类型
- 符合 L4「专有业务层」定义

### 2. 继承 L3 合同管理通用能力
- CLM 7 阶段方法论（需求→起草→谈判→审批→签署→履行→续签/终止）
- 中国民法典合同编（合同成立/效力/履行/违约）
- 合同经理 + 法务审查员角色定义
- L4 仅叠加：销售合同专用审批流 + 模板 + 风险规则

### 3. Skill 形式符合 OpenClaw 官方规范
- 官方文档：Skills 是 markdown 指令文件，教 agent 如何使用工具
- 加载优先级：Workspace skills > Bundled skills
- 通过 `agents.*.skills` allowlist 控制可见性
- 可独立使用，可单独启用/禁用

### 4. 复用 L2 基础设施（零新建）
| L2 组件 | 复用方式 |
|---------|---------|
| 持久化适配 | contracts / approvals / audit_logs 表 |
| Office 文档生成 | python-docx 生成合同 docx |
| 凭据管理 | 合同对方信息安全存储 |
| 可观测性 | 审批流程日志 |
| 知识库工具链 | 合同模板索引 |

### 5. 独立性与可扩展性
- 独立目录 `skills/contract-approval/`，自包含
- 零外部依赖（Python 标准库 + python-docx）
- 预留 REST API 接口契约，未来整合时只需加 API 层
- 核心业务逻辑（审批引擎、风险扫描器）与 IO 解耦

## 后果（Consequences）

### 正面
- ✅ 可独立使用：Skill 形式，加载即用
- ✅ 可扩展：预留 API 契约，未来整合到自建系统
- ✅ 符合规范：完全遵循 OpenClaw AI Agent 官方文档
- ✅ 知识驱动：基于 CLM 7 阶段 + 民法典，不是凭经验搭建
- ✅ 可审计：完整审计日志，状态变更可追溯

### 负面
- ⚠️ L4 组件增加，需要维护
- ⚠️ 当前为单用户模式，审批角色由 Rex 代行
- ⚠️ 风险扫描器定位为辅助提醒，不能替代法务专业判断

### 应对
- 通过 ADR + DESIGN.md 保持可追溯
- 未来对接真实组织架构时替换审批人配置
- 风险扫描器标注置信度，区分"必须修改"和"建议修改"

## 实现计划

- [ ] M1：ADR-018 + DESIGN.md + 数据模型 schema.sql
- [ ] M2：审查 checklist + 风险矩阵 + 销售合同模板（3 类）
- [ ] M3：审批流程引擎 + 风险扫描器 + 合同生成器
- [ ] M4：Skill 封装（SKILL.md）+ 端到端验证
- [ ] M5：架构文档同步（v2.10）+ commit

## 验证标准

| 验证项 | 标准 | 方式 |
|--------|------|------|
| Skill 加载 | `contract-approval` 出现在 skill 列表 | `openclaw skills list` |
| 审批引擎 | 合同状态流转正确（draft→review→approved→signed） | 端到端测试 |
| 风险扫描 | 对示例合同输出风险报告 | 实测 |
| 合同生成 | 基于模板生成 docx，关键信息正确 | 实测 |
| 数据持久化 | 合同/审批/审计数据写入 SQLite | 查询验证 |
| 独立性 | 不修改任何已有 L2/L3 组件 | 代码审查 |

## 相关决策

- 相关 ADR：ADR-002（知识库三维模型）、ADR-006（持久化适配）、ADR-010（知识库工具链）、ADR-016（Office 文档生成）
- 被替代：无

## 引用

- 系统架构：`docs/architecture/00-system-architecture.md` v2.8
- L3 合同管理：`docs/knowledge-base/by-category/business/contract-management/`
- CLM 7 阶段：`docs/knowledge-base/by-category/business/contract-management/knowledge/clm-lifecycle/`
- 民法典合同编：`docs/knowledge-base/by-category/business/contract-management/knowledge/legal-framework/chinese-contract-law.md`
- OpenClaw Skills 官方文档：`/opt/homebrew/lib/node_modules/openclaw/docs/tools/skills.md`
- OpenClaw Automation 官方文档：`/opt/homebrew/lib/node_modules/openclaw/docs/automation/`

## 变更历史

- 2026-09-02: proposed
- 2026-09-02: accepted
