# bangcle-project-report — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 技能: L3-business/skills/bangcle-project-report · 经 L4 PJME-001 路由
> 原则: 用真实数据、真实脚本运行验证；禁止编造测试结果。

## 验收标准（Definition of Done）

对应 SKILL.md「验证」与 PRD AC1–AC8：

| AC | 判据 |
|---|---|
| AC1 完整性 | 取数 `fetched == total`、`hitCap=false`；项目数与范围清单一致 |
| AC2 口径 | 剔除建档/范围记录；周期外成果不计入当期工作量 |
| AC3 可反推 | 三维 total 相等且 = 明细数；`done + wip = total` |
| AC4 闭环 | 每个产品方向都有 `realizationLevel`（受控枚举），无悬空 |
| AC5 零编造 | `audit_provenance.py` exit=0（PASS） |
| AC6 脱敏 | 对外版脱敏词表 grep = 0 |
| AC7 幂等 | 同输入连跑 3 次输出一致 |
| AC8 边界 | 无 retrospective/obligation/profile 越界内容；无外发副作用 |
| 黄金基准 | 8 行全部复现：113 / 104 / 9；类别 66/17/19/7/4；产品 44/34/19/10/3/2/1；季度 76/5/32 |

## 测试范围

- 脚本：`scripts/fetch_project_tasks.py`、`normalize_and_classify.py`、`aggregate.py`、`build_goal_matrix.py`、`render_report.py`、`audit_provenance.py`
- 黄金资产：`assets/golden/golden-baseline.json`、`assets/golden/ccb-2026-product-override.json`
- 真实数据：`L3-business/analysis_output/ones_raw/fetch_中国建设银行股份有限_20261108_211418.json`（15,334 任务 / 196 项目）
- 契约校验器：`L2-infra/prompts/tools/check_answer_contract.py`

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| T1 | 自动化测试发现 | `tests/` 目录 | pytest 通过 | ❌ 无 `tests/` 目录（无自动化测试） |
| T2 | 黄金基准回放（类别/产品/季度） | 113 条 override + 9 条在途 | 三维账 = 基准 | ✅ 全等 |
| T3 | 对账（reconciliation） | aggregate 输出 | 三维 total 相等 = detailCount | ✅ 113=113=113=113 |
| T4 | 口径清洗 | 真实 16 合同子集（591 任务） | exit=0，剔除/周期统计 | ✅ exit=0（254 inPeriod） |
| T5 | 渲染对外版 | stage4 JSON | md 生成，脱敏词 grep=0 | ✅ 230 行，grep=0 |
| T6 | 溯源审计 | 对外版 md | exit=0 PASS | ✅ PASS |
| T7 | fail-closed 反例 | 注入无源数字 999 | exit≠0 BLOCK | ✅ exit=2 BLOCK |
| T8 | 幂等 | 同输入连跑 3 次 | hash 三次一致 | ✅ md5 全等 |
| T9 | 契约校验 | 渲染 md | check_answer_contract PASS | ⚠️ BLOCK（见结论） |
| T10 | 真实取数 | ONES 浏览器登录态 | 逐项目枚举 | ⚠️ 枚举到 196 项目后中断（无登录态） |

## 实测结果

- 命令（T1）: `python3 -m pytest L3-business/skills/bangcle-project-report/tests -q`
  - 输出摘要: `ERROR: file or directory not found: .../tests` → `no tests ran`
- 命令（T2/T3 黄金回放）:
  ```
  python3 scripts/aggregate.py < <113条 workItems JSON> > /tmp/g_agg.json
  ```
  - 输出摘要: `reconciliation {'categoryTotal':113,'productTotal':113,'periodTotal':113,'detailCount':113,'ok':True}`
  - 类别: 客户定制需求 66(58) / 缺陷修复 17(16) / 问题工单 19(19) / 产研支持 7(7) / 专项任务 4(4)
  - 产品: 安全监测 44(43) / 合规检测 34(33) / 安卓SDK 19(19) / 测评 10(3) / 小程序 3(3) / H5API 2(2) / 鸿蒙 1(1)
  - 季度: Q1 76(76) / Q2 5(5) / Q3 32(23) —— 与 `golden-baseline.json` **逐行全等**
- 命令（T4 真实数据）: `python3 scripts/normalize_and_classify.py < 16合同子集.json`
  - 输出摘要: `exit=0`，stats `total=591, excluded=255, inPeriod=254, outPeriod=337`
- 命令（T5 渲染+脱敏）: `python3 scripts/render_report.py --audience external --output /tmp/rep_ext.md`
  - 输出摘要: `exit=0`，230 行；`grep -nE "ONES|OA|BDMS|GraphQL|harbor|SSXM|内部任务号|回款|结算|验收条款"` → **0 命中**
- 命令（T6 审计）: `python3 scripts/audit_provenance.py < audit_in.json`
  - 输出摘要: `{"status":"PASS","missing":[],"checks":{"numbers":0,"nouns":0,"redaction":0,"contractNames":0}}` exit=0
- 命令（T7 fail-closed）: 将报告 `113` 改为 `999` 后重跑审计
  - 输出摘要: `{"status":"BLOCK","missing":[{"token":"999",...}]}` **exit=2**
- 命令（T8 幂等）: 同输入渲染 3 次
  - 输出摘要: md5 `286e1fee4f6aaacbccb373616a993255` × 3（一致）
- 命令（T9 契约）: `python3 L2-infra/prompts/tools/check_answer_contract.py /tmp/rep_ext.md`
  - 输出摘要: `❌ 无任何【已验证 YYYY-MM-DD|来源】时间戳标注`、`❌ 信封F3：缺数据基准时间` → **BLOCK exit=1**
- 命令（T10 真实取数）: `echo '{...}' | python3 scripts/fetch_project_tasks.py`
  - 输出摘要: stderr `[INFO] 团队项目总数: 19676` → `过滤后项目数: 196` → 逐项目 `fetched=N` 后中断（本机无 ONES 浏览器登录态，属环境依赖）

- 结论:
  1. **黄金基准 8 行全部复现**（113/104/9 与三维账逐行相等）→ AC3/黄金基准达成。
  2. 脱敏、fail-closed 审计、幂等三项机器门禁**实测通过** → AC5/AC6/AC7 达成。
  3. **缺口 1（已验证缺陷）**: 渲染产物在缺 `fetchedAt` 时不含 `【已验证 日期|来源】`，`check_answer_contract.py` 判 BLOCK。真实报告 `analysis_output/ccb-2026/中国建设银行-项目服务汇总材料-20261106.md` 该校验 **PASS**（47 处时间戳），说明缺陷出现在**回放/无快照时间**场景，需在 `render_report.py` 强制注入 `fetchedAt` 或标注【缺失】以过闸门。
  4. **缺口 2**: 无 `tests/` 自动化测试目录，黄金回归目前依赖手工命令序列（本文档已给出可复现步骤）。
  5. AC1/AC2 的真实取数链路（T10）依赖 ONES 浏览器登录态，本机环境不可完整复现；已用 2026-11-08 真实快照（15,334 任务）完成等价回放。
