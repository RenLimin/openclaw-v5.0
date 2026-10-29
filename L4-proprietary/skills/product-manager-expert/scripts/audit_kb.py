#!/usr/bin/env python3
"""Bangcle 产品知识库检准脚本 (Product KB Audit)

用法:
    python3 audit_kb.py --db <product_kb.db路径> [--report <输出md路径>] [--json <输出json路径>]

检查维度:
  A. 结构完整性: FK引用 / 唯一性 / 必填字段 / 枚举合法性
  B. 一致性: doc_type契约 / 扩展名-format / 版本号 / 路径存在性
  C. 覆盖度: 产品-文档覆盖 / 文档-源文件 / chunk覆盖
  D. 数据健康: 价格 / 销售状态 / embedding / 关系表

退出码: 0=无异常 1=有警告级 2=有错误级
"""
import argparse, json, os, re, sqlite3, sys, collections

ERROR, WARN, INFO = "error", "warn", "info"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./data/product_kb.db")
    ap.add_argument("--report", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    findings = []  # (level, category, message)
    def add(level, cat, msg):
        findings.append({"level": level, "category": cat, "message": msg})

    # ---------- A. 结构完整性 ----------
    products = cur.execute("SELECT * FROM product").fetchall()
    skus = cur.execute("SELECT * FROM sku").fetchall()
    docs = cur.execute("SELECT * FROM doc_asset").fetchall()
    chunks = cur.execute("SELECT * FROM doc_chunk").fetchall()
    lines = cur.execute("SELECT * FROM product_line").fetchall()
    cats = cur.execute("SELECT * FROM product_category").fetchall()

    valid_p = {r["id"] for r in products}
    THIRD_PARTY_STATUS = "第三方产品/服务"
    third_party_p = {r["id"] for r in products if r["status"] == THIRD_PARTY_STATUS}

    valid_line = {r["id"] for r in lines}
    valid_cat = {r["id"] for r in cats}

    bad_line = [r["id"] for r in products if r["line_id"] not in valid_line]
    bad_cat = [r["id"] for r in products if r["category_id"] is not None and r["category_id"] not in valid_cat]
    bad_sku_p = [r["id"] for r in skus if r["product_id"] not in valid_p]
    bad_doc_p = [r["id"] for r in docs if r["product_id"] not in valid_p]
    bad_cat_line = [r["id"] for r in cats if r["line_id"] not in valid_line]
    if bad_line: add(ERROR, "FK", f"product 引用不存在 line_id: {bad_line}")
    if bad_cat: add(ERROR, "FK", f"product 引用不存在 category_id: {bad_cat}")
    if bad_sku_p: add(ERROR, "FK", f"sku 引用不存在 product_id: {bad_sku_p}")
    if bad_doc_p: add(ERROR, "FK", f"doc_asset 引用不存在 product_id: {bad_doc_p}")
    if bad_cat_line: add(ERROR, "FK", f"product_category 引用不存在 line_id: {bad_cat_line}")

    name_counts = collections.Counter(r["name"] for r in products)
    dup_names = {k: v for k, v in name_counts.items() if v > 1}
    if dup_names: add(WARN, "UNIQUE", f"产品名重复: {dup_names}")
    code_counts = collections.Counter(r["code"] for r in products if r["code"])
    dup_codes = {k: v for k, v in code_counts.items() if v > 1}
    if dup_codes: add(WARN, "UNIQUE", f"产品 code 重复: {dup_codes}")
    sku_code_counts = collections.Counter(r["sku_code"] for r in skus)
    dup_sku = {k: v for k, v in sku_code_counts.items() if v > 1}
    if dup_sku: add(WARN, "UNIQUE", f"sku_code 重复: {dup_sku}")

    no_code = [r["id"] for r in products if not r["code"]]
    if no_code: add(WARN, "NULL", f"产品 code 为空: {no_code}")
    no_summary = [r["id"] for r in products if not r["summary"] and r["id"] not in third_party_p]
    if no_summary: add(WARN, "NULL", f"产品 summary 为空: {no_summary}")
    if third_party_p: add(INFO, "THIRDPARTY", f"第三方占位桶(无需summary/文档/目录价): {sorted(third_party_p)}")
    no_version = [r["id"] for r in products if not r["version_latest"]]
    if no_version: add(INFO, "NULL", f"产品 version_latest 为空(共{len(no_version)}): 前10 {no_version[:10]}")

    # ---------- B. 一致性 ----------
    DOC_TYPE_CONTRACT = {"white_paper", "sales_note", "func_list", "ppt", "tech_white_paper", "manual", "faq", "other", "version_note"}
    dt_counts = collections.Counter(r["doc_type"] for r in docs)
    dt_bad = {k: v for k, v in dt_counts.items() if k not in DOC_TYPE_CONTRACT}
    if dt_bad: add(WARN, "ENUM", f"doc_type 超出设计契约(8类): {dt_bad} — 设计文档需更新或归类需校准")

    fmt_ext_mismatch = []
    for d in docs:
        ext = os.path.splitext(d["file_name"])[1].lstrip(".").lower()
        fmt = (d["format"] or "").lower()
        if ext and fmt and ext != fmt:
            fmt_ext_mismatch.append((d["id"], d["file_name"], fmt, ext))
    if fmt_ext_mismatch: add(WARN, "CONSIST", f"format与扩展名不一致(共{len(fmt_ext_mismatch)}): 前10 {fmt_ext_mismatch[:10]}")

    missing_files = []
    for d in docs:
        if not os.path.exists(d["original_path"]):
            missing_files.append((d["id"], d["original_path"]))
    if missing_files: add(ERROR, "PATH", f"源文件缺失(共{len(missing_files)}): {missing_files[:10]}")

    md5_counts = collections.Counter(r["md5"] for r in docs if r["md5"])
    dup_md5 = {k: v for k, v in md5_counts.items() if v > 1}
    if dup_md5: add(WARN, "CONSIST", f"同一文件(md5)被多条记录引用: {dict(list(dup_md5.items())[:5])}")

    # ---------- C. 覆盖度 ----------
    doc_p = {r["product_id"] for r in docs}
    no_doc = sorted((valid_p - doc_p) - third_party_p)
    if no_doc: add(WARN, "COVERAGE", f"无文档产品(共{len(no_doc)},已剔除第三方占位桶): 前20 {no_doc[:20]}")

    chunk_doc_ids = {r["doc_id"] for r in chunks}
    doc_ids = {r["id"] for r in docs}
    no_chunk = sorted(doc_ids - chunk_doc_ids)
    if no_chunk: add(WARN, "COVERAGE", f"无chunk文档(共{len(no_chunk)}): 前20 {no_chunk[:20]}")

    orphan_chunks = [r["id"] for r in chunks if r["doc_id"] not in doc_ids]
    if orphan_chunks: add(ERROR, "FK", f"孤儿chunk(无doc): {len(orphan_chunks)}")

    empty_chunks = [r["id"] for r in chunks if not r["text"] or not r["text"].strip()]
    if empty_chunks: add(WARN, "NULL", f"空文本chunk: {len(empty_chunks)}")

    bad_idx = []
    bydoc = collections.defaultdict(list)
    for c in chunks: bydoc[c["doc_id"]].append(c["chunk_index"])
    for d, v in bydoc.items():
        if sorted(v) != list(range(len(v))):
            bad_idx.append(d)
    if bad_idx: add(WARN, "CONSIST", f"chunk_index 不连续文档(共{len(bad_idx)}): {bad_idx[:5]}")

    # ---------- D. 数据健康 ----------
    bad_price = [r["id"] for r in skus if r["unit_price"] is not None and r["unit_price"] <= 0 and r["product_id"] not in third_party_p]
    if bad_price: add(WARN, "PRICE", f"unit_price<=0(共{len(bad_price)}): {bad_price}")
    no_price = [r["id"] for r in skus if r["unit_price"] is None]
    if no_price: add(WARN, "PRICE", f"unit_price为空(共{len(no_price)}): {no_price}")

    embed_count = sum(1 for c in chunks if c["embedding"])
    if embed_count == 0:
        add(WARN, "EMBED", f"doc_chunk.embedding 全为空({embed_count}/{len(chunks)}) — 语义检索降级为纯FTS")

    rel_count = cur.execute("SELECT count(*) FROM kb_relation").fetchone()[0]
    if rel_count == 0:
        add(INFO, "RELATION", "kb_relation 表为空(0行) — 知识图谱关系未构建")

    status_counts = collections.Counter(r["status"] for r in products)
    unknown_status = [r["id"] for r in products if r["status"] in ("未知", "unknown", "") or r["status"] is None]  # 第三方产品/服务 为合法枚举，不在此列
    if unknown_status: add(WARN, "STATUS", f"产品状态异常(共{len(unknown_status)}): {unknown_status}")

    # ---------- 汇总 ----------
    summary = {
        "db": args.db,
        "counts": {
            "products": len(products), "skus": len(skus), "docs": len(docs),
            "chunks": len(chunks), "lines": len(lines), "categories": len(cats),
        },
        "findings": findings,
        "severity": {"error": sum(1 for f in findings if f["level"] == "error"),
                     "warn": sum(1 for f in findings if f["level"] == "warn"),
                     "info": sum(1 for f in findings if f["level"] == "info")},
    }
    con.close()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    if args.report:
        lines_out = ["# Bangcle 产品知识库检准报告", "",
                     f"检查时间: (见json) | 数据库: `{args.db}`", "",
                     "## 规模快照", "",
                     "| 维度 | 数量 |", "|---|---|"]
        for k, v in summary["counts"].items():
            lines_out.append(f"| {k} | {v} |")
        lines_out += ["", "## 问题清单", ""]
        for f in findings:
            icon = {"error": "🔴", "warn": "🟡", "info": "🔵"}[f["level"]]
            lines_out.append(f"- {icon} **[{f['level']}]** {f['category']}: {f['message']}")
        lines_out += ["", f"## 汇总: 🔴 {summary['severity']['error']} / 🟡 {summary['severity']['warn']} / 🔵 {summary['severity']['info']}", ""]
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines_out))

    for f in findings:
        icon = {"error": "🔴", "warn": "🟡", "info": "🔵"}[f["level"]]
        print(f"{icon} [{f['level']}] {f['category']}: {f['message']}")
    print(f"\n汇总: error={summary['severity']['error']} warn={summary['severity']['warn']} info={summary['severity']['info']}")
    return 2 if summary["severity"]["error"] else (1 if summary["severity"]["warn"] else 0)

if __name__ == "__main__":
    sys.exit(main())
