# Bangcle 产品/服务知识库 操作手册

| 项 | 值 |
|---|---|
| 文档 | OPERATIONS |
| 版本 | v1.0 |
| 层级 | L4 Bangcle 专有业务模块 |

---

## 1. 安装/启动

### 1.1 环境依赖

- Python 3.10+
- 依赖包：`openpyxl python-docx python-pptx PyPDF2 jieba`（均为系统已有，不需要新增）
- 依赖 L2 组件：`persistence-006` / `memory-search-009` / `ocr-digitalization`（均已存在）

### 1.2 初始化

```bash
# 进入模块目录
cd L4-proprietary/components/product-kb

# 初始化数据库
python -m product_kb.cli init --db ./data/product_kb.db
```

## 2. 数据导入/构建

### 2.1 导入价格表

```bash
python -m product_kb.cli import-price \
  --xlsx "/path/to/梆梆_产品价格查询-YYYY-MM-DD.xlsx" \
  [--db ./data/product_kb.db]
```

输出示例：
```
导入完成:
  产品线: 8
  分类: 45
  产品: 195
  SKU: 386
```

### 2.2 扫描文档目录

```bash
python -m product_kb.cli scan \
  --root "/path/to/07. Bangcle Prod/" \
  [--db ./data/product_kb.db]
```

输出示例：
```
扫描完成:
  文档总数: 1158
  自动关联: 1052 (90.8%)
  待审核: 106
```

待审核文档会输出列表，需要人工处理：修改文件名或在产品表添加别名。

### 2.3 构建全文和向量索引

```bash
python -m product_kb.cli build-index \
  [--full] [--db ./data/product_kb.db]
```

- `--full`：全量重建，否则增量构建（仅处理新抽取文档）

### 2.4 数据质量检查

```bash
python -m product_kb.cli check [--db ./data/product_kb.db]
```

输出问题清单：
- 产品覆盖率：哪些产品没有文档
- 重名产品：哪些产品名称重复
- 版本冲突：哪些产品版本异常

## 3. 日常使用

### 3.1 合同标的比对

输入 CSV 格式：
```csv
产品名称,型号,数量,单价
全渠道应用安全监测软件V6.0,APP授权扩展年付费许可版,2,90000
鸿蒙Next元服务加固软件V2.0,,1,0
Android应用加固服务,,10,8000
```

运行比对：
```bash
python -m product_kb.cli match \
  --input /path/to/contract.csv \
  [--output /path/to/result.xlsx] \
  [--db ./data/product_kb.db]
```

输出：
- 终端输出比对表
- 如果指定 `--output`，输出 Excel 文件
- 异常结果高亮标记：🔴 未匹配 / 🟡 价格异常 / 🟡 停用产品

### 3.2 产品知识问答查询

```bash
python -m product_kb.cli query "你的问题" \
  [--top 5] [--db ./data/product_kb.db]
```

输出每个结果：
```
=== 结果 1 (得分: 0.89) ===
产品: 梆梆安全鸿蒙NEXT SDK加固软件V2.3.0
文档: 05-梆梆安全鸿蒙NEXT SDK加固V2.3.0_产品白皮书.docx
类型: 产品白皮书
片段: ... 支持的版本范围是 HarmonyOS NEXT Beta/Release 5.0+ ...
路径: /Users/bangcle/...
```

### 3.3 多产品对比

```bash
python -m product_kb.cli compare \
  --products "产品ID1,产品ID2,产品ID3" \
  [--output compare.xlsx] \
  [--db ./data/product_kb.db]
```

输出对比矩阵，支持 Excel 导出。

### 3.4 产品列表查询

```bash
# 按产品线筛选
python -m product_kb.cli list --line "安全保护线" [--status normal]

# 按关键词搜索
python -m product_kb.cli list --search "鸿蒙"
```

## 4. 配置

### 4.1 配置文件

`config.yaml` 示例：
```yaml
db_path: ./data/product_kb.db
doc_root: /Users/bangcle/Bangcle Workspace/07. Bangcle Prod/
match_threshold: 0.5
top_k: 5
weights:
  name_similarity: 0.6
  version_match: 0.3
  category_match: 0.1
```

### 4.2 别名配置

如果产品名称不一致，可以在产品表添加别名（JSON 数组），支持匹配。可以通过 SQL 更新：

```sql
UPDATE product SET aliases = '["别名1", "别名2"]' WHERE id = ?;
```

## 5. 故障排查

### 问题 1：文档抽取失败/乱码

**原因**：文件损坏/加密/格式不支持。

**解决**：
1. 检查文件是否能正常打开
2. 扫描版 PDF 确认 OCR 组件正常：`python -m ocr_digitalization test --file /path/to/file.pdf`
3. 重新抽取：`python -m product_kb.cli reextract --doc-id <ID>`

### 问题 2：产品匹配不到正确结果

**原因**：名称不一致/拼写差异/别名没加。

**解决**：
1. 添加别名到产品表
2. 降低匹配阈值：修改配置 `match_threshold: 0.4`
3. 检查数据质量报告，处理未关联文档

### 问题 3：增量更新后旧文档还在

**原因**：文件删除后索引没清理。

**解决**：全量重建索引：`python -m product_kb.cli build-index --full`

### 问题 4：检索结果不对，问题回答错了

**原因**：切片不对/向量召回偏差。

**解决**：
1. 检查切片是否正确，调整切片策略（需要改代码）
2. 重新构建全量索引
3. 如果是特定问题，确认文档内容是否正确

### 问题 5：数据库损坏

**原因**：意外中断写入。

**解决**：
1. 备份旧数据库 `mv product_kb.db product_kb.db.bak`
2. 重新初始化并全量导入：从 PRICE 导入开始走一遍流程

## 6. FAQ

### Q: 原始文档需要复制到项目目录吗？

A: 不需要，只保存索引和抽取文本，原始文档保留在原路径。如果原始路径变更，修改 `config.yaml` 里的 `doc_root` 即可。

### Q: 支持增量更新价格表和文档吗？

A: 支持，价格表重新导入会增量更新，文档扫描只处理变更文件，索引构建默认增量。

### Q: 支持多个版本价格表并存吗？

A: 当前版本不支持，每次导入覆盖旧数据。如果需要版本管理，可以备份数据库。

### Q: 扫描一个文件要多久？

A: 普通文档几秒，大文档/扫描版 PDF（OCR）几十秒到几分钟，看文档大小。

### Q: 总构建时间要多久？

A: 1158 个文档，预估 30-60 分钟（取决于 OCR 使用率）。


## 6. 通过 WebChat/企业微信调用

### 6.1 直接对话（推荐，零配置）

在对话中直接提问，例如：
> "帮我查询产品：鸿蒙NEXT安全键盘"
> "帮我匹配这个产品：APP双平台安全测试"
> "列出安全服务产品线所有正常销售产品"

Jerry 会直接执行查询并返回结果。

### 6.2 Skill 封装调用（标准化调用，推荐高频查询）

已经封装为 `bangcle-product-kb` skill，调用格式：
```
产品知识库 查询 "合规评估"
产品知识库 匹配 "APP双平台安全测试"
产品知识库 列表 产品线 "安全服务"
```

### 6.3 API 调用（第三方系统接入）

启动服务（端口 8812）：
```bash
uvicorn product_kb.api:app --port 8812
```

查询接口：
```
GET http://localhost:8812/search?query=关键词
```
返回 JSON 格式结果。


