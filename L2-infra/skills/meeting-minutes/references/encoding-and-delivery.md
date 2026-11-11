# 编码与交付规范

## 1. 编码

- 一律输出 **UTF-8**。
- 面向可能误判编码的应用（macOS「文本编辑」、部分 Windows 编辑器、老 Markdown 渲染器），加 **UTF-8 BOM**：
  ```bash
  printf '\xEF\xBB\xBF' | cat - minutes.md > minutes.bom && mv minutes.bom minutes.md
  head -c 3 minutes.md | xxd   # 应为 efbb bf
  ```
- 注意：个别工具（如某些 git diff、严格 parser）不喜欢 BOM。默认不加；用户出现乱码/打不开时再加，或同时提供 HTML。

## 2. 判断"文件坏了"还是"打开方解码错了"

用户反馈乱码 / `???` / 打不开时，先字节级核验，别急着重写：

```bash
file minutes.md                 # 应为 UTF-8 Unicode text
xxd minutes.md | head           # 看中文是否为多字节（如 e4bc9a=会）
grep -c '??' minutes.md         # 是否真有字面问号 0x3F
iconv -f UTF-8 -t UTF-8 minutes.md >/dev/null && echo OK
```

- 字节正常但显示 `???` → **打开应用编码/字体问题**，不是文件坏：加 BOM 或给 HTML。
- 字节确实损坏 → 重新生成。

## 3. 交付路径（关键）

- 沙箱工作目录（`~/.openclaw/sandboxes/...`）是隐藏路径，用户在 Finder 里不便打开，**不能作为唯一交付位置**。
- 始终复制一份对用户可达的副本：
  ```bash
  cp minutes.md ~/Downloads/
  # 需要时再放 ~/Desktop/
  ```

## 4. 多格式

- **HTML**：自带 `<meta charset="UTF-8">`，浏览器打开中文必正常，`⌘P → 存储为 PDF` 可直接转 PDF。适合"md 打不开"时兜底与外发。
- **PDF**：正式归档/外发用。
- 多份格式保持内容一致、同批同步到可达目录。

## 5. 对外发送

- 邮件/群里发给外部人员 = 对外副作用，**必须先经用户确认**，不得自动发送。
