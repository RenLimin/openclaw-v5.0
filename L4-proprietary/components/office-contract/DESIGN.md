# office-contract

## 设计目标

为面向企业 Office 场景的销售合同审批提供全流程管理能力，覆盖从合同起草到归档的完整生命周期。基于 SCA-001（contract-approval skill）通用合同审批能力构建，增加持久化、状态机、分级审批等企业级能力。

## 架构决策

- **L4 编排 L3**：L4 负责持久化 + 状态机 + 业务编排，L3 负责纯逻辑（风险扫描/条款解析）
- **分级审批**：按金额自动判定审批层级（1~4级），每级对应不同角色和 SLA
- **状态机驱动**：`draft → review1 → review2 → review3 → approved → signed → archived`，任一环节驳回回退 draft
- **审计日志**：所有操作留痕，不可篡改
- **CLI 入口**：`contractctl` 提供完整命令行操作
- **风险扫描复用**：调用 L3 contract-approval 的风险扫描规则和审核标准库

## 模块划分

```
office-contract/
├── cli/
│   ├── __init__.py
│   └── contractctl.py          # CLI 入口（init/create/submit/risk-scan/approve/generate/sign/archive）
├── services/
│   ├── __init__.py
│   └── contract_service.py     # 业务服务层（审批流转/状态机/文档生成）
├── config/
│   ├── __init__.py
│   └── settings.py             # Office 场景配置（甲方/角色/SLA）
├── tests/
│   ├── test_doc_gen.py         # 文档生成测试
│   ├── test_web_api.py         # Web API 测试
│   ├── test_e2e.py             # 端到端集成测试（25 用例）
│   └── test_cli.py
└── outputs/                    # 生成的合同文档
```

## 关键接口/数据结构

- `contract_service.ContractService`：核心业务服务
  - `create_contract(title, party_b, amount, type, ...)`：创建合同
  - `submit_for_review(contract_id)`：提交审批
  - `approve(contract_id, approver, role, comment)`：审批通过
  - `reject(contract_id, approver, role, reason)`：驳回
  - `risk_scan(contract_id)`：调用 L3 风险扫描
  - `generate_document(contract_id)`：生成 docx 合同
- `contractctl`：CLI 入口，8 个子命令
- `settings.OfficeConfig`：Office 场景配置（甲方信息、审批角色、SLA 规则）
- 状态机：`draft → review1 → review2 → review3 → approved → signed → archived`
- 审批层级：
  - 1 级（<10 万）：销售经理
  - 2 级（10-50 万）：销售经理 → 法务审查员
  - 3 级（50-200 万）：销售总监 → 法务审查员 → 财务经理
  - 4 级（>200 万）：VP/CEO → 法务总监 → 财务总监

## 依赖关系

- **依赖**：L3 contract-approval（风险扫描规则、审核标准库）、python-docx、SQLite
- **被依赖**：无（顶层应用组件）

## 演进方向

1. **Web UI**：从 CLI 扩展到 Web 界面，支持在线审批
2. **电子签名**：集成电子签章能力
3. **合同模板**：对接 office-business 的合同模板库
4. **批量审批**：支持多合同并行审批
5. **审批统计**：审批时效分析、驳回率统计
6. **多租户**：支持多公司/多部门独立管理
