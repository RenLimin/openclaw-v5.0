# SCA-001 销售合同审批 — 产品操作手册（OPERATIONS）

> 版本：v1.0（2026-09-28）
> 组件：SCA-001（L3 core + L4 office-contract）
> L3 代码：`L3-business/skills/contract-approval/`
> L4 代码：`L4-proprietary/components/office-contract/`
> 使用方式：OpenClaw skill（对话触发）或 CLI

---

## 1. 安装与依赖

```bash
# L4 依赖（L3 core 零依赖，无需安装）
cd L4-proprietary/components/office-contract
pip install python-docx openpyxl

# 验证安装
python3 -m pytest tests/ -q   # → 58 passed
```

---

## 2. 操作指南

### 2.1 对话触发（推荐，OpenClaw skill）

直接对 Jerry 说：
- 「起草一份销售合同，甲方 X，乙方 Y，金额 Z 万」
- 「扫描审核这份合同：~/Downloads/contract.pdf」
- 「生成合同审批分析报告」

skill 入口：`L3-business/skills/contract-approval/SKILL.md`（含 Hard Rules，状态机/驳回/分级/审计/免责声明）。

### 2.2 CLI 全流程（L4 contractctl）

> 实际入口：`src/office_contract/cli/contractctl.py`，用 `--id`（数字 ID）操作，非合同编号。

```bash
cd L4-proprietary/components/office-contract
export PYTHONPATH=src

# 0. 初始化（首次）
python3 -m office_contract init

# 1. 起草（甲方默认从 settings 注入，--party-b 必填）
python3 -m office_contract create --title "XX服务合同" --party-b "客户公司" --amount 150000
# → 输出合同 ID（如 1）

# 2. 风险扫描（可选，随时可扫）
python3 -m office_contract risk-scan --id 1 --json

# 3. 提交审批（进入 review1）
python3 -m office_contract submit --id 1

# 4. 审批（approve / reject，驳回必须带 --comment）
python3 -m office_contract approve --id 1 --approver 张三 --role manager
python3 -m office_contract reject --id 1 --approver 张三 --role manager --comment "条款5需修改"

# 5. 生成合同文档（docx）
python3 -m office_contract generate --id 1

# 6. 签署 + 归档
python3 -m office_contract sign --id 1
python3 -m office_contract archive --id 1

# 7. 查看 / 列表
python3 -m office_contract show --id 1
python3 -m office_contract list
```

### 2.3 风险扫描（独立使用）

```bash
# 纯文本扫描（L3 core，零依赖）
python3 -c "
import sys; sys.path.insert(0, 'L3-business/skills/contract-approval')
from core.risk_engine import scan_text_dict
import json
print(json.dumps(scan_text_dict(open('合同.txt').read()), ensure_ascii=False, indent=2))
"
```

### 2.4 扫描件审批（OCR 接入）

```bash
# 1. OCR 识别（L2 OCR-001）
python3 L2-infra/components/ocr-digitalization/scripts/ocr_main.py 合同.pdf output.md

# 2. 用识别文本做逐条审核
python3 L3-business/skills/contract-approval/scripts/generate_full_analysis.py output/合同识别文本.txt
```

### 2.5 Excel 审批报告

```bash
python3 L3-business/skills/contract-approval/scripts/export_unified_report.py \
  --input 合同文本 --output output/审批报告.xlsx
```

---

## 3. 分级审批规则（默认）

| 金额 | 层级 | 流程 |
|---|---|---|
| <10 万 | 1 级 | review1 → approved |
| 10-50 万 | 2 级 | review1 → review2 → approved |
| 50-200 万 | 3 级 | review1 → review2 → review3 → approved |
| >200 万 | 4 级 | 全流程 + 更高角色 |

> L4 可通过 `config/settings.py` 注入自定义 `level_table`。

---

## 4. 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `非法状态流转` 报错 | 跳步操作（如 draft 直接 approve） | 按 §2.2 顺序走流程；被驳回后先重新 submit |
| docx 生成失败「金额大小写不一致」 | 预期行为（Hard Rule 6） | 核对金额输入 |
| OCR 结果质量差影响审核 | 扫描件质量低 | 参照 OCR-001 OPERATIONS §5.2 |
| `No module named office_contract` | 未设 PYTHONPATH | `export PYTHONPATH=src`（在 office-contract 目录） |
| 测试失败 | 依赖缺失 | `pip install python-docx openpyxl` |

---

## 5. FAQ

**Q1: 风险扫描结果能当法律意见吗？**
A: 不能。风险扫描定位是「辅助提醒，非法务专业判断」（Hard Rule 5），重大合同需人工法务复核。

**Q2: 驳回后合同数据还在吗？**
A: 在。驳回只是状态回 draft，合同元数据与审计日志保留，可修改后重新提交。

**Q3: 想加自定义风险规则？**
A: `scan_text(text, custom_rules=[RiskRule(...)])` 传入自定义规则列表，与默认 22 条合并执行。

**Q4: 非销售合同能用吗？**
A: 状态机与分级审批是通用的；但风险规则 22 条针对销售合同场景，其他场景用 custom_rules 定制。

---

## 6. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-28 | v1.0 | 初版归档 |
