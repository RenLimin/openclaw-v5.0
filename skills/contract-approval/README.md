# 销售合同审批模块 (SCA-001)

> L4 专有业务层组件 | 基于《民法典》合同编 + CLM 7 阶段方法论

## 快速开始

```bash
# 1. 初始化数据库
python3 scripts/approval_engine.py init

# 2. 创建合同
python3 scripts/approval_engine.py create \
  --title "技术服务合同-XXX项目" \
  --type tech_service \
  --party-a "我方公司" \
  --party-b "客户公司" \
  --amount 90000

# 3. 提交审批
python3 scripts/approval_engine.py submit --contract-id 1

# 4. 风险扫描
python3 scripts/risk_scanner.py scan --contract-id 1

# 5. 生成合同文档
python3 scripts/contract_gen.py generate --contract-id 1

# 6. 查看合同详情
python3 scripts/approval_engine.py show --contract-id 1
```

## 目录结构

```
contract-approval/
├── SKILL.md              # 技能入口
├── README.md             # 本文件
├── templates/            # 合同模板
├── checklists/           # 审查清单
│   ├── sales-contract.md # 基于民法典的审查 checklist
│   └── risk-matrix.md    # 风险评估矩阵
└── scripts/              # 工具脚本
    ├── approval_engine.py   # 审批流程引擎
    ├── risk_scanner.py      # 风险扫描器
    ├── contract_gen.py      # 合同生成器
    └── schema.sql           # 数据库 schema
```

## 审批流程

```
DRAFT → REVIEW_1 → REVIEW_2 → REVIEW_3 → APPROVED → SIGNED → ARCHIVED
  ↑         │          │          │
  └─────────┴──────────┴──────────┘（驳回回 DRAFT）
```

## 分级审批

| 金额区间 | 层级 | 审批角色 |
|----------|------|----------|
| < 10 万 | 1 | 销售经理 |
| 10-50 万 | 2 | 销售经理 + 法务 |
| 50-200 万 | 3 | 销售总监 + 法务 + 财务 |
| > 200 万 | 4 | VP/CEO + 法务总监 + 财务总监 |

## 风险扫描

基于《民法典》合同编的 13 类条款扫描：
- 输出：通过 / 警告 / 不通过 三级
- 综合评级：高 / 中 / 低
- 每个检查项标注法条依据

## 数据模型

- `contracts`：合同主表
- `approvals`：审批流表
- `audit_logs`：审计日志表

## 与其他组件的关系

| 层级 | 组件 | 关系 |
|------|------|------|
| L3 | 合同管理维度 | 继承通用能力 |
| L2 | 持久化适配 | 复用 SQLite |
| L2 | Office 文档生成 | 复用 python-docx |
| L2 | 知识库工具链 | 复用模板索引 |

## 验证记录

- [x] 数据库初始化
- [x] 合同创建 + 编号生成
- [x] 审批流转（通过/驳回）
- [x] 风险扫描输出
- [x] 合同生成（docx）
- [x] 审计日志完整
- [x] 端到端流程验证
