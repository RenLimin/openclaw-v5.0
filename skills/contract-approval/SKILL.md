---
name: contract-approval
description: "销售合同审批工作流：起草、分级审批、风险扫描、合同生成、归档。基于《民法典》合同编 + CLM 7 阶段方法论。可独立使用，也可整合至自建系统。"
user-invocable: true
---

# 销售合同审批模块 (SCA-001)

> L4 专有业务层组件，基于《民法典》合同编 + CLM 7 阶段方法论。

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

## 工作流程

### 1. 创建合同

```bash
python3 scripts/approval_engine.py create \
  --title "技术服务合同-XXX项目" \
  --type tech_service \
  --party-a "北京梆梆安全科技有限公司" \
  --party-b "客户公司名称" \
  --amount 90000 \
  --effective-date "2026-09-07" \
  --expiry-date "2027-09-06"
```

### 2. 提交审批

```bash
python3 scripts/approval_engine.py submit --contract-id 1
```

### 3. 审批操作

```bash
# 通过
python3 scripts/approval_engine.py approve \
  --contract-id 1 --approver-name "Rex" --approver-role "销售经理" --comment "同意"

# 驳回
python3 scripts/approval_engine.py reject \
  --contract-id 1 --approver-name "Rex" --approver-role "法务审查员" --comment "违约责任不对等，需修改"
```

### 4. 风险扫描

```bash
python3 scripts/risk_scanner.py scan --contract-id 1
```

### 5. 生成合同文档

```bash
python3 scripts/contract_gen.py generate --contract-id 1
```

### 6. 签署 & 归档

```bash
python3 scripts/approval_engine.py sign --contract-id 1
python3 scripts/approval_engine.py archive --contract-id 1
```

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

## 与其他维度的关系

| 维度 | 关系 |
|------|------|
| L3 合同管理 | 继承 CLM 7 阶段 + 民法典 + 角色定义 |
| L2 持久化 | 复用 SQLite + Repository 模式 |
| L2 Office 文档 | 复用 python-docx |
| L2 OCR 数字化 | 复用 contract_ocr.py（扫描件→文本，ADR-023） |
| L2 知识库 | 复用合同模板索引 |

### 7. 扫描件合同数字化（复用 L2 OCR-001）

支持直接处理扫描件合同（PDF/图片），先数字化再审核：

```bash
# 扫描件 PDF → 高精度文本（自动纠错）
python3 scripts/contract_ocr.py <扫描件.pdf> <输出.md> --engine auto

# 生成的文本可直接进入审核流水线
python3 scripts/contract_auditor.py audit-file --file <输出.txt>
```

**OCR 能力来自 L2 文档数字化组件（OCR-001，ADR-023）**：
- 600 DPI 高分辨率渲染
- 8 版本图像预处理自动选最优
- RapidOCR 主引擎 + PaddleOCR 可选（自动回退）
- 合同场景 40+ 规则自动纠错
- 版面分析还原阅读顺序

```bash
# Python API（供 L3/L4 复用）
python3 -c "
from contract_ocr import digitalize_document
res = digitalize_document('合同扫描件.pdf', engine='auto')
print(res.text)      # 纯文本全文
print(res.meta)      # 页数/行数/引擎/置信度
"
```

#### 签名/印章自动检测提取（v5 增强）

自动检测合同中的手写签名和红色公章位置，截图保存：

```bash
# 扫描件 PDF → 文本 + 签名/印章截图
python3 scripts/contract_ocr_v5.py <扫描件.pdf> <输出.md>

# 只提取文本，不检测签名
python3 scripts/contract_ocr_v5.py <扫描件.pdf> <输出.md> --no-signatures

# 指定签名截图保存目录
python3 scripts/contract_ocr_v5.py <扫描件.pdf> <输出.md> --signature-dir ./signatures
```

**v5 新增能力**：
- 🔴 **红色印章检测**：基于红色像素+形态学分析，自动定位公章/合同章
- ✍️ **手写签名检测**：基于关键词附近墨色密度，定位签名区域
- 📸 **自动截图保存**：每个签名/印章单独保存为 PNG
- 🏷️ **智能标注**：关联"甲方/乙方 + 签字/盖章"等上下文标签
- 📝 **位置标注**：在输出 Markdown 中标注签名/印章位置和置信度

```bash
# Python API
python3 -c "
from contract_ocr_v5 import digitalize_document_v5
res = digitalize_document_v5('合同.pdf', extract_signatures=True)
print(res.text)           # 纯文本
print(res.markdown)       # Markdown（含签名标注）
print(f'印章 {len(res.seals)} 处')
print(f'签名 {len(res.signatures)} 处')
for s in res.seals:
    print(f'  第{s.page}页: {s.image_path}')
"
```

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
