# DESIGN-DETAIL — 实时动态确认收入预估（Revenue Forecast）v1.0

| 项 | 值 |
|---|---|
| 所属系统 | BDMS（Bangcle 专属概念） |
| 模块 | revenue_forecast |
| 版本 | v1.0（极细双口径稿） |
| 作者 | Jerry |
| 日期 | 2026-11-08 |
| 前置 | PRD v1.0 / OUTLINE v1.0（通过）；双口径经 Rex 2026-11-08 19:44 确认 |
| 状态 | **待 Rex 终审** |

---

## 0. Bangcle 核心概念（一切设计的前提）

- 财报 = **预算执行表**，全称**收入预算执行表**；对应**签约项目**的收入预算（项目确认收入预算 + 实际发生额）。
- BDMS 用两个日期表达两种口径：

| 日期 | 口径 | 调整权 |
|---|---|---|
| **预估交付完成日期** | 项目确认收入预算（**动态预估**） | 项目经理按交付进度**全权动态调整** |
| **预算-预估交付完成日期** | **已提交公司/财务**的项目确认收入预算（**锁定**） | 一经提交，**本年度锁定**，不可随意调 |

- 该概念仅适用 Bangcle（含 BDMS），不外推。
- v1.0 基于**已提供的上一账期财报（202609）**计算；Part B（ONES 实时）只预留位置。

---

## 1. 财报结构与权威恒等式（全部实测零误差）

文件：`2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx`，3 个业务 Sheet。

### 1.1 预算执行表（财报本体，10,472 个有预算履约项）

| 列 | 标题 | 角色 |
|---|---|---|
| col0 | 分类 | **新签 / 递延** |
| col4 | 履约ID（预算） | 带 `YS` 后缀的预算键 |
| col6 | 履约ID | 现行键（= 底稿 col7） |
| col7 | 收入确认方法 | 时点法 / 时段法 |
| col8 | 单项履约义务金额 | 总额（合计 2.73 亿） |
| col9 | 截止20251231已确收 | 已确收（0.36 亿） |
| col10 | 2026年及以后计划确收 | **2.23 亿** |
| col12/13/14 | 计划开始/结束/完成时间 | 参考 |
| col15–26 | **202601…202612（逐月锁定预算）** | **锁定口径取数** |
| col27 | 2026年预计 | **= Σcol15–26（1.38 亿）** |
| col28 | 202601-09预计 | 0.92 亿 |
| col29/30/31 | 1–9 月确收/提前/滞后 | 实际对照 |
| col32–40 | 202601…202609（预算执行=实际） | **实际发生取数（0.94 亿）** |

**恒等式（10,472 行逐行验证，0 不符）：**
```
col27「2026年预计」 = Σ(col15..col26)                         ……(E1)
col10「2026及以后」 = col27(2026=1.38) + col10−col27(2027+=0.84) ……(E2)
```

### 1.2 计划确收底稿（38,052 行，动态日期快照）

| 列 | 标题 | 角色 |
|---|---|---|
| col2 | 交付预计完成时间 | **动态口径分类主依据**（日期/文本混合） |
| col7 | 履约ID | 现行键 → join 预算执行表 col6 |
| col8 | 对应预算履约ID | 预算键（无预算时为文本"2026年无预算ID"） |
| col33 | 收入确认方法 | 时点/时段 |
| col34 | 履约不执行原因 | 辅助排除 |
| col40/41/42 | 计划履约 / 截止2025已确收 / **2026及以后计划确收** | 恒等式同 E1，**动态金额取 col42** |

**恒等式：col40 = col41 + col42（38,052 行零误差）。**

### 1.3 关联规则（无 unknown 的关键）

- 主关联：底稿 `col7` → 预算执行表 `col6`（现行键），命中 10,301；
- 兜底：底稿 `col8` → 预算执行表 `col4`（预算键），再命中 498；
- 未命中 27,253 行：col8 恒为"2026年无预算ID"，全部是 **ALREADY_DONE（YP 老合同）**，本不进任何预算口径，对金额零影响；
- 新签/递延一律取自预算执行表 col0，**计入项 100% 可归类，无 unknown**。

---

## 2. 两个口径的精确算法

### 2.1 锁定口径（Locked，已提交公司，本年不可调）

```
对预算执行表每行：
  locked_year_2026      = col27                 = Σ col15..26
  actual_2026_01_09     = Σ col32..40
  按 col0 拆 新签/递延；按 col15..26 拆月
```
实测：

| | 新签 | 递延 | 合计 |
|---|---|---|---|
| **锁定 2026** | 0.67 | 0.72 | **1.38** |
| 实际 1–9 月 | 0.44 | 0.51 | **0.94** |

逐月锁定（亿）：01 .116 / 02 .071 / 03 .110 / 04 .093 / 05 .087 / 06 .107 / 07 .126 / 08 .099 / 09 .114 / 10 .135 / 11 .101 / 12 .227。

### 2.2 动态口径（Dynamic，经理可调日期的最新快照）

底稿 col2 按下列**优先级**分类（互斥穷尽），金额取 **col42**：

| 优先级 | category | 判定 | 计入 | 归月 |
|---|---|---|---|---|
| 1 | DUE_2026 | col2 日期 year=2026 | ✅ col42 | 按 col2 月份 |
| 2 | FUTURE_YEAR | col2 日期 year≥2027 | ❌ | 跨年清单 |
| 3 | IN_PIPELINE | 文本含「已提交资料」 | ✅ col42 | pipeline 桶* |
| 4 | ALREADY_DONE | 文本含「100%确收」 | ❌ | — |
| 5 | EXCEPTION | 含「异常」 | ❌ | 风险清单 |
| 6 | TERMINATED | 含「终止」 | ❌ | 排除清单 |
| 7 | ADJUSTED | 含「调整」 | ❌ | — |
| 8 | NOT_STARTED | 含「未立项」「未预计」 | ❌ | 风险清单 |
| 9 | ZERO_AMOUNT | 含「金额为0」 | ❌ | 零额清单 |
| 兜底 | MISSING_DATE | 空/不可解析 | ❌ | 风险清单 |

\* IN_PIPELINE 为已提交资料、col2 无未来日期，动态口径归入 `pipeline` 桶；其**锁定月份**在锁定口径 col15–26 可见（3,742/3,767 有逐月值，如时段法每月等额），前端支持下钻对照，不伪造动态月份。

实测动态 2026（亿）：

| 子类 | 新签 | 递延 | 小计 |
|---|---|---|---|
| DUE_2026 | 0.592 | 0.277 | 0.869 |
| IN_PIPELINE | 0.259 | 0.583 | 0.841 |
| **合计** | **0.851** | **0.860** | **1.710** |

DUE_2026 逐月（亿）：01 .001 / 03 .010 / 04 .020 / 05 .030 / 06 .159 / 07 .102 / 08 .093 / 09 .101 / 10 .106 / 11 .054 / 12 .194。

### 2.3 口径差异

```
动态 1.71 − 锁定 1.38 = +0.33 亿
含义：经理把原排在 2027 及以后的部分项目，用"预估交付完成日期"提前到 2026。
```

---

## 3. 数据结构

```python
@dataclass(frozen=True)
class ObligationRow:
    obligation_id: str          # col7/col6
    budget_id: str              # col8/col4（无预算="2026年无预算ID"）
    contract_no: str; contract_name: str
    customer: str; end_user: str
    revenue_method: str         # col33/col7
    category_group: str         # 新签|递延 （join col0）
    # 锁定口径
    locked_year: float          # col27
    locked_monthly: tuple[float,...]  # col15..26 (12)
    actual_ytd: float           # Σ col32..40
    # 动态口径
    raw_due: str                # col2 原文
    due_date: str | None
    dyn_category: str           # §2.2 十类
    amount_future: float        # col42
    dyn_in_plan: bool
    dyn_counted: float

@dataclass(frozen=True)
class ForecastResult:
    period: str; forecast_year: int
    locked_total: float; locked_by_group: dict
    locked_monthly: dict
    actual_ytd_total: float
    dynamic_total: float; dynamic_by_group: dict
    dynamic_due_monthly: dict; dynamic_pipeline: float
    gap_dynamic_minus_locked: float
    line_count: int
```

引擎纯函数：不读文件/DB、不取系统时间、无随机；同输入连跑 3 次逐字段相等。

---

## 4. 持久化 DDL（SQLite）

```sql
CREATE TABLE IF NOT EXISTS forecast_period (
    period TEXT PRIMARY KEY, forecast_year INTEGER NOT NULL,
    source_file TEXT NOT NULL, is_current INTEGER NOT NULL DEFAULT 0,
    locked_total REAL NOT NULL, dynamic_total REAL NOT NULL,
    actual_ytd REAL NOT NULL, line_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL, obligation_id TEXT NOT NULL,
    budget_id TEXT, contract_no TEXT, contract_name TEXT, customer TEXT, end_user TEXT,
    category_group TEXT NOT NULL, revenue_method TEXT,
    locked_year REAL NOT NULL, actual_ytd REAL NOT NULL,
    raw_due TEXT, due_date TEXT, dyn_category TEXT NOT NULL,
    amount_future REAL NOT NULL, dyn_in_plan INTEGER NOT NULL, dyn_counted REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'report',          -- Part B: report|ones
    UNIQUE(period, obligation_id)
);
CREATE INDEX IF NOT EXISTS idx_fl_cat ON forecast_line(period, dyn_category);
CREATE TABLE IF NOT EXISTS forecast_monthly (
    period TEXT NOT NULL, basis TEXT NOT NULL,      -- locked|dynamic_due|pipeline
    month TEXT NOT NULL, category_group TEXT NOT NULL DEFAULT 'all',
    amount REAL NOT NULL,
    PRIMARY KEY(period, basis, month, category_group)
);
CREATE TABLE IF NOT EXISTS forecast_totals (
    period TEXT PRIMARY KEY, forecast_year INTEGER,
    locked_total REAL, locked_by_group_json TEXT,
    dynamic_total REAL, dynamic_by_group_json TEXT,
    dynamic_pipeline REAL, actual_ytd REAL, gap REAL
);
```

- 上传新账期：单事务内旧 `is_current=0` → 新=1（保留历史版本，默认读当前）。
- 同期重算：单事务 DELETE 该 period 三表后重插（仅版本内幂等重建）。

---

## 5. API 契约（`/api/forecast`，金额单位元）

| 方法/路径 | 响应要点 |
|---|---|
| `POST /upload` (multipart file, period?, year=2026) | `{job_id, period}`，异步 |
| `GET /progress/{job_id}` | `{status, step, pct, error}` |
| `GET /periods` | `{current, periods[]}` |
| `GET /overview?period=` | locked 1.38 / dynamic 1.71 / actual .94 / gap +.33 + 各自 by_group |
| `GET /monthly?period=&basis=locked\|dynamic` | 12 月 + pipeline |
| `GET /lines?period=&category=&in_plan=&page=&page_size=` | 分页明细 |
| `GET /provider-status` | `{part_b:{name:'ones',status:'not_configured'}}` |
| `GET /export?period=` | Excel 多 sheet |

错误复用全局异常处理；失败保留上版 current，不切换。

---

## 6. Part B 占位（仅契约）

```python
class ForecastProvider(ABC):
    @abstractmethod
    def get_status(self) -> ProviderStatus: ...        # ready|not_configured|error
    @abstractmethod
    def fetch(self, obligation_ids: list[str], year: int) -> dict: ...

class NotConfiguredProvider(ForecastProvider):
    name = "ones"
    def get_status(self): return ProviderStatus("ones","not_configured","待接入 ONES 动态数据")
    def fetch(self, obligation_ids, year): raise NotImplementedError
```

未来 Part B 提供**真正实时的动态口径**（替代 1.71 静态快照）。ONES 参数（team `RZxvwUZ8`；`_VKZye7iw`/`_CMCM3HGF`/`_4nzm7sk7` 等）归档 PRD §3.2，本版不建调用链、不引依赖。

---

## 7. 模块文件（落地清单）

```
modules/revenue_forecast/
  report_parser.py    两 Sheet → ObligationRow（含关联/恒等式校验）
  classifier.py       §2.2 十类（关键词/年份配置常量）
  engine.py           双口径纯计算
  repository.py       §4 DDL/事务/版本/查询
  service.py          上传 job + 进度 + 读模型
  exporter.py         BaseExporter 多 sheet
  providers/{base.py, null_provider.py}
```

---

## 8. 错误与边界

| 情况 | 行为 |
|---|---|
| 缺 Sheet / 格式错 | job error，保留上版 |
| E1/E2/col40 恒等式不符 | 记差异行入校验报告，不静默 |
| 日期不可解析 | MISSING_DATE 入风险清单 |
| Part B fetch 被调 | NotImplemented；恒显 not_configured |
| 凭据 | Part A 无；Part B 未来仅从 secrets 读 |

---

## 9. 黄金测试锚点（以 202609 财报为 fixture）

- 行数：预算执行表 10,472、底稿 38,052；
- 恒等式：col27=Σ15–26（0 不符）、col40=col41+col42（0 不符）；
- 锁定 2026 = **1.38**（新 .67/递 .72）；实际 1–9 = **.94**（新 .44/递 .51）；
- 动态 2026 = **1.71**（新 .851/递 .860）= DUE .869 + PIPE .841；
- col10 = 2.23；2027+ = .84；gap 动态−锁定 = **+.33**；
- 幂等：同财报解析 3 次，上述全部数字逐分相等；
- 覆盖率：classifier 十类分支全测，新增测试数 ≥ 分支数；API 用真实 HTTP；不破坏现有 367 passed。

---

## 10. 待 Rex 终审

1. 双口径定义与取数列（§2）；2. 十类分类与 pipeline 桶（§2.2）；3. 关联规则与零 unknown（§1.3）；
4. 四张表 DDL（§4）；5. API 契约（§5）；6. 黄金锚点（§9）。

**终审通过 → 测试方案 / OPERATIONS / IMPLEMENTATION-PLAN → 开工。**

---

## 11. 预算趋势分析计算列（202609 落地，对齐 202606 公式）

> 2026-11-09 Rex 指令：按 202606 报表计算逻辑，为 202609 生成 AW/BQ/BU/BV 计算列；AW/BV 按 202606 公式自动计算，BQ/BU 按履约ID匹配 + 日期判断，剩余留空人工。

### 11.1 202606 权威公式（实测确认）

202606「预算执行表」存在 5 个概念列（AV/AW/BQ/BU/BV），公式链如下：

| 202606 列 | 公式 | 作用 |
|---|---|---|
| `AV` | `=C{r}&"-"&BQ{r}` | 合同数量统计唯一值（**合同编号** + 预算填报） |
| `AW` | `=IF(COUNTIF(AV$3:AV{r-1},AV{r})>0,"","统计")` | 统计位（按 AV 去重，首现标"统计"） |
| `BQ` | `=VLOOKUP(J{r},[3]预算执行表!$J:$BQ,60,FALSE)` | 预算填报（外部工作簿按履约明细匹配） |
| `BU` | `=VLOOKUP(J{r},[3]预算执行表!$J:$BU,64,FALSE)` | 预算趋势（外部工作簿按履约明细匹配） |
| `BV` | `=VLOOKUP(BU{r},图例!L:M,2,FALSE)` | 预算趋势类别（BU → 图例映射） |

**图例 L:M 映射**（202606「图例」sheet，权威）：

| BU（预算趋势） | BV（预算趋势类别） |
|---|---|
| 已归档但未下单 | 异常中 |
| 已下单但无法交付 | 异常中 |
| 已交付但无法确收 | 异常中 |
| 之前年度已确收 | 异常中 |
| 本年度正常可确收 | 本年正常交付 |
| 未来可确收 | 未来交付 |
| 合同消失 | 合同消失 |

### 11.2 202609 列映射（按表头名对齐，禁止按字母硬套）

202609「预算执行表」原有 45 列（A–AS），新增 5 列（AT–AX）：

| 202609 列 | 对应 202606 | 表头 | 来源/公式 |
|---|---|---|---|
| `AT` (col46) | `AV` | 合同数量统计唯一值 | `=B{r}&"-"&AV{r}`（B=合同编号） |
| `AU` (col47) | `AW` | 统计位 | 按 AT 去重，首现标"统计" |
| `AV` (col48) | `BQ` | 预算填报 | 匹配 202606 → M/O 日期判断 → 留空 |
| `AW` (col49) | `BU` | 预算趋势 | 匹配 202606 → O 日期判断 → 留空 |
| `AX` (col50) | `BV` | 预算趋势类别 | BU → 图例映射（Python 直查，202609 无图例 sheet） |

**202609 输入列**（按表头名）：

| 列 | 表头 | 用途 |
|---|---|---|
| `B` | 合同编号 | AT 组成 |
| `E` | 履约ID（预算） | 匹配键（**末尾 `YS` 后缀需剥离**后匹配 202606 `J`） |
| `M` | 计划开始时间 | BQ 日期判断 |
| `O` | 计划完成时间 | BQ/BU 日期判断 |

### 11.3 Rex 规则（2026-11-09 指令，逐条落地）

| # | 规则 | 实现 |
|---|---|---|
| 1 | **AW 列**按 202606 计算公式自动生成 | `AT = B & "-" & AV(填报)`；`AU` 按 AT 去重首现标"统计"（对齐 `COUNTIF` 语义） |
| 2 | **BQ 列**下拉列表，按履约ID匹配 202606 自动带入；无法匹配的按「计划开始时间」/「计划完成时间」是否在本年度（2026）判断「本年度正常可确收」；剩余留空人工 | 匹配 8855 行；M/O 日期判断 881 行；留空 738 行 |
| 3 | **BV 列**按 202606 计算公式自动生成（依赖 BU 列） | Python 直查图例映射（不依赖 202609 图例 sheet） |
| 4 | **BU 列**下拉列表，按履约ID匹配 202606 自动带入；无法匹配的按「预估交付完成日期（周报）」是否在本年度判断；剩余留空人工 | 匹配 8855 行；O 日期判断 385 行；留空 1234 行；**202609 无「预估交付完成日期（周报）」列，用 `O`（计划完成时间）替代** |

### 11.4 202609 填充结果（实测）

| 列 | 分布 |
|---|---|
| `AT` 合同数量统计唯一值 | 2463 个唯一值（合同号×填报状态） |
| `AU` 统计位 | "统计" 2464 行 / 空 8009 行（**0 重复**） |
| `AV` 预算填报 | 本年度正常可确收 7204 / 未来可确收 2128 / 已下单但无法交付 379 / 已归档但未下单 13 / 已交付但无法确收 9 / 之前年度已确收 2 / 合同消失 1 / 空 736 |
| `AW` 预算趋势 | 本年度正常可确收 6728 / 未来可确收 2096 / 已下单但无法交付 386 / 已归档但未下单 13 / 合同消失 10 / 已交付但无法确收 7 / 空 1232 |
| `AX` 预算趋势类别 | 本年正常交付 6728 / 未来交付 2096 / 异常中 406 / 合同消失 10 / 空 1232 |

**口径差异说明（诚实标注）**：
- 202609 统计位 2464 行 ≠ 202606 的 2078 行，差异来自账期新增合同/状态组合，属正常账期差异；
- 202609 匹配率 84.6%（8855/10472），未匹配 1617 个履约ID 为 202609 新增（202606 不存在）；
- 202609 无「图例」sheet、「预估交付完成日期（周报）」列，已用 Python 映射与 `O` 列替代，**与 202606 公式语义一致但实现路径不同**。

### 11.5 预留接口：202606 完整自动化生产

> Rex 2026-11-09：「后续我们需要根据 202606 报表实现确收分析报表的完整自动化生产。」

**目标**：从 202606 报表（含 AV/AW/BQ/BU/BV 五列）自动生成下一账期的预算趋势分析，无需人工填表。

**预留设计**：

```python
# modules/revenue_forecast/trend_columns.py（预留，本版未实现）

BU_TO_BV = {  # 图例 L:M 权威映射，配置化
    "已归档但未下单": "异常中", "已下单但无法交付": "异常中",
    "已交付但无法确收": "异常中", "之前年度已确收": "异常中",
    "本年度正常可确收": "本年正常交付", "未来可确收": "未来交付",
    "合同消失": "合同消失",
}

@dataclass(frozen=True)
class TrendColumnConfig:
    period: str                      # 202609
    prev_period: str                  # 202606（匹配源）
    contract_col: str = "B"           # 合同编号
    budget_id_col: str = "E"          # 履约ID（预算，带 YS）
    plan_start_col: str = "M"         # 计划开始时间
    plan_done_col: str = "O"          # 计划完成时间
    year: int = 2026
    match_strip_suffix: str = "YS"    # 匹配时剥离后缀
    date_judge_col_bq: tuple = ("M", "O")   # BQ 日期判断列
    date_judge_col_bu: tuple = ("O",)        # BU 日期判断列（202609 用 O 替代「预估交付完成日期（周报）」）
    bu_to_bv: dict = BU_TO_BV
    # 202606 完整自动化时，date_judge_col_bu 应切换为「预估交付完成日期（周报）」列

def build_trend_columns(
    rows: list[dict],
    prev_mapping: dict[str, tuple[str, str]],  # 履约ID → (BQ, BU)，来自上一账期
    cfg: TrendColumnConfig,
) -> list[dict]:
    """生成 AT/AU/AV/AW/AX 五列。纯函数，无 I/O。"""
    ...

def extract_prev_mapping(prev_report_path: Path) -> dict[str, tuple[str, str]]:
    """从上一账期报表提取 履约ID → (BQ, BU) 映射。"""
    ...
```

**自动化生产流程（预留）**：

```
1. 读取上一账期报表（如 202606）→ 提取 履约ID → (BQ, BU) 映射
2. 读取当前账期报表（如 202609）→ 按 §11.3 规则生成五列
3. 人工补填留空行（BQ/BU 留空 → 人工执行）
4. 按 202606「预算趋势分析」sheet 公式（§11.6）生成分析表
5. 导出完整报表
```

### 11.6 预算趋势分析表公式（202606 权威，供自动化生产用）

202606「预算趋势分析」sheet（19 行 × 17 列）公式：

**递延合同**（R4–R9）：

| 行 | BQ 状态 | 期初金额列 | 累计金额列 |
|---|---|---|---|
| R4 | 已归档但未下单 | `O` | `O` |
| R5 | 已下单但无法交付 | `O` | `O` |
| R6 | 已交付但无法确收 | `O` | `O` |
| R7 | 本年度正常可确收 | `AG` | `AG` |
| R8 | 未来可确收 | `N`+(N7−AG7) | `N` |
| R9 | 之前年度已确收 | `AG` | `Q` |

**新签合同**（R12–R16）：

| 行 | BQ 状态 | 期初金额列 | 累计金额列 |
|---|---|---|---|
| R12 | 已归档但未下单 | `Q` | `Q` |
| R13 | 已下单但无法交付 | `Q` | `Q` |
| R14 | 已交付但无法确收 | `Q` | `Q` |
| R15 | 本年度正常可确收 | `AG` | `AG` |
| R16 | 未来可确收 | `Q`+(Q15−AG15) | `Q` |

**筛选条件**：`AW="统计"` + `A=递延/新签` + `BQ=状态` + `BV=交付分类`

**202609 列对应**（按表头名对齐）：

| 202606 列 | 202606 表头 | 202609 对应 | 202609 表头 | 等价计算 |
|---|---|---|---|---|
| `O` | 年初-未立项&项目异常未计划确收 | `L` | 年初-未立项&项目异常未计划确收 | 直接对应 |
| `AG` | 2026年预计 | `AB` | 2026年预计 | 直接对应 |
| `N` | 2026年及以后计划确收 | `K` | 2026年及以后计划确收 | 直接对应 |
| `Q` | 截止20251231未确收金额（调整） | **无独立列** | — | `I − J`（单项履约义务金额 − 截止20251231已确收金额） |

> **Q 列等价验证**（2026-11-09 实测）：202606 的 Q 列 = `L − M`（8985 行 0 不匹配），且 Q = P（0 差异）。
> 202609 无独立 Q 列，按 202606 逻辑用 `I − J` 计算等价值。
> **注意**：这是推算值，不是权威列；202609 源库 `budget_exec` 中无 `unrev_adj` 字段，需在计算时显式生成。

---

*Part B（ONES 实时动态）本版仅预留位置。*
