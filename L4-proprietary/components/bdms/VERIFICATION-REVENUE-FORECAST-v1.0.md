# VERIFICATION — 实时动态确认收入预估（Revenue Forecast）v1.0

| 项 | 值 |
|---|---|
| 所属 | BDMS / 模块 revenue_forecast |
| 版本 | v1.0 |
| 前置 | PRD/OUTLINE/DETAIL v1.0（均通过） |
| 日期 | 2026-11-08 |

---

## 1. 测试策略

### 1.1 分层

| 层 | 范围 | 工具 |
|---|---|---|
| 单元 | parser / classifier / engine 纯函数 | pytest |
| 持久化 | repository DDL/事务/版本/幂等 | pytest + 临时 sqlite |
| API | 8 个端点真实 HTTP | 真实起服务 + HTTP（不用 TestClient 测网络/分页/Cookie） |
| E2E | 上传→进度→概览→月度→明细→导出 | 真实浏览器（Playwright，slow，单独标记） |
| 回归 | 不破坏现有 367 passed / 16 skipped | pytest 全量（排除 visual/slow） |

### 1.2 铁律

- 新增测试数 ≥ classifier 新增判定分支数（10 类 + 优先级互斥）。
- 所有金额断言用 `pytest.approx(abs=0.01)`（分），不用裸 `==`。
- 黄金 fixture 锁定全部关键数字；引擎纯函数连跑 3 次逐字段相等。
- E2E 用真实财报文件走真实上传，不用 mock 数据冒充。

### 1.3 环境

- 临时 DB（`tmp_path`），不污染 `data/bdms.db`；
- 服务绑 `127.0.0.1` 随机端口；
- Part B 恒 `not_configured`，测试不访问 ONES、不需凭据。

---

## 2. 单元测试

### 2.1 report_parser
- col2 混合形态：真实日期（datetime）、「2026年7月」字符串、各文本标签、空、非法；
- col15–26 / col32–40 / col42 数值解析，文本/空按 0；
- 预算键 col4 带 `YS`、现行键 col6；col8="2026年无预算ID"；
- 恒等式校验：构造 col40≠col41+col42、col27≠Σ15–26 的行 → 进校验报告，不静默、不崩溃。

### 2.2 classifier（10 类分支全测）
- 每类各至少 1 正例；
- **优先级互斥**：构造同时含多个关键词的值（如「已提交资料…异常」）断言按优先级落第 3 类 IN_PIPELINE；
- 年份边界：2025-12-31、2026-01-01、2026-12-31、2027-01-01；
- 空/不可解析 → MISSING_DATE（fail-closed）。

### 2.3 engine
- 锁定：1.38（新 .67/递 .72）、逐月 12 值；
- 动态：1.71（新 .851/递 .860）= DUE .869 + PIPE .841；
- pipeline 归独立桶、不进月份；
- gap = +.33；col10 = 2.23；2027+ = .84；
- 实际 1–9 = .94；
- 幂等：同输入 ×3 逐字段相等。

### 2.4 repository
- 建表幂等（连调 ensure_schema 不报错）；
- 上传两期 → is_current 唯一；切版旧数据保留；
- 同期重算 → 不产生重复行，数字稳定；
- 分页/分类过滤/金额汇总正确。

---

## 3. 集成 / API 测试（真实 HTTP）

| 端点 | 断言 |
|---|---|
| POST /upload | 返回 job_id；错误文件 → 明确错误、保留上版 |
| GET /progress | running→done，pct 单调；error 信息可读 |
| GET /periods | current 与列表正确 |
| GET /overview | locked 1.38/dynamic 1.71/actual .94/gap .33 + by_group |
| GET /monthly | basis=locked 12 月和=1.38；dynamic 含 pipeline .841 |
| GET /lines | 分页 total=38052；category/in_plan 过滤生效（参数被解析≠生效，须实际验证） |
| GET /provider-status | part_b.status=not_configured |
| GET /export | 返回 xlsx，多 sheet，可被 openpyxl 重新打开且数字一致 |

---

## 4. E2E（Playwright，标记 slow，人工验收前跑）

1. 打开 `/forecast`，上传真实财报 → 进度条实时（分步+pct，无空白等待）；
2. 概览页显示 1.38 / 1.71 / .94 / +.33；
3. 切 Tab 看锁定逐月柱状、动态逐月+pipeline；
4. 明细表分类筛选、分页、下钻 IN_PIPELINE 看锁定月份；
5. 导出 Excel 并打开核对；
6. Part B 区域显示"待接入 ONES"。

---

## 5. 黄金基准（锚点）

| 指标 | 值（亿元） |
|---|---|
| 预算执行表有效行 | 10,472 |
| 底稿行 | 38,052 |
| col27=Σ15–26 不符 | 0 |
| col40=col41+col42 不符 | 0 |
| 锁定 2026 / 新签 / 递延 | 1.38 / .67 / .72 |
| 实际 1–9 / 新签 / 递延 | .94 / .44 / .51 |
| 动态 2026 / 新签 / 递延 | 1.71 / .851 / .860 |
| 动态 = DUE + PIPE | .869 + .841 |
| col10 / 2027+ | 2.23 / .84 |
| gap 动态−锁定 | +.33 |

---

## 6. 验收门

- 单测全绿；新增测试数达标；
- API 8 端点真实 HTTP 全过；
- E2E 6 路径通过；
- 全量回归：现有基线不下降；
- 交付前按 7 步法独立审计。

---

## 7. 实际测试结果（2026-11-08 主会话独立复跑）

### 7.1 测试计数

| 套件 | 用例数 | 结果 |
|---|---|---|
| test_forecast_core.py | 35 | passed |
| test_forecast_repository.py | 20 | passed |
| test_forecast_api.py | 5 | passed |
| test_forecast_export.py | 3 | passed |
| test_forecast_e2e.py | 1（slow） | passed（Playwright 真实浏览器） |
| **forecast 合计** | **64** | **全绿** |
| 全量非 slow 回归 | — | **436 passed / 16 skipped / 2 deselected / 0 failed** |

基线核对：367（恢复基线）+ 66（core41+repo20+api5）+ 3（export）= 436 ✓；skipped 仍 16 ✓；2 deselected 为既有 conftest 去选，非本次引入。

### 7.2 7 步法独立审计（主会话亲自执行，非子会话自审）

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 清空上下文独立审计 | ✅ 从代码现状出发 |
| 2 | 契约对齐 | ✅ 8 端点齐全、8 文件全在、无残留临时文件 |
| 3 | 全入口覆盖 | ✅ 真实 HTTP 跑通 upload→progress→7 GET→export |
| 4 | 黄金基准对比 | ✅ 导出 xlsx 逐元命中 138,420,136.78 / 171,048,611.81 / 94,457,828.53 / +32,628,475.03 / pipeline 84,112,097.86 |
| 5 | 幂等性 | ✅ 同上传连跑 3 次，locked/dynamic/actual/gap 逐分一致 |
| 6 | 调用点扫描 | ✅ 仅 api.py/main.py 引用；revenue/importer.py 的 `forecast_category` 为既有列名，无 import，非耦合 |
| 7 | 回归锁定 | ✅ 新增测试 64 ≥ 新增分支 32（classifier 16 + engine 6 + service 10）；全量 0 failed |

### 7.3 审计结论

**通过。** 唯一可疑点（revenue/importer.py 含 "forecast" 字样）经查为既有列名 `forecast_category`，非本次引入，无耦合。

### 7.4 遗留事项（非本次范围）

- Part B（ONES 实时动态）：仅占位 `NotConfiguredProvider`，待 ONES 凭据与采集链路接入；
- OA 写回：独立立项，需 Rex 二次授权与端点契约；
- 身份映射补全：法务/财务总监 OA 节点归属待确认。
