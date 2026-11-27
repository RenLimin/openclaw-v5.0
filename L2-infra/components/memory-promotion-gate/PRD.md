# PRD — memory-promotion-gate（记忆晋升门禁）

- 版本：v1.0 · 2026-11-27 · 作者：Lane C（诊断重跑）
- 关联：`DESIGN.md` / `README.md` / `tests/` / Lane A registry 合并项
- 状态：设计已定稿，待评审后实施（本仓库铁律：先设计后代码）

## 1. 背景与问题

OpenClaw `memory-core` 插件的 nightly dreaming（cron `Memory Dreaming Promotion`，每天 03:00）
连续多日产出固定结果：

- `memory/dreaming/deep/*.md`：`Ranked 0 candidate(s)` / `Promoted 0 candidate(s) into MEMORY.md`
- `memory/dreaming/light/*.md`：每日 100 条候选全部 `status: staged`；累计 7499 条 staged / 0 promoted
- `MEMORY.md` mtime 停在 2026-11-17，长期零新增

### 根因（已在 Lane C 阶段 1 定位，证据见 `/tmp/lane_c_diag.md`）

L1 晋升判据为**三重 AND 门槛**（`dist/short-term-promotion-DjSWxJDt.mjs:1332-1350`）：

1. `signalCount = recallCount + dailyCount + groundedCount`，要求 `> 0` 且 `>= minRecallCount(默认 3)`
2. `uniqueQueries = len(userQueryHashes)`，要求 `>= minUniqueQueries(默认 3)`
3. `score >= minScore(默认 0.75)`

其中 `recallCount` 只能由 **真实 `memory_search` 命中 short-term 路径**（`memory/YYYY-MM-DD.md`、
`memory/.dreams/session-corpus/*`）累积（`short-term-promotion-record-ebH47tOv.mjs:78-149`，
调用点 `dist/tools-Cl5BDJQS.mjs:896-904`）；`userQueryHashes` **只**在 `signalType === "recall"` 时写入
（同文件 :149）。daily/grounded 信号不写 `userQueryHashes`。

→ 若从未发生「用户查询命中该短期条目」，则 `recallCount=0` 且 `uniqueQueries=0`，**两个门槛同时死锁**：
候选永远进不了 deep 排序，也就永远不会被晋升；不晋升就永远不会被后续查询命中——自锁闭环。

### 为何不能纯配置解决

阈值全在 `plugins.entries.memory-core.config.dreaming.phases.deep.*`，可下调
（`minRecallCount`/`minUniqueQueries`/`minScore`）。但 store 中根本没有带信号的条目：
`signalCount <= 0` 的候选在排序第一步即被 `continue`，**改阈值无效**（候选集为空）。
本机实测 light 报告 7499 条全部 `recalls: 0`，证实该链路未产生信号。
硬约束 ADR-202608-001：禁改 `/opt/homebrew/lib/node_modules/openclaw/`。

## 2. 目标与非目标

### 目标（做成定义）
1. 以 **`memory_search` 命中次数作为 recalls 信号**，对 `memory/dreaming/{light,deep}/*.md` 候选做累积评分，
   使 `confidence` 可随时间增长（打破恒 0.58/0.62）。
2. 分级门槛：
   - **低风险**（命名/口径/模板/流程类）→ 可自动晋升入 `MEMORY.md` 或对应 `SKILL.md`
   - **高风险**（契约/财务/身份/凭据）→ 只输出待确认清单，不自动写入
3. 幂等：重复运行不产生重复段落（重复运行前后 `MEMORY.md` diff 为空）。
4. CLI：`--dry-run`（默认）/ `--apply` / `--stats`。
5. fail-closed 验收：`promoted > 0` 且 `recalls` 非零才算生效。

### 非目标
- 不修改、不旁路 L1 `memory-core` 插件任何文件
- 不直接写 L1 的 plugin-state SQLite（召回存储归 L1 所有）
- 不替代 nightly dreaming；本组件是**补充晋升通道**
- 不处理会话压缩/快照（另有组件）

## 3. 功能需求

| # | 需求 | 优先级 |
|---|---|---|
| F1 | 解析 `memory/dreaming/{light,deep}/*.md` 中 `- Candidate:` 块（snippet/confidence/evidence/recalls/status） | P0 |
| F2 | 对每条候选提取文本指纹（归一化 snippet hash），跨日累积出现天数 `days_seen`、历史出现次数 `occurrences` | P0 |
| F3 | 用 `openclaw memory search --json` 对候选做召回探测，命中数计入 `recalls`（限定 `source==="memory"` 且路径在 workspace 内） | P0 |
| F4 | 综合分 `score = w1*recalls_norm + w2*days_seen_norm + w3*avg_confidence + w4*occurrence_norm`；默认权重见 DESIGN §4 | P0 |
| F5 | 风险分级：关键词/正则规则集把候选分为 low / high；high 只进待确认清单 | P0 |
| F6 | `--dry-run` 输出将晋升/待确认清单（默认，不写盘） | P0 |
| F7 | `--apply` 幂等写入 `MEMORY.md`（追加带 `<!-- dream-promoted: <hash> -->` 标记段落）；已有同 hash 标记则跳过 | P0 |
| F8 | `--stats` 输出计数（候选数/唯一数/有信号数/待晋升/高风险拦截） | P0 |
| F9 | 真实运行验证：`--dry-run` 与 `--apply` 各一次，对比 `MEMORY.md` diff | P0 |

## 4. 验收标准（怎么算做成）

1. `--dry-run` 输出包含 `would promote N` 且 N>0（基于真实数据）
2. `--apply` 后 `MEMORY.md` 新增段落均带 `dream-promoted` 标记，条数 == dry-run 的 N
3. 再次 `--apply`：`MEMORY.md` **零变化**（幂等，diff 为空）
4. `--stats` 显示 `candidates_with_recalls > 0`
5. `pytest tests/` 全绿（含 fail-closed：无 recalls 时必须报错或 0 晋升）

## 5. 边界与风险

- `memory_search` 依赖本地 embedding 服务（llama-cpp），冷启动约 2–3s；批量查询需限速/缓存
- 高风险关键词误判 → 宁可漏晋升（fail-closed），不可误写入
- 候选 snippet 含敏感信息（凭据片段）时必须落入 high-risk，且不写入任何自动输出之外的位置
- `MEMORY.md` 写入采用**追加式**，不重写既有条目（避免 L1 consolidation 冲突）
