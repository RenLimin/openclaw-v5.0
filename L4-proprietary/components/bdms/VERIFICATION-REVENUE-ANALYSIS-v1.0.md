# VERIFICATION — 确收分析报告（Revenue Analysis）v1.0

| 项 | 值 |
|---|---|
| 所属 | BDMS / 模块 revenue_analysis |
| 版本 | v1.0 |
| 前置 | OUTLINE / DETAIL v1.0 |
| 日期 | 2026-11-10 |

---

## 1. 测试策略

### 1.1 分层

| 层 | 范围 | 工具 |
|---|---|---|
| 单元 | importer / validator / caliber_builder / trend_builder / exporter 纯函数 | pytest |
| 服务 | service 三模式幂等 + 快照兜底 + fail-closed | pytest + 临时 sqlite |
| CLI | import/generate/export/summary/caliber/trend 全链路 | 真实 CLI 调用 |
| 回归 | forecast + revenue_analysis 相关模块不破坏 | pytest 全量（相关套件） |

### 1.2 铁律

- 金额断言一律 `pytest.approx(abs=0.01)`（分），不用裸 `==`；
- 黄金锚点逐分锁定（见 §5），引擎纯函数连跑幂等；
- 临时 DB（`tmp_path`），不污染 canonical `data/bdms.db`；
- 金额红线：202609 J/K/L 全 0，trend 金额列必须 `None`，禁止硬摊；
- 测试用真实财报文件，不用 mock 数字冒充锚点。

---

## 2. 单元测试覆盖

### 2.1 importer / validator（P1）

- 预算执行表 10,473 行、底稿 38,052 行落盘；
- 校验 0 errors / 82 warnings（全部 `AMOUNT_NEGATIVE`）；
- `DB_PATH` 修复后重跑稳定（历史 bug：默认路径误用未 re-export 的 `DATA_DIR`）。

### 2.2 caliber_builder（P3）

- 锁定：新签 66,520,133.5 / 递延 71,900,003.28 / 合计 138,420,136.78；
- 动态：DUE 86,936,513.95 / PIPE 84,112,097.86 / 合计 171,048,611.81；
- by_group（新签/递延）：85,065,322.34 / 85,983,289.47；
- `normalize_due`：字符串 ISO 日期归一化后，34,285 行标签分歧归零；
- `_group_of`：H 现行键优先 + I 预算键兜底；月份键 `YYYYMM`。

### 2.3 trend_builder（P3）

- 19 行 row_index 映射 + R19 特殊单元格；
- 递延：init 1465 / normal 1264 / exception 89 / disappear 4 / future 108；
- 新签：init 998 / normal 594 / exception 288 / disappear 0 / future 116；
- 合计 R18：init 2463 / normal 1858 / exception 377 / disappear 4 / future 224；
- R19 新签预计确收率 0.5951903807615231；
- audit：disappear_routed=1，unfilled=123，unmatched_disappear=[]。

### 2.4 exporter（P4）

- 10 Sheet 全齐；
- 预算执行表 10,474 行（含表头）、底稿 38,053、重拆履约 276；
- 中文表头映射（BUDGET_COLUMNS / DRAFT_COLUMNS）；
- persist 宽表 columns 不被清空（修复 `fields=[]` bug）。

### 2.5 service（P5）

- 三模式：auto（有数据 read/无数据 generated）、read、regenerate；
- `_ensure_snapshots`：仅宽表无快照时自动补 compute+persist；
- summary/caliber/trend 无数据 fail-closed（ValueError）；
- dynamic by_group 扩展键 DUE/PIPE/OTHER/MISSING 落 ra_caliber。

---

## 3. CLI 链路（真实调用，2026-11-10）

| 命令 | 结果 |
|---|---|
| `revenue-analysis summary 202609` | 双口径 + 逐月 JSON，锚点一致 |
| `revenue-analysis caliber 202609` | DUE 86,936,513.95 / PIPE 84,112,097.86 / diff 32,628,475.03 |
| `revenue-analysis trend 202609` | R4–R19 15 条快照 |
| `revenue-analysis generate 202609 --mode read` | read，共 59,357 行，10 Sheet 计数正确 |
| `revenue-analysis export 202609` | 成功导出 xlsx |

---

## 4. 实际测试结果

| 套件 | 用例数 | 结果 |
|---|---|---|
| test_revenue_analysis_p3.py | 13 | passed |
| test_revenue_analysis_service.py | 7 | passed |
| **RA 合计** | **20** | **全绿** |

### 4.1 相关模块回归（2026-11-10 主会话复跑）

套件：p3 + service + revenue_validator + forecast_core + forecast_repository + forecast_export

```
98 passed in 288.42s
0 failed
```

### 4.2 过程中修复的真实缺陷

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | importer/validator 默认路径误用 `DATA_DIR`（未 re-export）→ 0 行 | 统一 `DB_PATH` |
| 2 | 宽表 JSON 序列化 datetime→字符串，权威 classifier fail-closed MISSING_DATE | `normalize_due` 归一化 |
| 3 | 动态 by_group `H or I` 在 H 非空未命中时跳过 I 兜底 | `_group_of` 显式两跳 |
| 4 | persist 宽表 dict 行传 `fields=[]` 清空 meta.columns | 取首行键 / 最大宽度生成 fields |
| 5 | 临时 DB 未建 ra_* schema | engine 构造幂等 `init_db(db_path)` |
| 6 | BaseService auto/read 不写 ra_* 快照 | service `_ensure_snapshots` 兜底 |

---

## 5. 黄金基准（202609 锚点）

| 指标 | 值 |
|---|---|
| 预算执行表行 | 10,473 |
| 底稿行 | 38,052 |
| 校验 errors / warnings | 0 / 82 |
| 锁定合计 | 138,420,136.78 |
| 锁定 新签 / 递延 | 66,520,133.50 / 71,900,003.28 |
| 动态合计 | 171,048,611.81 |
| 动态 DUE_2026 / IN_PIPELINE | 86,936,513.95 / 84,112,097.86 |
| 动态 by_group 新签 / 递延 | 85,065,322.34 / 85,983,289.47 |
| 双口径差异 | 32,628,475.03 |
| R18 init / disappear / unfilled | 2463 / 4 / 123 |
| R19 新签预计确收率 | 0.5951903807615231 |

---

## 6. 验收门

- [x] RA 单测 20 全绿；
- [x] CLI 6 子命令真实链路通过；
- [x] 相关模块回归 98 passed / 0 failed；
- [x] 黄金锚点逐分命中；
- [x] 幂等：persist 多次结果一致；
- [x] 金额红线：trend 金额列 None，不硬摊；
- [x] OPERATIONS / VERIFICATION 文档齐备。
