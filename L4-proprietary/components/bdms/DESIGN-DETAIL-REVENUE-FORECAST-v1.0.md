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

*Part B（ONES 实时动态）本版仅预留位置。*
