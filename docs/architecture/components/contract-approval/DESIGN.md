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

## 12. 三大核心能力（v2.0 新增）

### 12.1 条款解析器（contract_parser.py）

按《民法典》合同编 28 条核心条款类别，逐条解析合同原文：

| 能力 | 说明 |
|------|------|
| 条款分类 | 28 个条款类别，对应民法典合同编核心条文 |
| 原文提取 | 从合同文本中提取每个条款的原始段落 |
| 摘要生成 | 自动生成每个条款的摘要 |
| 关键术语提取 | 提取金额、日期、比例等关键数值 |
| 问题识别 | 自动识别条款中的明显问题 |

### 12.2 审核标准库（audit_standard.py）

基于《民法典》+ 司法解释 + 行业规范，形成统一的审核标准：

| 能力 | 说明 |
|------|------|
| 标准数量 | 43 项审核标准 |
| 条款类别 | 17 个（主体信息、合同标的、价款与报酬等） |
| 法条依据 | 每项标准标注对应的民法典条文 |
| 风险分级 | 高/中/低三级风险 |
| 建议模板 | 每项标准附带修改建议模板 |

### 12.3 逐条审核引擎（contract_auditor.py）

按审核标准逐条审核合同，输出结构化结果：

| 能力 | 说明 |
|------|------|
| 逐条审核 | 按 43 项标准逐条审核 |
| 证据引用 | 每项审核结果附带合同原文证据 |
| 问题描述 | 发现的问题和风险描述 |
| 修改建议 | 具体的修改建议和替代文本 |
| 综合评级 | 基于最高风险项的综合评级 |
| 审核结论 | 通过/有条件通过/驳回 |

## 13. 变更历史（续）

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-02 | 0.2 | 新增三大核心能力：条款解析器 + 审核标准库 + 逐条审核引擎 |


## 7. 输出标准（Excel 审批报告）

### 7.1 业务目标

合同审批模块的核心交付物是**统一格式的 Excel 审批报告**，目标：

1. **100% 全文覆盖**：合同原文逐字呈现，不遗漏任何段落
2. **结构化解析**：每段条款都有法条依据 + 解析说明 + 风险标注
3. **风险分级**：P0（高危）/ P1（中危）/ P2（低危）三级，颜色区分
4. **可执行整改**：每条风险对应明确的整改建议，按优先级排序
5. **签署要素审计**：扫描件/图片合同自动检测公章、签字、日期、页码完整性

### 7.2 输出格式规范

统一为 **3 + 1** 个 Sheet 结构（3 个核心 + 1 个可选）：

| Sheet | 名称 | 必填 | 说明 |
|---|---|---|---|
| 1 | 合同条款拆解 | ✅ | 合同基本信息 + 全文结构总览 + 逐段拆解详情 |
| 2 | 统一审核标准 | ✅ | 标准分类统计 + 34 项审核标准明细 |
| 3 | 审核与整改建议 | ✅ | 风险分级统计 + 整改清单（按优先级排序） |
| 4 | 签署要素审计 | ⭕ | OCR 驱动，仅扫描件/图片合同时生成 |

### 7.3 Sheet 1：合同条款拆解（详细规范）

**结构（自上而下）**：

```
[标题行] 合同条款拆解报告
[基本信息区]
  ├─ 合同名称 / 合同类型
  ├─ 甲方 / 乙方
  ├─ 合同金额 / 服务期限
  ├─ 签署日期 / 审核时间
  └─ 全文有效字符数 / 段落数
[空行]
[全文结构总览]
  └─ N 段条款的摘要列表（编号 + 类别 + 摘要 + 风险）
[空行]
[逐段拆解详情]
  └─ 每段：
     ├─ 段落编号 + 段落标题
     ├─ 原文摘要（前120字）
     ├─ 完整原文（可折叠/多行）
     ├─ 解析说明（对应法条 + 合规判断）
     └─ 风险提示（P0/P1/P2，颜色标注）
```

**段落拆分规则**：
- 优先按「第X条」拆分（中文数字 + 阿拉伯数字均支持）
- 无编号合同按自然段/标题行拆分
- 确保拆分后拼接回原文 = 100% 完整（逐字对比校验）

### 7.4 Sheet 2：统一审核标准

**结构**：
- 标准分类统计（按类别汇总数量）
- 34 项审核标准明细（编号/类别/标准名称/法条依据/判定规则）

### 7.5 Sheet 3：审核与整改建议

**结构**：
- 顶部风险统计摘要（P0/P1/P2 数量 + 颜色标注）
- 风险分级统计（按类别/等级交叉统计）
- 整改建议清单（按 P0 → P1 → P2 优先级排序）
  - 每条含：风险项 / 风险等级 / 法条依据 / 问题描述 / 整改建议 / 涉及条款

### 7.6 Sheet 4：签署要素审计（可选）

OCR v5 驱动，仅在提供扫描件/图片合同时生成：

| 要素 | 检测项 | 输出 |
|---|---|---|
| 公章/合同章 | 甲方公章、乙方公章 | 状态/页码/置信度/截图 |
| 法定代表人签字 | 甲方签字、乙方签字 | 状态/页码/置信度/截图 |
| 签署日期 | 合同签署日期 | 状态/识别结果/置信度 |
| 页码完整性 | 全文页码连续 | 状态/总页数/校验结果 |

### 7.7 视觉规范

| 元素 | 颜色 | 字体 |
|---|---|---|
| 标题 | 深蓝底白字 | 加粗 16pt |
| 章节标题 | 浅蓝底黑字 | 加粗 12pt |
| P0 高危 | 红底白字 | 加粗 |
| P1 中危 | 橙底白字 | 加粗 |
| P2 低危 | 黄底黑字 | 正常 |
| 通过项 | 绿底白字 | 正常 |
| 表格表头 | 深灰底白字 | 加粗 |

### 7.8 输入来源支持

| 输入类型 | 处理方式 | 输出 Sheet 4 |
|---|---|---|
| .docx / .doc 文本合同 | python-docx 直接提取文本 | ❌ |
| .pdf 文本层合同 | PyMuPDF 提取文本层 | ⭕（可选，如有签署页图片） |
| .pdf 扫描件/图片 | OCR v5 + RapidOCR 全文识别 | ✅ |
| 图片（jpg/png） | OCR v5 单页识别 | ✅ |

---

> **版本**: v1.0 (2026-09-03) · 基于信创数安技术服务合同和指南针软件授权合同两次实测确定
