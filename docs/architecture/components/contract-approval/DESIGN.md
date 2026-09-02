---
component_id: SCA-001
component_name: 销售合同审批模块
layer: L4
status: 🔨 开发中
date: 2026-09-02
adr: ADR-202609-018
---

# SCA-001: 销售合同审批模块 — 设计文档

## 1. 定位

### 1.1 层级归属

| 层级 | 关系 | 说明 |
|------|------|------|
| L4 专有业务层 | ★ 本组件 | 销售合同专用审批流 + 模板 + 规则 |
| L3 通用业务层 | 继承 | 合同管理维度：CLM 7 阶段 + 民法典 + 角色 |
| L2 基础设施层 | 复用 | 持久化 / Office文档 / 凭据 / 可观测 / 知识库 |
| L1 运行时 | 通过适配层 | OpenClaw Agent Loop / Tools / Memory |

### 1.2 核心问题

解决销售合同从起草到归档的全生命周期管理，提供：
1. 分级审批流程（按金额 4 级）
2. 风险扫描（基于民法典 13 项检查）
3. 合同生成（基于模板库）
4. 审计追踪（完整状态变更历史）

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **独立可运行** | `skills/contract-approval/` 自包含，零外部依赖 |
| **可扩展** | 预留 REST API 契约，未来整合时只需加 API 层 |
| **知识驱动** | 基于 CLM 7 阶段方法论 + 民法典，不凭经验 |
| **辅助定位** | 风险扫描器是"辅助提醒"而非法务判断替代 |
| **可审计** | 所有状态变更写入 audit_logs，可追溯 |

## 3. 模块架构

```
skills/contract-approval/
├── SKILL.md              # 技能入口（frontmatter + 使用说明）
├── README.md             # 详细文档
├── templates/            # 合同模板
│   ├── tech-service.docx # 技术服务合同
│   ├── software-license.docx # 软件许可合同
│   └── sow.docx          # 工作说明书
├── checklists/           # 审查清单
│   ├── sales-contract.md # 销售合同审查 checklist
│   └── risk-matrix.md    # 风险评估矩阵
└── scripts/              # 工具脚本
    ├── approval_engine.py   # 审批流程引擎
    ├── risk_scanner.py      # 风险扫描器
    └── contract_gen.py      # 合同生成器
```

## 4. 审批流程设计

### 4.1 状态机

```
DRAFT → REVIEW_1 → REVIEW_2 → REVIEW_3 → APPROVED → SIGNED → ARCHIVED
  ↑         │          │          │
  └─────────┴──────────┴──────────┘（任一环节驳回回 DRAFT）
```

### 4.2 状态定义

| 状态 | 名称 | 说明 |
|------|------|------|
| `DRAFT` | 起草 | 合同创建/编辑中 |
| `REVIEW_1` | 业务初审 | 销售经理审批 |
| `REVIEW_2` | 法务审查 | 法务审查员审批 |
| `REVIEW_3` | 财务审查 | 财务审批 |
| `APPROVED` | 审批通过 | 所有审批完成 |
| `SIGNED` | 已签署 | 双方签署完成 |
| `ARCHIVED` | 已归档 | 合同归档 |
| `REJECTED` | 已驳回 | 任一环节驳回 |

### 4.3 分级审批阈值

| 金额区间 | 审批层级 | 审批角色 | SLA |
|---|---|---|---|
| < 10 万 | 1 级 | 销售经理 | 1 工作日 |
| 10 - 50 万 | 2 级 | 销售经理 + 法务 | 2 工作日 |
| 50 - 200 万 | 3 级 | 销售总监 + 法务 + 财务 | 3 工作日 |
| > 200 万 | 4 级 | VP/CEO + 法务总监 + 财务总监 | 5 工作日 |

> 当前为单用户模式，审批角色由 Rex 代行。

## 5. 数据模型

### 5.1 contracts 表

```sql
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT UNIQUE NOT NULL,           -- 合同编号 CON-YYYY-NNN
    title TEXT NOT NULL,                         -- 合同名称
    contract_type TEXT NOT NULL,                 -- 类型：tech_service / software_license / sow
    party_a TEXT NOT NULL,                       -- 甲方（我方）
    party_b TEXT NOT NULL,                       -- 乙方（客户）
    amount REAL NOT NULL,                        -- 合同金额（元）
    tax_rate REAL DEFAULT 0.06,                  -- 税率
    effective_date DATE,                         -- 生效日期
    expiry_date DATE,                            -- 到期日期
    status TEXT DEFAULT 'draft',                 -- 状态
    current_approver TEXT,                       -- 当前审批人
    created_by TEXT NOT NULL,                    -- 创建人
    file_path TEXT,                              -- 合同文件路径
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 approvals 表

```sql
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    approval_level INTEGER NOT NULL,             -- 审批层级（1/2/3/4）
    approver_role TEXT NOT NULL,                 -- 审批角色
    approver_name TEXT NOT NULL,                 -- 审批人
    action TEXT NOT NULL,                        -- 动作：approve / reject / delegate
    comment TEXT,                                -- 审批意见
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contracts(id)
);
```

### 5.3 audit_logs 表

```sql
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    action TEXT NOT NULL,                        -- 操作类型
    operator TEXT NOT NULL,                      -- 操作人
    from_status TEXT,                            -- 变更前状态
    to_status TEXT,                              -- 变更后状态
    detail TEXT,                                 -- 详情（JSON）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contracts(id)
);
```

## 6. 风险扫描器设计

### 6.1 检查项（基于民法典）

| 类别 | 检查项 | 风险等级 | 法条依据 |
|---|---|---|---|
| 主体信息 | 双方名称/地址/联系方式完整 | 高 | §470 |
| 合同标的 | 服务内容明确、可衡量 | 高 | §470 |
| 金额与支付 | 金额/支付方式/发票明确 | 高 | §510 |
| 履行期限 | 服务期限/交付时间明确 | 中 | §511 |
| 验收标准 | 验收方式/标准/期限明确 | 高 | §509 |
| 违约责任 | 违约条款对等/违约金合理 | 高 | §577-585 |
| 争议解决 | 管辖法院/仲裁机构明确 | 高 | §507 |
| 知识产权 | 成果归属明确 | 中 | §847 |
| 保密条款 | 保密范围/期限/违约责任 | 中 | §501 |
| 不可抗力 | 不可抗力定义/通知义务 | 低 | §180 |
| 合同解除 | 解除条件/通知方式 | 中 | §563 |
| 格式条款 | 无加重对方责任的格式条款 | 中 | §496-498 |
| 签字盖章 | 授权代表/公章齐全 | 高 | §490 |

### 6.2 输出格式

```json
{
  "contract_no": "CON-2026-001",
  "overall_risk": "medium",
  "scan_time": "2026-09-02T12:00:00",
  "findings": [
    {
      "category": "主体信息",
      "item": "双方名称/地址/联系方式完整",
      "status": "pass",
      "risk": "high",
      "detail": "双方信息完整"
    },
    {
      "category": "违约责任",
      "item": "违约金是否合理",
      "status": "warning",
      "risk": "high",
      "detail": "甲方逾期付款违约金为日1%，乙方逾期交付违约金为日1%，建议确认是否对等"
    }
  ],
  "summary": {
    "pass": 10,
    "warning": 2,
    "fail": 1
  }
}
```

## 7. 合同生成器设计

### 7.1 模板变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `{{contract_no}}` | 合同编号 | CON-2026-001 |
| `{{party_a_name}}` | 甲方名称 | 北京梆梆安全科技有限公司 |
| `{{party_a_address}}` | 甲方地址 | 北京市海淀区... |
| `{{party_b_name}}` | 乙方名称 | 北京信创数安科技有限公司 |
| `{{party_b_address}}` | 乙方地址 | 北京市海淀区... |
| `{{amount}}` | 合同金额 | 90000.00 |
| `{{amount_cn}}` | 金额大写 | 玖万元整 |
| `{{service_content}}` | 服务内容 | ... |
| `{{effective_date}}` | 生效日期 | 2026-09-07 |
| `{{expiry_date}}` | 到期日期 | 2027-09-06 |
| `{{sign_date}}` | 签订日期 | 2026-09-02 |

### 7.2 生成流程

```
模板选择 → 变量填充 → docx 生成 → 质量检查 → 输出文件
```

## 8. 接口契约（未来整合）

### 8.1 REST API

```
POST   /api/contracts              # 创建合同
GET    /api/contracts              # 合同列表
GET    /api/contracts/:id          # 合同详情
PUT    /api/contracts/:id/status   # 状态变更
POST   /api/contracts/:id/approve  # 提交审批
GET    /api/contracts/:id/audit    # 审计日志
POST   /api/contracts/scan         # 风险扫描
```

### 8.2 CLI 接口（当前）

```bash
# 创建合同
python scripts/approval_engine.py create --title "..." --party-b "..." --amount 90000

# 审批操作
python scripts/approval_engine.py approve --contract-id 1 --action approve --comment "..."

# 风险扫描
python scripts/risk_scanner.py scan --contract-id 1

# 生成合同
python scripts/contract_gen.py generate --contract-id 1 --template tech-service
```

## 9. 与其他层的关系

### 9.1 L3 继承

| L3 能力 | 复用方式 |
|---------|---------|
| CLM 7 阶段 | 审批流状态机映射 CLM 阶段 |
| 中国民法典合同编 | 风险扫描器法条依据 |
| 合同经理角色 | Skill 中的审批流程指导 |
| 法务审查员角色 | Skill 中的风险审查指导 |

### 9.2 L2 复用

| L2 组件 | 复用方式 |
|---------|---------|
| 持久化适配 | SQLite + Repository 模式 |
| Office 文档生成 | python-docx / docxtpl |
| 凭据管理 | 合同对方信息 SecretRef |
| 可观测性 | 审批流程日志 |
| 知识库工具链 | 合同模板索引 |

## 10. 验证标准

| 验证项 | 标准 |
|--------|------|
| Skill 加载 | `contract-approval` 出现在 skill 列表 |
| 审批引擎 | 状态流转正确（draft→review→approved→signed） |
| 风险扫描 | 对示例合同输出结构化风险报告 |
| 合同生成 | 基于模板生成 docx，关键信息正确 |
| 数据持久化 | 合同/审批/审计数据写入 SQLite |
| 独立性 | 不修改任何已有 L2/L3 组件 |

## 11. 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-02 | 0.1 | 初始设计文档 |
