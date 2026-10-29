# DESIGN-DETAIL — BDMS 人工数据校准与填写 v1.0

> 状态：**待 Rex 审核** | 作者：Jerry 🦞 | 日期：2026-10-28
> 依据：`PRD-MANUAL-CALIBRATION-v1.0.md`、`DESIGN-OUTLINE-MANUAL-CALIBRATION-v1.0.md`（均通过）
> 范围：交付月报（delivery_report）域
> 本文确定：数据模型 DDL、API 契约、服务方法签名、关键技术方案。通过后才进入 VERIFICATION。

---

## 1. 数据模型

### 1.1 新增表 DDL：`dr_calibration`

注册方式：在 `core/schemas_v21.py` 新增常量 `DR_CALIBRATION_SCHEMA`，
并在 `core/db.py::init_db()` 的 executescript 序列中追加（与 `DR_EXT_SCHEMA` 同级），
保证旧库启动时幂等建表。

```sql
-- 人工校准覆盖层（原始 dr_sheet_row 永不修改）
CREATE TABLE IF NOT EXISTS dr_calibration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    column_name TEXT NOT NULL,

    original_value TEXT,              -- 提交时 dr_sheet_row 原值快照
    corrected_value TEXT NOT NULL,    -- 当前生效校准值
    previous_value TEXT,             -- 上一条校准值（修改留痕），首次为空

    reason TEXT NOT NULL,             -- 校准原因（必填）
    operator TEXT NOT NULL,           -- 操作人
    status TEXT NOT NULL DEFAULT 'active',  -- active / revoked

    issue_id INTEGER,                 -- 关联触发的 dr_import_validation.id（可空）
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT                  -- 撤销时间
);

CREATE INDEX IF NOT EXISTS idx_dr_cal_month ON dr_calibration(month, status);
CREATE INDEX IF NOT EXISTS idx_dr_cal_lookup ON dr_calibration(month, sheet, row_index);

-- 同一单元格同时至多一条 active；revoked 历史行可留存多行。
-- 用部分唯一索引（SQLite >= 3.8，当前环境满足），不加表级 UNIQUE 约束。
CREATE UNIQUE INDEX IF NOT EXISTS uq_dr_cal_active
    ON dr_calibration(month, sheet, row_index, column_name)
    WHERE status = 'active';
```

**为什么不用表级 UNIQUE**：`revoked` 历史行也要保留，同一单元格会有多条记录；
部分唯一索引只约束 `status='active'`，撤销后该单元格可再次校准，旧记录仍可审计。

### 1.2 归档表：`dr_calibration_history`（撤销/修改留痕）

```sql
CREATE TABLE IF NOT EXISTS dr_calibration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,             -- 被替换/撤销的那个校准值
    reason TEXT,
    operator TEXT,
    change_type TEXT NOT NULL,        -- revise / revoke
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_dr_cal_hist ON dr_calibration_history(month, sheet, row_index);
```

### 1.3 现有表的关系与改动

| 表 | 改动 |
|---|---|
| `dr_sheet_row` | **零改动、只读**。无任何 UPDATE/DELETE 路径指向它（除月报重新生成的既有逻辑）。 |
| `dr_sheet_meta` | 只读；提供列顺序、行数。 |
| `dr_import_validation` | 校准时同步回填 `corrected_value`；`status` 由重校验驱动；`operator/resolved_at` 在 confirmed 时写入。不新增列。 |
| `dr_review_status` | 每次重校验后重算 `total_errors / total_warnings / pending_fixes` 与 `updated_at`。不新增列。 |

### 1.4 值的序列化约定

- 所有 value 列以 **TEXT** 存储；写入时 `str(value)`，读取后按列类型还原。
- 空值：原始为空存 `NULL` 或空串，校准补填后存实际值。
- 日期：统一 `YYYY-MM-DD` 文本；数值：十进制文本，不做千分位。
- JSON 不用于校准值本体（区别于 `dr_sheet_row.data`），保证可在 SQL 层比较与台账导出。

---

## 2. 校准解析层（唯一口径）

### 2.1 模块与函数签名

新文件：`src/bdms/modules/delivery_report/calibration.py`

```python
class CalibrationService:
    def __init__(self, db_path: Optional[Path] = None): ...

    # ---- 读取 / 解析 ----
    def get_active_map(self, month: str) -> dict[tuple, dict]:
        """返回 {(sheet,row_index,column_name): {corrected_value,operator,reason,updated_at}}"""

    def apply_overlays(self, month: str,
                       raw_sheets: dict[str, pd.DataFrame]
                       ) -> dict[str, pd.DataFrame]:
        """把 active 校准覆盖到 raw DataFrame，返回 effective（不修改入参，返回副本）。"""

    # ---- 写入 ----
    def upsert(self, month: str, sheet: str, row_index: int,
               column_name: str, corrected_value: str, reason: str,
               operator: str, issue_id: int | None = None) -> dict:
        """新增/修改校准；修改时旧 corrected_value 入 history(change_type='revise')。"""

    def revoke(self, month: str, sheet: str, row_index: int,
               column_name: str, operator: str) -> dict:
        """撤销：当前行置 revoked 并写 history(change_type='revoke')。"""

    # ---- 查询 / 台账 ----
    def list_calibrations(self, month: str, sheet: str | None = None,
                          row_index: int | None = None,
                          status: str | None = None) -> dict: ...
    def overview(self, month: str) -> dict: ...
    def ledger_rows(self, month: str) -> list[dict]:
        """校准台账行（供导出 Sheet）。"""
```

### 2.2 apply_overlays 算法

```
1. active_map = get_active_map(month)
2. for each sheet, df in raw_sheets:
     eff = df.copy()
     for (s, r, col), cal in active_map:
         if s != sheet: continue
         if col not in eff.columns: 记录告警并跳过（列可能在重生成后消失）
         if 0 <= r < len(eff):
             eff.iat[r, column_index] = _coerce(eff[col].dtype, cal.corrected_value)
3. 返回 eff 集合
```
- 输入 raw 不被修改（copy），保证审计可同时拿到原值。
- 定位不到（行/列缺失）：写入一条告警到返回的 meta，不抛异常中断整体。

### 2.3 类型 / 枚举校验（保存前置）

`_validate_value(sheet, column_name, value)`：
- 从 `dr_sheet_meta.columns` 推断类型：列名含"日期/时间" → date（正则 + strptime）；
  推断数值列 → numeric；其余 text。
- 枚举：允许集合从 `md_reference`（`data_type='legend_config'`）的指定列动态读取。
  **枚举映射经真实数据校准后仅启用一个安全列**（见 §2.3.1）：
  `异常项目.状态` ← legend「状态」（8 值，202606 真实 17177 行 100% 命中）。
- 枚举列非法 → 抛 `CalibrationError(code='INVALID_VALUE')`；类型非法 → `code='INVALID_TYPE'`；API 均映射 400。
- 非枚举的 text 列：允许集合为空集 → 仅类型（文本）校验、不阻断（与 validator 空集降级同口径）。

#### 2.3.1 枚举列映射（v1.0，唯一启用项）

| 业务 Sheet.列 | legend 来源列 | 合法值 | 真实数据命中 |
|---|---|---|---|
| `异常项目.状态` | `状态` | 义务已拆分 / 交付邮件交接中 / 交付邮件已归档 / 实施未开始 / 实施进行中 / 实施已完成 / 验收文件交接中 / 验收文件已归档 | 100% |

**废弃的错误配置**：原 `validator.ENUM_COLS` 中的 `签约.履约状态` —— 真实「签约」表无此列（83 列中不存在），予以删除，不进入映射。
其余列（如 `异常项目.项目验收状态`）经比对词表不匹配（命中仅 21.6%），本期不启用枚举，避免误报。

> 新增枚举列必须先用真实数据做命中率分析（建议 ≥99% 且无业务越界值），追加到本表并评审后才启用。

---

## 3. 重校验闭环

### 3.1 增量重校验

新编排方法（在 `DeliveryReportService`）：

```python
def recalculate_after_calibration(self, month: str,
                                  affected: list[tuple]) -> dict:
    """
    affected: [(sheet, row_index), ...] 本次校准涉及位置
    返回 {status, resolved_issues, remaining_pending, review_status}
    小批量（受影响行数 <= SYNC_LIMIT）同步执行；否则创建 job 异步执行。
    """
```

流程：
```
1. raw = engine.load_raw(month)            # 不经校准的原始数据
2. eff = CalibrationService.apply_overlays(month, raw)
3. result = validator.collect_suspicious_from_df(month, eff, only_sheets=set(...))
4. 对受影响 (sheet,row_index) 的既有 issue：
     - 同位置在新 result 中已无违例 → UPDATE status='confirmed',
       operator, resolved_at=now
     - 仍违例 → 保持 pending，刷新 message/original_value
5. 重算 dr_review_status（total_errors/warnings/pending_fixes）
6. 返回摘要
```

### 3.2 validator 复用改造

- 抽出 `collect_suspicious_from_df(month, sheets_data, only_sheets=None)`，
  现有 `collect_suspicious(month)` 改为"load 数据后调用它"，保持规则单份实现。
- 规则（非空/类型/去重/行数偏差）逻辑不变；**新接入 `validate_enum`**：
  对启用映射的枚举列（v1.0：`异常项目.状态`）执行 R10 枚举检查，
  允许集合由 `_load_enum_options(sheet, column)` 从 `md_reference` legend 动态读取。
- 入参为 effective 数据集 → 校准值自然参与规则判定（含枚举）。

### 3.3 异步与进度

- 常量 `SYNC_LIMIT = 200`（受影响行数）；超出走 job：
  `create_job(module='calibration', month)` → 后台线程执行，
  前端按 `generate-progress/{job_id}` 同模式轮询。
- 进度分步：应用覆盖层 → 重校验(按 Sheet) → 流转问题 → 重算 KPI；
  遵守 >10s 必须进度条的铁律。

---

## 4. Web API 契约

路由加在 `web/api.py`，prefix `/api/report`。请求体用 Pydantic。

### 4.1 提交 / 修改校准
`POST /api/report/calibrations/{month}`

```json
// request
{
  "sheet": "签约",
  "row_index": 12,
  "column_name": "签约日期",
  "corrected_value": "2026-06-03",
  "reason": "源表日期格式错误，按合同实际签署日修正",
  "operator": "gateway-owner",
  "issue_id": 1001
}
```
```json
// 200 response（小批量，同步重校验）
{
  "ok": true,
  "calibration": {"id": 88, "status": "active"},
  "recalculation": {
    "resolved_issues": 1,
    "remaining_pending": 25055,
    "review_status": {"total_errors": 0, "pending_fixes": 25055}
  }
}
```
- 大批量触发时返回 `{"ok": true, "job_id": 42}`，前端转轮询。
- 400：类型/枚举非法、原因空、月报已 approved（需先驳回）。

### 4.2 撤销校准
`POST /api/report/calibrations/{month}/revoke`
```json
// request
{"sheet":"签约","row_index":12,"column_name":"签约日期","operator":"gateway-owner"}
```
```json
// 200
{"ok":true,"status":"revoked","recalculation":{ "...": "..." }}
```

### 4.3 查询校准记录
`GET /api/report/calibrations/{month}?sheet=&row_index=&status=`
```json
{
  "month": "202610",
  "total": 1,
  "items": [
    {"id":88,"sheet":"签约","row_index":12,"column_name":"签约日期",
     "original_value":"2026/6/3","corrected_value":"2026-06-03",
     "previous_value":null,"reason":"...","operator":"gateway-owner",
     "status":"active","created_at":"...","updated_at":"..."}
  ]
}
```

### 4.4 校准总览
`GET /api/report/calibrations/{month}/overview`
```json
{
  "month":"202610",
  "active_calibrations": 30,
  "revoked": 4,
  "pending_issues": 25026,
  "by_sheet": {"签约": 18, "异常项目": 12},
  "review_locked": false
}
```

### 4.5 动态 Sheet 列表
`GET /api/report/sheets/{month}`
```json
{
  "month":"202610",
  "sheets":[
    {"name":"签约","rows":17181},
    {"name":"POC&提前实施","rows":5174},
    "...":"共 15 项"
  ]
}
```
> 前端"数据浏览"硬编码 5 项下拉改为调用本接口。

### 4.6 枚举选项（校准对话框下拉数据源）
`GET /api/report/enum-options/{month}/{sheet}/{column}`
```json
// 200（枚举列）
{"sheet":"异常项目","column":"状态","options":["义务已拆分","交付邮件交接中","交付邮件已归档","实施未开始","实施进行中","实施已完成","验收文件交接中","验收文件已归档"]}
// 200（非枚举列）
{"sheet":"签约","column":"合同编号","options":[]}
```
- 枚举选项由 `md_reference` legend（`data_type='legend_config'`）对应列动态读取，按 sort_order 排序；
  非枚举列返回空数组，前端据此渲染 `<input>` 而非 `<select>`（见 §5.1）。

### 4.7 校准台账（预览/JSON）
`GET /api/report/calibration-ledger/{month}`
```json
{
  "month":"202610",
  "columns":["月份","Sheet","行号","列名","原始值","校准值","操作人","校准时间","校准原因","状态"],
  "rows":[ ["202610","签约",12,"签约日期","2026/6/3","2026-06-03","gateway-owner","...","...","active"] ]
}
```

### 4.8 导出（既有端点增强，不新增路径）
`GET /api/report/export/{month}`
- 各 Sheet 数据来自 **effective**；已校准单元格加批注（openpyxl Comment：`原值→新值 / 人 / 时间`）。
- 末尾追加「**校准台账**」Sheet（= `ledger_rows`）。
- 当无任何 active 校准时，台账 Sheet 仍可输出表头+0 行（或省略；取**省略**，避免空 Sheet）。

### 4.9 错误响应统一
```json
{"detail": {"code": "INVALID_TYPE"|"LOCKED"|"EMPTY_REASON"|"NOT_FOUND", "message": "..."}}
```

---

## 5. 前端契约

### 5.1 校准对话框（问题清单 + 数据浏览共用）
字段：
- 只读：月份 / Sheet / 行号 / 列名 / 规则说明 / **原始值**；
- 输入：校准值（日期列→`<input type=date>`；数值→`type=number>`；枚举列→`<select>`；文本→`<input>`）。
  v1.0 仅 `异常项目.状态` 为枚举列，选项来自 §2.3.1 的 8 个合法值，通过新接口 `GET /api/report/enum-options/{month}/{sheet}/{column}` 动态加载；
- 必填：原因（常用原因下拉 + 自定义）；
- 按钮：保存 / 取消；保存成功 toast 并刷新问题列表与 KPI。

### 5.2 数据浏览
- Sheet 下拉：来自 §4.5，动态渲染 15 项。
- 「进入编辑」切换：单元格可点 → 打开同一对话框；已校准单元格显示标记（角标/底色），
  悬停显示校准摘要，提供「记录 / 撤销」。

### 5.3 状态与进度
- 同步保存：局部刷新受影响行 + KPI。
- 返回 job_id：显示分步进度条与当前步骤，完成后刷新。

---

## 6. 旧路径收敛（精确到行）

当前破坏性链路（已 grep 确认仅 3 处）：
- `service.py:775` `apply_fixes()` → 调 `apply_manual_fixes`
- `service.py:756` 内部调用 `validator.apply_manual_fixes`
- `validator.py:191` 定义 `apply_manual_fixes`（直接 UPDATE dr_sheet_row）

动作：
1. 确认无 Web 路由/CLI 子命令外部调用 `apply_fixes`（开发期再次 grep 全仓）。
2. 删除/废弃 `apply_manual_fixes`；`service.apply_fixes` 若需保留语义，
   改为循环调用 `CalibrationService.upsert`（覆盖层）。
3. 新增回归测试断言：校准任意次数后 `dr_sheet_row` 对应行 data 与生成后完全一致。

---

## 7. 事务与一致性

- 单次 upsert + history + 回填 corrected_value 在**一个事务**内提交。
- 重校验对 issue 与 review_status 的批量更新在一个事务内提交，失败回滚，不留半态。
- 并发：本地单用户；DB 写入用短事务，避免长锁。异步 job 与同步保存不重叠
  （同一 month 的校准 job 进行中，新提交返回 409 `CALIBRATION_BUSY`，前端提示稍后重试）。

---

## 8. 月报重新生成与既有校准的关系

- 重新生成（regenerate）会重写 `dr_sheet_row`，row_index 可能变化。
- 策略：发起 regenerate 时，检测该月存在 active 校准 →
  **二次确认**："重新生成将使 N 条现有校准失效"；确认后将 active 校准批量置 revoked
  （写 history, change_type='revoke'，reason='regenerate_invalidate'）。
- 重新生成后基于新数据重新校验，从干净校准态开始。

---

## 9. 验收映射（对齐 PRD AC）

| AC | 本文落点 |
|---|---|
| AC-01/04 校准/补填保存 | §4.1、§5.1 |
| AC-02 原值不变 | §1.3、§6 测试锁定、§7 事务 |
| AC-03 自动重校验 | §3、§4.1 recalculation |
| AC-05 留痕完整 | §1.1/1.2、§4.3 |
| AC-06/07 撤销/修改 | §2.1 upsert/revoke、§4.2、§1.2 history |
| AC-08 导出+台账 | §4.8、§4.7 |
| AC-09 15 Sheet 动态 | §4.5、§5.2 |
| AC-10 非法值拒绝 | §2.3/§2.3.1、§3.2、§4.9 |

---

## 变更记录

- v1.0 → v1.0.1（2026-10-29）：枚举强校验订正——废弃不存在的 `签约.履约状态` 配置，
  改为真实数据验证过的 `异常项目.状态`（legend「状态」8 值 100% 命中）；
  新增 §2.3.1 映射表、§4.6 enum-options 端点；§3.2 接入 validate_enum；
  前端枚举 `<select>` 仅对映射列生效；VERIFICATION 同步更新。
- v1.0：初版（2026-10-28）。

- 2026-10-28 v1.0：Jerry 初稿。确定 `dr_calibration`(+history) 表、部分唯一索引、
  CalibrationService 签名、7+1 个 API 契约、增量重校验与 job 阈值、旧路径 3 处收敛、
  regenerate 失效策略。
