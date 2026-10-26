# SCA-001 销售合同审批 — 设计大纲（DESIGN-OUTLINE）

> 组件 ID：SCA-001
> 版本：v1.0（2026-09-28 补录）
> 依据：PRD-v1.0 + ADR-202609-018 + ADR-202609-031
> 详细设计：ARCHITECTURE.md（276 行，L3/L4 边界完整定义）

---

## 1. 整体架构

```
L4 office-contract（持久化 + 编排 + CLI）
  contractctl CLI / contract_service / settings / SQLite / docx 生成
        │ 调用（L4 → L3，依赖注入）
        ▼
L3 contract-approval core（纯逻辑核心）
  models（数据模型）
  state_machine（状态机 + 分级规则）
  risk_engine（22 条风险规则）
  amount_utils（金额工具）
  contract_parser / audit_standard / contract_auditor（解析 + 审核标准库）
        │ 依赖
        ▼
L2 基础设施
  OCR-001（扫描件数字化）/ Office 生成 011 / 持久化 006
```

## 2. 模块划分

| 模块 | 层 | 职责 | 副作用 |
|---|---|---|---|
| `core/models.py` | L3 | 6 个 dataclass（Contract/ApprovalConfig/ApprovalRecord/AuditLogEntry/RiskFinding/RiskReport） | 零 |
| `core/state_machine.py` | L3 | 状态机 + 金额→层级映射 + 流转校验 | 零 |
| `core/risk_engine.py` | L3 | 22 条《民法典》规则 + 综合评级 | 零 |
| `core/amount_utils.py` | L3 | 金额转中文大写 | 零 |
| `scripts/contract_parser.py` | L3 | 28 类核心条款解析 | 零（CLI 入口除外） |
| `scripts/audit_standard.py` | L3 | 43 项审核标准 / 17 类别 | 零 |
| `scripts/contract_auditor.py` | L3 | 逐条审核逻辑 | 零（CLI 入口除外） |
| `services/contract_service.py` | L4 | 业务编排 + DB CRUD + 审计持久化 | 有 |
| `cli/contractctl.py` | L4 | 命令行交互 | 有 |
| `config/settings.py` | L4 | Office 场景定制（默认甲方/角色映射/SLA） | 有 |

## 3. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| L3/L4 边界 | L3 纯逻辑零副作用 / L4 持久化编排 | ADR-031；L3 可被任意 L4 复用 |
| 状态机 | 显式 7 态 + 驳回回退 draft | 审批流程刚性，禁止跳步 |
| 分级注入 | `level_table` 参数依赖注入 | L3 默认四级，L4 注入场景定制 |
| 风险规则 | 数据化 `RiskRule` 列表 + `custom_rules` | 规则可扩展，不写死 |
| 重复消除 | 1400 行重复 → 590 行（-58%） | 单一实现路径（禁止功能共存原则） |

## 4. 状态机

```
draft → review1 → review2 → review3 → approved → signed → archived
  ▲        │（驳回）    │
  └────────┴────────────┘   任一环节驳回 → 回 draft
```

分级映射：<10万 → 1 级 / 10-50万 → 2 级 / 50-200万 → 3 级 / >200万 → 4 级（走完 review1~3）

## 5. 接口契约（摘要）

详见 ARCHITECTURE.md §4（完整 API 签名 + dataclass 定义）。

| 接口 | 签名 |
|---|---|
| 分级查询 | `get_approval_config(amount, level_table=None) → ApprovalConfig` |
| 流转校验 | `can_transition(from_status, to_status) → bool` |
| 状态推进 | `next_approval_status(amount, current_status, action, level_table=None) → (next, role, level)` |
| 风险扫描 | `scan_text(text, custom_rules=None) → RiskReport` |
| 金额大写 | `amount_to_chinese(amount) → str` |

## 6. 演进方向

1. 印章检测（图像识别）
2. 企业微信审批通知（L4 接口已预留）
3. 合同模板库（Bangcle 专有模板接入）
4. 审批 SLA 超时提醒

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-28 | v1.0 | 补录归档（实际架构见 ARCHITECTURE.md） |
