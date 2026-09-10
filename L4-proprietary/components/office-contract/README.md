# Office 合同审批模块 (OFC-001)

> L4 专有业务层 — Office 合同审批工作流
> 组件代号: OFC-001
> 基于 SCA-001 (skills/contract-approval) 通用合同审批能力构建

## 概述

面向企业 Office 场景的销售合同审批全流程管理，覆盖从合同起草到归档的完整生命周期。

## 架构

```
┌─────────────────────────────────────────────────────┐
│           L4 Office 层 (本模块) — 持久化 + 编排      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │   CLI    │  │ Services  │  │  Office 特化配置  │  │
│  │contractctl│  │  (业务)  │  │  (甲方/角色/SLA)  │  │
│  └──────────┘  └─────┬─────┘  └──────────────────┘  │
│                      │ 数据库读写 / 文件 I/O         │
└──────────────────────┼──────────────────────────────┘
                       │ 调用 (L4 → L3)
                       ▼
┌─────────────────────────────────────────────────────┐
│    L3 通用层 (skills/contract-approval/core)         │
│     纯逻辑 · 零副作用 · 可单元测试                    │
│  审批状态机 · 风险扫描引擎 · 数据模型 · 金额工具     │
│  条款解析器 · 审核标准库 · 逐条审核器               │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              L2 基础设施层                           │
│  SQLite 持久化 · OCR 数字化 · python-docx 文档生成  │
└─────────────────────────────────────────────────────┘
```

## 核心能力

| 能力 | 说明 |
|------|------|
| 合同起草 | 录入基本信息，自动生成合同编号 |
| 分级审批 | 按金额自动判定审批层级（1~4级） |
| 风险扫描 | 基于《民法典》13 类条款自动扫描 |
| 合同生成 | 基于模板生成 docx 合同文档 |
| 签署归档 | 签署 → 归档，完整状态流转 |
| 审计日志 | 所有操作留痕，不可篡改 |

## 审批层级

| 金额范围 | 层级 | 审批角色 | SLA |
|----------|------|----------|-----|
| < 10 万 | 1 级 | 销售经理 | 1 工作日 |
| 10 - 50 万 | 2 级 | 销售经理 → 法务审查员 | 2 工作日 |
| 50 - 200 万 | 3 级 | 销售总监 → 法务审查员 → 财务经理 | 3 工作日 |
| > 200 万 | 4 级 | VP/CEO → 法务总监 → 财务总监 | 5 工作日 |

## 状态机

```
draft → review1 → review2 → review3 → approved → signed → archived
  ↓        ↓         ↓         ↓
  └────────┴─────────┴─────────┘  (任一环节驳回 → 回退 draft)
```

## Quick Start

```bash
cd L4-proprietary/components/office-contract

# 1. 初始化数据库
python3 -m cli.contractctl init

# 2. 创建合同
python3 -m cli.contractctl create \
  --title "技术服务合同-XX项目" \
  --party-b "客户公司名称" \
  --amount 250000 \
  --type tech_service \
  --effective-date 2026-09-01 \
  --expiry-date 2027-08-31

# 3. 提交审批
python3 -m cli.contractctl submit --id 1

# 4. 风险扫描
python3 -m cli.contractctl risk-scan --id 1

# 5. 分级审批（按角色依次审批）
python3 -m cli.contractctl approve --id 1 --approver "张经理" --role "销售经理" --comment "同意"
python3 -m cli.contractctl approve --id 1 --approver "李法务" --role "法务审查员" --comment "合规"

# 6. 生成合同文档
python3 -m cli.contractctl generate --id 1

# 7. 签署 & 归档
python3 -m cli.contractctl sign --id 1
python3 -m cli.contractctl archive --id 1

# 8. 查看详情
python3 -m cli.contractctl show --id 1
```

## 目录结构

```
office-contract/
├── cli/
│   ├── __init__.py
│   └── contractctl.py      # CLI 入口 (contractctl)
├── services/
│   ├── __init__.py
│   └── contract_service.py # 业务服务层
├── config/
│   ├── __init__.py
│   └── settings.py         # Office 场景配置
├── tests/
│   └── test_e2e.py         # 端到端集成测试
├── outputs/                # 生成的合同文档
└── README.md
```

## 测试

```bash
cd L4-proprietary/components/office-contract
python3 tests/test_e2e.py
```

覆盖 25 个测试用例，11 个测试阶段：
- 数据库初始化
- 合同创建（4个金额级别）
- 提交审批
- 风险扫描
- 1级审批（单步）
- 3级审批（多步）
- 驳回回退机制
- 合同文档生成
- 签署与归档
- 审计日志
- 审批记录

## 依赖

- Python 3.10+
- python-docx (合同文档生成)
- SQLite (Python 内置)
- SCA-001 (skills/contract-approval，提供风险扫描规则、金额大写等能力)

## 相关文档

- **L3 架构与职责边界**：[ARCHITECTURE.md](../../../L3-business/skills/contract-approval/ARCHITECTURE.md)
- **架构决策记录**：[ADR-031](../../../docs/architecture/adr/ADR-202609-031-contract-approval-l3-l4-boundary.md)
- 风险扫描规则：`L3-business/skills/contract-approval/checklists/risk-matrix.md`
- 审核标准库：`L3-business/skills/contract-approval/checklists/sales-contract.md`
- L3 契约测试：`L3-business/skills/contract-approval/tests/test_l3_contract.py`
