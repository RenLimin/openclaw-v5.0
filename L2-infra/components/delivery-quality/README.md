# delivery-quality：交付质量反馈闭环

> 归属 L2 基础设施 · ADR-035 Prompt 治理体系「数据闭环层」· 2026-10-30 建立

把 Rex 对交付结果的**问题反馈/纠正**默认沉淀为结构化记录，定期聚类 review，把复发/高危问题反哺到知识库、黄金 fixture、P2 契约，持续提升技能返回准确率。

## 闭环

```
Rex 反馈/纠正
   │  （默认行为，见 AGENTS.md 交付质量反馈铁律）
   ▼
record.py ──► feedback.jsonl（git-tracked JSONL，每行一条）
   │
   ▼  每次反馈确认（record 记录）后立即自动触发 review（事件驱动，无 cron）
review.py ──► reviews/review-YYYYMMDD.md（只读建议，不改核心文件）
   │           · 按维度/域/严重度分布
   │           · 复发根因（≥2 次）
   │           · 高危单次项（high 首次即评估，不等复发）
   ▼  Rex 拍板
   ├─ 收紧 P2 域契约「维度合格判据」+ 加 check_answer_contract.py 校验
   ├─ 加黄金 fixture（正例/反例）纳入 pre-commit
   ├─ 沉淀 docs/knowledge-base 文档
   └─ wontfix（须在 resolution 写明理由）
```

## 为什么用 JSONL 而非 SQLite

质量反馈需 git 版本化、可 diff、可 grep、跨会话不丢；量级小（人因反馈，非高频遥测）。规避 MEMORY 教训「SQLite DB 重制全丢」。

## 用法

### 记录反馈（收到纠正时默认执行）

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

- `--domain`：project / contract / product / cross / other
- `--dimension`：见 `SCHEMA.md`（data_fidelity / calculation_logic / data_completeness / missing_risk_analysis / missing_context / best_practice_gap / sourcing / format_presentation / other）
- `--severity`：high / medium / low（对结论正确性的影响）
- `--status`：open（默认）/ corrected / promoted / wontfix
- id 自动生成 `FB-YYYYMMDD-NN`，时间自动打 Asia/Shanghai

### 触发时机（事件驱动，非 cron）

- **默认**：每次 `record.py` 记录一条反馈后，**立即自动**跑一次 review（即"确认反馈→即优化"）。
- 批量导入历史反馈时用 `--no-review` 只记录不触发，导完手动跑一次。
- 手动跑：

```bash
python3 L2-infra/components/delivery-quality/review.py          # 全量，落盘报告
python3 L2-infra/components/delivery-quality/review.py --days 14 --json
```

## 升级判据

| 信号 | 处置 |
|---|---|
| 同根因复发 ≥2 次 | 系统级升级（P2 契约 + checker + fixture） |
| high 严重度首次出现 | review 即提示评估，不必等复发 |
| 仅 medium/low 单次且已纠正 | 留痕观察，不立即改核心 |
| 判为不处理 | wontfix + resolution 写明理由 |

## 边界

- review **只生成报告和建议**，不自动改 P2/技能/KB（遵循「巡检只报告，action 走拍板」原则）。
- 不记录凭据/敏感身份；finding 用问题描述，不贴原始敏感数据。
- feedback.jsonl 入库 git；reviews/ 为派生报告。
