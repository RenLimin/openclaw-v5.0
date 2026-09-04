---
name: contract-approval
description: "销售合同审批工作流：起草、分级审批、风险扫描、合同生成、归档。基于《民法典》合同编 + CLM 7 阶段方法论。可独立使用，也可整合至自建系统。"
user-invocable: true
---

# 销售合同审批模块 (SCA-001)

> L4 专有业务层组件，基于《民法典》合同编 + CLM 7 阶段方法论。

## 依赖组件

- **OCR-001（L2 文档数字化）**：`skills/ocr-digitalization/`
  - 通过兼容层（`scripts/contract_ocr_v5.py` / `contract_ocr.py`）透明调用
  - 实际实现位于 `ocr-digitalization/scripts/ocr_engine.py`

## When to Use

- 用户需要创建、审批、签署、归档销售合同
- 用户需要扫描销售合同的法律风险
- 用户需要基于模板生成合同文档（docx）
- 用户需要查询合同状态、审批进度、审计日志

## Hard Rules

1. **审批流转必须按状态机**：draft → review1 → review2 → review3 → approved → signed → archived
2. **驳回回退到 draft**：任一环节驳回，合同回到起草状态
3. **分级审批按金额**：<10万(1级) / 10-50万(2级) / 50-200万(3级) / >200万(4级)
4. **所有操作写入审计日志**：不可跳过
5. **风险扫描器是辅助工具**：标注"辅助提醒，非法务专业判断"
6. **合同金额必须大小写一致**：生成时自动校验
7. **数据持久化到 SQLite**：复用 L2 持久化适配

---

## 独立使用方式（完整 CLI 调用链）

适用于单份合同快速审核，无需数据库、无需审批流转。

### 方式 A：扫描件 PDF → Excel 报告（一条命令）

```bash
python skills/contract-approval/scripts/export_unified_report.py \
  --ocr-pdf 合同扫描件.pdf \
  --output 合同审批报告.xlsx
```

内部自动完成：OCR 数字化 → 条款解析 → 逐条审核 → 生成 Excel（4 个 Sheet）。

### 方式 B：分步骤执行（调试用）

```bash
# Step 1: OCR 数字化（扫描件才需要，原生 PDF/文本可跳过）
python skills/contract-approval/scripts/contract_ocr_v5.py \
  合同扫描件.pdf \
  合同.md \
  --signature-dir signatures/ \
  --json ocr_result.json

# Step 2: 仅解析条款（查看解析结果）
python skills/contract-approval/scripts/contract_auditor.py parse --file 合同.md

# Step 3: 逐条审核（控制台输出）
python skills/contract-approval/scripts/contract_auditor.py audit-file --file 合同.md

# Step 4: 生成 Excel 报告
python skills/contract-approval/scripts/export_unified_report.py \
  --file 合同.md \
  --ocr-result ocr_result.json \
  --output 合同审批报告.xlsx
```

### 方式 C：审批流完整模式（需要数据库）

```bash
# 1. 初始化数据库（首次运行）
python skills/contract-approval/scripts/approval_engine.py init

# 2. 创建合同
python skills/contract-approval/scripts/approval_engine.py create \
  --title "技术服务合同-XXX项目" \
  --type tech_service \
  --party-a "北京梆梆安全科技有限公司" \
  --party-b "客户公司名称" \
  --amount 90000 \
  --effective-date "2026-09-07" \
  --expiry-date "2027-09-06"

# 3. 提交审批
python skills/contract-approval/scripts/approval_engine.py submit --contract-id 1

# 4. 风险扫描
python skills/contract-approval/scripts/risk_scanner.py scan --contract-id 1

# 5. 审批通过/驳回
python skills/contract-approval/scripts/approval_engine.py approve \
  --contract-id 1 --approver-name "Rex" --approver-role "销售经理" --comment "同意"

python skills/contract-approval/scripts/approval_engine.py reject \
  --contract-id 1 --approver-name "Rex" --approver-role "法务审查员" --comment "违约责任不对等"

# 6. 生成合同文档
python skills/contract-approval/scripts/contract_gen.py generate --contract-id 1

# 7. 签署 & 归档
python skills/contract-approval/scripts/approval_engine.py sign --contract-id 1
python skills/contract-approval/scripts/approval_engine.py archive --contract-id 1

# 8. 查看详情
python skills/contract-approval/scripts/approval_engine.py show --contract-id 1
```

---

## 与 OCR skill 的集成方式

### 方式一：兼容层调用（推荐，向后兼容）

`scripts/contract_ocr_v5.py` 是 OCR 组件的兼容层，内部 re-export `ocr-digitalization` 的全部公共 API。

**CLI 方式：**

```bash
python skills/contract-approval/scripts/contract_ocr_v5.py \
  合同扫描件.pdf output.md --signature-dir signatures/ --json ocr_result.json
```

**Python API 方式：**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from contract_ocr_v5 import digitalize_document_v5, ocr_image, detect_signature_page_v2

# 端到端数字化
result = digitalize_document_v5(
    pdf_path="合同.pdf",
    output_path="合同.md",
    extract_signatures=True,
    signature_dir="./signatures"
)

print(result.text)          # 纯文本
print(result.markdown)      # Markdown（含签名标注）
print(f"印章 {len(result.seals)} 处, 签名 {len(result.signatures)} 处")
```

**兼容层 re-export 的完整 API：**

| 类 / 函数 | 说明 |
|---|---|
| `OCRResultV5` | 端到端结果对象 |
| `OCRLine` | 单行 OCR 结果 |
| `SignatureRegion` | 签名/印章区域 |
| `digitalize_document_v5()` | 端到端数字化（最常用） |
| `ocr_image()` | 单图 OCR |
| `pdf_to_images()` | PDF 转图 |
| `detect_signature_page_v2()` | 签署页签名/印章联检 |
| `detect_red_seals()` | 红色印章检测 |
| `correct_contract_text()` | 合同文本纠错 |

### 方式二：直接调用 OCR 组件（性能最优）

跳过兼容层，直接 import `ocr-digitalization/scripts/` 下的模块：

```python
import sys, os

_ocr_dir = os.path.join(os.path.dirname(__file__),
                        '..', 'ocr-digitalization', 'scripts')
if _ocr_dir not in sys.path:
    sys.path.insert(0, _ocr_dir)

from ocr_engine import digitalize_document_v5, ocr_image

result = digitalize_document_v5("合同.pdf", "合同.md")
```

**适用场景**：需要深度定制、或想减少一层间接调用时使用。
**缺点**：OCR 组件路径变更时需要修改调用方代码。

### 方式三：通过 Excel 报告自动集成

`export_unified_report.py` 内置了 OCR 调用，直接传 `--ocr-pdf` 即可自动完成全流程：

```bash
python skills/contract-approval/scripts/export_unified_report.py \
  --ocr-pdf 合同扫描件.pdf \
  --output 合同审批报告.xlsx
```

这是最省心的方式，OCR 结果直接进入 Sheet 4（签署要素审计）。

---

## 核心能力

| 能力 | 命令 | 说明 |
|------|------|------|
| 创建合同 | `create` | 输入基本信息，生成合同编号 |
| 提交审批 | `submit` | draft → review1 |
| 审批通过 | `approve` | 按层级流转 |
| 审批驳回 | `reject` | 回退到 draft |
| 签署合同 | `sign` | approved → signed |
| 归档合同 | `archive` | signed → archived |
| 风险扫描 | `scan` | 基于民法典 13 类条款扫描 |
| 合同生成 | `generate` | 基于模板生成 docx |
| 查询合同 | `list` / `show` | 列表 / 详情 |

## 审批阈值

| 金额 | 层级 | 审批角色 | SLA |
|------|------|----------|-----|
| < 10 万 | 1 | 销售经理 | 1 工作日 |
| 10-50 万 | 2 | 销售经理 + 法务 | 2 工作日 |
| 50-200 万 | 3 | 销售总监 + 法务 + 财务 | 3 工作日 |
| > 200 万 | 4 | VP/CEO + 法务总监 + 财务总监 | 5 工作日 |

## 风险扫描 13 项

主体信息(5) + 合同标的(4) + 金额与支付(5) + 履行期限(4) + 验收标准(4) + 违约责任(4) + 争议解决(3) + 知识产权(3) + 保密条款(4) + 不可抗力(3) + 合同解除(3) + 格式条款(3) + 其他(4)

详见 `checklists/sales-contract.md` 和 `checklists/risk-matrix.md`。

## 数据库

初始化：`python3 scripts/approval_engine.py init`

数据库文件：`~/.openclaw/workspace/contracts.db`

## 依赖

- Python 3.10+ 标准库
- python-docx（合同生成，可选）
- openpyxl（Excel 报告生成）
- ocr-digitalization skill（扫描件数字化）

## 与其他维度的关系

| 维度 | 关系 |
|------|------|
| L3 合同管理 | 继承 CLM 7 阶段 + 民法典 + 角色定义 |
| L2 持久化 | 复用 SQLite + Repository 模式 |
| L2 Office 文档 | 复用 python-docx |
| L2 OCR 数字化 | 复用 contract_ocr_v5.py（扫描件→文本，ADR-023） |
| L2 知识库 | 复用合同模板索引 |

---

## 三大核心能力

### 1. 条款解析（contract_parser.py）

按《民法典》合同编 28 条核心条款类别，逐条解析合同原文：

```bash
python3 scripts/contract_auditor.py parse --file <合同文本文件>
```

输出：每个条款的类别、法条依据、原文摘录、摘要、关键术语

### 2. 审核标准库（audit_standard.py）

基于《民法典》+ 司法解释 + 行业规范，43 项审核标准，覆盖 17 个条款类别：

```bash
python3 scripts/audit_standard.py  # 查看标准库概览
```

### 3. 逐条审核（contract_auditor.py）

按审核标准逐条审核合同，输出结构化结果 + 修改建议：

```bash
# 审核合同文件
python3 scripts/contract_auditor.py audit-file --file <合同文本文件>

# 审核数据库中的合同
python3 scripts/contract_auditor.py audit --contract-id <ID>

# JSON 输出
python3 scripts/contract_auditor.py audit-file --file <文件> --json
```

输出包含：
- 综合风险评级（高/中/低）
- 审核结论（通过/有条件通过/驳回）
- 逐条审核结果（✅通过/⚠️警告/❌不通过/N/A）
- 证据引用（合同原文）
- 问题和修改建议
- 必须修改项和建议修改项汇总
