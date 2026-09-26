# BDMS v2.1 合同管理（Contract Management）详细设计

| 项 | 值 |
|---|---|
| 版本 | v2.1 |
| 层级 | L4 BDMS 模块详细设计 |
| 继承 | L3 `contract-approval` 纯逻辑核心（状态机 + 风险扫描 + 审批分级标准） |
| 状态 | 设计中 |
| 模块编码 | contract_management |
| 对应 L3 域 | Contract Management |
| 横切依赖 | Base Engine / Service / Importer / Exporter 框架，OCR-Digitalization，docx 模板引擎，产品/服务知识库 |

### 1.4 Bangcle 官方合同模板

合同模板是合同生成的核心资产。Bangcle 已有 **11 份官方合同模板**（.doc/.docx 格式），存放在本地：

```
/Users/bangcle/Bangcle Workspace/00. Bangcle Manual/02. Bangcle Template/合同模版/
```

**模板清单**：

| 编号 | 模板文件 | 合同类型 | 用途 |
|---|---|---|---|
| 1 | 软件授权许可使用合同（公有云软件）（2026）.doc | 公有云授权 | SaaS 软件授权 |
| 2 | 软件授权许可使用合同（年授权）（2026）.doc | 年度授权 | 按年订阅的软件许可 |
| 3 | 软件产品销售合同（永久授权）（2026）.doc | 永久授权 | 一次性买断软件 |
| 4 | 产品销售合同（软硬一体）（2026）.doc | 软硬件一体 | 硬件+软件捆绑销售 |
| 5 | 产品及服务销售合同（综合类）（2026）.doc | 综合服务 | 软件+服务的综合合同 |
| 6 | 安全服务销售合同（2026）.doc | 安全服务 | 等保/渗透/运维等服务 |
| 7 | 技术开发合同（2026）.doc | 技术开发 | 定制开发/技术委托 |
| 8 | 变更协议（销售类-合同条款变更）.docx | 条款变更 | 已签署合同的条款修改 |
| 9 | 变更协议（销售类-客户变更）.docx | 客户变更 | 合同主体信息变更 |
| 10 | 补充协议（销售类-补充合同内容）.docx | 补充协议 | 新增/补充合同内容 |

**v2.1 模板策略**：

| 阶段 | 模板处理方式 | 说明 |
|---|---|---|
| Phase 1 | 模板引用 | 数据库记录模板元数据（路径/类型/版本），生成时读取本地文件 |
| Phase 2 | 模板上传 | 支持从本地上传/替换模板文件，无需改代码 |
| Phase 3 | 模板在线编辑 | 支持在线编辑模板字段和条款（可选高级功能） |

### 1.5 产品/服务知识库关联 — 合同标的对比分析

合同签订前需确认合同标的（产品/服务/金额）与 Bangcle 产品/服务知识库一致，避免标的错误导致后续履约风险。

**关联方式**：

```
cr_contract (合同)
    │ 1:N
    ▼
cr_contract_clause (合同条款)
    │ clause_type = "subject" (标的条款)
    │ 提取标的字段：产品/服务/数量/单价/金额
    ▼
kb_item (知识库 — 产品定价参考 pricing_ref)
    │ 自动匹配：按产品类型 + 客户类型
    ▼
→ 对比分析：合同标的 vs 知识库参考 → 差异预警
```

**对比分析能力**：

| 分析项 | 数据来源 | 预警规则 |
|---|---|---|
| 产品匹配度 | 合同标的 vs 知识库产品 Spec | 产品不在知识库中 → 标的风险 |
| 价格合理性 | 合同单价 vs 知识库 pricing_ref | 单价偏离参考价 ±20% → 价格异常预警 |
| SLA 匹配度 | 合同 SLA vs 知识库 service_sla | SLA 低于公司标准 → 履约风险预警 |
| 交付周期 | 合同交付日期 vs 知识库 deploy_manual | 周期短于标准实施周期 → 交付风险预警 |

**实现位置**：`ContractManagementEngine.analyze_subject(kb_items)` 方法，在 `scan_risks()` 中自动调用。

---

---

## 1 模块概述

### 1.1 业务域

合同管理模块覆盖**销售合同全生命周期**：

```
起草 → 风险扫描 → 分级审批 → 签署 → 归档 → 查阅/审计
```

业务目标：
- 把销售合同从"邮件 + 人工签字"搬到线上，全程留痕
- 风险条款自动扫描，降低法务/财务漏判率
- 按金额/类型自动分级审批，避免越权
- 归档后支持审计追踪与版本回溯

### 1.2 L3 域归属

- **主域**：Contract Management（合同管理）
- **继承资产**：L3 `contract-approval` skill — 纯逻辑核心，包括：
  - 合同状态机（draft → approved → signed → archived 及中间审批层级）
  - 风险扫描规则引擎（27 条常见风险条款）
  - 审批分级标准（按金额、客户类型、合同类型）
- **L4 扩展点**：数据库持久化、OCR 导入、docx 生成、审计日志、CLI/API 层

### 1.3 横切关系

| 横切关注点 | 处理方式 |
|---|---|
| 权限 | 基于角色（sales / sales_manager / finance / legal / gm / admin） |
| 审计 | 所有状态变更写入 `cr_audit_log` |
| 加密 | 客户名称、合同金额、签约方身份证号 加密存储 |
| 脱敏 | 列表接口金额脱敏（精确到万），详情按权限完整返回 |
| 通知 | 审批节点变更触发企业微信通知 |
| 幂等 | 合同编号 + 版本号唯一约束 |

---

## 2 技术方案

### 2.1 L3 纯逻辑核心继承方式

采用**组合 + import 调用**模式，而非继承：

```
L3 contract-approval（纯函数 / 无状态）
        ↑ import
L4 ContractManagementEngine（有状态 / 持久化）
```

理由：
- L3 核心是纯逻辑（输入→输出，无副作用），适合函数调用
- L4 层负责 I/O（DB、OCR、文件），与纯逻辑解耦
- 后续 L3 升级时，L4 只需适配输入输出格式

### 2.2 OCR 集成方式

依赖 L2 `ocr-digitalization` skill，通过 **Importer 模式**集成：

```
ContractOCRImporter
  └─ 调用 OCR skill（scan → text + tables + signatures）
       └─ 结构化提取 → ContractDraft DTO
```

支持的输入：
- PDF 扫描件（最常见）
- 图片（jpg/png）
- 已有 docx（直接解析，跳过 OCR）

### 2.3 docx 生成方式

采用 **模板引擎 + 占位符替换**：

- 模板库：`templates/contracts/` 下按合同类型存放 `.docx` 模板
- 引擎：python-docx + Jinja2 风格占位符
- 输出：带水印（草稿/已审批/已签署 三种）
- 版本控制：每次生成写入 `cr_contract_documents` 表

---

## 3 接口契约

### 3.1 ContractManagementEngine

```python
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from datetime import datetime
from enum import Enum


class ContractState(str, Enum):
    DRAFT = "draft"
    REVIEW_1 = "review1"       # 销售经理初审
    REVIEW_2 = "review2"       # 财务审核
    REVIEW_3 = "review3"       # 法务审核
    REVIEW_4 = "review4"       # 总经理审批（大额）
    APPROVED = "approved"
    SIGNED = "signed"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContractManagementEngine(BaseEngine):
    """合同管理引擎：封装 L3 纯逻辑核心 + L4 持久化。"""

    # ---------- 解析与扫描 ----------

    def parse_contract(self, file_path: str, file_type: str = "pdf") -> Dict:
        """
        解析合同文件 → 结构化字段。
        内部调用 ContractOCRImporter（扫描件）或 docx 解析器（电子件）。

        Args:
            file_path: 文件路径
            file_type: pdf / docx / image

        Returns:
            提取的结构化字段（合同编号、甲乙双方、金额、日期、关键条款等）

        Raises:
            OCRParseError: 识别失败
        """
        ...

    def scan_risks(self, contract_content: Dict) -> List[Dict]:
        """
        风险扫描：调用 L3 contract-approval 风险规则引擎。

        Args:
            contract_content: 结构化合同内容（parse_contract 产出或手动填写）

        Returns:
            风险清单：[{rule_id, rule_name, level, description, location, suggestion}]
        """
        ...

    def get_approval_level(self, contract_content: Dict) -> int:
        """
        根据 L3 分级标准计算审批层级。

        规则（简化）：
        - 金额 < 50 万：2 级（销售经理 + 财务）
        - 50 万 ≤ 金额 < 200 万：3 级（+ 法务）
        - 金额 ≥ 200 万：4 级（+ 总经理）
        - 特殊合同类型（框架协议/保密协议）独立规则

        Returns:
            审批层级数（2 / 3 / 4）
        """
        ...

    def validate_state_transition(
        self,
        current_state: ContractState,
        target_state: ContractState,
        role: str,
        contract: Dict = None,
    ) -> Tuple[bool, str]:
        """
        验证状态转换是否合法（委托 L3 状态机）。

        Args:
            current_state: 当前状态
            target_state: 目标状态
            role: 操作者角色
            contract: 合同上下文（用于判断审批层级）

        Returns:
            (是否合法, 原因说明)
        """
        ...
```

### 3.2 ContractManagementService

```python
class ContractManagementService(BaseService):
    """合同管理服务层：事务编排 + 权限校验 + 审计。"""

    # ---------- 合同生命周期 ----------

    def create_contract(
        self,
        title: str,
        contract_type: str,
        party_a: str,
        party_b: str,
        amount: Decimal,
        content: Dict = None,
        project_id: str = None,
        created_by: str = None,
    ) -> str:
        """
        创建合同草稿。

        Returns:
            contract_id
        """
        ...

    def submit_approval(self, contract_id: str, operator: str) -> None:
        """
        提交审批：draft → review1。
        自动计算审批层级，触发首节点通知。
        """
        ...

    def approve(
        self,
        contract_id: str,
        operator: str,
        role: str,
        comment: str = "",
    ) -> None:
        """
        审批通过。根据当前节点推进到下一审批节点，或直达 approved。
        """
        ...

    def reject(
        self,
        contract_id: str,
        operator: str,
        role: str,
        reason: str,
    ) -> None:
        """
        审批驳回 → draft。
        """
        ...

    def scan_risks(self, contract_id: str) -> List[Dict]:
        """对指定合同执行风险扫描，结果写入 cr_risk_scan_results。"""
        ...

    def generate_docx(self, contract_id: str, template_id: str = None) -> str:
        """生成合同 docx 文件，返回文件路径。"""
        ...

    def sign(
        self,
        contract_id: str,
        signatory_a: str,
        signatory_b: str,
        sign_date: datetime,
        signed_file_path: str = None,
    ) -> None:
        """
        标记合同已签署：approved → signed。
        支持上传签署后的扫描件。
        """
        ...

    def archive(self, contract_id: str, archive_location: str = None) -> None:
        """
        归档：signed → archived。
        归档后不可修改，只能查阅。
        """
        ...

    # ---------- 查询 ----------

    def list_contracts(
        self,
        state: ContractState = None,
        contract_type: str = None,
        party_keyword: str = None,
        amount_min: Decimal = None,
        amount_max: Decimal = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        """
        合同列表查询。
        注意：列表中金额字段按角色脱敏。
        """
        ...

    def get_contract(self, contract_id: str, viewer_role: str = None) -> Dict:
        """
        获取合同详情 + 当前审批节点 + 风险扫描结果。
        根据 viewer_role 决定是否返回完整金额。
        """
        ...

    def audit_log(self, contract_id: str) -> List[Dict]:
        """审计追踪：返回合同全生命周期操作日志。"""
        ...
```

### 3.3 ContractOCRImporter

```python
class ContractOCRImporter(BaseImporter):
    """
    合同 OCR 导入器。
    输入：扫描件 PDF / 图片
    输出：结构化合同字段 + 原始文本 + 表格数据
    """

    def import_from_file(self, file_path: str, **kwargs) -> Dict:
        """
        实现 BaseImporter.import_from_file。

        流程：
        1. 调用 ocr-digitalization skill 执行 OCR
        2. 从识别结果中提取结构化字段（正则 + 规则匹配）
        3. 提取表格（金额明细、付款计划等）
        4. 检测签名/印章位置
        5. 返回 ContractDraft DTO
        """
        ...

    def extract_fields(self, ocr_result: Dict) -> Dict:
        """从 OCR 原始结果中提取合同关键字段。"""
        ...

    def detect_signatures(self, ocr_result: Dict) -> List[Dict]:
        """检测签名和印章位置及有效性。"""
        ...
```

### 3.4 ContractExporter

```python
class ContractExporter(BaseExporter):
    """
    合同导出器。
    输出格式：Excel / PDF / CSV
    """

    def export_contract_overview(self, filters: Dict = None) -> bytes:
        """导出合同概览（列表 + 汇总统计）。"""
        ...

    def export_risk_details(self, contract_id: str) -> bytes:
        """导出单份合同的风险明细报告。"""
        ...

    def export_approval_log(self, contract_id: str) -> bytes:
        """导出审批日志。"""
        ...

    def export_audit_trail(self, contract_id: str) -> bytes:
        """导出审计追踪（全生命周期操作记录）。"""
        ...
```

---

## 4 数据模型

引用《BDMS v2.1 数据模型详细设计》§6，共 6 张 `cr_` 表。

### 4.1 表清单

| 表名 | 中文名 | 说明 |
|---|---|---|
| `cr_contracts` | 合同主表 | 合同基本信息 |
| `cr_contract_documents` | 合同文件表 | 各版本文件（草稿/已审批/已签署） |
| `cr_approval_nodes` | 审批节点表 | 审批流程节点实例 |
| `cr_risk_scan_results` | 风险扫描结果表 | 每次扫描的风险清单 |
| `cr_audit_log` | 审计日志表 | 全生命周期操作记录 |
| `cr_templates` | 合同模板表 | docx 模板管理 |

### 4.2 加密字段

| 表 | 字段 | 加密方式 | 说明 |
|---|---|---|---|
| `cr_contracts` | `party_a_name` | AES-256 | 甲方名称 |
| `cr_contracts` | `party_b_name` | AES-256 | 乙方名称 |
| `cr_contracts` | `amount` | AES-256 + 单独密钥 | 合同金额（核心敏感数据） |
| `cr_contracts` | `signatory_id_no` | AES-256 | 签约方身份证号（如有） |
| `cr_contracts` | `bank_account` | AES-256 | 银行账户信息 |
| `cr_contract_documents` | `file_content_hash` | SHA-256 | 文件内容哈希（校验用，非加密） |

### 4.3 脱敏规则

| 场景 | 字段 | 脱敏规则 |
|---|---|---|
| 列表接口（非授权角色） | `party_a_name`, `party_b_name` | 首尾各保留 1 字，中间用 `*` |
| 列表接口（非财务角色） | `amount` | 精确到"万元"，如 `约 125 万` |
| 列表接口 | `signatory_id_no` | 前 6 后 4，中间 `*` |
| 导出（非管理员） | `bank_account` | 前 4 后 4，中间 `*` |
| 详情接口（有权限） | 全部 | 完整返回，记录审计日志 |

---

## 5 审批状态机

### 5.1 状态转换矩阵

| 当前状态 | 操作 | 目标状态 | 执行角色 | 条件 |
|---|---|---|---|---|
| `draft` | submit_approval | `review1` | sales / sales_manager | 必填字段完整 |
| `draft` | edit | `draft` | 创建者 / sales_manager | 草稿可自由编辑 |
| `review1` | approve | `review2`（如需）或 `approved` | sales_manager | 第 1 级审批通过 |
| `review1` | reject | `draft` | sales_manager | 驳回修改 |
| `review2` | approve | `review3`（如需）或 `approved` | finance | 第 2 级审批通过 |
| `review2` | reject | `draft` | finance | 驳回修改 |
| `review3` | approve | `review4`（如需）或 `approved` | legal | 第 3 级审批通过 |
| `review3` | reject | `draft` | legal | 驳回修改 |
| `review4` | approve | `approved` | gm | 第 4 级审批通过 |
| `review4` | reject | `draft` | gm | 驳回修改 |
| `approved` | sign | `signed` | sales + 外部签署 | 双方签署完成 |
| `approved` | void | `archived` | legal / gm | 审批后未签署作废 |
| `signed` | archive | `archived` | admin | 执行完成或主动归档 |
| `archived` | (无) | (终态) | - | 归档后不可修改 |
| `rejected` | resubmit | `review1` | 创建者 | 修改后重新提交 |

### 5.2 审批层级与状态映射

| 合同类型 | 审批层级 | 经过的 review 状态 |
|---|---|---|
| 普通销售合同 < 50 万 | Level 2 | draft → review1 → review2 → approved |
| 50 万 ≤ 销售合同 < 200 万 | Level 3 | draft → review1 → review2 → review3 → approved |
| 销售合同 ≥ 200 万 | Level 4 | draft → review1 → review2 → review3 → review4 → approved |
| 框架协议 / 年度合同 | Level 4 | 强制 4 级审批 |
| 保密协议 (NDA) | Level 2 | draft → review1 → review3 → approved（跳财务） |

> 注意：具体分级规则以 L3 `contract-approval` skill 中的标准为准，L4 不硬编码业务规则。

---

## 6 核心数据流

### 6.1 合同创建 → 审批 → 签署 完整流程

```python
# 伪代码：完整流程
def contract_full_lifecycle():
    # 1. 销售创建合同草稿
    contract_id = contract_service.create_contract(
        title="XX 项目服务合同",
        contract_type="service",
        party_a="梆梆安全",
        party_b="客户公司",
        amount=Decimal("850000"),
        content={...},
        created_by="zhangsan",
    )

    # 2. 上传合同文件 → OCR 解析 → 自动填充字段
    ocr_result = ocr_importer.import_from_file("/path/to/scan.pdf")
    contract_service.update_fields(contract_id, ocr_result["fields"])

    # 3. 风险扫描
    risks = contract_service.scan_risks(contract_id)
    if any(r["level"] in ("high", "critical") for r in risks):
        # 高风险：提示销售修改，或标记后进入审批
        flag_high_risk(contract_id)

    # 4. 生成正式 docx
    docx_path = contract_service.generate_docx(contract_id)

    # 5. 提交审批
    contract_service.submit_approval(contract_id, operator="zhangsan")
    # 自动计算审批层级 = 3 级（85 万 → review1/2/3）
    # 触发 review1 节点通知

    # 6. 销售经理审批通过 → review2
    contract_service.approve(contract_id, operator="lisi", role="sales_manager")
    # 触发 review2 节点通知

    # 7. 财务审批通过 → review3
    contract_service.approve(contract_id, operator="wangwu", role="finance")
    # 触发 review3 节点通知

    # 8. 法务审批通过 → approved
    contract_service.approve(contract_id, operator="zhaoliu", role="legal")

    # 9. 双方签署
    contract_service.sign(
        contract_id,
        signatory_a="Qi SX",
        signatory_b="Customer CEO",
        sign_date=datetime.now(),
        signed_file_path="/path/to/signed.pdf",
    )

    # 10. 归档（通常在项目结项后触发）
    contract_service.archive(contract_id, archive_location="/archive/2026/...")
```

---

## 7 CLI 命令设计

```bash
# 合同管理模块命令
bdms contract <subcommand> [options]

# 合同创建与编辑
bdms contract create --title "..." --type service --amount 850000 --party-a "..." --party-b "..."
bdms contract update <contract_id> --field value...
bdms contract delete <contract_id>          # 仅草稿状态可删

# 审批流程
bdms contract submit <contract_id>          # 提交审批
bdms contract approve <contract_id> --role sales_manager --comment "同意"
bdms contract reject <contract_id> --role finance --reason "金额与预算不符"

# 风险扫描
bdms contract scan-risks <contract_id>
bdms contract scan-risks --all-draft        # 批量扫描所有草稿

# 文件与生成
bdms contract import <file_path> [--ocr]    # 导入合同文件（可选 OCR）
bdms contract generate-docx <contract_id> [--template standard_service]
bdms contract upload-signed <contract_id> <signed_file>

# 签署与归档
bdms contract sign <contract_id> --signatory-a "..." --signatory-b "..." --date "2026-09-19"
bdms contract archive <contract_id> [--location "..."]

# 查询
bdms contract list [--state draft] [--type service] [--keyword "..."] [--page 1]
bdms contract show <contract_id>
bdms contract audit-log <contract_id>
bdms contract risks <contract_id>

# 导出
bdms contract export overview [--filters ...] --format xlsx
bdms contract export risks <contract_id> --format pdf
bdms contract export audit <contract_id> --format csv
```

---

## 8 实现路径

### 第 1 步：核心引擎 + 数据模型（0.5 天）

- [ ] 创建 `contract_management/` 模块目录
- [ ] 定义 6 张 `cr_` 表的 SQLAlchemy 模型（含加密/脱敏字段）
- [ ] 实现 `ContractManagementEngine`（调用 L3 contract-approval）
- [ ] 单元测试：状态机转换 + 风险扫描 + 分级标准

### 第 2 步：服务层 + OCR/文档集成（0.5 天）

- [ ] 实现 `ContractManagementService`（11 个核心方法）
- [ ] 实现 `ContractOCRImporter`（对接 ocr-digitalization skill）
- [ ] 实现 `ContractExporter`（4 种导出）
- [ ] 实现 docx 生成（模板引擎 + 占位符替换）
- [ ] 集成测试：创建 → 审批 → 签署 全流程

### 第 3 步：CLI + 审计 + 收尾（1 天）

- [ ] 实现 `bdms contract` CLI 命令（约 20 个子命令）
- [ ] 完善审计日志（所有写操作留痕）
- [ ] 加密/脱敏字段验证
- [ ] 编写模块 README
- [ ] 端到端测试 + 幂等验证

---

## 9 预期效果 + 验收标准

### 9.1 预期效果

- 销售合同从起草到归档**全程线上化**，平均审批周期从 7 天缩短到 2 天
- 风险扫描覆盖率 ≥ 90%（人工补漏剩余 10%）
- 审计追踪完整率 100%
- 支持每年 500+ 份合同的管理规模

### 9.2 验收标准（验收 7 步法映射）

| 步骤 | 验收项 | 通过标准 |
|---|---|---|
| ① 功能正确性 | 合同 CRUD | 创建/查询/更新/删除 全部通过 |
| ② 状态机验证 | 12 种合法转换 + N 种非法转换 | 合法转换全部通过；非法转换全部被拒绝并给出原因 |
| ③ 风险扫描 | 27 条规则覆盖测试 | 每条规则至少 1 个命中用例 + 1 个未命中用例 |
| ④ 分级审批 | 4 个金额档位 + 特殊合同类型 | 每档对应正确的审批节点数 |
| ⑤ 安全合规 | 加密 + 脱敏 + 审计 | 加密字段数据库中不可读；脱敏列表不泄露完整信息；每次写操作有审计记录 |
| ⑥ 性能 | 列表查询 + 风险扫描 | 列表查询 < 500ms（万级数据）；单份合同风险扫描 < 2s |
| ⑦ 幂等验证 | 重复提交审批 / 重复签署 / 重复归档 | 重复操作不产生副作用，返回幂等成功 |

### 9.3 幂等验收矩阵

| 操作 | 幂等键 | 重复调用结果 |
|---|---|---|
| create_contract | contract_no（合同编号） | 第二次返回已存在的 contract_id |
| submit_approval | contract_id + 当前状态 | 已在审批中则返回"审批已提交" |
| approve | contract_id + role + operator | 同一节点重复审批返回"已审批" |
| sign | contract_id | 重复签署返回"已签署" |
| archive | contract_id | 重复归档返回"已归档" |

---

## 10 复用资产映射

| 资产 | 来源 | 复用方式 |
|---|---|---|
| 合同状态机 | L3 `contract-approval` skill | import 调用，L3 纯逻辑核心 |
| 风险扫描规则引擎 | L3 `contract-approval` skill | 27 条规则直接复用 |
| 审批分级标准 | L3 `contract-approval` skill | 分级逻辑直接复用 |
| OCR 能力 | L2 `ocr-digitalization` skill | 通过 ContractOCRImporter 封装调用 |
| BaseEngine / BaseService | BDMS Base 模块 | 继承基类 |
| BaseImporter / BaseExporter | BDMS Base 模块 | 继承基类 |
| 审计日志框架 | BDMS Base 模块 | 复用通用审计机制 |
| 加密/脱敏组件 | BDMS Base 模块 | 复用字段级加密工具 |
| 企业微信通知 | 全局 WeCom 集成 | 审批节点变更通知 |
| docx 模板引擎 | python-docx + Jinja2 | 合同文档生成 |

---

## 11 非功能设计

### 11.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| 合同列表查询（万级） | < 500ms | 分页 + 索引 + 状态缓存 |
| 风险扫描（单份合同） | < 2s | 纯 Python 正则匹配 + 规则引擎 |
| OCR 解析（单页） | < 5s | RapidOCR 并行 + 版面分析 |
| docx 生成 | < 3s | 模板预编译 + 批量写入 |
| 并发合同处理 | 100+ 并行审批 | SQLite WAL + 连接池 |

### 11.2 可靠性

- **L3 纯逻辑核心隔离**：L3 contract-approval 无状态，L4 调用失败可重试
- **OCR 失败兜底**：解析失败时转为手动录入模式，不阻塞审批流程
- **状态转换原子性**：状态变更 + 审计日志同事务
- **幂等保障**：合同编号 + 版本号唯一约束

### 11.3 安全

- **字段级加密**：客户名称/金额/身份证号 AES-256 加密存储
- **分级脱敏**：非授权角色看到脱敏金额和名称
- **审计追踪**：所有状态变更 + 文件操作留痕（who/when/what）
- **权限控制**：基于角色的访问控制（sales/finance/legal/gm/admin）
- **文件安全**：上传文件类型白名单 + 病毒扫描（预留）

### 11.4 可用性

- **降级策略**：OCR 服务不可用时，提示用户手动录入字段
- **模板热更新**：docx 模板文件可在线替换，无需重启服务
- **密钥轮换**：支持双密钥过渡期，不影响已加密数据

---

## 12 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| L3 contract-approval 接口变更 | L4 适配成本 | 语义化版本 + 适配层 + 契约测试 |
| OCR 识别率不足 | 字段提取不全 | 置信度阈值 + 人工审核标记 + 模型迭代 |
| 审批规则复杂化 | 状态机难以维护 | 状态机可视化文档 + 全量单元测试覆盖 |
| 加密密钥泄露 | 客户信息泄露 | HSM/KMS 管理 + 定期轮换 + 最小权限 |
| docx 模板版本混乱 | 生成文件格式不一致 | 模板版本化 + 模板校验脚本 + 预览机制 |
| 合同编号冲突 | 数据覆盖 | UUID 主键 + 业务编号唯一约束 + 冲突检测 |

---

## 12.5 业界最佳实践对比

### 对标标准

| 业界实践 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **CLM（合同生命周期管理）** | 合同从起草到归档全流程线上化 | 有基础流程，缺电子签名和版本控制 | 缺电子签名集成 | 集成 e签宝/法大大/腾讯电子签等第三方电子签名 |
| **条款库（Clause Library）** | 条款独立存储、可复用、可组合 | 条款混在模板中，修改需改所有模板 | 条款未解耦 | 条款独立表（cr_clause_library），模板引用条款 ID |
| **合同 AI 辅助** | LLM 辅助起草/审查/比对 | 仅 OCR 提取，缺智能审查 | 缺 AI 辅助 | 增加基于 LLM 的条款审查和起草建议（OPTIONAL_TOKEN） |
| **审批工作流引擎** | 可视化审批流程配置，低代码修改 | 状态机硬编码审批流 | 流程不可配置 | 审批流程可配置（节点/角色/条件），未来支持低代码修改 |
| **合同分析仪表盘** | 签约趋势/金额分布/履约风险可视化 | 仅风险扫描，缺全局分析 | 缺全景视图 | 增加签约趋势、金额分布、履约风险等可视化分析 |
| **电子签名 + 存证** | 在线签署 + 司法存证 | 线下手工签署 + 扫描归档 | 缺在线签署 | 集成第三方电子签名 + 区块链存证（增强司法效力） |
| **数据驻留** | 敏感数据分级存储 | 全量本地存储 | 缺分级策略 | 敏感数据（金额/身份证）单独加密存储 |

### 建议的优化项

**P0（v2.1 必须做）**：

1. **条款库解耦**
   - 问题：条款混在模板中，修改条款需改所有模板
   - 方案：条款独立存储（`cr_clause_library`），模板引用条款 ID
   - 成本：低（+1 表 + 适配模板引擎）
   - 收益：高（条款复用 + 维护成本低）

2. **合同标的对比分析**
   - 问题：合同标的与产品知识库脱节，容易出错
   - 方案：新增 `analyze_subject()` 方法，自动对比知识库 pricing_ref/service_sla/deploy_manual
   - 成本：低（复用已有知识库）
   - 收益：高（减少标的风险和履约纠纷）

**P1（v2.2 可做）**：

3. **电子签名集成**
   - 问题：签署靠线下手工，周期长（7 天→目标 1 天）
   - 方案：集成 e签宝/法大大/腾讯电子签 API
   - 成本：中（第三方服务费用 + 集成开发 2-3 天）
   - 收益：高（签署周期从 7 天→1 天，体验质变）

4. **合同分析仪表盘**
   - 问题：缺管理层决策支持视图
   - 方案：签约趋势/金额分布/履约风险/审批效率可视化
   - 成本：中（+ Dashboard 集成）
   - 收益：中（管理层实时掌握合同全貌）

**P2（远期）**：

5. **合同 AI 辅助起草/审查**
   - 问题：起草靠人工+模板，缺智能辅助
   - 方案：LLM 辅助条款审查 + 合同起草建议
   - 成本：高 | 收益：中（OPTIONAL_TOKEN）

6. **审批工作流可配置化**
   - 问题：审批规则硬编码，修改需改代码
   - 方案：审批流程配置表 + 可视化配置界面
   - 成本高 | 收益：低（当前 4 档够用，配置需求不迫切）

---

---

## 13 变更历史

| 版本 | 日期 | 作者 | 变更内容 |
|---|---|---|---|
| v2.1 | 2026-09-19 | BDMS Architecture | 初始版本：合同管理模块详细设计 |
