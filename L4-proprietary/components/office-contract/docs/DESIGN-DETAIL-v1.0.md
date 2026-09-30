# OFC-001 Office 合同审批模块 DESIGN-DETAIL v1.0

## 1. 数据模型

### 1.1 合同主表 `contracts`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 合同ID，自增 |
| contract_no | VARCHAR(32) UNIQUE | 合同编号，自动生成 `OFC-[YYYYMMDD]-[SEQ]` |
| title | VARCHAR(256) | 合同标题 |
| party_b | VARCHAR(256) | 乙方名称 |
| amount | DECIMAL(18,2) | 合同金额 |
| type | VARCHAR(64) | 合同类型，如 `tech_service`, `sales` |
| effective_date | DATE | 生效日期 |
| expiry_date | DATE | 到期日期 |
| status | VARCHAR(32) | 当前状态，见状态机定义 |
| current_level | INTEGER | 当前审批层级 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |
| signed_at | DATETIME | 签署时间 |
| archived_at | DATETIME | 归档时间 |

### 1.2 审批记录表 `approvals`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 审批记录ID |
| contract_id | INTEGER | 关联合同ID |
| approver | VARCHAR(64) | 审批人姓名 |
| role | VARCHAR(64) | 审批角色 |
| level | INTEGER | 审批层级 |
| action | VARCHAR(16) | 动作：approve/reject |
| comment | TEXT | 审批意见/驳回原因 |
| created_at | DATETIME | 审批时间 |

### 1.3 审计日志表 `audit_logs`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 日志ID |
| contract_id | INTEGER | 关联合同ID |
| operation | VARCHAR(64) | 操作类型 |
| operator | VARCHAR(64) | 操作人 |
| detail | TEXT | 操作详情 JSON |
| created_at | DATETIME | 操作时间 |

## 2. 状态机定义

### 2.1 状态列表

| 状态 | 说明 |
|------|------|
| `draft` | 草稿，可编辑 |
| `review1` | 1级审批中 |
| `review2` | 2级审批中 |
| `review3` | 3级审批中 |
| `approved` | 全部审批通过 |
| `signed` | 已签署 |
| `archived` | 已归档 |

### 2.2 流转规则

| 当前状态 | 操作 | 下一状态 |
|----------|------|----------|
| draft | submit → 自动计算 level | reviewN (N=层级) |
| reviewN | approve → 还有下一级 | reviewN+1 |
| reviewN | approve → 无下一级 | approved |
| * (任一审批中) | reject → | draft |
| approved | sign → | signed |
| signed | archive → | archived |

### 2.3 层级计算规则

根据合同金额自动判定层级：

| 金额范围 | 层级 |
|----------|------|
| < 10万 | 1 |
| 10万 ≤ 金额 < 50万 | 2 |
| 50万 ≤ 金额 < 200万 | 3 |
| ≥ 200万 | 4 |

> 金额阈值可在 `config/settings.py` 中修改。

## 3. 接口契约

### 3.1 ContractService 核心接口

```python
class ContractService:
    # 创建新合同
    def create_contract(self, title: str, party_b: str, amount: Decimal, 
                        type: str, effective_date: date, expiry_date: date) -> Contract: ...
    
    # 获取合同详情
    def get_contract(self, contract_id: int) -> Optional[Contract]: ...
    
    # 列出合同，支持分页和状态筛选
    def list_contracts(self, page: int = 1, page_size: int = 20, 
                      status: Optional[str] = None) -> Tuple[List[Contract], int]: ...
    
    # 提交审批
    def submit_for_review(self, contract_id: int) -> bool: ...
    
    # 审批通过
    def approve(self, contract_id: int, approver: str, role: str, comment: str) -> bool: ...
    
    # 驳回
    def reject(self, contract_id: int, approver: str, role: str, reason: str) -> bool: ...
    
    # 风险扫描
    def risk_scan(self, contract_id: int) -> RiskScanResult: ...
    
    # 生成合同文档
    def generate_document(self, contract_id: int) -> str: ...
    
    # 签署合同
    def sign_contract(self, contract_id: int) -> bool: ...
    
    # 归档合同
    def archive_contract(self, contract_id: int) -> bool: ...
    
    # 获取审批历史
    def get_approval_history(self, contract_id: int) -> List[Approval]: ...
    
    # 获取审计日志
    def get_audit_logs(self, contract_id: int) -> List[AuditLog]: ...
```

### 3.2 CLI 子命令

| 子命令 | 参数 | 说明 |
|--------|------|------|
| `init` | - | 初始化数据库 |
| `create` | --title, --party-b, --amount, --type, --effective-date, --expiry-date | 创建合同 |
| `list` | [--status], [--page], [--page-size] | 列出合同 |
| `show` | --id | 显示合同详情 |
| `submit` | --id | 提交审批 |
| `approve` | --id, --approver, --role, [--comment] | 审批通过 |
| `reject` | --id, --approver, --role, --reason | 驳回 |
| `risk-scan` | --id | 执行风险扫描 |
| `generate` | --id | 生成合同文档 |
| `sign` | --id | 签署合同 |
| `archive` | --id | 归档合同 |
| `history` | --id | 查看审批历史 |
| `audit` | --id | 查看审计日志 |

### 3.3 Web API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/dashboard` | 仪表盘页面 |
| GET | `/contracts` | 合同列表（分页筛选） |
| POST | `/contracts` | 创建合同 |
| GET | `/contracts/{id}` | 获取合同详情 |
| POST | `/contracts/{id}/submit` | 提交审批 |
| POST | `/contracts/{id}/approve` | 审批通过 |
| POST | `/contracts/{id}/reject` | 驳回 |
| POST | `/contracts/{id}/risk-scan` | 风险扫描 |
| POST | `/contracts/{id}/generate` | 生成文档 |
| POST | `/contracts/{id}/sign` | 签署 |
| POST | `/contracts/{id}/archive` | 归档 |
| GET | `/contracts/{id}/history` | 审批历史 |
| GET | `/stats` | 审批统计 |

## 4. 配置项

`config/settings.py` 中可配置：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `PARTY_A_NAME` | 甲方名称 | "梆梆安全" |
| `DB_PATH` | SQLite 数据库路径 | `data/office_contract.db` |
| `OUTPUT_DIR` | 生成文档输出目录 | `outputs/` |
| `APPROVAL_LEVELS` | 审批层级配置 | 金额阈值、角色列表 |
| `TEMPLATE_PATH` | 合同模板路径 | `templates/sales_contract_template.docx` |

## 5. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 合同不存在 | 返回 404 / 错误提示，不崩溃 |
| 状态流转非法（如在 review1 直接归档） | 拒绝操作，返回错误说明当前状态 |
| 参数缺失/格式错误 | 参数校验提前返回错误 |
| 金额为零或负数 | 拒绝创建合同 |
| 数据库读写错误 | 捕获异常，返回错误信息 |

