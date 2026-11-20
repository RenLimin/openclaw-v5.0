# delivery-quality — 交付质量反馈闭环组件设计

> 层级：L2 基础设施层 · 组件类：质量反馈闭环（数据闭环层）
> 状态：✅ 已建设（2026-10-30 建立，2026-10-30 改事件驱动；2026-11-20 补写本设计）
> 关联规范：ADR-035 §4「数据闭环层」、AGENTS.md §交付质量反馈闭环 ★★★、`README.md`、`SCHEMA.md`
> 能力登记：`capability-registry/registry.yaml` id=`delivery-quality`

## 1. 定位

把 Rex 对交付结果的**问题反馈 / 纠正**默认沉淀为结构化记录，聚类 review，
把复发 / 高危问题反哺到知识库、黄金 fixture、P2 域契约与 checker，
形成「用户反馈 → 记录 → 评审 → 契约升级」的持续改进闭环。

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 质量反馈闭环（Prompt 治理体系的数据闭环层） |
| 状态 | ✅ 已建设（2026-10-30 建立） |
| 权威入口 | `record.py`（记录）、`review.py`（评审） |
| 数据资产 | `feedback.jsonl`（git-tracked JSONL） |
| 派生产物 | `reviews/review-YYYYMMDD.md`（只读报告，`reviews/.gitignore` 不入库） |
| 关联规范 | ADR-035 §4、AGENTS.md §交付质量反馈闭环、`SCHEMA.md` |
| 契约对接 | P2 域契约「维度合格判据」、`check_answer_contract.py`、黄金 fixture、`docs/knowledge-base` |

**非目标**：review 不自动修改 P2 契约 / 技能 / 知识库（只报告 + 建议，Rex 拍板）；
不记录凭据与敏感身份；不替代 P2 契约本身。

## 2. 设计约束（来自代码实证）

1. **存储用 git-tracked JSONL，不用 SQLite**：`feedback.jsonl` 每行一条 JSON，
   可 git 版本化 / diff / grep，跨会话不丢；规避 MEMORY「SQLite DB 重制全丢」教训。
2. **事件驱动，无 cron**：`record.py` 每次成功记录后立即 `subprocess.run([sys.executable, review.py])`
   触发一次评审；批量导入用 `--no-review` 只记录不触发，导完手动跑一次。
   （2026-10-30 `7057b49` 由每周 cron 改为事件驱动。）
3. **评审只读、不改核心**：`review.py` 只生成 `reviews/review-YYYYMMDD.md` 报告与升级建议，
   不写 P2 / 技能 / KB；是否升级由 Rex 拍板（「巡检只报告，action 走拍板」）。
4. **fail-closed 输入校验**：`finding` 为空即 `exit 2`；`--domain/--dimension/--severity/--status`
   由 `argparse choices` 强约束（5 域 / 9 维度 / 3 严重度 / 4 状态，见 `SCHEMA.md`）。
5. **复发与高危双阈值**：同根因（`root_cause` 非空按根因、否则退回 `dimension`）出现
   ≥2 次判复发；`severity=high` 首次即进「高危单次项」，不必等复发。
6. **时间与 id 口径固定**：`ts` 固定 `Asia/Shanghai`（UTC+8），`id` 自动生成 `FB-YYYYMMDD-NN`
   （按当日已有 FB- 前缀计数），保证可排序、可引用。

## 3. 架构

```
Rex 反馈 / 纠正
   │  （默认行为，AGENTS.md §交付质量反馈闭环）
   ▼
record.py ──────────────► feedback.jsonl  (git-tracked JSONL)
   │  --domain/--dimension/--severity/--target/--finding/...
   │  --status open|corrected|promoted|wontfix
   │
   │  记录成功后立即（--no-review 则跳过）
   ▼
review.py ──────────────► reviews/review-YYYYMMDD.md（只读建议）
   │  · 分布：维度 / 域 / 严重度 / 状态
   │  · 复发聚类（同根因 ≥2，含 open/corrected）
   │  · 高危单次项（high 首次即评估）
   │  · open 反馈跟踪 + 全量状态表
   ▼
Rex 拍板
   ├─ 收紧 P2 域契约「维度合格判据」+ 加 checker 校验
   ├─ 加黄金 fixture（正例/反例）纳入 pre-commit
   ├─ 沉淀 docs/knowledge-base 文档
   └─ wontfix（须在 resolution 写明理由）
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 记录器 | `record.py` | 追加一条反馈到 `feedback.jsonl`，自动生成 id/ts，记录后触发 review |
| 评审器 | `review.py` | 载入 / 聚类 / 复发检测 / 升级建议 / 渲染只读报告 |
| 契约 | `SCHEMA.md` | 字段定义、dimension 枚举、生命周期、去重与复发规则 |
| 数据 | `feedback.jsonl` | 每行一条 JSON，git-tracked |
| 报告 | `reviews/` | 派生只读报告，`.gitignore` 排除 `*.md` |

### 3.2 分析口径（`review.py` 实证）

- **聚类键**：`root_cause` 非空 → 用根因；为空 → 退回 `[dimension:<dimension>]`。
- **复发**：`len(items) >= RECUR_THRESHOLD(=2)` 且其中存在 `open` 或 `corrected`。
- **高危单次**：`severity == high` 且状态非 `promoted`/`wontfix`，且根因未进入复发集合。
- **升级建议映射**：`data_fidelity / calculation_logic / data_completeness` → 收紧 P2 判据 +
  checker + 黄金 fixture；`missing_risk_analysis / missing_context` → P2 必备章节 + 缺失 BLOCK；
  `best_practice_gap` → 固化要素清单进 P2/模板；`sourcing` → 强化降级标注校验 + 溯源 fixture。

## 4. 接口与用法（真实可执行）

### 4.1 记录反馈

```bash
python3 L2-infra/components/delivery-quality/record.py \
  --domain project \
  --dimension data_fidelity \
  --severity high \
  --target "SSXM-2026-0525-1294" \
  --finding "项目类型误标，应区分签约/POC/提前实施" \
  --root-cause "未查 ONES type 字段，凭名称推断" \
  --corrective-action "v2 已按业务分类修正" \
  --status corrected
```

- `--domain`：`project / contract / product / cross / other`
- `--dimension`：见 `SCHEMA.md`（`data_completeness / data_fidelity / calculation_logic /
  missing_risk_analysis / missing_context / best_practice_gap / sourcing /
  format_presentation / other`）
- `--severity`：`high / medium / low`（对结论正确性的影响）
- `--status`：`open`（默认）/ `corrected` / `promoted` / `wontfix`
- 可选：`--target`、`--root-cause`、`--corrective-action`、`--resolution`、
  `--tags t1,t2`、`--reporter`（默认 `gateway-owner`）、`--session`
- 无 `--finding` 时从 stdin 读取；`--no-review` 仅记录不触发评审（批量导入用）。

### 4.2 触发评审

```bash
python3 L2-infra/components/delivery-quality/review.py          # 全量，落盘 reviews/review-YYYYMMDD.md
python3 L2-infra/components/delivery-quality/review.py --days 14 --json
```

- `--days N`：只看近 N 天（按 `ts` 过滤）
- `--json`：打印结构化结果（`total / by_dim / recurring / open_count`）

### 4.3 前置检索（防重复建设）

```bash
python3 L2-infra/components/config/capability-registry/capability_registry.py --query 质量反馈
```

## 5. 业界对标

| 实践 | 来源 | 本组件对应 |
|---|---|---|
| **Human judgment in the agent improvement loop**：用人工评审 trace 构建 golden dataset，作为未来版本「至少不差于」的基线 | LangChain Blog（<https://www.langchain.com/blog/human-judgment-in-the-agent-improvement-loop>）、LangSmith Evaluation concepts（<https://docs.langchain.com/langsmith/evaluation-concepts>） | 「加黄金 fixture（正例/反例）纳入 pre-commit」正是把人工纠正固化为基线，防止回归 |
| **NIST AI RMF MEASURE 4.1 / 3.3**：识别并文档化「评估与整合终端用户反馈」的方法，纳入持续改进过程 | NIST AI RMF 1.0（<https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf>） | `feedback.jsonl` = 结构化反馈采集，`review.py` = 反馈聚类与复发度量，反哺契约 |
| **OWASP Gen AI Security Project / shift-left**：在开发—部署—管理全生命周期前置安全控制，而非事后补救 | <https://genai.owasp.org/llm-top-10> | 前置 P2 域契约 + checker 门禁（pre-commit），把复发问题拦在提交前 |
| **DoD / ADR Guard（资产生命周期闭环）**：新增资产须先有设计与验收标准，再建设 | `capability-registry/DESIGN.md`（<https://github.com/adr/adr-log> 同类 ADR 工具链） | 本组件自身的 `--lifecycle --require-design` 门禁由 pre-commit step 8 强制 |

> 结论：本组件把「人工反馈」从一次性纠错升级为**可度量、可复现、可门禁**的改进闭环，
> 与业界 agent 评测 / AI 风险治理的「反馈进基线」方向一致。

## 6. 与其他组件的关系

```
delivery-quality（本组件）
   ├── 被调用 ── AGENTS.md §交付质量反馈闭环（Rex 纠正时默认执行 record.py）
   ├── 反哺 ──── P2 域契约 / check_answer_contract.py / 黄金 fixture / docs/knowledge-base
   ├── 被反哺 ── session-boundary-guard（拦截审计写入 state 日志 → 可反哺反馈）
   └── 检索 ──── capability-registry --query（动手前确认能力是否已建成）
```

## 7. 测试与验收

- 数据契约：`SCHEMA.md` 字段与枚举即验收标准。
- 记录器行为：id 自增、时区固定、空 finding 拒绝（`exit 2`）、记录后自动 review、`--no-review` 跳过。
- 评审器行为：`--days` 过滤、复发聚类、高危单次、报告渲染、`--json` 输出。
- 报告溯源链：报告头部含「`feedback.jsonl → review.py → 本报告`」与生成日期。

> 存量红账说明：本组件目前无独立 `tests/` 目录；评审口径由 `README.md` / `SCHEMA.md`
> 与报告样本（`reviews/review-*.md`）共同约束。补测试为已知演进项。

## 8. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 补 `tests/`（record/review 单元测试） | 中 | 资产生命周期要求可执行验收 |
| 反馈与 checker 自动挂钩（promoted → 生成 fixture 骨架） | 中 | promoted 记录累积 ≥10 条 |
| 评审报告纳入资产清单 / 可观测摘要 | 低 | Rex 拍板 |
| 按域/维度做趋势图（复发率下降曲线） | 低 | 反馈量 ≥100 条 |

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-30 | 建立组件（`38bccd0`）：`feedback.jsonl` + `record.py` + `review.py` + `README.md` + `SCHEMA.md`，ADR-035 §4 数据闭环层 |
| 2026-10-30 | 优化时机由每周 cron 改为反馈确认后即时执行（事件驱动，`7057b49`） |
| 2026-11-01 ~ 11-12 | 反馈台账持续入库（BDMS 系列验收反馈），`18cfe8b` 补录 11/6–11/9 历史反馈 |
| 2026-11-20 | 补写根级 `DESIGN.md`：定位 / 设计约束 / 架构 / 接口 / 业界对标 / 变更记录 |
