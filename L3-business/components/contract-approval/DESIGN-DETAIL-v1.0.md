# 销售合同审批模块 — 详细设计

> 组件：contract-approval (L3)
> 版本：v1.0
> 日期：2026-09-02

## 1. 概述

销售合同审批模块的详细设计，包含分级审批流程、风险扫描规则、合同生成逻辑和审计追踪机制。

## 2. 接口契约

### 2.1 审批流程接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| submit_contract | POST | contract_data | approval_id |
| approve | POST | approval_id, level | status |
| reject | POST | approval_id, reason | status |
| get_status | GET | approval_id | status_detail |

### 2.2 风险扫描接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| scan_risk | POST | contract_text | risk_report |
| validate_compliance | POST | contract_data | compliance_result |

## 3. 数据模型

### 3.1 合同数据模型

```python
@dataclass
class Contract:
    id: str
    title: str
    amount: float
    parties: List[Dict[str, str]]
    terms: List[str]
    status: ContractStatus
    created_at: datetime
    updated_at: datetime
```

### 3.2 审批记录模型

```python
@dataclass
class ApprovalRecord:
    id: str
    contract_id: str
    level: int
    approver: str
    decision: ApprovalDecision
    comment: str
    timestamp: datetime
```

## 4. 技术方案

### 4.1 分级审批流程

```
金额 < 1万 → 直属经理审批
1万 ≤ 金额 < 10万 → 部门总监审批
10万 ≤ 金额 < 50万 → VP审批
金额 ≥ 50万 → CEO审批
```

### 4.2 风险扫描规则

基于民法典13项核心条款的风险扫描：
1. 合同主体资格检查
2. 标的物合法性检查
3. 价格条款合理性检查
4. 履行期限合法性检查
5. 违约责任对等性检查
6. 争议解决条款检查
7. 知识产权条款检查
8. 保密条款检查
9. 不可抗力条款检查
10. 合同解除条款检查
11. 通知送达条款检查
12. 法律适用条款检查
13. 合同完整性检查

### 4.3 合同生成

使用 python-docx 生成标准合同文档，支持模板渲染和动态字段填充。

### 4.4 审计追踪

所有审批操作记录到审计日志，包含操作人、时间、决策和备注。

## 5. 依赖关系

- L2 Office 文档生成 (python-docx)
- L2 凭据管理 (审批人凭据)
- L2 知识库 (合同模板存储)

## 6. 测试方案

- 单元测试：审批流程状态机
- 集成测试：风险扫描 + 合同生成
- E2E 测试：完整审批流程
