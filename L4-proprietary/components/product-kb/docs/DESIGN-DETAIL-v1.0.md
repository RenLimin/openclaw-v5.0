# Bangcle 产品/服务知识库 详细设计

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL |
| 版本 | v1.0 |
| 层级 | L4 Bangcle 专有业务模块 |
| 状态 | 设计待审 |
| 模块编码 | product-kb |
| 业务域 | 产品销售支撑 |

---

## 1. 数据模型设计

### 1.1 数据库表结构

#### `product_line` 产品线表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| name | TEXT NOT NULL | 产品线名称（如"安全保护产品线"） |
| code | TEXT UNIQUE NOT NULL | 编码（如`security_protect`） |
| description | TEXT | 描述 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `product_category` 分类表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| line_id | INTEGER NOT NULL FK | 产品线ID |
| name | TEXT NOT NULL | 分类名称 |
| parent_id | INTEGER FK | 父分类ID（支持多级分类，当前单级够用） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `product` 产品主档表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| line_id | INTEGER NOT NULL FK | 产品线ID |
| category_id | INTEGER FK | 分类ID |
| name | TEXT NOT NULL | 产品标准名称 |
| aliases | TEXT | 别名（JSON数组，用于匹配） |
| code | TEXT UNIQUE | 产品编码 |
| version_latest | TEXT | 最新版本号 |
| type | TEXT NOT NULL | 类型：product/service/hardware |
| status | TEXT NOT NULL | 销售状态：normal/controlled/reported/discontinued |
| summary | TEXT | 产品简介 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `sku` SKU 明细表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| product_id | INTEGER NOT NULL FK | 产品ID |
| sku_code | TEXT UNIQUE NOT NULL | SKU编码 |
| model | TEXT | 型号 |
| unit_price | REAL | 标准单价 |
| price_base | TEXT | 报价基准（如"/APP/年"） |
| discount_type | TEXT | 折扣类型 |
| sale_mode | TEXT | 销售模式 |
| sale_status | TEXT | 启用状态 |
| notes | TEXT | 注意事项 |
| service_desc | TEXT | 服务描述 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `doc_asset` 文档资产表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| product_id | INTEGER NOT NULL FK | 关联产品ID |
| doc_type | TEXT NOT NULL | 文档类型：white_paper/sales_note/func_list/ppt/tech_white_paper/manual/faq/other |
| original_path | TEXT NOT NULL | 原始文件绝对路径 |
| relative_path | TEXT | 相对根路径（方便根路径迁移） |
| file_name | TEXT NOT NULL | 文件名 |
| version | TEXT | 版本号提取 |
| format | TEXT NOT NULL | 文件格式：docx/xlsx/pptx/pdf |
| extracted_text | TEXT | 抽取全文（太长？存文件，这里存路径） |
| md5 | TEXT | 文件MD5，用于增量更新判断 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `doc_chunk` 文档切片表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| doc_id | INTEGER NOT NULL FK | 文档ID |
| chunk_index | INTEGER NOT NULL | 切片序号 |
| title | TEXT | 切片标题（章节标题） |
| text | TEXT NOT NULL | 切片文本 |
| embedding | BLOB | 向量二进制（sqlite 支持） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### `kb_relation` 知识图谱关系表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增ID |
| subject_type | TEXT NOT NULL | 主体实体类型 |
| subject_id | INTEGER NOT NULL | 主体实体ID |
| relation_type | TEXT NOT NULL | 关系类型 |
| object_type | TEXT NOT NULL | 客体实体类型 |
| object_id | INTEGER NOT NULL | 客体实体ID |
| metadata | TEXT | JSON 元数据 |

---

### 1.2 索引设计

| 表 | 索引字段 | 索引类型 |
|---|---|---|
| product | (line_id, status) | 复合索引 |
| product | name | FTS5 全文索引 |
| sku | product_id | 普通索引 |
| doc_asset | product_id | 普通索引 |
| doc_chunk | doc_id | 普通索引 |
| doc_chunk | text | FTS5 全文索引 |

### 1.3 向量检索

复用现有 L2 `memory_search` 的嵌入能力：
- 嵌入模型：与系统一致，`doubao-embedding-vision-251215` 或 `embeddinggemma-300m`
- 存储：向量直接存在 `doc_chunk.embedding` 列（SQLite BLOB）
- 检索：余弦相似度计算在 Python 层做，Top-k 召回后与 FTS 结果混合排序

---

## 2. 核心流程设计

### 2.1 价格表导入流程

```
1. 读取 Excel
2. 按行处理：
   a. 产品线去重 → 插入 product_line
   b. 分类去重 → 插入 product_category
   c. 产品去重（按名称+版本）→ 插入/更新 product
   d. SKU 插入/更新 sku 表
   e. 建立关系：产品线 → 分类 → 产品 → SKU
3. 提交事务
4. 输出导入统计
```

### 2.2 文档扫描与关联流程

```
1. 递归扫描根目录，收集所有支持格式的文件
2. 提取文件名中的产品/版本关键词
3. 产品匹配：
   a. 精确匹配产品名 → 关联
   b. 模糊匹配 → 候选列表，置信度 > 0.8 自动关联，否则进人工审核队列
4. 提取版本号 → 写入 doc_asset.version
5. 输出扫描统计 + 待审核列表
```

### 2.3 文档抽取与切片流程

```
1. 按文档类型解析：
   - docx: python-docx 提取文本 + 标题层级
   - xlsx: openpyxl 逐行逐单元格提取，保留表格结构
   - pptx: python-pptx 逐页提取
   - pdf: PyPDF2 文本提取，文本为空则调用 L2 OCR 兜底
2. 切片策略：
   - 按标题切分，切片大小控制在 300-1000 字
   - 功能清单 xlsx：按行/模块切片
   - PPT：每页一片
3. 每个切片生成嵌入向量，存入 doc_chunk
4. 构建 FTS 全文索引
```

### 2.4 合同标的匹配流程

```
1. 输入：CSV 格式标的列表（产品名 + 型号 + 数量 + 单价）
2. 对每个标的：
   a. 提取关键词 + 版本号
   b. FTS 全文检索 → Top 20 候选 SKU
   c. 相似度排序：编辑距离 + 语义相似度 + 版本匹配加权
   d. 输出最佳匹配 + 比对结果
3. 生成比对报告，标记异常（低于折扣红线/未匹配/价格偏差过大）
4. 可选输出 Excel
```

### 2.5 问答检索流程

```
1. 输入：自然语言问题
2. 问题向量化
3. 混合召回：
   a. 向量检索 → Top 20 切片
   b. 关键词检索 → Top 20 切片
   c. 去重合并 → Top 30
4. 重排序：按相似度 + 产品最新版本 + 文档类型权重排序
5. 返回 Top 5 结果，附带产品信息 + 文档信息 + 切片文本
```

---

## 3. 匹配算法设计

### 3.1 产品匹配得分公式

```
score = w1 * name_similarity + w2 * version_match + w3 * category_match
w1=0.6, w2=0.3, w3=0.1
```

- `name_similarity`: 编辑距离归一化（0-1）+ 语义相似度（0-1）平均
- `version_match`: 精确匹配得 1，兼容匹配得 0.5，不匹配得 0
- `category_match`: 分类相同得 1，不同得 0

### 3.2 异常判断规则

| 异常类型 | 判断规则 | 预警级别 |
|---|---|---|
| 未匹配 | 最佳匹配得分 < 阈值（0.5） | 🔴 高 |
| 价格偏差 | | |
|  - 低于折扣红线 | (合同单价 / 标准单价) < 折扣红线比例 | 🔴 高 |
|  - 偏差过大 | abs(合同单价 - 标准单价) / 标准单价 > 0.2 | 🟡 中 |
| SKU 停用 | 产品/SKU 状态不是正常销售 | 🟡 中 |

---

## 4. 技术方案选型对比

| 方案 | 优势 | 劣势 | 选型结论 |
|---|---|---|---|
| 纯 SQLite + FTS5 + 向量 Python 计算 | 零新增依赖，纯 Python，部署简单，单文件方便迁移 | 大数据量下检索慢（千级文档没问题） | ✅ 选中 |
| Elasticsearch + 向量插件 | 检索快，功能强大 | 新增重型依赖，运维复杂，资源占用大 | ❌ 放弃 |
| PostgreSQL + pgvector | 检索性能好 | 需要安装 PostgreSQL，超出轻量需求 | ❌ 放弃 |
| Neo4j 知识图谱 | 原生图存储，推理方便 | 新增依赖，当前数据量小，遍历足够 | ❌ 放弃 |

结论：当前数据量（千级文档，万级切片）纯 SQLite 足够满足性能需求，遵循最小依赖原则，选中纯 Python + SQLite 方案。

---

## 5. 文件目录结构

```
L4-proprietary/components/product-kb/
├── docs/
│   ├── PRD-v1.0.md
│   ├── DESIGN-OUTLINE-v1.0.md
│   ├── DESIGN-DETAIL-v1.0.md
│   ├── VERIFICATION-v1.0.md
│   └── OPERATIONS-v1.0.md
├── product_kb/
│   ├── __init__.py
│   ├── io.py              # 导入/扫描/抽取
│   ├── db.py              # 数据库操作
│   ├── index.py           # 索引构建
│   ├── search.py          # 混合检索
│   ├── graph.py           # 知识图谱推理
│   ├── contract.py        # 合同比对
│   ├── qa.py              # 问答
│   ├── compare.py         # 产品对比
│   └── cli.py             # CLI 入口
├── scripts/
│   ├── import_price.py
│   ├── scan_docs.py
│   └── build_index.py
├── tests/
│   ├── test_*.py
│   └── data/
├── README.md
└── requirements.txt
```

---

## 6. 增量更新设计

- 价格表重新导入：自动检测变更（新增/修改/停用），增量更新，不用重建索引
- 文档重新扫描：用 MD5 检测文件变更，仅重新抽取变更文件
- 版本策略：保留旧版本文档，标记最新版

