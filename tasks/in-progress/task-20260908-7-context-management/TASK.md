# 上下文管理缺口全覆盖

## 任务说明

根据 ADR-202608-018 上下文管理设计，补齐所有设计要求的覆盖缺口，实现完整的会话上下文治理。

ADR-018 原设计缺口：
1. compaction 配置为空对象 `{}` → 需要补全所有配置
2. session pruning 因 provider 白名单限制不生效 → 需要用会话生命周期 cron 替代
3. subagent 上下文保护规范需要固化到 AGENTS.md

## 验收标准

1. 补全 compaction 所有配置：mode/size/midTurnPrecheck/model委托等
2. 会话生命周期管理 cron 正常运行，替代原设计 session pruning
3. 完整的 subagent 上下文保护规范写入 AGENTS.md
4. `subagent_ctx_guard.py` 实现并验证工作正常
5. 所有覆盖缺口全部完成

## 进度与结果

### Goals 完成情况

| ID | Description | Status |
|----|-------------|--------|
| g1 | 补齐 compaction 配置 | ✅ 完成 |
| g2 | 补齐会话生命周期替代 session pruning | ✅ 完成 |
| g3 | 固化 subagent 上下文保护规范到 AGENTS.md | ✅ 完成 |
| g4 | 验证所有缺口已覆盖 | ✅ 完成 |

### 交付结果

| 项目 | 位置 | 完成情况 |
|------|------|----------|
| compaction 完整配置 | `openclaw.json` | ✅ 配置完成：<br/>  - mode: safeguard<br/>  - keepRecentTokens: 30000<br/>  - maxActiveTranscriptBytes: 400kb<br/>  - midTurnPrecheck enabled: true<br/>  - compaction.model: coding-plan/deepseek-v4-flash<br/>  - memoryFlush.model: coding-plan/doubao-seed-2-1-turbo<br/>  - 各模型水位阈值已按 ADR 要求配置 |
| 会话生命周期管理 cron | job ID: `2f7846b7-f4da-4d3e-b3bf-e7036bb80e4a` | ✅ 每日 02:00 运行，lastRunStatus: ok |
| `subagent_ctx_guard.py` 辅助脚本 | `L2-infra/components/context-management/` | ✅ 实现完成，验证工作正常：<br/>  输入任务描述和预估步数 → 输出分段策略和 token 预算 |
| AGENTS.md 规范固化 | `AGENTS.md` | ✅ 完整写入：<br/>  - 长任务隔离规则<br/>  - 主会话三层防护<br/>  - Subagent 上下文保护规范<br/>  - 多会话并行建设规范<br/>  - 异常自动处置规则 |

### 验证结论

所有覆盖缺口已全部补齐，符合 ADR-018 设计要求。

## 最终结论

任务已完成，所有缺口覆盖。

---
<!-- project: github.com/RenLimin/openclaw-v5.0 -->
