# memory-promotion-gate — 记忆晋升门禁

## 用途

解决 OpenClaw `memory-core` nightly dreaming 的**晋升死锁**：
L1 要求候选同时满足 `signalCount>=3`、`uniqueQueries>=3`、`score>=0.75`，
而 `recallCount`/`userQueryHashes` 只由真实 `memory_search` 命中累积；
一旦从未被召回命中就永远排不上序 → `Ranked 0` / `Promoted 0`，`MEMORY.md` 长期零新增。

本组件作为 **L2 补充晋升通道**：以 `memory_search` 命中次数为 recalls 信号，
对 `memory/dreaming/{light,deep}/*.md` 候选做跨日累积评分，低风险候选幂等晋升入 `MEMORY.md`，
高风险候选只输出待确认清单。

> 不修改 L1 插件（ADR-202608-001）；不直接写 L1 的 plugin-state SQLite。

## 用法

```bash
cd /Users/bangcle/.openclaw/workspace

# 干跑（默认，不写盘）
python3 L2-infra/components/memory-promotion-gate/scripts/promote.py --dry-run

# 查看统计
python3 L2-infra/components/memory-promotion-gate/scripts/promote.py --stats

# 实际晋升（fail-closed：无 recalls 信号时退出码 2，不写 MEMORY.md）
python3 L2-infra/components/memory-promotion-gate/scripts/promote.py --apply
```

可选参数：
```
--workspace <dir>      工作区根目录（默认自动探测）
--min-score <float>    晋升门槛（默认 0.30）
--min-days <int>       最少跨日出现天数（默认 2）
--max-results <int>    recall 探测每次查询返回条数（默认 5）
--json                 机器可读输出
--no-probe             跳过 memory_search 召回探测（仅用跨日频次评分）
```

## 输出示例（dry-run）

```
[memory-promotion-gate] candidates=7499 unique=6628 with_recalls=...
would promote 5 into MEMORY.md
blocked (high-risk) 3  -> 见 pending-review.json
```

## 幂等保证

写入段落格式：
```
<!-- dream-promoted: <fingerprint12> -->
- <snippet>  (evidence: path:line-line)
```
重复运行先扫描既有标记，同指纹即跳过。验收：连续两次 `--apply` 后 `git diff MEMORY.md` 为空。

## 文件结构

```
memory-promotion-gate/
├── DESIGN.md / PRD.md / README.md
├── scripts/promote.py        # CLI
├── state/scores.json         # 组件私有评分状态（gitignore）
├── logs/                     # 运行日志
└── tests/                    # pytest
```

## 验收指标（fail-closed）

`promoted > 0` 且 `candidates_with_recalls > 0` 才算生效；否则 `--apply` 非零退出且不写盘。
