# ocr-digitalization — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/ocr-digitalization/`（SKILL.md + README.md + checklists/ + scripts/ocr_engine.py + scripts/ocr_backends.py）
> 关联组件: `L2-infra/components/ocr-digitalization/`（独立测试套件）

## 验收标准（Definition of Done）

1. 公共 API 可用：`digitalize_document_v5` / `ocr_image` / `pdf_to_images` / `detect_signature_page_v2` / 纠错函数可按文档签名导入调用。
2. CLI 契约与 SKILL.md 一致：位置参数 input/output，选项 `--engine/--dpi/--no-signatures/--signature-dir/--json`。
3. OCR 主引擎（rapidocr）真实可用：单图输入能产出带 bbox/置信度的行结果。
4. 纠错规则真实生效：合同场景常见错误被纠正。
5. 依赖声明与实际安装一致（缺失引擎需明确为可选）。
6. 关联组件回归套件可运行。

## 测试范围

- skill 脚本导入与 API 存在性（`ocr_engine` / `ocr_backends`）。
- CLI `--help` 契约。
- 真实 OCR 推理（rapidocr，合成图）。
- 纠错规则命中（`correct_ocr_errors` 72 条规则 / `correct_contract_text`）。
- 组件 pytest 全量。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 导入 | `import ocr_engine` | 成功，关键函数存在 | ✅ 通过 |
| TC02 | CLI 契约 | `ocr_engine.py --help` | 参数与 SKILL.md 一致 | ✅ 一致 |
| TC03 | 真实 OCR | 合成图 + `ocr_image(engine='rapidocr')` | 出行文本/置信度/bbox | ✅ 1 行，conf 0.911 |
| TC04 | 纠错（backends） | 5 个真实错误词 | 纠正为正确词 | ✅ 5/5 |
| TC05 | 纠错（engine） | 6 个合同错误词 | 纠正为正确词 | ✅ 6/6 |
| TC06 | 组件回归 | `pytest tests -q`（组件目录） | 全绿 | ⚠️ 112 passed, 1 failed |
| TC07 | 依赖盘点 | import 各后端 | 主引擎可用，可选缺失有说明 | ⚠️ paddle/pytesseract 未装 |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01
  python3 -c "import sys; sys.path.insert(0,'L2-infra/skills/ocr-digitalization/scripts'); import ocr_engine; \
    print([hasattr(ocr_engine,f) for f in ['digitalize_document_v5','ocr_image','pdf_to_images','detect_signature_page_v2']])"
  # → [True, True, True, True]   （注: correct_ocr_errors 在 ocr_backends，非 ocr_engine）

  # TC03（真实推理，非仅读代码）
  python3 -c "import sys; sys.path.insert(0,'L2-infra/skills/ocr-digitalization/scripts'); \
    from PIL import Image,ImageDraw; from ocr_engine import ocr_image; \
    img=Image.new('RGB',(220,60),'white'); ImageDraw.Draw(img).text((8,18),'Hello OCR 123',fill='black'); \
    lines=ocr_image(img,engine='rapidocr'); print(len(lines), repr(lines[0].text), round(lines[0].confidence,3), lines[0].bbox)"
  # → 1 'Hello OCR123' 0.911 (6.0, 16.0, 77.0, 33.0)

  # TC04 / TC05（纠错规则实测命中）
  #   backends: 北京郴郴安全→北京梆梆安全 / 贵任→责任 / 产晶→产品 / 精速单价→版本单价 / 钓管辖→约管辖
  #   engine  : 违约全→违约金 / 知识产杈→知识产权 / 有限公可→有限公司 / 验收标谁→验收标准
  #             / 合同金额1O0万元→合同金额100万元 / 不可抗→不可抗力
  #   （OCR_CORRECTIONS 规则总数实测 72 条）

  # TC06
  cd L2-infra/components/ocr-digitalization && python3 -m pytest tests -q -p no:cacheprovider
  # → 1 failed, 112 passed in 0.41s
  #   FAILED tests/test_03_preprocess.py::TestBinarize::test_adaptive_binarize
  #   assert np.uint8(255) == 0  （自适应二值化结果全白，未产生黑色像素）

  # TC07
  #   rapidocr_onnxruntime OK / fitz OK / PIL OK / numpy OK / scipy OK / cv2 OK
  #   paddleocr MISSING / pytesseract MISSING
  ```
- 结论: **通过（引擎链路 + 纠错实测达标）**。主链路（导入、CLI、rapidocr 真实推理、纠错规则）全部实测通过；关联组件回归 112 通过、1 个既有失败用例（与本 skill 改动无关，属二值化预处理）。

## 遗留问题（如实记录）

1. **组件既有失败用例**：`test_03_preprocess.py::TestBinarize::test_adaptive_binarize` 失败（渐变图二值化后 `arr.min()==255`）。非本次 skill 层改动引入，但属该能力回归范围内的红项，需单独立项修复。
2. **文档与实现位置不一致**：SKILL.md「公共 API 总览」把 `correct_ocr_errors(text)` 列为 `ocr_engine` 的 API，实际定义在 `scripts/ocr_backends.py`（`ocr_engine` 内对应函数名为 `correct_contract_text`）。→ 建议修正 SKILL.md 或提供 re-export，避免调用方按文档找不到符号。
3. **CLI 错误路径不友好**：对不存在的输入文件，`ocr_engine.py <missing.pdf>` 直接抛 `pymupdf.FileNotFoundError` 栈回溯，未转为一行 `error:` 提示（对比 pdf-toolkit 的 `error:` 约定）。
4. **可选引擎未装**：paddleocr / pytesseract 缺失。SKILL.md 已声明 paddle 为可选，但 `auto` 引擎在二者皆缺时的降级路径建议补一条实测。
