# DESIGN-DETAIL — Bangcle 合同管理专家 MVP（4 步分析闭环）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL |
| 版本 | v1.0（MVP） |
| 层级 | L4 专有业务层 |
| 组件编码 | bangcle-contract（CLM-BANGCLE-001 / CLI: contractctl） |
| 状态 | 待 Rex 审核 |
| 依据 | PRD-v1.0 §10（范围定稿 v1.2）+ OUTLINE-v1.0 §13 + L3 DESIGN-DETAIL v1.0 |

> 本 DETAIL 只冻结 **MVP 4 步分析闭环**（PRD §10.2）：合同获取 → 全文数字化+条款解析 → 风险扫描 → 产品知识库参照 → 审查报告。
> **不做**：OA 双向审批回写、多级状态机流转、docx 合同生成、Web UI（OUTLINE 保留接口，后续迭代）。

---

## 1. 范围与红线

### 1.1 MVP 必做

1. 合同文件获取（本地路径；本期不做 OA 在线拉取，保留 `--oa-billid` 接口位但不实现）
2. 数字化：PDF/docx/xlsx/pptx/txt/md/html/图片扫描件 → 全文文本
3. 条款解析：全文 → 结构化条款（L3 `parse_contract`）
4. 风险扫描：L3 `scan_text`（22 条受控规则，法条来自规则库）
5. 产品知识库参照：抽合同标的行项目 → product-kb `ContractMatcher` → 满足度三态 + 价格红线
6. 《合同智能审查报告》：Markdown + Excel（openpyxl），含免责声明

### 1.2 红线（不可违反）

- L4 不重算规则：风险/状态/法条一律调 L3，L4 不得增删改 22 条规则（rule_id 集合须 100% 匹配 L3 `CHECK_RULES`）。
- **合同原文不发公网模型**；本期不接语义 LLM 轨（`semantic_enabled=False` 写死，接口保留）。
- 单向依赖：L4→L3/L2，L3 禁 import L4。
- 审计 append-only；审查记录持久化（reviews / review_item / audit_log）。
- 真实文件测试：E2E 必须喂真实 PDF/docx/扫描件，禁止 mock 解析器后伪 pass。
- 无新强制第三方依赖：pdfplumber 0.11.10 / openpyxl 3.1.5 / tesseract 5.5.3 均已实测就位。

---

## 2. 目录结构

```
L4-proprietary/components/bangcle-contract/
├── contract_review/
│   ├── __init__.py
│   ├── models.py         # ReviewItem / LineItem / ReviewReport 数据类
│   ├── ingest.py         # 文件定位 + 格式探测
│   ├── digitize.py       # 分发 L2 parsers → 全文文本
│   ├── extract_items.py  # 🆕 从标的条款抽枚举行项目（L4 编排，补 L3 parser 弱项）
│   ├── parser.py         # 包 L3 parse_contract
│   ├── risk.py           # 包 L3 scan_text
│   ├── kb_match.py       # 包 product-kb ContractMatcher
│   ├── report.py         # 合并 → Markdown + Excel 渲染
│   └── pipeline.py       # ReviewService：串 5 阶段 + 持久化
├── config/settings.py    # DB 路径 / 产品库路径 / 阈值 / 免责文案
├── repository/db.py      # SQLite：reviews / review_item / audit_log（migration v1）
├── cli/contractctl.py    # init-db / review / report
├── tests/                # 单测 + E2E（真实样例文件）
└── docs/                 # PRD/OUTLINE/DETAIL/VERIFICATION/OPERATIONS
```

---

## 3. 阶段接口契约

### 3.1 ingest（获取）

```python
def load_source(path: str) -> LoadedFile
@dataclass
class LoadedFile:
    path: str
    fmt: str            # pdf|docx|xlsx|pptx|txt|md|html|png|jpg|jpeg|tif
    size: int
```
- 按扩展名探测；不支持格式抛 `UnsupportedFormat`（列已支持格式，不静默）。
- 文件不存在抛 `FileNotFound`。

### 3.2 digitize（数字化）

```python
def to_text(loaded: LoadedFile) -> DigitizedText
@dataclass
class DigitizedText:
    text: str
    parser_used: str
    parse_errors: list[str]
    quality: float          # L2 BaseParser.check_quality 口径
```
- 分发：`ai_kb.parsers.get_parser_for_format(fmt)`（已注册 text/md/html/csv/json + office 可用项 + ImageOcrParser）。
- PDF → PdfParser(pdfplumber)；docx → WordParser；图片 → ImageOcrParser(tesseract)。
- 无可用 parser（如 office 依赖缺失）→ 报明确阻塞，不降级伪造。
- 返回 `ParsedDocument.content`；空文本（<50 字符）在报告标 `digitize_low_quality` 警告但继续（扫描件可能短）。

### 3.3 parser（条款解析）

```python
def to_clauses(text: str) -> ParsedContract        # 直接 re-export L3 parse_contract
```
- 调 L3 `core.contract_parser.parse_contract(text)`；L4 不复制条款逻辑。

### 3.4 extract_items（行项目抽取，L4 新增）

> 背景：实测 L3 parser 的 `合同标的.key_terms` 对"1. … 2. …"枚举清单提取不全。L4 需独立的行项目抽取器喂给匹配器。

```python
def extract_line_items(text: str, parsed: ParsedContract) -> list[LineItem]
@dataclass
class LineItem:
    raw_name: str
    model: str | None
    price: float | None
    source_line: str
```
- 定位标的区：取 parsed 中 category in {合同标的, 数量与质量} 的条款 `original_text`；若空则用关键词窗口（服务内容/采购内容/产品清单/授权产品 后 ~40 行）。
- 枚举行：`^\s*[(（]?\d+[)）.、]\s*(.+)`；非枚举但含产品词的独立行也收。
- 名称清洗：去前导序号、数量词（套/个/年/授权）、尾部金额短句；截断 60 字符。
- 单价：同行 `单价[:：]?\s*([\d,]+(?:\.\d+)?)\s*[万元]?`；"万"换算（如 10万 → 100000）。
- 型号：`[Vv]\d+(?:\.\d+)+` 或 `型号[:：]\s*(\S+)`。
- 抽不到任何行项目 → 返回 `[]`，报告标 `no_line_items_extracted`（提示人工核对，不报错阻塞——纯服务合同可能无产品清单）。

### 3.5 risk（风险扫描）

```python
def scan(text: str) -> RiskReport        # L3 scan_text，取 .to_dict()
```
- 调 L3 `core.risk_engine.scan_text(text)`；输出 dict：`overall_risk / summary{pass,warning,fail} / findings[{id,category,item,status,risk,law}] / scan_time`。

### 3.6 kb_match（知识库参照）

```python
def match_items(items: list[LineItem]) -> list[ItemMatchResult]
```
- 构造 `ProductKBDB(db_path=config.PRODUCT_KB_PATH)`，`connect()`；`ContractMatcher(db, match_threshold=0.5)`。
- 对每个 LineItem 调 `matcher.match_item(raw_name, model, price)`；逐条转 `ItemMatchResult`。
- 满足度判定（per item）：

| 结论 | 条件 |
|---|---|
| `satisfied` | matched=True 且 score≥0.85 且无 alert 且 SKU `sale_status=启用` |
| `partial` | 0.5≤score<0.85，或有"低匹配度/需人工确认"alert |
| `unsatisfied` | matched=False，或 SKU 非启用（停售 hard-fail），或触发价格红线 alert |

- 关闭 db。

### 3.7 report（合并 + 渲染）

```python
def build_report(loaded, digitized, parsed, risk, matches) -> ReviewReport
def render_markdown(r: ReviewReport) -> str          # 写 .md
def render_excel(r: ReviewReport, out_path: str)     # openpyxl 写 .xlsx
```
- 汇总满足度：全 satisfied→`满足`；任一 unsatisfied→`不满足`；否则`部分满足`。
- Markdown 结构：标题 + **免责声明**（首屏）+ 一、审查元信息（文件/解析器/质量/时间）+ 二、风险汇总（overall + 计数表 + 22 条明细表，fail/high 置顶）+ 三、产品/服务参照（逐 item：输入名→匹配产品/SKU/score/合同单价 vs 标准单价/红线/满足度）+ 四、总体结论与建议。
- Excel：Sheet1 顶部摘要+免责；Sheet2 风险明细（high 红/medium 黄填色）；Sheet3 标的匹配（满足度绿/黄/红）。
- 免责固定文案：`本报告由 AI 基于受控规则库辅助生成，不构成法律意见，合同原文未外发，最终以法务审核为准。`

---

## 4. 数据模型与持久化（migration v1，增量幂等）

```sql
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id TEXT UNIQUE,              -- uuid
  file_path TEXT, file_format TEXT,
  parser_used TEXT, digitize_quality REAL,
  risk_overall TEXT, risk_pass INT, risk_warning INT, risk_fail INT,
  satisfaction TEXT,                  -- satisfied|partial|unsatisfied
  report_md_path TEXT, report_xlsx_path TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS review_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id TEXT, input_name TEXT, input_model TEXT, input_price REAL,
  matched INT, score REAL, matched_product TEXT, matched_sku TEXT,
  standard_price REAL, alert TEXT, satisfaction TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id TEXT, action TEXT, detail TEXT, created_at TEXT
);  -- append-only：Repository 只暴露 INSERT
```
- `repository/db.py`：建表幂等；`ReviewRepository.insert_review / insert_items / audit`；无 update/delete 接口。

---

## 5. 配置（config/settings.py）

| 键 | 默认 |
|---|---|
| `COMPONENT_DB` | 组件内 `data/bangcle_contract.db` |
| `PRODUCT_KB_PATH` | `L4-proprietary/components/product-kb/data/product_kb.db` |
| `MATCH_THRESHOLD` | 0.5；`SATISFIED_SCORE` | 0.85 |
| `SEMANTIC_ENABLED` | False（本期写死） |
| `DISCLAIMER` | §3.7 固定文案 |

---

## 6. CLI 契约（contractctl）

```bash
python3 cli/contractctl.py init-db
python3 cli/contractctl.py review --file <path> [--format md|xlsx|both] [--out-dir <dir>]
python3 cli/contractctl.py report <review_id>
```
- `review`：跑完整 pipeline → 持久化 → 打印 review_id + 风险/满足度摘要 + 报告路径。
- 非 0 退出码：文件/格式/DB 阻塞；匹配到风险不作为错误退出（审查本职就是发现风险）。

---

## 7. 测试与验收

### 7.1 测试
- 单测：`extract_line_items`（枚举/非枚举/万换算/无清单）、满足度判定三态、report 合并逻辑、repository 幂等与 append-only。
- E2E（真实文件，落 `tests/fixtures/`）：
  - 构造 docx（含枚举产品清单+单价）、文本版合同、tesseract 渲染的扫描图片（或现有 PDF）。
  - 跑 `review`：断言风险 rule_id 集合 == L3 CHECK_RULES id 集合；至少 1 个标的 satisfied、停售/红线场景 unsatisfied；报告文件生成且含免责。
- 回归：L3 42 unittest + L2 114 pytest 不被破坏（L4 只新增目录，不改下层）。

### 7.2 验收口径（对齐 PRD §10.3）
1. 真实销售合同（含扫描件）一条命令跑通 4 步；
2. 风险结构化（rule_id + 法条 + status）；
3. 产品/服务 ↔ product-kb 匹配出满足度三态 + 偏差/红线；
4. 报告含免责；原文不外发（本期无任何外发调用，静态可证）。

---

## 8. 遗留/后续（不在 MVP）
- OA 泛微在线拉取（requestid→docid→imagefileid）与企微回调/推送；
- 审批回写、多级状态机、docx 生成、Web UI、语义 LLM 轨（脱敏后）。

## 9. 变更历史
| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | MVP DETAIL 初稿（依赖契约全部实测对齐） |
