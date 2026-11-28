# 任务状态快照 — revenue_analysis P2 完成 / P3 待启动（2026-11-18 15:20）

> 用途：精确断点恢复。P1 旧快照见 `TASK-STATE-REVENUE-ANALYSIS-P1-20261112.md`（保留审计链，不覆盖）。
> 恢复入口：读本文 + 跑 §5 验证命令。

## 1. 任务身份
- 任务：确收分析及预测建设 — **P2 已闭环，P3 待启动**
- 计划：`IMPLEMENTATION-PLAN-REVENUE-ANALYSIS-v1.1.md` §5（P2）/ §6（P3）
- 设计：`DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1.md`（含 §15 实证回写，待 Rex 终审）
- 分支：`main`，HEAD = `89f6cf8`（Rex 他会话推进的 docs 提交不含本组件）

## 2. 已完成 ✅
| 阶段 | 状态 | 证据 |
|---|---|---|
| P1 透视引擎（F3+F4） | ✅ 已提交 | `pivot_builder.py` + `engine._build_diff/_build_restructure` 重写 + 10 测试 |
| P2 趋势/归因/预警 | ✅ 已提交 `6e72d3e` | 8 文件 1152+/144-：`trend_builder.py`、`attribution_engine.py`、`alert_builder.py`、`engine.py`、`service.py`、`schemas_v21.py`、26 专项测试 |
| 实证回写 | ✅ | `DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1.md` §15（635→765 行，§15.1–15.9） |
| 全量回归 | ✅ 499 passed | §15.9：+16 skipped +2 deselected = 517 |
| P2 定向测试（docstring 修正后复跑） | ✅ 26 passed | 2026-11-18 15:2x，112.76s |

### 2.1 §15 实证关键结论（防再踩坑）
- **Q1 触发 109 行** = `AF>0`(106) ∪ `AD<0`(27)，交集 24；旧「106」为仅 AF 子集
- 列键投影：AF←AK、AD←AI、AR←AT；BK/BL 列号实测 **63/64**
- 规则1（AT=合同终止）命中 **9**：6 行与 golden 一致，**3 行误覆盖**（考核扣款 2 / 结算差异 1）
- 规则2（BF=3：交付异常）命中 **0**；pending **100**，auto_filled **9**
- golden 全表 BL=客户原因-终止 25 行，19 行 AT 空白 → **自动覆盖率 9/25=36%**
- Q4 新签消失 2 行（均 `XSZS2512301176`）：合计 −859.75 / −905.00 = **−1,764.75**
- R18 金额 19,122.569346 万 vs golden 11916.985699（差 3.972372 万）；R19 金额口径率 0.607421038 一致

## 3. 待完成 ⏳（恢复后从第 1 步继续）
1. **【需 Rex 拍板】§15.4 决策 C** — 规则1 误覆盖 3 行怎么处理：
   - (a) 保持现状（3 行偏差入审计）
   - (b) 规则1 仅当 `BL` 空白时才填（覆盖率降为 6/25）
   - (c) 规则1 仅填 BK 不填 BL
2. **【需对齐】「有效输出物」定义** — Rex 2026-11-18 指出「空跑未生成任何有效输出物」。
   当前 `output/` 有 5 个 xlsx（确认收入分析_202606/202609、收入预估_202609、交付月报_202606/202610），
   但均为引擎建设前的产物，**非 P1/P2 引擎产出的月报成品**。需确认目标输出物形态。
3. **P3 分桶引擎**（计划 §6）：`bucket_engine.py` 新建 + Q3 跨期继承（用 202605 验证）
4. 可选：`skipped_aggregate_rows` 透传到 `RevenueAnalysisService.attribution()`

## 4. 关键口径备忘
- 触发条件 `AF>0 或 AD<0`；硬规则仅两条，其余留空 + 人工清单
- 校验：BK 非空 ⇔ BL 非空（成对）
- 聚合行（B="合计"）不参与 Q1 归因（`skipped_aggregate_rows` 计数）
- 202606 有权威金额 → `amount_pending=None`（红线只针对 202609）
- R9 漂移按 §7.3 保留计算值 + routing_audit
- BQ/BU/BV 不写死；BU→BV 以 `图例!L:M` VLOOKUP 为准

## 4.5 P3 分桶引擎 · 切片1 进度（2026-11-24，已闭环）

| 项 | 内容 |
|---|---|
| 口径依据 | `DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1.md` §4.1 / §4.2 |
| 落地位置 | `engine.py` 新增 4 方法：`_prev_period` / `inherit_previous_buckets` / `persist_buckets` / `load_buckets`（**未新建 bucket_engine.py**，复用既有避免重复建设） |
| 优先级 | ① 显式人工改判 > ② 上期有值则继承 > ③ 留空待 §3 规则引擎 |
| fail-closed | 本期/上期《预算执行表》任一缺失 → `ImportError_`，不推断不伪造 |
| 关键设计 | **本期 BU 列为产出物，不作判定输入**（否则循环论证）；降级为 `audit_vs_source` 审计字段 |
| 计数 | 键级自洽 `total = inherited + overridden + blank`；同 ID 多行去重（`duplicate_rows`） |
| 列位实证 | `J`=履约ID、`BU`=预算趋势（r2/r3 表头，202605/202606 一致） |

**真实数据验证**（临时库导入 202605+202606）：
`inherited=1192 overridden=0 blank=0`，`audit_vs_source` 一致 1192 / 不一致 0；落库+回读 1192。

**测试**：`tests/test_revenue_analysis_p3_bucket_inherit.py` 11 passed
（含 fail-closed 两例、冷启动语义、优先级顺序、落库回读、账期跨年）。

**提交**：`fe033b9`（2 文件 +261/-0）

**下一片待办**：③ 留空行的 §3 七桶规则引擎（`bucket_engine` 真正算法层），以及 P4/P5、终审设计文档。

### 4.5.1 切片2：§3 七桶规则引擎（2026-11-24，已闭环）

| 项 | 内容 |
|---|---|
| 口径依据 | `DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1.md` §3.1–§3.5 |
| 落地位置 | `engine.py` 新增 3 方法：`judge_bucket` / `save_bucket_entry` / `apply_bucket_rules` |
| BU 规则（§3.3） | BX 年份：>本年→未来可确收；=本年→本年度正常可确收；**<「之前年度已确收」Rex 未给规则 → 不产出该桶（留空）** |
| BQ 规则（§3.2） | M/N/O 计划时间：年内→本年度；之后→未来；之前→之前年度 |
| 合同消失 | AR=「合同终止」，优先级最高（§3.4） |
| fail-closed（§3.5） | ②③④ 依赖 OA+ONES，RA 模块当前未接线 → 信号未知即跳过并记 `missing_signals` |
| 不覆盖红线 | `apply_bucket_rules` 遇已落库值一律 skip，只填新增 |

**⚠️ 键位修正（重要，影响切片1的验证有效性）**

DB 行键是**规范字母**（`config.BUDGET_CANONICAL_FROM_202606` 投影表），**不是 Excel 物理列位**：

| 语义 | Excel 物理列 | DB 规范键 |
|---|---|---|
| 履约ID | J | **G** |
| 消失备注 | AT | **AR** |
| 计划开始/结束/完成 | R/S/T | **M/N/O** |
| 预算趋势 | BU | BU（不变） |

切片1初版误用 `PERF_ID_COL="J"`（实为「截止20251231已确收金额」），导致首轮「审计 100% 一致」无效；修正后重验，见下。

**真实源验证**（202605→202606）：

```
首轮：inherited=8062，审计一致 8058 / 不一致 4
      4 条差异正是 §4.1 举例的 XSZS2605180322_* （人工改判）
带 manual_override 后：一致 8062 / 不一致 0；落库回读 8062
§3 冷启动：合同消失命中 11（修正前误判 0）、BX 未来 46、BX 年内 311
```

**测试**：`test_revenue_analysis_p3_bucket_rules.py` 17 passed；
`test_revenue_analysis_p3_inherit_golden.py` 5 passed（**锁定 §4.1 的 8058/4/8062**）；
回归 p2 14 + p3 14 + inherit 11 = 68 passed。

**提交**：`05f7ef1`（4 文件 +463/-3；含 hook 再生的 `01-asset-inventory.md`，bdms 184→186）

**下一片待办**：P4 / P5、终审设计文档。

### 4.5.2 切片3-5 + P5 闭环（2026-11-26，D5 剩余全部完成）

**切片3：§3 分桶接入 service/API/CLI 主流程（`7a1072f`）**

| 层 | 落地 |
|---|---|
| engine | `compute()` 集成 Q3 继承 + §3 规则（fail-closed：上期缺失降级冷启动）；`persist` 跳过 `bucket_result` |
| service | `buckets()`：读 ra_bucket 返分布 + 前 200 条预览 |
| API | `GET /revenue-analysis/buckets/{period}` |
| CLI | `revenue-analysis buckets` |

真实源验证：generate 后 8071 条（8062 继承 + 9 rule:at_contract_terminated）；合同消失 54 / 本年度 5870 / 未来 1766 / 已下单未交付 358，与设计口径一致；read 模式幂等。

**切片4：Q8 年度目标维护（`e66672d`）**

engine 新增 `get/set/list_annual_targets`（ra_annual_target upsert）；`_build_summary_analysis` r21/r22/r60 目标值 **DB 优先，缺省回退 config**（23000/13340，golden 不飘）。service/API（GET/POST annual-targets）/CLI 全接。真实源验证：未设值 23000/13340 不变；设 25000 → r21/r60 读 DB；upsert 更新；2027 独立并存。单测 5 passed。

**切片5：Q6/Q7 台账时序快照（`033b09d`）**

engine 新增 `persist/load/list_ledger_snapshot`：ra_snapshot (period, snapshot_type) 唯一 upsert（幂等）；月度/履约汇总记录随 generate 自动落盘（§7.1）；上一统计期无快照 → warnings 缺月告警，不推断不伪造；历史行不回写（§7.2）。service/API（snapshots/{period}、snapshot-periods）/CLI 全接。真实源验证：202605 落盘 254+120 行；202606 连续无告警；冷启动缺月告警。单测 7 passed。

**P5：汇总分析 64×50 + Q5 同比区（`8f64317` 单测）**

实证：64 行 × 50 列结构完整；同比区 B 块（Y26/Y25 销售确收、增长率、确收度增长）5 指标就位；产线展开 12 行；年度目标 r21/r22 差距自动算。单测 5 passed（结构 + 同比列位 + 目标 DB 优先）。

**D5 全量回归**：64 passed（inherit 11 + rules 17 + golden 5 + p3 14 + annual 5 + snapshot 7 + p5 5）。

**D5 状态**：切片1-5 + P5 全部完成 → **P3/P4/P5 建设闭环**。

**遗留（非阻塞，需 Rex 决策）**：
1. §3.3「之前年度已确收」Rex 未给规则 → BQ 侧该桶不自动产出（留空人工）
2. §3 ②③④ 桶依赖 OA+ONES 信号，RA 模块未接线 → fail-closed 跳过
3. D1 15 格统计口径差异、D4 3 行人工核实仍待业务侧
4. 生产库 202605 导入与正式 uvicorn 重启（按运维流程）


### 4.5.3 切片6（BQ 落库 + 信号装载接线）+ P7 预测模型（2026-11-28）

**切片6：§3.5/§3.6 信号装载与 BQ 落库接线**

锁定三处实证缺口（实测 2026-11-27）：① `apply_bucket_rules` 硬编码只判 BU → `ra_bucket.budget_fill` 恒空、API `budget_fill_dist` 恒报「(空)」；② `compute()` 不传 OA/ONES 信号 → ②③④ 桶永远 fail-closed、`missing_signals` 恒含两键；③ `_resolve_ones_export` 单月回退 → 202606 的 634 行新签合同被假阴性为「无法匹配」。

| 层 | 落地 |
|---|---|
| engine | 新增 `load_bucket_signals(period)`（OA `oa_contracts` 按 htbh 去重 / ONES 周报 CSV 按销售合同编号去重，O(n) 建字典，fail-closed）；`apply_bucket_rules` 增 `column` 参数，`save_bucket_entry` 按列写 BU→`bucket_source`、BQ→`budget_fill_source`（双列溯源互不覆盖） |
| schema | `ra_bucket` 增 `budget_fill_source`（`_migrate_columns` 迁移 + v2.1 DDL） |
| 口径 | BQ 继承优先级与 BU 一致（人工改判 > 跨期继承 > 规则）；修 `compute()` 落库顺序后写者覆盖先写者的溯源丢失 |

**P7：Q8 年度目标 + 预测模型（IMPLEMENTATION-PLAN §10）**

新建 `forecast_engine.py`：复用 `CaliberBuilder`（双口径单一事实源）与 `ra_bucket`，产出锁定/动态 + future 桶 + 实际达成 + 差距 + 四类风险清单（manual_review / missing_signals / contract_disappear / caliber_gap）。单位红线：caliber 为元、对外统一万元，边界一次性换算。服务 `forecast()` fail-closed 空结构；CLI `revenue-analysis forecast`；Web `GET /revenue-analysis/forecast/{period}`。

**复用判定**：仓库已有 `modules/revenue_forecast/`（v1.0，输入 ObligationRow 物理列解析，不消费 ra_caliber/ra_bucket，无 future 桶/年度目标语义）——输入契约不同不可直接复用，仅复用其 CaliberBuilder；合并须单独立项做接口兼容评审。

**回归证据（真实运行）**
- 新增单测：`test_revenue_analysis_p7_forecast.py` 19 + `test_revenue_analysis_p3_slice6_wiring.py` 11 → **30 passed in 70.96s**
- RA 全量回归（`-k revenue_analysis`）：**157 passed / 454 deselected in 1345.37s**（含真实源集成锚点 202606/202609 零差异）
- CLI 真实链路：`forecast 202609` 空库 fail-closed `{has_data:false, risks:[]}` exit=0；`annual-targets` exit=0

**遗留（非阻塞）**
1. §3.3「之前年度已确收」Rex 未给规则 → BQ 侧该桶仍留空人工
2. 生产库 202605 导入与正式 uvicorn 重启（按运维流程）
3. `ra_annual_target` 已支持 2026 目标；2027 并存待业务填值

---

## 5. 验证命令（恢复后先跑）
```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms
PYTHONPATH=src python3 -m pytest tests/test_revenue_analysis_p2_trend_attribution.py -q   # 26 passed
PYTHONPATH=src python3 -m pytest tests/test_revenue_analysis_p1_pivot.py -q              # 10 passed
```

## 6. 环境备注
- 本会话「Active exec sessions: none」快照**不可信**（已误报 70+ 次），用 `ps`/落盘日志判活
- `timeout` 命令在 macOS 不存在，长任务用 `yieldMs>=60000` 或直接跑
- git 提交必须隔离临时 index + 逐条显式列路径（zsh 不对变量分词）
- 工作树有他会话未提交改动：`docs/architecture/01-asset-inventory.md`、`L2-infra/components/context-guardian/`，**绝不提交**
