# OPERATIONS — 确收分析报告（Revenue Analysis）v1.0

| 项 | 值 |
|---|---|
| 所属 | BDMS / revenue_analysis |
| 版本 | v1.0 |
| 日期 | 2026-11-10 |

> 本手册描述 v1.0：导入**官方财报源文件**（2026 年计划确收&实际确收对比表），经 校验 → 双口径引擎 → 趋势/重拆构建 → 导出 10 Sheet 分析报告。全程本地计算，无 AI Token、无外部请求。

---

## 1. 安装与启动

模块随 BDMS 主包安装，仅依赖 `openpyxl`（已有），无新增第三方依赖、无额外服务。

### 1.1 数据库

首次使用自动建表（`ra_period / ra_caliber / ra_trend_row / ra_trend_cell`）。引擎构造时幂等执行 `init_db`，无需手工初始化。

Canonical DB：

```
/Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms/data/bdms.db
```

### 1.2 模块布局

```
src/bdms/modules/revenue_analysis/
├── config.py           # Sheet 名 / 分类 / 趋势映射常量
├── importer.py         # Excel → 宽表落盘（rr_sheet_row）
├── validator.py        # 结构/金额校验（error + warning）
├── caliber_builder.py  # 双口径构建（锁定 + 动态，单一事实源）
├── trend_builder.py    # 预算趋势分析 R4–R20
├── engine.py           # 编排 + compute + persist
├── service.py          # RevenueAnalysisService（三模式幂等）
└── exporter.py         # 10 Sheet Excel 导出
```

---

## 2. CLI 操作指南

### 2.1 导入源文件

```bash
bdms revenue-analysis import 202609 \
  --source "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
```

- 预算执行表 + 计划确收底稿两个 Sheet 写入宽表（202609 实测 10,473 + 38,052 行）；
- 重跑覆盖同期数据，幂等。

### 2.2 计算（三模式）

```bash
bdms revenue-analysis generate 202609 --mode auto
```

| mode | 行为 |
|---|---|
| `auto`（默认） | 有数据→读；无数据→计算 |
| `read` | 只读，无数据报错 |
| `regenerate` | 强制重算并覆盖 |

`auto/read` 若仅导入过宽表而 `ra_*` 快照缺失，service 层 `_ensure_snapshots` 会自动补计算落盘，保证双口径/趋势始终可查。

### 2.3 查询

```bash
bdms revenue-analysis summary 202609   # 双口径 by_group + by_month + 差异
bdms revenue-analysis caliber 202609   # 锁定 新签/递延 + 动态 DUE/PIPE
bdms revenue-analysis trend  202609    # 趋势表 R4–R19（计数 + 确收率）
```

### 2.4 导出

```bash
bdms revenue-analysis export 202609 \
  --out output/确认收入分析_202609.xlsx
```

不传 `--out` 时默认落到 `output/确认收入分析_{period}.xlsx`。导出约 2–2.5 分钟（宽表 4.8 万行 + 样式渲染）。

### 2.5 列出账期

```python
RevenueAnalysisService().list_periods()  # ra_period，倒序
```

---

## 3. 输出工作簿（10 Sheet）

| Sheet | 内容 |
|---|---|
| 预算执行表 | 源宽表 + 中文表头（10,473 行） |
| 计划确收底稿 | 源宽表 + 中文表头（38,052 行） |
| 汇总 | 锁定/动态双口径 by_group + by_month |
| 汇总分析 | 差异 + 分类桶（DUE/PIPE/OTHER/MISSING） |
| 预算趋势分析 | R4–R20 趋势（正常/异常/消失/未来 + 校验） |
| 确收差异分析 | 双口径差异明细 |
| 重拆履约 | forecast classifier 重拆结果（276 行） |
| 图例 | 分类/状态图例 |
| 月度汇总记录 | 宽表逐月聚合 |
| 履约汇总记录 | 履约桶聚合 |

样式：微软雅黑；主表头 `#4472C4` 白字、子表头 `#D9E1F2`；边框 `#D9D9D9`；金额 `#,##0.00`；完成率 `0.0000`。

---

## 4. 口径定义

| 口径 | 来源 | 定义 |
|---|---|---|
| 锁定（period_locked） | 财报锁定列 | 已提交公司/财务的 2026 预算，本年不可调 |
| 动态（period_dynamic） | 宽表现行数据 | 按最新项目状态重算：DUE_2026（年内到期）+ IN_PIPELINE（资料已提交/在途）+ OTHER_2027plus + MISSING |

关联（`_group_of`）：H 列现行键优先，未命中时 I 列预算键兜底；月份键统一 `YYYYMM`。

---

## 5. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 导入后 `rr_sheet_row` 0 行 | 历史 bug（`DATA_DIR` 未 re-export）已修；确认为当前版本即可 |
| 动态分类大量 MISSING_DATE | 宽表 JSON 序列化把 datetime 变字符串；caliber_builder `normalize_due` 已归一化，仍异常则检查源日期格式 |
| trend 计数全 0 | 1017 原始文件缺 AT–AX 计算列；用带计算列版本导入（`tmp/202609_with_trend_cols.xlsx`） |
| J/K/L 金额全 0 | 金额红线：不硬摊，trend 金额列输出 `None` + `amount_pending`，属预期 |
| 导出耗时长 | 4.8 万行 + 全量样式，约 2–2.5 分钟，正常 |
| `no such table: ra_caliber` | 引擎构造已幂等建表；若手工建库需跑 `init_db(db_path)` |

---

## 6. 数据与权限

- 仅读取本地财报文件，写入本地 BDMS SQLite；
- 不访问 ONES、不发任何外部请求、不写回业务系统、不调用 LLM（🔒 NO_TOKEN）；
- 历史账期版本保留，重算只在同一账期内幂等重建；
- 无自动对外副作用。
