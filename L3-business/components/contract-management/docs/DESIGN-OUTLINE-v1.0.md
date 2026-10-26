# L3 通用合同管理专家 — 设计大纲（DESIGN-OUTLINE）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-OUTLINE |
| 版本 | v1.0 |
| 层级 | L3 通用业务层 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 状态 | 待审核 |
| 依据 | PRD-v1.0 + 系统架构 ADR-001 + 业界调研 tmp/clm-best-practices.md |

---

## 1. 设计原则

1. **纯函数核心**：所有公共 API 相同输入 → 相同输出，零副作用
2. **依赖注入**：分级表 `level_table`、风险规则 `custom_rules`、审核标准全部可注入，默认值对齐既有 SCA-001
3. **契约冻结**：公开 API 签名即契约，L4 依赖其稳定演进
4. **单一实现**：逻辑唯一存在（消除 skills/ 与 components/ 重复）

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  L4 业务实例（Bangcle 合同管理专家 / 其他企业）           │
│  依赖注入 level_table / custom_rules / 持久化 / OA 编排  │
└──────────────────────────┬──────────────────────────────┘
                           │ L4 → L3（唯一调用方向）
                           ▼
┌─────────────────────────────────────────────────────────┐
│  L3 contract-management（纯逻辑，零副作用）              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ models.py   │  │state_machine │  │  risk_engine   │ │
│  │ (数据模型)   │  │ (状态机+分级) │  │ (22条风险扫描) │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│  ┌─────────────┐  ┌─────────────────────────────────┐  │
│  │amount_utils │  │ contract_parser / audit_standard │ │
│  │ (金额工具)   │  │ (条款解析 / 审核标准库 43项)      │ │
│  └─────────────┘  └─────────────────────────────────┘  │
│  ✅ 纯函数 / 零副作用 / 可单元测试 / 不依赖 L4          │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 模块划分

| 模块 | 职责 | 副作用 |
|---|---|---|
| `core/models.py` | 6 个 dataclass（Contract/ApprovalConfig/ApprovalRecord/AuditLogEntry/RiskFinding/RiskReport）+ 状态枚举 + 流转图 | 零 |
| `core/state_machine.py` | 状态机 + 金额→层级映射 + 流转校验 + 动作计算（submit/approve/reject/sign/archive） | 零 |
| `core/risk_engine.py` | 22 条《民法典》规则 + 综合评级（high/medium/low） | 零 |
| `core/amount_utils.py` | 金额转中文大写 | 零 |
| `core/contract_parser.py` | 28 类核心条款解析 | 零 |
| `core/audit_standard.py` | 43 项审核标准 / 17 类别 | 零 |
| `core/contract_auditor.py` | 逐条审核逻辑 | 零（CLI 入口除外） |
| `tests/` | 单元测试（不依赖 DB/文件/网络） | — |

**目录结构**（对齐 finance-engine 的 L3 规范）：

```
L3-business/components/contract-management/
├── core/
│   ├── __init__.py          # 公共 API 导出
│   ├── models.py
│   ├── state_machine.py
│   ├── risk_engine.py
│   ├── amount_utils.py
│   ├── contract_parser.py
│   ├── audit_standard.py
│   └── contract_auditor.py
├── tests/
├── docs/                    # PRD / OUTLINE / DETAIL / VERIFICATION / OPERATIONS / IMPLEMENTATION-PLAN
└── README.md
```

---

## 4. 状态机设计

```
draft → review1 → review2 → review3 → approved → signed → archived
  ▲        │           │           │
  └────────┴───────────┴───────────┘     任一环节驳回 → 回 draft
```

**分级映射（默认，可注入）**：

| 金额区间 | 级别 | 角色序列 |
|---|---|---|
| < 10 万 | 1 | [销售经理] |
| 10-50 万 | 2 | [销售经理, 法务审查员] |
| 50-200 万 | 3 | [销售总监, 法务审查员, 财务经理] |
| > 200 万 | 4 | [VP/CEO, 法务总监, 财务总监] |

**动作语义**：
- `submit`：draft → review1，首个审批角色
- `approve`：reviewN → review(N+1) 或末级 → approved
- `reject`：任一 review → draft
- `sign`：approved → signed
- `archive`：signed → archived

---

## 5. 接口契约（摘要）

| 接口 | 签名 |
|---|---|
| 分级查询 | `get_approval_config(amount, level_table=None) -> ApprovalConfig` |
| 流转校验 | `can_transition(from_status, to_status) -> bool` |
| 状态推进 | `next_approval_status(amount, current_status, action, level_table=None) -> (next, role, level)` |
| 风险扫描 | `scan_text(text, custom_rules=None) -> RiskReport` / `scan_text_dict(...) -> dict` |
| 金额大写 | `amount_to_chinese(amount) -> str` |
| 条款解析 | `parse_contract(text) -> ParsedContract` |
| 逐条审核 | `audit_text(text) -> AuditReport` |

完整 dataclass 定义与函数签名在 DETAIL 文档中冻结。

---

## 6. 与既有 SCA-001 的关系

- **代码基线**：迁移 `L3-business/skills/contract-approval/core/` + `scripts/` 纯逻辑部分
- **契约以本文档为准**：迁移完成后验证数据流、生命周期、接口签名与文档一致（AGENTS.md 旧代码迁移规范）
- **消除重复**：skills/ 下保留兼容层（DEPRECATED 标记），正式入口指向 L3 组件
- **既有 58 pytest + L4 e2e**：回归锁定

---

## 7. 演进方向

1. 风险规则扩展：custom_rules 数据化（JSON/YAML）
2. 审核标准库版本管理
3. 模板条款库抽象（配合 L4）

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初稿 |

---

## 9. 修订 v1.1（2026-10-27，基于 28 来源调研补充）

### 9.1 新增模块：OA 连接器抽象

| 模块 | 职责 |
|---|---|
| `core/oa/base.py`（OaProvider ABC） | 抽象接口：`get_contract_attachment` / `query_process` / `push_result` / `register_callback`；**放 L3 作为通用模式，具体厂商实现放 L4 注入** |
| `core/risk/dual_track.py` | 双轨风险引擎：阈值规则（确定性，22条）+ 语义判断（LLM，可配置开关） |

### 9.2 新增设计原则

1. **合同原文不发公网模型**：敏感信息本地处理；公网模型仅用于通用条款分析或脱敏后调用
2. **法条引用受控**：风险报告中的法条依据只能来自受控规则库，不允许 LLM 自由生成
3. **规则库版本化 + 反馈闭环**：风险规则 / 审核标准带版本号，支持法务持续迭代
4. **可追溯性**：每条 RiskFinding 含 `source_location`（原文位置）+ `rule_id`（规则ID）+ `legal_basis`（法条依据）
