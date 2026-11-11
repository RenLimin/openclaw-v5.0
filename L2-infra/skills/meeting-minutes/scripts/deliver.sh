#!/usr/bin/env bash
# 会议纪要交付脚本：加 BOM、复制到可达目录、生成 HTML 兜底。
# 用法: bash deliver.sh minutes.md --html --copy-to ~/Downloads
set -euo pipefail

FILE=""
COPY_TO="$HOME/Downloads"
MAKE_HTML=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --html) MAKE_HTML=1; shift ;;
    --copy-to) COPY_TO="$2"; shift 2 ;;
    *) FILE="$1"; shift ;;
  esac
done

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "ERROR: 请提供存在的 .md 文件" >&2
  exit 1
fi

# 1) UTF-8 BOM
if ! head -c3 "$FILE" | grep -q $'\xef\xbb\xbf'; then
  printf '\xEF\xBB\xBF' | cat - "$FILE" > "$FILE.tmp" && mv "$FILE.tmp" "$FILE"
  echo "added BOM"
fi

# 2) 复制到可达目录
mkdir -p "$COPY_TO"
cp "$FILE" "$COPY_TO/$(basename "$FILE")"
echo "copied -> $COPY_TO/$(basename "$FILE")"

# 3) HTML 兜底
if [[ "$MAKE_HTML" -eq 1 ]]; then
  HTML="${FILE%.md}.html"
  TITLE=$(head -1 "$FILE" | sed 's/^#\s*//')
  cat > "$HTML" << HTMLHEAD
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${TITLE}</title>
<style>
  body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.7;color:#1d1d1f}
  h1{font-size:24px;border-bottom:2px solid #111;padding-bottom:10px}
  h2{font-size:18px;margin-top:28px;border-left:4px solid #d9411e;padding-left:10px}
  table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
  th,td{border:1px solid #ccc;padding:7px 10px;text-align:left}
  th{background:#f5f5f7}
  pre{background:#f5f5f7;padding:12px;border-radius:6px;overflow:auto;font-size:13px}
  code{background:#f0f0f2;padding:1px 5px;border-radius:3px;font-size:13px}
  blockquote{border-left:3px solid #d9411e;margin:8px 0;padding:4px 12px;color:#555;background:#fafafa}
  footer{margin-top:30px;color:#888;font-size:12px;border-top:1px solid #eee;padding-top:10px}
</style>
</head>
<body>
HTMLHEAD
  # 简单 md->html：标题、表格、引用、列表、段落
  python3 - "$FILE" >> "$HTML" << 'PYEOF'
import sys, re, html
p = sys.argv[1]
raw = open(p, encoding="utf-8-sig").read()
lines = raw.splitlines()
out, in_table, in_ul, in_ol = [], False, False, False
def esc(s): return html.escape(s)
def inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s
for ln in lines:
    if ln.startswith("# "):
        continue  # 标题已在 <title>
    if ln.startswith("## "):
        if in_table: out.append("</table>"); in_table=False
        out.append(f"<h2>{esc(ln[3:])}</h2>")
    elif ln.startswith("> "):
        if in_table: out.append("</table>"); in_table=False
        out.append(f"<blockquote>{inline(esc(ln[2:]))}</blockquote>")
    elif ln.startswith("|") and "---" not in ln:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if not in_table:
            out.append("<table><tr>" + "".join(f"<th>{inline(esc(c))}</th>" for c in cells) + "</tr>")
            in_table = True
        else:
            out.append("<tr>" + "".join(f"<td>{inline(esc(c))}</td>" for c in cells) + "</tr>")
    elif re.match(r"^[-*]\s+", ln):
        if in_table: out.append("</table>"); in_table=False
        if not in_ul: out.append("<ul>"); in_ul=True
        out.append(f"<li>{inline(esc(re.sub(r'^[-*]\s+','',ln)))}</li>")
    elif re.match(r"^\d+\.\s+", ln):
        if in_table: out.append("</table>"); in_table=False
        if in_ul: out.append("</ul>"); in_ul=False
        if not in_ol: out.append("<ol>"); in_ol=True
        out.append(f"<li>{inline(esc(re.sub(r'^\d+\.\s+','',ln)))}</li>")
    elif ln.startswith("```"):
        out.append("<pre>")
    elif ln.strip() == "":
        if in_table: out.append("</table>"); in_table=False
        if in_ul: out.append("</ul>"); in_ul=False
        if in_ol: out.append("</ol>"); in_ol=False
    else:
        if in_table: out.append("</table>"); in_table=False
        if in_ul: out.append("</ul>"); in_ul=False
        if in_ol: out.append("</ol>"); in_ol=False
        out.append(f"<p>{inline(esc(ln))}</p>")
if in_table: out.append("</table>")
if in_ul: out.append("</ul>")
if in_ol: out.append("</ol>")
print("\n".join(out))
PYEOF
  echo "</body></html>" >> "$HTML"
  cp "$HTML" "$COPY_TO/$(basename "$HTML")" 2>/dev/null || true
  echo "html -> $HTML"
fi

echo "DONE"
