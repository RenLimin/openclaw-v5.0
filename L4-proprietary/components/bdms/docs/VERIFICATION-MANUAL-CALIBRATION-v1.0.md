# VERIFICATION — BDMS 人工数据校准 v1.0 测试方案

> 状态：**待 Rex 审核** | 作者：Jerry 🦞 | 日期：2026-10-28
> 依据：`PRD-MANUAL-CALIBRATION-v1.0.md`、`DESIGN-DETAIL-MANUAL-CALIBRATION-v1.0.md`（均通过）
> 方法论：交付验收 7 步法（AGENTS.md 铁律）
> 本文通过后才进入 OPERATIONS。

---

## 0. 测试原则与约束

| 原则 | 说明 |
|---|---|
| **真实 HTTP** | Web/写路径禁用 FastAPI TestClient；用真实 HTTP 请求（`httpx` 起服务 or `requests` 打本机） |
| **E2E 模拟人工** | Playwright 驱动浏览器，模拟用户点按钮、填对话框，不跳过 UI 层 |
| **幂等 3 次** | 每条写操作连跑 3 次，结果一致、不产生重复记录 |
| **调用点全扫描** | 所有读 `dr_sheet_row` 的入口必须经校准解析层；所有写原始行的路径必须审查 |
| **回归锁定** | 新增测试数 ≥ 本次功能新增的 bug 风险点数量（本版本 >10 条） |
| **黄金基准对比** | 导出 Excel 的校准后值与台账 Sheet，与手工计算的黄金基准逐行对 |

---

## 1. 测试环境

- **服务**：启动 BDMS 服务（`launchctl kickstart -k gui/$(id -u)/com.bdms.server` 或 `uvicorn bdms.web.main`），端口 8000
- **测试库**：独立测试 DB（`bdms_test.db`），跑前建表、跑后清理；不污染生产库
- **种子数据**：最小可测月报（202610），3 个 Sheet × 20 行，内置 5 类问题：
  - 签约 Sheet：2 条日期格式错、1 条合同编号重复、3 条必填空值
  - POC&提前实施 Sheet：1 条日期格式错、2 条数值异常
  - 异常项目 Sheet：4 条必填空值、2 条日期格式错
- **浏览器自动化**：Playwright + Chromium，headless
- **测试框架**：`pytest`（单元）+ `pytest-playwright`（E2E）

---

## 2. 验收标准总表（对齐 PRD 10 条 AC）

| AC | 验收点 | 测试类型 | 判定标准 |
|---|---|---|---|
| **AC-01** | 提交校准（值+原因）成功，toast 显示成功 | E2E + API | 接口 200 + dr_calibration 有 1 条 active + 前端 toast 可见 |
| **AC-02** | 校准后 `dr_sheet_row.data` 原始值字节级不变 | 单元 + 集成 | 校准前后 data 列 `md5()` 一致 |
| **AC-03** | 保存后自动重校验，被修复问题转 confirmed，KPI 下降 | E2E + API | pending 数减少 confirmed 数增加；total_errors 下降 |
| **AC-04** | 补填空值后非空规则问题消失 | API + 单元 | 原空值问题 status→confirmed |
| **AC-05** | 校准记录 5 要素齐全（原值/新值/人/时间/原因） | API + DB | 全部字段非空且正确 |
| **AC-06** | 撤销校准后恢复原值并重校验，问题重新出现 | E2E + API | status→revoked，问题回 pending，review KPI 回退 |
| **AC-07** | 修改校准：旧值入快照，新值生效并重校验 | API + DB | history 有 revise 记录，corrected_value 更新，重校验结果正确 |
| **AC-08** | 导出 Excel：校准单元格为新值 + 「校准台账」Sheet | 集成 | openpyxl 逐格比对；台账行数=active 校准数 |
| **AC-09** | 数据浏览 Sheet 下拉显示当月全部 Sheet（动态） | E2E | 下拉项数 == `/report/sheets` 返回数 == 当月实际 Sheet 数 |
| **AC-10** | 非法类型/枚举值被拒绝且不落库 | API + DB | 400 + dr_calibration 未新增行（枚举列：`异常项目.状态`，合法集=legend「状态」8 值） |

---

## 3. 测试用例清单

### 3.1 单元测试（CalibrationService）

| 编号 | 用例 | 预期 |
|---|---|---|
| U-01 | `get_active_map` 返回空（无校准） | 空 dict |
| U-02 | `upsert` 首次校准，原值正确 | 1 条 active，original_value 与 dr_sheet_row 一致 |
| U-03 | 同单元格 `upsert` 第二次（修改） | active 仍 1 条，history 有 revise 记录，previous_value 正确 |
| U-04 | `revoke` 撤销 | status→revoked，history 有 revoke 记录，resolved_at 有值 |
| U-05 | 撤销后再校准 | 新 active 行，原 revoked 行保留，不触发唯一冲突 |
| U-06 | `apply_overlays` 不修改 raw 入参 | raw DataFrame 引用值不变（copy 语义） |
| U-07 | `apply_overlays` 行号超界/列不存在 | 不抛异常，返回告警，其他校准正常应用 |
| U-08 | 类型校验：日期列非法值 | 抛 CalibrationError，DB 无写入 |
| U-09 | 类型校验：数值列非数字 | 同上 |
| U-10 | 枚举列值不在允许集合（`异常项目.状态`，legend 已 seed） | 抛 CalibrationError(code=INVALID_VALUE)，DB 无写入 |
| U-11 | 原因空字符串 | 抛 CalibrationError |
| U-12 | `ledger_rows` 输出格式正确 | 列顺序与字段与契约一致 |
| U-13 | `overview` 统计正确 | active/revoked/pending/by_sheet 数值准确 |

### 3.2 API 集成测试（真实 HTTP）

| 编号 | 端点 | 用例 | 预期 |
|---|---|---|---|
| A-01 | POST `/calibrations/{month}` | 正常提交一条 | 200 + calibration.id + recalculation 摘要 |
| A-02 | POST `/calibrations/{month}` | 空 reason | 400 `EMPTY_REASON` |
| A-03 | POST `/calibrations/{month}` | 日期列非法 | 400 `INVALID_TYPE` |
| A-04 | POST `/calibrations/{month}` | approved 月报提交 | 400 `LOCKED` |
| A-05 | POST `/calibrations/{month}/revoke` | 撤销存在的校准 | 200 status=revoked，重校验回退 |
| A-06 | POST `/calibrations/{month}/revoke` | 撤销不存在的校准 | 400 `NOT_FOUND` |
| A-07 | GET `/calibrations/{month}` | 查全部 | 列表字段齐全，total 正确 |
| A-08 | GET `/calibrations/{month}?sheet=` | 按 Sheet 过滤 | 只返回指定 Sheet |
| A-09 | GET `/calibrations/{month}?status=revoked` | 按状态过滤 | 只返回 revoked |
| A-10 | GET `/calibrations/{month}/overview` | 总览 | KPI 与实际统计一致 |
| A-11 | GET `/sheets/{month}` | 动态 Sheet 列表 | 数量=实际 Sheet 数，顺序一致 |
| A-12 | GET `/calibration-ledger/{month}` | 台账 JSON | 行列与 DB 一致 |
| A-13 | GET `/export/{month}` | 导出 Excel 含台账 Sheet | 文件存在、有"校准台账"Sheet |
| A-14 | GET `/report/data/{month}/{sheet}` | 数据浏览走校准层 | 已校准单元格返回校准后值 |
| A-15 | GET `/enum-options/{month}/{sheet}/{column}` | 枚举列 `异常项目.状态` | 200 + options 恰为 legend「状态」8 值 |
| A-16 | POST `/calibrations/{month}` | 枚举列提交非法值（不在 8 值内） | 400 `INVALID_VALUE`，dr_calibration 无新增 |

### 3.3 E2E 测试（Playwright 模拟人工）

| 编号 | 场景 | 操作路径 | 预期 |
|---|---|---|---|
| E-01 | 问题清单校准一条 | 登录 → 报告页 → 切"问题清单" → 选第一条 → 点"校准" → 填值+原因 → 保存 | 对话框关闭 + toast "校准成功" + 该问题状态变"已修正" + 顶部 KPI 刷新 |
| E-02 | 问题清单补填空值 | 找到一条"必填缺失"问题 → 校准 → 填写合法值 → 保存 | 问题消失或转 confirmed，pending 数 -1 |
| E-03 | 撤销校准 | 在问题清单点某条已校准问题 → "查看校准" → "撤销" → 确认 | 校准状态 revoked，问题恢复 pending，KPI 回退 |
| E-04 | 数据浏览发起校准 | 切"数据浏览" → 选 Sheet → 点某单元格 → "校准" → 填值保存 | 单元格值更新 + 标记显示 |
| E-05 | 已校准单元格查看记录 | 悬停/点击已校准单元格 → "查看校准记录" | 弹窗显示 5 要素齐全 |
| E-06 | 数据浏览 Sheet 动态 | 下拉列表项数 = 当月 Sheet 总数（15） | 不少于硬编码的 5 个，全部可切换 |
| E-07 | 导出并下载 | 点"导出月报" → 下载 Excel → 打开检查 | 有"校准台账"Sheet，行数匹配 active 校准数 |
| E-08 | 批量场景：>200 行触发异步 | （构造批量提交）返回 job_id → 进度条推进 → 完成后刷新 | 进度条非空、有步骤文字，完成后数据正确 |
| E-09 | approved 月报锁定 | 先 approve → 尝试校准 | 400/前端禁用，无写入 |
| E-10 | 原因空校验 | 校准对话框不填原因直接保存 | 按钮不可点 or 红字提示，不落库 |
| E-11 | 枚举列校准下拉 | 数据浏览切到 `异常项目` → 点「状态」单元格 → 校准 → 值输入区应渲染为 `<select>` 且恰 8 选项 → 选合法值保存 | 下拉出现且 8 项；保存后 toast 成功、问题状态更新 |

### 3.4 幂等性测试

| 编号 | 操作 | 3 次结果 |
|---|---|---|
| I-01 | 同一单元格提交同一条校准（相同 corrected_value+reason） | dr_calibration 仅 1 条 active，history 无重复 |
| I-02 | 撤销同一校准 3 次 | 仅 1 条 revoked 记录，history 1 条 revoke，不追加 |
| I-03 | 同一 revalidate 触发 3 次 | issue 状态不反复，KPI 稳定，review_status.updated_at 可更新但数值一致 |
| I-04 | 同一导出 3 次 | 文件内容一致（可用 md5 比对数据部分，忽略时间戳） |

### 3.5 安全 / 一致性测试

| 编号 | 检查项 | 方法 |
|---|---|---|
| S-01 | 原始行不可变 | 全量 `dr_sheet_row` md5 校验：所有校准操作后原值字节级一致 |
| S-02 | 事务一致性 | 模拟中途异常（mock DB 报错），不残留半态数据 |
| S-03 | 同月并发 job | 触发大批量重校验的同时提交新校准，应返回 409 `CALIBRATION_BUSY` |
| S-04 | 跨月隔离 | 校准 202610 不影响 202609 的数据与状态 |

---

## 4. 黄金基准（Golden Baseline）

### 4.1 黄金数据集（`tests/fixtures/calibration_golden.csv` 或内置 dict）

构造固定输入：3 Sheet × 20 行，含预置问题类型清单（见 §1 种子数据）。

### 4.2 预期产出

| 检查维度 | 黄金值（精确） |
|---|---|
| 初始 pending 问题数 | 15 条（签约 6 + POC 3 + 异常 6） |
| 校准 3 条（修 3 个不同问题）后 pending | 12 条，confirmed 3 条 |
| 应用覆盖层后 签约 Sheet 第 5 行 `签约日期` 字段 | `"2026-06-15"`（从 `"2026/6/15"` 校准） |
| 修改同一条校准后 history 条数 | 1 条 revise + 0 条 revoke = 1 |
| 撤销后 pending 数 | 恢复到 13（视撤销那条是否再次违规） |
| 台账列顺序 | `[月份,Sheet,行号,列名,原始值,校准值,操作人,校准时间,校准原因,状态]` |
| 导出"校准台账"Sheet 行数 | = active 校准数（不含 revoked） |

### 4.3 验证方法

- 单元/集成测试：`assert result == GOLDEN[key]`
- 导出验证：用 openpyxl 读 Excel，逐格与黄金比对（忽略动态时间戳列，只比业务字段）

---

## 5. Bug 修复调用点扫描（开发期执行清单）

| # | 扫描项 | 方法 | 预期结果 |
|---|---|---|---|
| C-01 | 所有 `UPDATE dr_sheet_row` 路径 | `grep -rn "dr_sheet_row" src/` | 仅 engine.persist / engine.compute 等生成期写路径；无校准相关写路径 |
| C-02 | 所有调用 `apply_manual_fixes` 的点 | `grep -rn "apply_manual_fixes\|apply_fixes" src/ tests/` | 0 处（已废弃/改走覆盖层） |
| C-03 | 所有报表数据读取入口 | `grep -rn "load_sheet_rows\|load(" src/bdms/modules/delivery_report/` | 全部经 `apply_overlays` 或明确标注 raw 用途（审计/对比） |
| C-04 | 导出路径数据来源 | 读 exporter.py 所有 df 来源 | 来自 effective 而非 raw |
| C-05 | 问题清单数据来源 | 读 review-issues API 与列表渲染 | 来自 dr_import_validation（与校准层独立，状态由重校验驱动） |
| C-06 | 前端所有问题列表/数据浏览调用 | grep `bdms.js` + `report.html` 内联 JS 中 fetch | 调正确端点，无绕过 |

---

## 6. 回归测试锁定

本功能新增风险点（估计 12 个）：

| # | 风险点 | 对应测试 |
|---|---|---|
| 1 | 原始数据被改 | S-01 |
| 2 | 校准口径不一致（界面/校验/导出三处值不同） | A-14 + E-07 + C-03/C-04 |
| 3 | 重校验后问题状态错误流转 | A-01 + E-01 |
| 4 | 撤销后数据未恢复 | A-05 + E-03 |
| 5 | 修改校准留痕缺失 | U-03 |
| 6 | 非法值通过校验落库 | U-08/09/10 + A-02/03 |
| 7 | approved 月报仍可校准 | A-04 + E-09 |
| 8 | 大批量重校验无进度条 | E-08 |
| 9 | 数据浏览 Sheet 不全 | A-11 + E-06 |
| 10 | 导出台账缺失或行数错 | A-13 + E-07 |
| 11 | 同单元格重复校准冲突 | U-05 + I-01 |
| 12 | 事务半态 | S-02 |

**新增测试数 ≥ 风险点数**：本方案单元 13 + API 16 + E2E 11 + 幂等 4 + 安全 4 = **48 条**，
远大于 12 个风险点，满足 7 步法"回归测试锁定"要求。

---

## 7. 验收 7 步法执行清单

| 步 | 动作 | 产出 |
|---|---|---|
| 1 清空上下文独立审计 | 不看本方案，从代码现状出发，列 10 条检查点 | 审计清单 |
| 2 契约对齐检查 | 对照 DETAILED 的每个接口/每张表/每条规则，确认实现 | 对齐报告 |
| 3 全入口覆盖执行 | API 16 + E2E 11 全部实跑 | pytest + playwright 报告 |
| 4 黄金基准对比 | 导出 vs 黄金值逐格比对 | 对比报告（0 差异） |
| 5 幂等性测试 | I-01 ~ I-04 各跑 3 次 | 结果稳定 |
| 6 Bug 修复调用点扫描 | C-01 ~ C-06 全扫 | 扫描报告（0 残留） |
| 7 回归测试锁定 | 新增 48 条 ≥ 12 风险点 | 测试覆盖率报告 |

---

## 8. 测试命令（预留给执行期）

```bash
# 单元 + API 集成（真实 HTTP）
pytest tests/test_calibration_unit.py tests/test_calibration_api.py -v

# E2E（需要服务在 8000 端口运行）
pytest tests/test_calibration_e2e.py --headed=false -v

# 生成报告
pytest --html=reports/calibration-test-report.html --self-contained-html

# 调用点扫描（开发期 & 验收前各跑一次）
grep -rn "apply_manual_fixes\|apply_fixes" src/ tests/ && echo "FAIL: 残留破坏性方法" || echo "OK"
```

---

## 变更记录

- 2026-10-29 v1.0.1：枚举强校验订正（对齐 DESIGN-DETAIL v1.0.1）——
  废弃不存在的 `签约.履约状态`；启用 `异常项目.状态`（legend「状态」8 值，真实数据 100% 命中）；
  新增 A-15（enum-options 端点）、A-16（枚举非法值 400 INVALID_VALUE）、E-11（枚举列下拉渲染）；
  测试总量 45 → 48。
- 2026-10-28 v1.0：Jerry 初稿。45 条测试覆盖 12 风险点；真实 HTTP + Playwright E2E；
  黄金基准逐格比对；幂等 4 条；调用点 6 项扫描；7 步法完整清单。
