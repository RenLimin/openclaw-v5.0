# VERIFICATION — Bangcle 合同管理专家 MVP（4 步分析闭环）

> 日期：2026-11-02 · 对应 DESIGN-DETAIL-bangcle-contract-mvp-v1.0（已通过）
> 执行：主会话直接落地，全部命令真实运行。

## 1. 交付文件（L4-proprietary/components/bangcle-contract/）

| 路径 | 说明 |
|---|---|
| `_bootstrap.py` | 跨组件 sys.path 引导（L4→L3/L2，同级 product-kb），单向依赖 |
| `config/settings.py` | DB/产品库路径、阈值（0.5/0.85）、免责文案、格式清单；SEMANTIC_ENABLED=False |
| `contract_review/models.py` | LoadedFile / DigitizedText / LineItem / ItemMatchResult / ReviewReport |
| `contract_review/ingest.py` | 文件定位 + 格式探测（不存在/不支持显式报错） |
| `contract_review/digitize.py` | 分发：图片→L4 OCR CLI；其余→L2 parsers |
| `contract_review/tesseract_cli.py` | 🆕 tesseract CLI OCR（chi_sim+eng）+ 中文空格归一化 |
| `contract_review/parser.py` | L3 parse_contract 薄封装 |
| `contract_review/extract_items.py` | 🆕 标的枚举行项目抽取（名称/型号/单价，含"万"换算，兼容 OCR 裸序号） |
| `contract_review/risk.py` | L3 scan_text 薄封装 |
| `contract_review/kb_match.py` | product-kb ContractMatcher 参照 + 满足度三态 |
| `contract_review/report.py` | 合并 → Markdown + Excel（openpyxl，风险/满足度填色，免责首屏） |
| `contract_review/pipeline.py` | ReviewService：5 阶段编排 + 持久化 |
| `repository/db.py` | migration v1（reviews/review_item/audit_log，增量幂等，append-only 只 INSERT） |
| `cli/contractctl.py` | init-db / review / report |
| `tests/fixtures/` | 真实文件：sample_contract.docx / sample_contract.txt / scan_contract.png |
| `tests/` | test_extract_items(6) + test_satisfaction(10) + test_e2e_real_files(4) |

## 2. 两处对 DETAIL 的实证偏离（均已在代码注释固化）

1. **扫描件 OCR 走 tesseract CLI 而非 L2 ImageOcrParser**：
   - 实证：环境缺 Python 绑定 `pytesseract` → L2 `ImageOcrParser.is_available()=False` 不注册；
   - 且 L2 parser 调 `image_to_string(image)` 未指定 `lang`（默认 eng），中文必失败；L4 红线禁改 L2。
   - 处置：L4 直接调已就位的 tesseract 5.5.3 CLI（`-l chi_sim+eng`），同一引擎、非降级伪造。

2. **中文 OCR 空格归一化**：实证 tesseract chi_sim 在每汉字间插空格（"全 渠 道"），导致名称粘连/单价丢失/FTS 全败。
   - 处置：`_normalize_cjk_spacing` 删除汉字相邻及汉字↔ASCII 间噪声空格，保留换行；枚举正则兼容 OCR 裸序号 `1全渠道…`。
   - 效果：OCR 标的"全渠道应用安全监测软件V6.0 单价100000元"正确抽取并判**满足**。

## 3. 测试命令与实际结果

```bash
cd L4-proprietary/components/bangcle-contract
python3 cli/contractctl.py init-db
python3 cli/contractctl.py review --file tests/fixtures/sample_contract.docx
python3 -m unittest discover -s tests           # 20 tests OK
```
实际结果：
- **L4 20 unittest 全绿**（16 单测 + 4 真实文件 E2E）；
- 下层零破坏：**L2 114 passed**、**L3 42 unittest OK**。

E2E 实测：
| 输入 | 风险 | 标的满足度 |
|---|---|---|
| sample_contract.docx（3 真实产品） | high(18/3/1) | 满足（3/3 satisfied） |
| sample_contract.txt（含不存在产品） | high(8/10/4) | 不满足（1 satisfied + 1 unsatisfied） |
| scan_contract.png（OCR 扫描件） | high | 不满足（"全渠道…"满足；"API安全平司"OCR 误字如实暴露） |

## 4. 黄金契约
- 风险 rule_id 集合 **22/22 100% == L3 CHECK_RULES**（E2E 断言锁定）；
- 报告含固定免责声明；audit_log append-only（无 update/delete 接口，测试断言）；
- 合同原文零外发：本期无任何网络/LLM 调用，SEMANTIC_ENABLED=False 写死（静态可证）。

## 5. 红线确认
- L2/L3/skills 源码零改动（仅新增 L4 目录 + DETAIL/VERIFICATION 文档）；
- 无新增强制第三方依赖（pdfplumber/openpyxl/python-docx/Pillow/tesseract 均已就位）；无凭据。

## 6. 遗留/后续
1. OCR 误字（台→司）依赖模糊匹配/纠错——当前如实判不满足，符合"不伪 pass"；
2. OA 泛微在线拉取（requestid→docid→imagefileid）与企微回调/推送（P1）；
3. 审批回写、多级状态机、docx 生成、Web UI、语义 LLM 轨（脱敏后）。
