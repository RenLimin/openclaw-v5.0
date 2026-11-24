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
