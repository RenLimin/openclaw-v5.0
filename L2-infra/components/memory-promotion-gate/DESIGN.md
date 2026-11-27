# DESIGN — memory-promotion-gate

- 版本：v1.0 · 2026-11-27 · Lane C
- 关联：`PRD.md`（需求/验收） · `README.md`（用法）
- 上游铁律：ADR-202608-001（禁改 `/opt/homebrew/lib/node_modules/openclaw/`）

## 1. 背景与根因（诊断结论摘要）

L1 `memory-core` 的 deep 晋升是三重 AND 门槛（`dist/short-term-promotion-DjSWxJDt.mjs:1332-1350`）：
`signalCount>=minRecallCount(3)` 且 `uniqueQueries>=minUniqueQueries(3)` 且 `score>=minScore(0.75)`。
`recallCount` 与 `userQueryHashes` **只**由真实 `memory_search` 命中 short-term 路径时写入
（`short-term-promotion-record-ebH47tOv.mjs:78,149`；调用点 `dist/tools-Cl5BDJQS.mjs:896-904`）。
本机实测 7499 条候选全部 `recalls: 0`、deep 每日 `Ranked 0`，且下调阈值无效（store 无信号条目）。
→ 结论：**纯配置不可解，需 L2 补充累积评分层**。

## 2. 业界最佳实践对照（本仓库强制要求）

| 来源 | 做法 | 本设计取舍 |
|---|---|---|
| RecMem（arXiv 2605.16045） | 以「复现次数 θ_count」驱动 subconscious→episodic 晋升，θ_sim=0.7 聚类 | **采纳**：用跨日出现次数 + 召回命中作为复现信号，而非单次 LLM 置信度 |
| Continual AI《Agent memory consolidation》 | 加权分 = recency + relevance + 结构信号；设晋升 threshold | **采纳**：多信号加权（recalls/days/confidence），设显式门槛 |
| aimemoryworks《Memory Consolidation in AI Agents》 | 晋升四操作：merge / supersede / promote / compress | **部分采纳**：本组件只做 promote + 幂等去重，不重写既有条目 |
| DEV《Why Importance Scoring Changes Everything》 | 默认 importance=0.5，避免全高/全低两极化 | **采纳**：分数需有区分度，禁止恒定值 |
| OpenClaw 官方 Control UI「Dreaming」页 | staged / waiting-for-promotion / promoted 三段可见 | **对齐**：输出保留 staged / would-promote / blocked(high-risk) 三态 |

## 3. 方案总览

```
memory/dreaming/{light,deep}/*.md
        │  ① 解析 - Candidate: 块（snippet/confidence/evidence/recalls/status）
        ▼
   候选归一化 + 指纹（sha1 of normalized snippet）
        │  ② 跨日累积：days_seen / occurrences / evidence 集合
        ▼
   recalls 信号：openclaw memory search --json（每个唯一指纹 ≤N 次探测）
        │  ③ score = w_r*recalls_norm + w_d*days_norm + w_c*confidence + w_o*occ_norm
        ▼
   风险分级（规则集）→ low 可晋升 / high 待确认
        │  ④ 门槛：score>=PROMOTE_MIN_SCORE 且 days_seen>=MIN_DAYS_SEEN
        ▼
   --dry-run 打印 / --apply 幂等追加 MEMORY.md（带 dream-promoted:<hash> 标记）
```

### 关键设计决策
- **幂等**：写入段落带稳定标记 `<!-- dream-promoted: <sha1前12位> -->`；`--apply` 前先扫描既有标记，命中即跳过。重复运行 diff 必须为空。
- **fail-closed**：若 `candidates_with_recalls == 0`，`--apply` 拒绝写入并返回非零退出码（exit 2），避免「静默空转」。
- **不写 L1 存储**：recalls 由本组件独立探测得到，落盘于组件自有 `state/scores.json`，不触碰 plugin-state SQLite。
- **限速**：`memory_search` 冷启动 embedding 服务约 2–3s，逐条探测成本高 → 采用「按指纹批量去重 + 每指纹一次查询 + TTL 缓存」；查询失败降级为 0 并记录，不阻断整体。

## 4. 评分公式（默认权重，可被 CLI 覆盖）

```
recalls_norm    = log1p(recalls) / log1p(6)
days_norm       = min(days_seen, 7) / 7
occ_norm        = min(occurrences, 10) / 10
avg_confidence  = mean(light confidence, clip 0..1)

score = 0.40 * recalls_norm
      + 0.25 * days_norm
      + 0.20 * avg_confidence
      + 0.15 * occ_norm
```

门槛：`PROMOTE_MIN_SCORE = 0.30`，且 `days_seen >= 2`（与 RecMem θ_count 复现思想一致，
避免单日噪声直接晋升）。高风险候选无论分数一律不自动写入。

## 5. 风险分级规则（可解释、可审计）

**high-risk 命中任一即拦截**：
- 凭据类：`password|passwd|token|secret|api[_-]?key|cookie|credential|私钥`
- 财务契约类：`合同金额|付款|发票|税率|对公账户|银行账号|授信|结算账户|金额[：:]\s*\d`
- 身份类：`身份证|护照|手机号|银行卡|身份证号`
- 敏感动作类：`不可逆|force[- ]?push|删除生产|drop table`

**low-risk（白名单语义，优先晋升）**：
- 命名/口径：`命名|口径|约定|术语|规范`
- 模板：`模板|template|版式`
- 流程：`流程|步骤|顺序|SOP`
- 工具/命令：`命令|CLI|脚本|入口`

其余归 `medium`：达到门槛仍可晋升（low/medium 均允许自动写入），high 仅输出待确认清单。

## 6. 数据模型（`state/scores.json`，组件私有）

```json
{
  "version": 1,
  "updatedAt": "ISO8601",
  "candidates": {
    "<fingerprint>": {
      "snippet": "...", "confidence": 0.62, "days_seen": ["2026-11-26","2026-11-27"],
      "occurrences": 2, "recalls": 3, "score": 0.51, "risk": "low", "evidence": ["path:l-l"]
    }
  }
}
```

## 7. 边界与失败模式

| 场景 | 处理 |
|---|---|
| `openclaw` 不在 PATH | 用 `/opt/homebrew/bin/openclaw` 绝对路径兜底（遵循 AGENTS.md 定时任务红线） |
| embedding 服务未起 | 首次调用自动拉起（官方行为）；超时/失败 → recalls=0 并计入 `degraded` |
| 无任何候选带 recalls | fail-closed：`--apply` exit 2，不写 MEMORY.md |
| MEMORY.md 不存在 | `--apply` 报错退出，不自动创建 |
| 候选 snippet 含高危片段 | 归 high，不写入，进待确认清单 |

## 8. 测试策略

- `tests/test_parser.py`：候选块解析、跨日累积、指纹稳定性
- `tests/test_scoring.py`：权重/门槛边界、恒定置信度不得导致恒分（反两极化断言）
- `tests/test_risk.py`：分级规则正/负例
- `tests/test_idempotent.py`：dry-run→apply→再 apply，MEMORY.md diff 为空（真实文件副本上跑）
- `tests/test_fail_closed.py`：无 recalls 时 `--apply` 非零退出且不写盘
- 全部为本地文件操作，不打网络（召回探测在测试中注入 fake search 函数）
