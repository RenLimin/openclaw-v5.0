# pdf-toolkit — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/pdf-toolkit/`（SKILL.md + scripts/pdf_ops.py）

## 验收标准（Definition of Done）

1. 四类页级操作可用：`merge` / `split` / `rotate` / `extract`，语义与 SKILL.md 一致。
2. 页码 1-based，支持 `1,3-5` 混合写法；越界/非法输入给出一行 `error:` 并非零退出。
3. 结果可机器核验：merge 后页数 = 各源页数之和；split 后文件数 = 源页数；rotate/extract 页数符合预期。
4. 加密 PDF 被拒绝并给出明确提示（不静默产出错文件）。
5. 成功时打印一行摘要（files → pages / pages 数）。

## 测试范围

- 用 pypdf 现场合成 2 页 + 3 页两份 PDF 作为夹具，真实执行四类操作。
- 反向用例：越界页码、缺失输入、非法角度。
- 结果文件页数/文件数机器复核。

> 本 skill 目录内**无 pytest tests/**，验收方式为 CLI 真实运行（合成夹具 + 结果复核）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 合并 | a.pdf(2) + b.pdf(3) → merged.pdf | 5 页，摘要含 `merged 2 files … (5 pages)` | ✅ 5 页 |
| TC02 | 提取 | merged.pdf `--pages 1,3-4` | 3 页 | ✅ 3 页 |
| TC03 | 旋转 | merged.pdf `--angle 90 --pages 1` | 5 页，仅第 1 页旋转 | ✅ 5 页 |
| TC04 | 拆分 | merged.pdf → split/ | 5 个文件，命名 `merged_NNN.pdf` | ✅ 5 个 |
| TC05 | 越界页码 | `--pages 9`（总 5 页） | 一行 error，非零退出 | ✅ `error: page 9 out of bounds (1-5)`，exit=2 |
| TC06 | 缺失输入 | merge 不存在文件 | 一行 error，非零退出 | ✅ `error: [Errno 2] …`，exit=2 |
| TC07 | 非法角度 | `--angle 45` | argparse 拒绝，非零退出 | ✅ `invalid choice: '45'`，exit=2 |

## 实测结果

- 命令与输出摘要:
  ```bash
  # 合成夹具（真实生成，非读代码）
  python3 -c "from pypdf import PdfWriter; …"   # a.pdf=2 页, b.pdf=3 页

  python3 L2-infra/skills/pdf-toolkit/scripts/pdf_ops.py merge tmp/verif-l2/pdf/a.pdf tmp/verif-l2/pdf/b.pdf -o tmp/verif-l2/pdf/merged.pdf
  # → merged 2 files -> tmp/verif-l2/pdf/merged.pdf (5 pages)      exit=0

  python3 L2-infra/skills/pdf-toolkit/scripts/pdf_ops.py extract tmp/verif-l2/pdf/merged.pdf -o tmp/verif-l2/pdf/ext.pdf --pages 1,3-4
  # → extracted 3 pages -> tmp/verif-l2/pdf/ext.pdf                exit=0

  python3 L2-infra/skills/pdf-toolkit/scripts/pdf_ops.py rotate tmp/verif-l2/pdf/merged.pdf -o tmp/verif-l2/pdf/rot.pdf --angle 90 --pages 1
  # → rotated 1/5 pages by 90° -> tmp/verif-l2/pdf/rot.pdf         exit=0

  python3 L2-infra/skills/pdf-toolkit/scripts/pdf_ops.py split tmp/verif-l2/pdf/merged.pdf -o tmp/verif-l2/pdf/split/
  # → split … -> 5 files in tmp/verif-l2/pdf/split/ (prefix: merged_NNN.pdf)   exit=0

  # 结果复核（独立读取产物）
  python3 -c "from pypdf import PdfReader; …"
  # → merged.pdf 5 / ext.pdf 3 / rot.pdf 5 / split files 5     ✅ 全部符合预期
  ```
- 结论: **通过**。四类操作全部真实跑通，页数/文件数机器复核一致；三个反向用例均按约定给出一行 `error:` 并非零退出。

## 遗留问题（如实记录）

1. **无自动化回归**：夹具与断言目前内联在验收命令里，建议固化为 `tests/test_pdf_ops.py`（合成夹具 + subprocess 调用 + 页数断言）。
2. **加密 PDF 分支未实测**：`cmd_merge/split/rotate/extract` 均含 `is_encrypted` 拒绝逻辑，但本次未构造加密夹具。建议补一条加密 PDF 用例，确认「明确报错且不产出文件」。
3. **`rotate` 仅校验页数不校验角度累积**：`--angle` 由 argparse `choices` 限制，已实现；但重复 rotate 同一页的累积角度无提示（非缺陷，记录口径）。
