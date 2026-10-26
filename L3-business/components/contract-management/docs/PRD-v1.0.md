# L3 通用合同管理专家 — 产品需求文档（PRD）

| 项 | 值 |
|---|---|
| 文档 | PRD |
| 版本 | v1.0 |
| 层级 | L3 通用业务层 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 状态 | 待审核 |
| 依据 | 系统架构 00-system-architecture.md（ADR-001 四层架构）+ 业界最佳实践调研 tmp/clm-best-practices.md + 既有 SCA-001 PRD |

---

## 1. 背景与目标

### 1.1 背景

现有合同审批能力（L3-business/skills/contract-approval，SCA-001）已实现 L3 core 纯逻辑 + L4 演示编排，但存在结构性缺口：

1. **未按分层落位**：L3 core 在 `skills/` 目录，未正式成为 `L3-business/components/` 组件，无法被 L4 业务实例规范复用
2. **文档为补录**：PRD/DESIGN-OUTLINE 为 2026-09-28 补录，与实际架构存在偏差（ARCHITECTURE.md 声称的 L4 office-contract 组件实际不存在）
3. **缺抽象边界**：状态机/风险规则已纯化，但缺少"通用能力被任意企业实例复用"的正式契约文档

### 1.2 目标

将合同管理**通用纯逻辑能力**正式化为 L3 组件，供任意 L4 业务实例（Bangcle 及其他企业）依赖注入复用：

- 统一数据模型：Contract / ApprovalRecord / AuditLog / RiskReport
- 审批状态机：7 态流转 + 驳回回退 + 分级规则可注入
- 风险扫描：22 条《民法典》规则 + 自定义规则扩展
- 条款解析 / 审核标准库 / 金额工具

### 1.3 成功标准

1. L3 组件零副作用（不 import L4 / 不碰 DB / 不碰文件 / 不碰网络），可独立单测
2. 状态机流转 100% 合法，非法流转被拒绝
3. 分级表、风险规则均可依赖注入，默认值对齐既有 SCA-001
4. 契约文档完整（本 PRD + OUTLINE + DETAIL + VERIFICATION + OPERATIONS + IMPLEMENTATION-PLAN）

---

## 2. 功能清单

| # | 功能 | 说明 | 优先级 |
|---|---|---|---|
| L3-F1 | 数据模型 | Contract / ApprovalConfig / ApprovalRecord / AuditLogEntry / RiskFinding / RiskReport（dataclass，纯数据） | P0 |
| L3-F2 | 审批状态机 | draft→review1→review2→review3→approved→signed→archived；驳回回 draft；操作合法性校验 | P0 |
| L3-F3 | 分级审批规则 | 按金额映射审批层级与角色；`level_table` 参数依赖注入 | P0 |
| L3-F4 | 风险扫描引擎 | 22 条《民法典》规则 + `custom_rules` 注入 + 综合评级（high/medium/low） | P0 |
| L3-F5 | 条款解析 | 按《民法典》28 类核心条款类别逐条解析 | P1 |
| L3-F6 | 审核标准库 | 43 项审核标准、17 个类别，每条带法条依据 | P1 |
| L3-F7 | 逐条审核 | 按标准库逐条审计，输出 pass/warning/fail/na + 证据 + 修改建议 | P1 |
| L3-F8 | 金额工具 | 金额转中文大写、大小写一致性校验 | P0 |

**明确不做（本期）**：不引入 LangGraph/向量库等重型依赖；不做多 agent 编排；不做合同在线编辑/全文高亮（对齐业界调研启示 9、10）。

---

## 3. 用户角色

| 角色 | 用途 |
|---|---|
| L4 业务开发者 | 调用 L3 API 构建企业实例（依赖注入 level_table / custom_rules） |
| 单元测试 | 无环境依赖直接验证逻辑 |

---

## 4. 验收标准

1. ✅ `grep sqlite3 core/*.py` 无结果；`grep "L4\|office-contract\|bangcle" core/*.py` 无结果
2. ✅ 状态机：7 态流转合法路径 + 非法路径全部拒绝（ValueError）
3. ✅ 分级：默认 <10万(1级)/10-50万(2级)/50-200万(3级)/>200万(4级)，注入自定义表生效
4. ✅ 风险扫描：22 条规则全部可触发、输出结构化 RiskReport；custom_rules 覆盖默认
5. ✅ 金额大小写：转换正确、校验不一致报错
6. ✅ 单测通过率 100%，覆盖 ≥ 90%

---

## 5. 非功能需求

| 项 | 要求 |
|---|---|
| 纯函数 | 相同输入 → 相同输出；不修改输入参数 |
| 可移植性 | 仅依赖 Python 3.10+ 标准库（dataclasses / re / datetime） |
| 契约稳定 | 公开 API 签名冻结，L4 依赖其稳定演进 |

---

## 6. 依赖与复用

| 依赖 | 关系 |
|---|---|
| 既有 L3-business/skills/contract-approval/core | 代码基线（迁移为正式组件，契约以本文档为准） |
| L4 实例 | 本组件不依赖任何 L4 |

---

## 7. 已知限制

1. 22 条规则覆盖《民法典》核心项，特殊行业规则需 custom_rules 注入
2. 印章检测、签名验证不在 L3 职责（属 L4/L2 OCR 场景）

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初稿（分层落位 + 正式契约） |

---

## 9. 修订 v1.1（2026-10-27，基于 28 来源业界调研补充）

### 9.1 新增功能

| # | 功能 | 说明 | 优先级 |
|---|---|---|---|
| L3-F9 | OA 连接器抽象（OaProvider） | base class：`get_contract_attachment` / `query_process` / `push_result` / `register_callback`；**抽象放 L3 作为通用模式，具体厂商实现放 L4** | P1 |
| L3-F10 | 风险规则双轨 | 阈值规则（确定性，22 条）+ 语义判断（LLM，可配置开关）；法条依据只能来自受控规则库 | P1 |
| L3-F11 | 规则库版本化 | 风险规则 / 审核标准版本化管理，支持反馈闭环迭代 | P2 |

### 9.2 新增非功能约束

| 项 | 要求 |
|---|---|
| 数据隐私 | **合同原文不发公网模型**；公网模型仅用于通用条款分析或脱敏后调用 |
| 规则受控 | 法条引用只能来自受控规则库，不允许 LLM 自由生成法条依据 |
| 可审计 | 每条风险发现须追溯：条款原文位置 + 规则来源 + 法条依据 |
