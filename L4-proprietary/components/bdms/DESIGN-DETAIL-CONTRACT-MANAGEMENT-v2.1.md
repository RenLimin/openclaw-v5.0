# BDMS v2.1 详细设计 — 合同审核管理（Contract Management）

| 项 | 值 |
|---|---|
| 文档编号 | DESIGN-DETAIL-CONTRACT-MANAGEMENT-v2.1 |
| 版本 | v2.1 r2（2026-09-22） |
| 层级 | L4 专有业务层（BDMS）模块详细设计 |
| 模块编码 | `contract_management` |
| 对应 L3 域 | Contract Management（`L3-business/skills/contract-approval`） |
| 上游文档 | PRD-v2.1.md（F-CM-01~07）、DESIGN-OUTLINE-v2.1.md §3.1 |
| 下游文档 | IMPLEMENTATION-PLAN（Phase 拆分）、VERIFICATION（验收报告） |
| 状态 | 待 Rex 审核（通过后方可进入开发/继续开发） |
| 编制日期 | 2026-09-22 |
| Token 策略 | 🔒 NO_TOKEN — 纯代码，零 AI 依赖（LLM 辅助为 P2 可选项，OPTIONAL_TOKEN） |

---

## 目录

0. [版本记录](#0-版本记录)
1. [模块概述](#1-模块概述)
2. [与其他模块交互 — 三大工作场景](#2-与其他模块交互--三大工作场景)
3. [OS 依赖与限制](#3-os-依赖与限制)
4. [技术方案](#4-技术方案)
5. [接口设计](#5-接口设计)
6. [数据模型](#6-数据模型)
7. [合同关联关系](#7-合同关联关系)
8. [核心流程 — 合同状态机](#8-核心流程--合同状态机)
9. [风险扫描规则 — 民法典 13 项 49 条](#9-风险扫描规则--民法典-13-项-49-条)
10. [审批分级逻辑](#10-审批分级逻辑)
11. [OA 自动获取（浏览器自动化）](#11-oa-自动获取浏览器自动化)
12. [OCR 集成方案](#12-ocr-集成方案)
13. [知识库集成](#13-知识库集成)
14. [角色与权限](#14-角色与权限)
15. [错误处理](#15-错误处理)
16. [CLI 命令](#16-cli-命令)
17. [测试策略](#17-测试策略)
附录 B：[复用资产清单与使用方式](#附录-b复用资产清单与使用方式)
审核记录与变更历史


---

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版：对齐实际代码 + L3 22 条规则 + 8 表 DDL |
| v2.1 Detail r2 | 2026-09-22 | Rex 审核反馈 8 条：OA 三大场景 + F-CM-07 明确 + 13类49项 + 合同关联关系 + PMO 角色 + 超级管理员 + 业界最佳实践 |

## 1 模块概述

### 1.1 业务域

合同审核管理模块覆盖**销售合同全生命周期**：

```
起草（模板/OCR 导入/OA 自动获取）→ 风险扫描 → 分级审批（1~4 级）→ 签署（电子+纸质）→ 归档（对接 OA）→ 查询/审计
```

业务目标（对齐 PRD F-CM-01~07）：

| 功能编号 | 能力 | 业务目标 |
|---|---|---|
| F-CM-01 | 合同起草 | 基于 Bangcle 官方模板（11 份）选择模板 → 变量填充 → 生成 docx（带水印） |
| F-CM-02 | 风险扫描 | 基于民法典 13 大类 49 项审查清单自动扫描（22 条自动 + 27 项人工），高风险标红 + 整改建议 |
| F-CM-03 | 分级审批 | 按金额/风险分级：部门经理 → 法务 → 高管，1~4 级自动路由 |
| F-CM-04 | 合同签署 | 电子签章 + 纸质签署记录（扫描件版本化管理 + SHA-256 校验） |
| F-CM-05 | 合同归档 | 对接 OA 归档流程，归档后只读 |
| F-CM-06 | OCR 导入 | 扫描件/图片 → 结构化数据（复用 L2 OCR-001） |
| F-CM-07 | 合同查询 | 查询 BDMS 系统中已完成解析并完成结构化的合同信息（cr_contracts + cr_contract_clauses），按编号/客户/时间/状态/关键词检索 |

> **F-CM-07 说明**：合同查询指查询 **BDMS 系统内部**已完成解析+结构化的合同数据（cr_contracts 宽表 + cr_contract_clauses 条款），非 OA 系统查询。查询支持解密查看原始字段。

### 1.2 L3 域归属

- **主域**：Contract Management（合同管理）
- **继承资产**：L3 `contract-approval` skill 纯逻辑核心（零副作用、零 I/O）：

| L3 资产 | 位置 | 内容 | L4 使用方式 |
|---|---|---|---|
| 状态机 | `core/state_machine.py` | `VALID_TRANSITIONS`、`get_approval_config()`、`next_approval_status()` | `sys.path` 注入 + import |
| 风险引擎 | `core/risk_engine.py` | 22 条自动检查规则（`CHECK_RULES`）、`scan_text()` | import，L4 包装持久化 |
| 条款解析 | `scripts/contract_parser.py` | `parse_contract(text)`，28 类条款逐条提取 | import 委托 |
| 审核标准 | `checklists/sales-contract.md` | **13 大类 49 项**人工审查清单（从民法典抽象并验证） | 知识库落盘（kb_item） |
| 数据模型 | `core/models.py` | `Contract`、`ApprovalConfig`、`RiskFinding`、`RiskReport` | DTO 字段映射参考 |

> **审核标准说明**：13 大类 49 项审查清单是从《民法典》合同编抽象并验证后的逐项审查规则，其中 22 项已转化为自动扫描规则（L3 risk_engine），剩余 27 项为人工审查项（落知识库 kb_item 供法务参考）。

- **L4 扩展点**（L3 不做、本模块负责）：SQLite 持久化、OCR 导入、docx 生成、Excel 导出、加密/脱敏、审计追踪、CLI/Web API、OA 自动获取、WeCom 交互、通知集成。

#### 1.2.1 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **IACCM/WorldCC** | 合同生命周期管理标准 | 合同全流程标准化（起草→审批→签署→归档） | 状态机 draft→review1-4→approved→signed→archived |
| **SAP CLM / Ariba** | 企业合同管理 | 分级审批 + 风险条款库 + 模板管理 | 金额分级（1-4级）+ 民法典13类49项 + 11份模板 |
| **DocuSign CLM** | 电子合同平台 | AI 条款解析 + 自动风险提示 | parse_contract + scan_risks（22条自动规则） |
| **Ironclad** | 合同工作流 | 可配置审批流 + 里程碑提醒 | VALID_TRANSITIONS + 审批 SLA |
| **法大大/上上签** | 电子签章 | 电子签 + 存证 | sign() + SHA-256 版本化 |
| **企业会计准则14号 / ASC 606** | 收入确认 | 合同履约义务识别（五步法） | 履约义务拆分 → revenue 模块（见 REVENUE §1.7） |

---

## 2 与其他模块交互 — 三大工作场景

### 2.1 工作场景总览

本模块与外部系统（OA、WeCom）和 BDMS 内部模块形成三大工作场景：

| 场景 | 名称 | 触发方 | 核心流程 |
|---|---|---|---|
| A | OA 系统合同审批 | OA / WeCom 指令 | 获取待审批流程 → 提取合同文本 → 审核 → 生成建议 → 人工确认 → 返回 OA |
| B | OA 系统合同解析 | OA / WeCom 指令 | 获取合同台账 → 按编号提取文本 → 解析 → 落盘条款+风险 |
| C | WeCom 交互 | WeCom 消息 | 接收指令 → 执行审批/解析/查询 → 返回反馈 |

### 2.2 场景 A：OA 系统合同审批

```
OA 系统 ──(浏览器自动化)──▶ BDMS contract_management ──(WeCom)──▶ 人工审核

详细步骤：
1. integration 连接器（I-02 OA）通过浏览器自动化获取 OA 待审批合同流程列表
2. 按合同编号提取合同文本（docx/pdf/扫描件）
3. contract_management 执行：
   a. parse_contract(text) → 结构化字段 + 条款
   b. scan_risks(text) → 22 条自动规则扫描 + 风险评级
   c. generate_review_suggestions() → 生成可编辑的审核建议（结构化 JSON）
4. 审核建议推送至 WeCom / Web UI
5. 人工审核/调整后，通过浏览器自动化返回 OA 完成审批操作

数据流：
  OA 流程列表 → int_staging_oa → cr_contracts + cr_contract_clauses + cr_risk_scan_results
  审核建议 → WeCom/Web UI → 人工确认 → OA 审批操作（浏览器自动化写回）
```

**generate_review_suggestions 输出格式**：
```json
{
  "contract_no": "CR-20260922-0001",
  "overall_risk": "medium",
  "suggestions": [
    {
      "clause_type": "payment",
      "current_text": "...",
      "suggested_text": "...",
      "risk_level": "medium",
      "law_ref": "§510",
      "reason": "支付方式约定不明确，建议增加转账账户信息"
    }
  ],
  "auto_fill_fields": {
    "party_a": "北京梆梆安全科技有限公司",
    "amount": 850000,
    "effective_date": "2026-10-01"
  }
}
```

### 2.3 场景 B：OA 系统合同解析

```
OA 系统 ──(浏览器自动化)──▶ BDMS contract_management

详细步骤：
1. integration 连接器（I-02 OA）通过浏览器自动化获取 OA 合同台账信息
2. 按具体合同编号定位合同文档
3. 提取合同文本（支持 docx/pdf/扫描件）
4. contract_management 执行：
   a. parse_contract(text) → 结构化字段 + 条款明细
   b. scan_risks(text) → 风险扫描
   c. 落盘至 cr_contracts + cr_contract_clauses + cr_risk_scan_results

数据流：
  OA 合同台账 → int_staging_oa → cr_contracts + cr_contract_clauses + cr_risk_scan_results
  解析结果 → WeCom/Web UI 反馈
```

### 2.4 场景 C：WeCom 交互

```
WeCom ◀──双向──▶ BDMS contract_management

WeCom → BDMS（指令）：
- "审批 [合同编号]" → 获取待审批信息 → 执行审核 → 返回审核建议
- "解析 [合同编号]" → 按编号解析合同 → 返回结构化结果
- "查询 [关键词]" → 查询 BDMS 合同 → 返回列表
- "审批通过 [合同编号]" → 执行 approve → 返回结果
- "驳回 [合同编号] [原因]" → 执行 reject → 返回结果

BDMS → WeCom（主动通知）：
- 审批节点变更 → 通知下一级审批人
- 驳回 → 通知提交人
- 高风险预警 → 通知法务
- 归档完成 → 通知项目经理
```

**WeCom 消息协议**：

| 消息类型 | 方向 | 格式 | 响应 |
|---|---|---|---|
| 审批指令 | WeCom → BDMS | `审批 BC202609220001` | 审核建议卡片 |
| 解析指令 | WeCom → BDMS | `解析 BC202609220001` | 结构化结果 |
| 查询指令 | WeCom → BDMS | `查询 梆梆` | 合同列表 |
| 审批结果通知 | BDMS → WeCom | 模板卡片 | - |
| 风险预警通知 | BDMS → WeCom | 模板卡片 | - |

### 2.5 BDMS 内部模块交互

| 交互模块 | 方向 | 交互点 | 契约 |
|---|---|---|---|
| `project_management` | 本模块 → PM | 合同签署后立项，`pm_projects.contract_id` 外键引用 `cr_contracts.id` | PM 侧只读合同基本信息 |
| `knowledge_base` | 双向 | 模板/风险规则/产品定价参考落盘 `kb_item`；`analyze_subject()` 读取产品参考 | kb_item 结构见 §12 |
| `data_integration` | 集成 → 本模块 | OA/WeCom 数据导入（I-02/I-04，浏览器自动化） | staging 字段映射表 |
| `dashboard` | 本模块 → 看板 | KPI「合同数量 = COUNT(cr_contracts)」「合同金额 = SUM(amount)」 | `engine.compute(month)` 聚合输出 |
| `revenue` | 本模块 → 确收 | 签署合同的金额作为确收分析输入 | 只读 `cr_contracts` |
| `settings` | 配置 | 审批阈值、加密开关等系统配置 | `sys_settings` 表 |

---

## 3 OS 依赖与限制

> 本模块通过 integration 模块间接依赖浏览器自动化（OA 自动获取），需对齐 INTEGRATION 模块的 OS 适配方案。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| OA 自动获取（场景 A/B） | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-02 |
| WeCom 交互（场景 C） | 企微 API + 回调 | ✅ 支持 | ✅ 支持 | ✅ 支持 | HTTP 回调，OS 无关 |
| docx 生成 | python-docx | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| OCR 导入 | L2 OCR-001 | ✅ 已验证 | 📋 待适配 | 📋 待适配 | rapidocr/paddle 跨平台 |
| 字段加密 | cryptography (Fernet) | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
contract_management
├── OA 自动获取 → integration I-02 → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
├── WeCom 回调 → HTTP 回调（OS 无关）
├── OCR 导入 → L2 OCR-001 → rapidocr/paddle（跨平台）
└── docx/加密/Web/CLI → 纯 Python（全平台）
```

## 4 技术方案

### 3.1 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  接入层                                                              │
│  CLI: bdms contract <cmd>        Web API: /api/contract/*           │
│  (cli.py, Click)                 (web/contract.py, FastAPI)         │
│  WeCom: 消息回调 → contract_api.py (FastAPI /wecom/callback)        │
│  OA: 浏览器自动化 → integration I-02 连接器                          │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │                              │
┌──────────────▼──────────────────────────────▼───────────────────────┐
│  服务层  ContractManagementService (service.py)                     │
│  事务编排 + 状态流转 + 审计写入 + 加解密 + 脱敏 + 审核建议生成          │
├──────────────┬───────────────┬──────────────┬───────────────────────┤
│  计算引擎     │  文档生成      │  OCR 导入     │  Excel 导出           │
│  engine.py   │  docx_        │  ocr_         │  exporter.py          │
│  (统计/风险/  │  generator.py │  importer.py  │  (openpyxl)           │
│   审批/状态)  │  (python-docx)│  (L2 OCR-001) │                      │
├──────────────┴───────────────┴──────────────┴───────────────────────┤
│  持久层  bdms.core.db (SQLite) + schemas_v21.CR_SCHEMA              │
│  加密    _crypto.py (Fernet / BDMS_CONTRACT_KEY)                    │
├─────────────────────────────────────────────────────────────────────┤
│  L3 纯逻辑核心（import 调用，sys.path 注入）                          │
│  ~/.openclaw/workspace/L3-business/skills/contract-approval/core/   │
├─────────────────────────────────────────────────────────────────────┤
│  L2 基础设施（复用）                                                 │
│  OCR-001 │ Office-011 │ Persistence-006 │ 知识库 kb_item        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
src/bdms/modules/contract_management/
├── __init__.py            # 模块导出
├── engine.py              # ContractManagementEngine — 计算引擎
├── service.py             # ContractManagementService — 服务层
├── models.py              # dataclass 内存模型 + CONTRACT_STATUSES
├── docx_generator.py      # ContractDocxGenerator — 模板占位符替换 + 水印
├── ocr_importer.py        # ContractOCRImporter — OCR 导入
├── review_suggestions.py  # ReviewSuggestionGenerator — 审核建议生成（场景 A）
├── wecom_handler.py       # WeCom 消息处理（场景 C）
├── exporter.py            # ContractExporter — Excel 导出
├── _crypto.py             # encrypt/decrypt/mask_name/mask_amount
└── cli.py                 # Click 命令组 `bdms contract`

src/bdms/web/contract.py   # FastAPI 路由 /api/contract/*
src/bdms/web/wecom_contract.py  # WeCom 回调 /wecom/callback
src/bdms/core/schemas_v21.py    # CR_SCHEMA DDL
tests/test_contract_management.py
```

### 3.3 依赖关系

| 依赖 | 类型 | 用途 | 缺失时行为 |
|---|---|---|---|
| `cryptography`（Fernet） | 三方库 | 敏感字段加密 | 降级 base64 前缀 `b64:` |
| `python-docx` | 三方库 | 合同 docx 生成 | 抛 `ImportError` |
| `openpyxl` | 三方库 | Excel 导出 | 必装 |
| `click` | 三方库 | CLI | 必装 |
| L3 `contract-approval` | 内部 skill | 状态机/风险引擎 | 降级本地 fallback |
| L2 `ocr-digitalization` | 内部 skill | OCR | 降级 tesseract → 手工录入 |
| `selenium`/`playwright` | 三方库 | OA 浏览器自动化 | OA 自动获取不可用，转手工 |
| SQLite 3 | 系统库 | 持久化 | 必备 |

### 3.4 关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | L3 采用 **import 组合**而非继承 | L3 是纯函数库，继承会引入无关状态 |
| D2 | 状态流转表在 L4 `models.py` **本地持有**（含 review4） | L3 缺 review4 节点；L4 以本地表为准 |
| D3 | 驳回**直接回 draft**，不落 `rejected` 终态 | 业务上驳回 = 退回修改后重提 |
| D4 | 敏感字段**字段级加密**，金额**明文存储 + 出口脱敏** | 金额需参与 SQL 聚合 |
| D5 | 合同编号 `CR-YYYYMMDD-XXXX` **当日自增序列** | 可读、可排序、幂等 |
| D6 | OA 自动获取走 **integration 连接器**（浏览器自动化） | 与数据集成模块统一管道 |
| D7 | WeCom 交互走 **消息回调 + 指令解析** | 支持远程审批/解析/查询 |
| D8 | 审核建议**可编辑**（JSON 结构化） | 人工可调整后再确认 |

---

## 5 接口设计

### 11.1 ContractManagementEngine

```python
class ContractManagementEngine(BaseEngine):
    """合同管理计算引擎 — 封装 L3 纯逻辑核心 + L4 聚合统计。"""

    module_name: str = "contract_management"

    # ─── BaseEngine 契约 ───
    def compute(self, month: str) -> dict: ...
    def persist(self, month: str, data: dict, overwrite: bool = True) -> dict[str, int]: ...
    def load(self, month: str) -> dict: ...
    def has_data(self, month: str) -> bool: ...

    # ─── 合同解析 ───
    def parse_contract(self, text: str) -> dict:
        """解析合同文本 → 结构化字段 + 条款明细。委托 L3 contract_parser。"""

    # ─── 风险扫描 ───
    def scan_risks(self, contract_content: str) -> list[RiskScanResult]:
        """22 条自动规则扫描 + 27 项人工审查提示。L3 不可用时返回 []。"""

    # ─── 审批分级 ───
    def get_approval_level(self, amount: float) -> dict:
        """返回 {"level": int, "roles": list[str]}"""

    # ─── 状态流转校验 ───
    def validate_state_transition(self, from_status: str, to_status: str, role: str = "") -> dict:
        """返回 {"valid": bool, "message": str}"""

    # ─── 合同标的对比分析 ───
    def analyze_subject(self, contract: dict, kb_items: list[dict]) -> dict: ...

    # ─── 合同关联查询 ───
    def find_related_contracts(self, contract_no: str) -> list[dict]:
        """按合同编号前 14 位 + 关联规则查找关联合同。见 §6。"""
```

### 11.2 ContractManagementService

```python
class ContractManagementService(BaseService):
    """合同管理服务层 — 事务编排 + 审计 + 加解密 + 脱敏。"""

    module_name: str = "contract_management"

    # ─── 生命周期 ───
    def create_contract(self, data: dict, operator: str = "") -> dict: ...
    def submit_approval(self, contract_id: int, operator: str = "", comment: str = "") -> dict: ...
    def approve(self, contract_id: int, operator: str = "", role: str = "", comment: str = "") -> dict: ...
    def reject(self, contract_id: int, operator: str = "", role: str = "", comment: str = "") -> dict: ...
    def sign(self, contract_id: int, operator: str = "", comment: str = "") -> dict: ...
    def archive(self, contract_id: int, operator: str = "") -> dict: ...
    def soft_delete(self, contract_id: int, operator: str = "") -> dict: ...

    # ─── 风险与标的 ───
    def scan_risks(self, contract_id: int, contract_content: str = "") -> list[dict]: ...
    def analyze_subject(self, contract_id: int, kb_items: list[dict] = None) -> dict: ...

    # ─── 审核建议生成（场景 A）───
    def generate_review_suggestions(self, contract_id: int) -> dict:
        """
        生成可编辑的审核建议（结构化 JSON）。
        包含：条款修改建议、自动填充字段、风险提示。
        见 §2.2 输出格式。
        """

    # ─── OA 自动获取（场景 A/B）───
    def fetch_from_oa(self, contract_no: str = None, fetch_type: str = "single") -> dict:
        """
        通过 integration I-02 连接器从 OA 获取合同。
        fetch_type: "single" 按编号获取 / "batch" 获取待审批列表 / "ledger" 获取台账
        返回：{"contracts": list[dict], "source": "oa", "fetch_type": ...}
        """

    # ─── 文档 ───
    def generate_docx(self, contract_id: int, template_path: str = None, output_path: str = None) -> str: ...

    # ─── 查询 ───
    def get_contract(self, contract_id: int) -> Optional[dict]:
        """查询 BDMS 系统内部已完成解析+结构化的合同详情（解密）。"""
    def list_contracts(self, filters: dict = None, page: int = 1, page_size: int = 20, mask: bool = True) -> dict:
        """分页列表查询 BDMS 内部合同。支持按编号/客户/时间/状态/关键词筛选。"""
    def audit_log(self, contract_id: int) -> dict: ...
```

### 11.3 WeCom 消息处理器

```python
class WecomContractHandler:
    """WeCom 消息处理（场景 C）。"""

    def handle_message(self, message: dict) -> dict:
        """
        解析 WeCom 消息 → 执行对应操作 → 返回响应。

        支持指令：
        - "审批 [合同编号]" → 返回审核建议
        - "解析 [合同编号]" → 返回结构化结果
        - "查询 [关键词]" → 返回合同列表
        - "审批通过 [合同编号]" → 执行 approve
        - "驳回 [合同编号] [原因]" → 执行 reject
        """

    def send_approval_notification(self, contract_id: int, next_approver: str) -> None:
        """审批节点变更通知。"""

    def send_risk_alert(self, contract_id: int, risk_summary: str) -> None:
        """高风险预警通知。"""
```

### 11.4 Web API 路由

路由前缀 `/api/contract`，全部经登录会话（Cookie）鉴权。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/contract/list` | 列表查询（BDMS 内部） |
| GET | `/api/contract/{id}` | 合同详情 |
| POST | `/api/contract/create` | 创建合同 |
| POST | `/api/contract/{id}/submit` | 提交审批 |
| POST | `/api/contract/{id}/approve` | 审批通过 |
| POST | `/api/contract/{id}/reject` | 驳回 |
| POST | `/api/contract/{id}/sign` | 签署 |
| POST | `/api/contract/{id}/archive` | 归档 |
| GET | `/api/contract/{id}/risks` | 风险扫描结果 |
| GET | `/api/contract/{id}/review-suggestions` | 审核建议（场景 A） |
| POST | `/api/contract/{id}/fetch-oa` | OA 自动获取（场景 A/B） |
| GET | `/api/contract/{id}/audit-log` | 审计日志 |

WeCom 回调路由：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/wecom/callback` | WeCom 消息回调入口 |
| POST | `/wecom/approval-result` | WeCom 审批结果回调 |

---

## 6 数据模型

> DDL 与 `src/bdms/core/schemas_v21.py` 的 `CR_SCHEMA` 逐字段对齐。
> 所有业务表遵循：审计四字段（created_at/updated_at/created_by/updated_by）+ 软删除（deleted_at）。

### 11.1 表清单

| 表名 | 中文名 | 用途 |
|---|---|---|
| `cr_contracts` | 合同主表 | 基本信息 + 状态 + 金额 + 审批级别 |
| `cr_contract_documents` | 合同文件表 | 各版本文件，SHA-256 校验 |
| `cr_contract_clauses` | 条款明细表 | 解析产出的条款 + OCR 原文暂存 |
| `cr_risk_scan_results` | 风险扫描结果表 | 逐条风险记录 |
| `cr_approval_log` | 审批日志表 | 每次流转记录 |
| `cr_audit_trail` | 操作审计表 | 全量操作留痕 |
| `cr_templates` | 合同模板注册表 | 11 份官方模板元数据 |
| `cr_clause_library` | 条款库 | 标准条款，可复用组合 |
| `cr_contract_relations` | 合同关联关系表 | 合同间关联（补充/终止/订单） |

### 11.2 cr_contracts（合同主表）

```sql
CREATE TABLE IF NOT EXISTS cr_contracts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no      TEXT UNIQUE NOT NULL,          -- 合同编号 CR-YYYYMMDD-XXXX
    title            TEXT NOT NULL,
    contract_type    TEXT,                          -- 合同类型编码
    party_a          TEXT,                          -- 甲方（🔒 Fernet 加密）
    party_b          TEXT,                          -- 乙方（🔒 Fernet 加密）
    amount           REAL NOT NULL DEFAULT 0,       -- 金额（元，明文，出口脱敏）
    currency         TEXT DEFAULT 'CNY',
    effective_date   TEXT,
    expiry_date      TEXT,
    status           TEXT NOT NULL DEFAULT 'draft',
    approval_level   INTEGER DEFAULT 1,
    signed_date      TEXT,
    archive_date     TEXT,
    source           TEXT DEFAULT 'manual',         -- manual / oa_fetch / oa_approval / ocr_import
    oa_process_id    TEXT,                          -- OA 流程 ID（OA 获取时记录）
    -- 审计字段
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at       TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at       TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_cr_status  ON cr_contracts(status);
CREATE INDEX IF NOT EXISTS idx_cr_deleted ON cr_contracts(deleted_at);
CREATE INDEX IF NOT EXISTS idx_cr_no_prefix ON cr_contracts(substr(contract_no, 1, 14));
```

### 11.3 cr_contract_relations（合同关联关系表）

```sql
CREATE TABLE IF NOT EXISTS cr_contract_relations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_contract_id INTEGER NOT NULL,           -- 源合同
    target_contract_id INTEGER NOT NULL,           -- 目标合同
    relation_type    TEXT NOT NULL,                 -- supplement / termination / order / amendment
    match_rule       TEXT NOT NULL,                 -- prefix_14 / bc_prefix / zz_prefix / dash_order
    created_at       TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (source_contract_id) REFERENCES cr_contracts(id),
    FOREIGN KEY (target_contract_id) REFERENCES cr_contracts(id),
    UNIQUE(source_contract_id, target_contract_id, relation_type)
);
```

### 11.4 其余表

> cr_contract_documents / cr_contract_clauses / cr_risk_scan_results / cr_approval_log / cr_audit_trail / cr_templates / cr_clause_library — DDL 与旧版一致（见原文档 §4.3-4.9），此处不重复。

---

## 7 合同关联关系

### 11.1 关联规则

| 关联类型 | 编码 | 识别规则 | 示例 |
|---|---|---|---|
| 补充协议 | `supplement` | 合同编号前 14 位一致 + 编号含 `BC` | `CR-20260922-0001` ↔ `BC-20260922-0001` |
| 终止协议 | `termination` | 合同编号前 14 位一致 + 编号含 `ZZ` | `CR-20260922-0001` ↔ `ZZ-20260922-0001` |
| 框架合同订单 | `order` | 合同编号前 14 位一致 + 编号含 `-` | `CR-20260922-0001` ↔ `CR-20260922-0001-01` |
| 变更协议 | `amendment` | 合同编号前 14 位一致 + 编号含 `BG` | `CR-20260922-0001` ↔ `BG-20260922-0001` |

### 11.2 默认关联逻辑

```
1. 提取合同编号前 14 位作为匹配前缀
2. 在 cr_contracts 中查找同前缀的所有合同
3. 按编号后缀判断关联类型：
   - 含 "BC" → 补充协议
   - 含 "ZZ" → 终止协议
   - 含 "-" 且后缀为数字 → 框架合同订单
   - 含 "BG" → 变更协议
4. 写入 cr_contract_relations 表
```

### 11.3 关联查询接口

```python
def get_related_contracts(self, contract_id: int) -> dict:
    """
    获取合同关联关系树。
    Returns:
        {
            "source": {"id": int, "contract_no": str},
            "relations": [
                {"contract": {...}, "relation_type": "supplement", "match_rule": "bc_prefix"},
                ...
            ]
        }
    """
```

---

## 8 核心流程 — 合同状态机

### 11.1 状态定义

| 状态 | 中文名 | 语义 |
|---|---|---|
| `draft` | 起草 | 草稿，可自由编辑/删除 |
| `review1` | 一级审批 | 部门经理审查 |
| `review2` | 二级审批 | 法务审查（level≥2） |
| `review3` | 三级审批 | PMO 审查（level≥3） |
| `review4` | 四级审批 | 高管审批（level≥4） |
| `approved` | 审批通过 | 可生成正式文档 |
| `signed` | 已签署 | 双方签署完成 |
| `archived` | 已归档 | 终态，只读 |

### 11.2 状态转换表

| # | from | to | 触发 | 执行角色 | 守卫 |
|---|---|---|---|---|---|
| 1 | draft | review1 | submit | sales | 必填字段完整 |
| 2 | review1 | review2 | approve | sales_manager | level ≥ 2 |
| 3 | review1 | approved | approve | sales_manager | level = 1 |
| 4 | review1 | draft | reject | sales_manager | — |
| 5 | review2 | review3 | approve | legal | level ≥ 3 |
| 6 | review2 | approved | approve | legal | level ≤ 2 |
| 7 | review2 | draft | reject | legal | — |
| 8 | review3 | review4 | approve | pmo | level ≥ 4 |
| 9 | review3 | approved | approve | pmo | level ≤ 3 |
| 10 | review3 | draft | reject | pmo | — |
| 11 | review4 | approved | approve | gm | — |
| 12 | review4 | draft | reject | gm | — |
| 13 | approved | signed | sign | sales | 双方签署完成 |
| 14 | signed | archived | archive | admin | OA 归档回执确认 |

> **角色变更说明**：原「财务」角色已去掉，相关操作权限移交 **PMO**（交付中心与财务对接角色）。

---

## 9 风险扫描规则 — 民法典 13 项 49 条

### 11.1 规则体系

**13 大类 49 项** = 从《民法典》合同编抽象并验证后的完整审查清单：

- **自动扫描子集**：13 类中 11 类 × 22 条规则（L3 `risk_engine.CHECK_RULES`，正则/关键词判定）
- **人工审查子集**：49 - 22 = 27 项（需法务人工核对，落知识库 kb_item）
- 履行期限、格式条款两类暂无自动规则（语义判断复杂）

### 11.2 13 大类总表

| # | 类别 | 自动规则数 | 人工项数 | 总计 | 法条依据 |
|---|---|---|---|---|---|
| 1 | 主体信息 | 4 | 1 | 5 | §470、§490 |
| 2 | 合同标的 | 2 | 2 | 4 | §470、§511 |
| 3 | 金额与支付 | 4 | 1 | 5 | §510 |
| 4 | 履行期限 | 0 | 4 | 4 | §511 |
| 5 | 验收标准 | 1 | 1 | 2 | §509 |
| 6 | 违约责任 | 2 | 2 | 4 | §577、§585 |
| 7 | 争议解决 | 2 | 1 | 3 | §507 |
| 8 | 知识产权 | 1 | 1 | 2 | §847 |
| 9 | 保密条款 | 2 | 1 | 3 | §501 |
| 10 | 不可抗力 | 1 | 1 | 2 | §180 |
| 11 | 合同解除 | 1 | 1 | 2 | §563 |
| 12 | 格式条款 | 0 | 3 | 3 | §496、§497 |
| 13 | 其他 | 2 | 2 | 4 | — |
| **合计** | | **22** | **27** | **49** | |

> 自动规则定义、综合评级逻辑、落库映射与旧版一致（见原文档 §6.3-6.5）。

---

## 10 审批分级逻辑

### 11.1 金额阈值与审批层级

| 层级 | 金额区间（元） | 审批角色序列 | SLA |
|---|---|---|---|
| 1 | < 10 万 | 销售经理 | 1 工作日 |
| 2 | 10 万 ~ 50 万 | 销售经理 → 法务审查员 | 2 工作日 |
| 3 | 50 万 ~ 200 万 | 销售总监 → 法务审查员 → PMO | 3 工作日 |
| 4 | ≥ 200 万 | VP/CEO → 法务总监 → PMO | 5 工作日 |

> **角色变更**：原「财务经理/财务总监」已改为 **PMO**。

---

## 11 OA 自动获取（浏览器自动化）

### 11.1 集成架构

```
contract_management ──(调用)──▶ integration I-02 OA 连接器
                                      │
                                      ▼
                              ┌──────────────────────┐
                              │ 浏览器自动化引擎       │
                              │ (selenium/playwright) │
                              └──────────┬───────────┘
                                         │
                                         ▼
                                    OA 系统（浏览器操作）
```

### 11.2 场景 A：获取待审批合同流程

```python
def fetch_oa_approval_list(self, **filters) -> dict:
    """
    通过浏览器自动化获取 OA 待审批合同流程列表。
    Steps:
    1. 登录 OA（凭据走 L2 凭据管理）
    2. 导航至待审批列表页
    3. 提取流程列表（流程编号、合同编号、发起人、发起时间）
    4. 落盘 int_staging_oa

    Returns:
        {"processes": list[dict], "total": int}
    """

def fetch_oa_contract_text(self, process_id: str) -> dict:
    """
    按 OA 流程 ID 提取合同文本。
    Steps:
    1. 打开流程详情页
    2. 定位合同附件（docx/pdf/扫描件）
    3. 下载附件 → 提取文本
    4. 落盘 int_staging_oa

    Returns:
        {"process_id": str, "contract_no": str, "text": str, "attachments": list}
    """

def submit_oa_approval_result(self, process_id: str, result: dict) -> dict:
    """
    通过浏览器自动化将审批结果写回 OA。
    Steps:
    1. 打开流程审批页
    2. 填写审批意见（result.suggestions → 文本）
    3. 点击「通过」/「驳回」
    4. 确认提交

    Returns:
        {"process_id": str, "status": "approved"|"rejected", "oa_timestamp": str}
    """
```

### 11.3 场景 B：获取合同台账并解析

```python
def fetch_oa_contract_ledger(self, contract_no: str = None, date_range: tuple = None) -> dict:
    """
    通过浏览器自动化获取 OA 合同台账信息。
    Steps:
    1. 登录 OA → 导航至合同台账页
    2. 按合同编号/日期范围筛选
    3. 提取台账列表（合同编号、名称、金额、状态、归档日期）
    4. 落盘 int_staging_oa

    Returns:
        {"contracts": list[dict], "total": int}
    """

def fetch_oa_contract_by_no(self, contract_no: str) -> dict:
    """
    按具体合同编号提取合同文本。
    Steps:
    1. 在 OA 台账中搜索合同编号
    2. 打开合同详情/附件
    3. 下载并提取文本
    4. 落盘 int_staging_oa

    Returns:
        {"contract_no": str, "text": str, "title": str, "amount": float}
    """
```

### 11.4 OA 字段映射（int_staging_oa → cr_contracts）

| OA 字段 | cr_contracts 字段 | 转换规则 |
|---|---|---|
| 流程编号 | oa_process_id | 原样 |
| 合同编号 | contract_no | 原样，缺省自动生成 |
| 合同名称 | title | 原样 |
| 甲方 | party_a | 加密存储 |
| 乙方 | party_b | 加密存储 |
| 合同金额 | amount | 去千分位，万元→元 |
| 发起日期 | created_at | 归一 YYYY-MM-DD |
| 流程状态 | source | oa_approval / oa_ledger |

---

## 12 OCR 集成方案

> 与旧版一致（原文档 §8），复用 L2 OCR-001。新增：OA 获取的扫描件/PDF 同样走 OCR 管道。

---

## 13 知识库集成

> 与旧版一致（原文档 §9），11 份合同模板 + 13 类风险规则落 kb_item。

### 14.1 合同模板资产（11 份）

模板源目录：`/Users/bangcle/Bangcle Workspace/00. Bangcle Manual/02. Bangcle Template/合同模版/`

| template_code | 模板名称 | 合同类型编码 | 格式 |
|---|---|---|---|
| TPL-CM-001 | 软件授权许可使用合同（公有云软件）（2026） | saas_cloud | .doc→.docx |
| TPL-CM-002 | 软件授权许可使用合同（年授权）（2026） | license_yearly | .doc→.docx |
| TPL-CM-003 | 软件产品销售合同（永久授权）（2026） | license_perpetual | .doc→.docx |
| TPL-CM-004 | 产品销售合同（软硬一体）（2026） | hw_sw_bundle | .doc→.docx |
| TPL-CM-005 | 产品及服务销售合同（综合类）（2026） | mixed_product_service | .doc→.docx |
| TPL-CM-006 | 安全服务销售合同（2026） | security_service | .doc→.docx |
| TPL-CM-007 | 技术开发合同（2026） | tech_dev | .doc→.docx |
| TPL-CM-008 | 变更协议（销售类-合同条款变更） | amendment_clause | .docx |
| TPL-CM-009 | 变更协议（销售类-客户变更） | amendment_customer | .docx |
| TPL-CM-010 | 补充协议（销售类-补充合同内容）（2026） | supplementary | .docx |
| TPL-CM-011 | 终止协议（销售类） | termination | .docx |

> `.doc`（旧格式）模板需经 LibreOffice/Word 批量转 `.docx` 后方可被 python-docx 加载。

---

## 14 角色与权限

### 14.1 角色定义

| 角色 | 编码 | 可执行操作 |
|---|---|---|
| 销售 | `sales` | create / update(draft) / submit / scan-risks / generate-docx / list / show |
| 部门经理 | `sales_manager` | 上述 + approve/reject（review1） |
| 法务 | `legal` | approve/reject（review2）+ scan-risks + 全量只读 |
| PMO | `pmo` | approve/reject（review3）+ 金额相关只读 + 确收/成本/财务对接 |
| 高管 | `gm` | approve/reject（review4）+ 全量只读 |
| 管理员 | `admin` | 全部操作 + archive + delete |
| **超级管理员** | `super_admin` | **所有操作权限**（含系统级配置、用户管理、跨模块数据访问） |

> **变更说明**：
> - 去掉原「财务」角色，相关操作权限移交 PMO
> - 新增「超级管理员」角色，具备所有操作权限

### 14.2 权限矩阵

| 操作 | sales | sales_manager | legal | pmo | gm | admin | super_admin |
|---|---|---|---|---|---|---|---|
| 创建合同 | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 编辑草稿 | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 提交审批 | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 一级审批 | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 二级审批 | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 三级审批 | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| 四级审批 | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| 签署 | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 归档 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 风险扫描 | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 生成 docx | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 查看全部合同 | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 查看自己合同 | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 导出 Excel | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| OA 自动获取 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| WeCom 审批 | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 用户管理 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 系统配置 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

### 14.3 驾驶舱字段编辑权限（按角色 + 项目双重控制）

| 角色 | 可编辑字段 | 数据范围 |
|---|---|---|
| 项目经理 | 备注、状态 | 自己负责的项目 |
| PMO | 备注、状态、金额（±10%内） | 全部项目 |
| 管理员 | 全部字段 | 全部项目 |
| 超级管理员 | 全部字段 + 系统级 | 全部 |

---

## 15. 错误处理

### 15.1 错误码体系

| 错误码 | 异常类型 | HTTP | 用户提示 |
|---|---|---|---|
| CR-4001 | ContractNotFoundError | 404 | 合同不存在或已被删除 |
| CR-4002 | InvalidTransitionError | 400 | 当前状态不支持该操作 |
| CR-4003 | ContractValidationError | 400 | 合同标题为必填项 |
| CR-4004 | ContractDuplicateError | 409 | 合同编号已存在 |
| CR-4006 | ContractReadOnlyError | 409 | 合同已归档，只读 |
| CR-5001 | OCRExtractError | 422 | OCR 识别失败，请人工录入 |
| CR-5002 | DocxGenerateError | 500 | 文档生成失败 |
| CR-5005 | ContractParseError | 422 | 合同文本无法解析 |
| CR-6001 | OaFetchError | 502 | OA 自动获取失败（浏览器自动化异常） |
| CR-6002 | WecomParseError | 400 | WeCom 消息解析失败 |
| CR-6003 | RelationConflictError | 409 | 合同关联关系冲突 |

### 15.2 降级链

| 依赖失效 | 降级行为 |
|---|---|
| L3 risk_engine 不可用 | scan_risks 返回 []，提示人工审查 |
| L2 OCR/tesseract 全失效 | 提示人工录入（CR-5001） |
| 浏览器自动化失败 | OA 获取降级手工，WeCom 提示重试 |

## 16. CLI 命令

### 16.1 命令清单（21 条）

| # | 命令 | 说明 |
|---|---|---|
| 1-18 | create/update/delete/submit/approve/reject/sign/archive/scan-risks/analyze-subject/import/generate-docx/upload-signed/list/show/audit-log/risks/export | 生命周期 + 查询 + 导出（见旧版 §11 完整定义） |
| 19 | `fetch-oa --process-id --contract-no --type approval\|ledger` | OA 自动获取（场景 A/B） |
| 20 | `review-suggestions <contract_id>` | 生成审核建议（场景 A） |
| 21 | `related <contract_id>` | 查询关联合同 |

## 17. 测试策略

| 测试类型 | 覆盖内容 | 关键用例 |
|---|---|---|
| 单元测试 | 状态机 15 条转换 / 审批分级边界 / 22 条风险规则 / 加密脱敏 / 合同关联 | 非法转换拒绝、金额边界 10万/50万/200万 |
| 集成测试 | 2/3/4 级全生命周期 / 驳回重提 / 软删除 / 审计完整性 / OCR 导入幂等 | 双流审计（approval_log + audit_trail） |
| E2E（真实 HTTP） | 登录→Cookie→全链操作 / 归档只读 / 权限矩阵 | 禁 TestClient |
| 场景 A/B/C 测试 | OA 自动获取（mock 浏览器）/ WeCom 交互（mock 消息）/ 审核建议生成 | 数据落盘 + 指令执行验证 |
| 黄金基准 | docx 生成快照 / Excel 导出 4 Sheet / 风险扫描 22 规则结果 | 逐格比对 |

---

## 附录 B：复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `ApprovalStateMachine` | `L3-business/skills/contract-approval/core/state_machine.py` | **import 引用** | sys.path 注入 + import | `from core.state_machine import get_approval_config, validate_transition` |
| `risk_engine` | `L3-business/skills/contract-approval/core/risk_engine.py` | **import 引用** | 直接调用 | `from core.risk_engine import scan_contract` |
| `contract_parser` | `L3-business/skills/contract-approval/scripts/contract_parser.py` | **import 引用** | 直接调用 | `from scripts.contract_parser import parse_contract` |
| `checklists` | `L3-business/skills/contract-approval/checklists/sales-contract.md` | **知识库落盘** | 读取 → kb_item | `kb_item(knowledge_type='risk_rule', content=md_text)` |
| `BaseEngine` | `modules/base.py` | **继承** | 子类化 | `class ContractManagementEngine(BaseEngine): ...` |
| `BaseService` | `modules/base.py` | **继承** | 子类化 | `class ContractManagementService(BaseService): ...` |
| `BaseImporter` | `modules/base.py` | **继承** | 子类化 | `class ContractOCRImporter(BaseImporter): ...` |
| `BaseExporter` | `modules/base.py` | **继承** | 子类化 | `class ContractExporter(BaseExporter): ...` |
| `OCR-001` | `L2-infra/skills/ocr-digitalization/` | **组合** | 实例化调用 | `from ocr_engine import digitalize_document_v5` |
| `kb_item` | `core/schemas_v21.py` | **DB 共享** | 读写知识库表 | `INSERT INTO kb_item (kb_id, knowledge_type, content) VALUES (...)` |
| `outbox_events` | `core/schemas_v21.py` | **事件总线** | 写入事件 | `INSERT INTO outbox_events (module, event_type, payload) VALUES (...)` |
| `md_reference` | `core/schemas_v21.py` | **DB 共享** | 读写字典 | `SELECT label FROM md_reference WHERE data_type='project_manager' AND code=?` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] L3 纯逻辑核心通过 sys.path 注入（非复制到本模块）
- [ ] 继承关系正确（子类 → BaseEngine/BaseService/BaseImporter/BaseExporter）
- [ ] 组合关系正确（OCR-001/kb_item 实例化后调用）
- [ ] 无复制粘贴代码块
- [ ] 如需修改源文件功能，通过 PR 修改源文件（非本模块内重写）


## 审核记录与变更历史

### 1 审核

| 轮次 | 日期 | 审核人 | 结论 | 意见 |
|---|---|---|---|---|
| 1 | 2026-09-22 | Rex | ⏳ 待审 | — |

### 2 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r2 | 2026-09-22 | Rex 审核反馈 8 条修改：<br>① 新增 OA 自动获取（浏览器自动化）三大场景（审批/解析/WeCom）<br>② F-CM-07 明确为 BDMS 内部结构化查询<br>③ 审核标准明确为「13 大类 49 项（民法典抽象验证）」<br>④ 去掉「DTO 对齐参考」，改为 DTO 字段映射<br>⑤ 新增合同关联关系（前 14 位 + BC/ZZ/- 规则）<br>⑥ 去掉财务角色，权限移交 PMO<br>⑦ 新增超级管理员角色<br>⑧ 模板清单修正为 11 份（含终止协议） |
| v2.1 | 2026-09-22 | 初版 |
