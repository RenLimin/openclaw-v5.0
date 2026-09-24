---
name: pdf-toolkit
description: "Page-level PDF operations: merge multiple PDFs into one, split into per-page files, rotate pages, extract page ranges. Use when the user asks to combine/merge/整合/合并 PDF files, or do page-level ops (split/拆分, rotate/旋转, extract pages/提取页面). Not for content editing (use nano-pdf) or summarization (use summarize)."
metadata:
  openclaw:
    emoji: "📄"
    requires:
      bins: ["python3"]
      pythonPackages: ["pypdf"]
---

# pdf-toolkit

Deterministic page-level PDF operations via one script. No model-generated code — run the fixed helper.

## When to use / not use

| Task | Tool |
|---|---|
| Merge / split / rotate / extract pages | **this skill** |
| Edit content on a page (text, typo, title) | `nano-pdf` |
| Summarize / transcribe a PDF | `summarize` |
| OCR a scanned contract | `ocr-digitalization` / `contract-approval` |

## Commands

```bash
# Merge (order matters)
python3 {baseDir}/scripts/pdf_ops.py merge a.pdf b.pdf -o out.pdf

# Split one page per file
python3 {baseDir}/scripts/pdf_ops.py split in.pdf -o outdir/

# Rotate (90/180/270; --pages optional, default all)
python3 {baseDir}/scripts/pdf_ops.py rotate in.pdf -o out.pdf --angle 90 --pages 1,3-5

# Extract page subset
python3 {baseDir}/scripts/pdf_ops.py extract in.pdf -o out.pdf --pages 1,3-5
```

Pages are 1-based. Ranges `1-5`, lists `1,3`, mix `1,3-5`.

## Execution rules

1. Run the command for the requested operation. Chinese filenames/dirs are fine — quote paths in shell.
2. On success the script prints a one-line summary (files → pages). Report it to the user.
3. On `error:` output, report the reason; do not retry blindly. Encrypted PDFs are rejected with a clear message.
4. Verify: after merge/extract, page count must equal the sum of sources (the script's summary line shows it). After split, file count must equal source page count.

## Dependencies

`pypdf` (pip). If missing: `pip3 install pypdf` (or `uv pip install pypdf`). No network needed beyond that.
