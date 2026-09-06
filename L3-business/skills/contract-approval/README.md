# 销售合同审批模块 (SCA-001)

> L4 专有业务层组件 | 基于《民法典》合同编 + CLM 7 阶段方法论

## 完整端到端流程（5 步）

```
┌──────────┐   ┌─────┐   ┌────────┐   ┌────────┐   ┌──────────┐
│ 输入 PDF │ → │ OCR │ → │ 条款解析│ → │ 逐条审核│ → │ 生成报告 │
└──────────┘   └─────┘   └────────┘   └────────┘   └──────────┘
   Step 1       Step 2      Step 3        Step 4        Step 5
```

### Step 1：准备输入

输入可以是：
- 扫描件 PDF（走 OCR 流程）
- 原生 PDF（直接提取文本）
- 纯文本 / Markdown 文件（跳过 OCR）

### Step 2：OCR 数字化（扫描件必需）

```bash
# 调用 OCR 组件（通过兼容层）
python skills/contract-approval/scripts/contract_ocr_v5.py \
  合同扫描件.pdf \
  合同.md \
  --signature-dir signatures/ \
  --json ocr_result.json
```

### Step 3：条款解析

```bash
python skills/contract-approval/scripts/contract_auditor.py parse --file 合同.md
```

按《民法典》合同编 28 条核心条款类别，逐条解析合同原文。

### Step 4：逐条审核

```bash
python skills/contract-approval/scripts/contract_auditor.py audit-file --file 合同.md
```

基于 43 项审核标准，逐条审核，输出通过/警告/不通过。

### Step 5：生成 Excel 报告

```bash
python skills/contract-approval/scripts/export_unified_report.py \
  --file 合同.md \
  --ocr-result ocr_result.json \
  --output 合同审批报告.xlsx
```

---

## 快速开始（扫描件合同）

```bash
# 一条命令：扫描件 PDF → 完整 Excel 报告
python skills/contract-approval/scripts/export_unified_report.py \
  --ocr-pdf 合同扫描件.pdf \
  --output 合同审批报告.xlsx
```

---

## 所有脚本说明

| 脚本 | 用途 | 核心调用方式 |
|---|---|---|
| `approval_engine.py` | 审批流程引擎（CRUD + 状态流转） | `python approval_engine.py <command> [options]` |
| `risk_scanner.py` | 风险扫描器（13 类条款快速扫描） | `python risk_scanner.py scan --contract-id <id>` |
| `contract_gen.py` | 合同文档生成（docx 模板） | `python contract_gen.py generate --contract-id <id>` |
| `contract_parser.py` | 条款解析（28 类条款拆分） | 作为模块 import，或通过 contract_auditor 调用 |
| `contract_auditor.py` | 合同审核引擎（解析 + 审核 + 报告） | `python contract_auditor.py audit-file --file <path>` |
| `audit_standard.py` | 审核标准库（43 项标准定义） | `python audit_standard.py` 查看概览 |
| `export_unified_report.py` | 生成统一 Excel 报告（4 个 Sheet） | `python export_unified_report.py --file <path> --output <xlsx>` |
| `contract_ocr_v5.py` | OCR 兼容层（re-export ocr-digitalization） | `python contract_ocr_v5.py <pdf> <output>` |
| `contract_ocr.py` | 旧版 OCR 兼容层（已弃用，保留兼容） | `python contract_ocr.py <pdf> <output>` |
| `generate_full_analysis.py` | 完整版分析（已合并到 export_unified_report） | 已废弃，不推荐使用 |
| `schema.sql` | 数据库表结构定义 | 由 approval_engine init 自动执行 |

### 脚本依赖关系

```
export_unified_report.py
    ├── contract_ocr_v5.py ──→ ocr-digitalization/ocr_engine.py
    ├── contract_parser.py
    ├── audit_standard.py
    └── (内部审核逻辑)

contract_auditor.py
    ├── contract_parser.py
    ├── audit_standard.py
    └── approval_engine.py (DB 读取)
```

---

## Excel 输出说明（4 个 Sheet）

### Sheet 1：合同条款拆解

- **内容**：合同基本信息 + 所有条款的逐条拆解
- **包含字段**：条款编号、条款标题、法条依据、原文摘录、摘要、关键术语
- **用途**：快速了解合同全貌，定位重点条款

### Sheet 2：统一审核标准

- **内容**：43 项审核标准完整列表
- **包含字段**：标准编号、条款类别、检查项、法条依据、风险等级、检查方法
- **用途**：作为审核依据和知识库，供审核人员参考

### Sheet 3：逐条审核与整改建议

- **内容**：每条标准的审核结果 + 具体修改建议
- **包含字段**：条款类别、检查项、审核结果（✅/⚠️/❌）、风险等级、问题描述、证据原文、修改建议
- **用途**：核心输出，指导合同修改

### Sheet 4：签署要素审计（OCR 自动检测）

- **内容**：签名、印章的检测结果
- **包含字段**：所在页码、要素类型（印章/签名）、关联标签（甲方/乙方）、置信度、截图路径、bbox 坐标
- **用途**：签署合规性检查，确认双方都已签字盖章
- **前提**：需要 `--ocr-pdf` 或 `--ocr-result` 参数提供 OCR 数据

---

## 依赖组件

### 必选依赖

| 组件 | 层级 | 用途 |
|---|---|---|
| **ocr-digitalization（OCR-001）** | L2 基础设施层 | 扫描件 PDF 数字化 + 签署要素检测 |
| Python 3.10+ | 运行时 | — |
| openpyxl | Python 包 | Excel 报告生成 |

### OCR 依赖（由 ocr-digitalization 提供）

- `rapidocr-onnxruntime`（主引擎）
- `pymupdf`（PDF 渲染 + 原生文本提取）
- `pillow`（图像处理）
- `numpy` / `scipy`（数值计算）
- `paddleocr`（可选，GPU 加速）

### 可选依赖

| 组件 | 用途 |
|---|---|
| python-docx | 合同文档生成（docx 模板） |

### 依赖关系图

```
contract-approval (SCA-001, L4)
│
├── ocr-digitalization (OCR-001, L2)  ← 扫描件数字化
│   ├── RapidOCR / PaddleOCR
│   ├── PyMuPDF
│   └── Pillow / NumPy / SciPy
│
├── openpyxl                           ← Excel 报告
├── python-docx (可选)                 ← 合同生成
└── SQLite (标准库)                    ← 审批持久化
```

---

## 独立使用 vs 集成使用

### 独立使用

**适用场景**：单份合同审核，不需要审批流转，不需要数据库。

**使用方式**：直接调用 `export_unified_report.py`，输入 PDF 或文本，输出 Excel 报告。

```bash
# 扫描件合同 → Excel 报告（一条命令）
python skills/contract-approval/scripts/export_unified_report.py \
  --ocr-pdf 合同扫描件.pdf \
  --output 合同审批报告.xlsx
```

**特点**：
- ✅ 零配置，无需初始化数据库
- ✅ 单文件输入，单文件输出
- ✅ 适合一次性审核
- ❌ 没有审批流程、状态管理、审计日志

### 集成使用

**适用场景**：企业级合同管理，需要审批流转、状态跟踪、多用户协作。

**使用方式**：通过 `approval_engine.py` 管理合同生命周期，配合风险扫描、文档生成等模块。

```bash
# 1. 初始化数据库（只需一次）
python skills/contract-approval/scripts/approval_engine.py init

# 2. 创建合同
python skills/contract-approval/scripts/approval_engine.py create \
  --title "技术服务合同" --amount 90000 ...

# 3. 提交审批
python skills/contract-approval/scripts/approval_engine.py submit --contract-id 1

# 4. 风险扫描
python skills/contract-approval/scripts/risk_scanner.py scan --contract-id 1

# 5. 审批通过
python skills/contract-approval/scripts/approval_engine.py approve \
  --contract-id 1 --approver-name "Rex" --approver-role "销售经理"
```

**特点**：
- ✅ 完整审批流程（7 个状态）
- ✅ 分级审批（按金额 4 级）
- ✅ 审计日志完整
- ✅ 合同编号自动生成
- ❌ 需要初始化和维护数据库

---

## 配置项

### 审核标准（audit_standard.py）

所有审核标准定义在 `AUDIT_CRITERIA` 列表中，每项包含：

| 字段 | 说明 |
|---|---|
| `id` | 标准编号，如 `AUD-001` |
| `category` | 条款类别，如 `主体信息`、`违约责任` |
| `item` | 检查项名称 |
| `law_article` | 法条依据，如 `民法典第470条` |
| `risk_level` | 风险等级：`high` / `medium` / `low` |
| `check_method` | 检查方法说明 |
| `pass_condition` | 通过条件（正则或关键词） |

**查看标准库**：

```bash
python skills/contract-approval/scripts/audit_standard.py
```

### 审核阈值

在 `contract_auditor.py` 中可以调整：

| 配置 | 默认值 | 说明 |
|---|---|---|
| 高风险项数 ≥ N → 综合高风险 | 3 | 触发"高风险"评级的高风险项数量阈值 |
| 中风险项数 ≥ N → 综合中风险 | 5 | 触发"中风险"评级的中风险项数量阈值 |
| 必须修改项判定 | `high` 风险全部 | 哪些级别属于"必须修改" |

### 自定义规则

可以在 `audit_standard.py` 的 `AUDIT_CRITERIA` 列表中添加自定义标准：

```python
AUDIT_CRITERIA.append(AuditCriterion(
    id="CUST-001",
    category="保密条款",
    item="保密期限不得少于5年",
    law_article="公司内部规定",
    risk_level="medium",
    check_method="检查保密期限条款",
    pass_condition=r"保密期限.{0,10}(5|五).{0,5}年"
))
```

### 审批分级阈值

在 `approval_engine.py` 中定义：

| 金额区间 | 审批层级 |
|---|---|
| < 10 万 | 1 级（销售经理） |
| 10-50 万 | 2 级（销售经理 + 法务） |
| 50-200 万 | 3 级（销售总监 + 法务 + 财务） |
| > 200 万 | 4 级（VP/CEO + 法务总监 + 财务总监） |

---

## 目录结构

```
contract-approval/
├── SKILL.md              # 技能入口 + CLI + 集成方式
├── README.md             # 本文件
├── templates/            # 合同模板（docx）
├── checklists/           # 审查清单
│   ├── sales-contract.md # 基于民法典的审查 checklist
│   └── risk-matrix.md    # 风险评估矩阵
└── scripts/              # 工具脚本
    ├── approval_engine.py     # 审批流程引擎
    ├── risk_scanner.py        # 风险扫描器
    ├── contract_gen.py        # 合同生成器
    ├── contract_parser.py     # 条款解析器
    ├── contract_auditor.py    # 合同审核引擎
    ├── audit_standard.py      # 审核标准库
    ├── export_unified_report.py # Excel 报告生成
    ├── contract_ocr_v5.py     # OCR 兼容层（v5）
    ├── contract_ocr.py        # OCR 兼容层（旧版，保留）
    └── schema.sql             # 数据库 schema
```

---

## 审批流程

```
DRAFT → REVIEW_1 → REVIEW_2 → REVIEW_3 → APPROVED → SIGNED → ARCHIVED
  ↑         │          │          │
  └─────────┴──────────┴──────────┘（驳回回 DRAFT）
```

## 验证记录

- [x] 数据库初始化
- [x] 合同创建 + 编号生成
- [x] 审批流转（通过/驳回）
- [x] 风险扫描输出
- [x] 合同生成（docx）
- [x] 审计日志完整
- [x] 扫描件 OCR 数字化（复用 L2 OCR-001）
- [x] 条款解析 + 逐条审核
- [x] Excel 统一报告（4 Sheet）
- [x] 端到端流程验证
