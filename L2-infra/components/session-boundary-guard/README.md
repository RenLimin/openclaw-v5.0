# session-boundary-guard — 会话边界护栏

> L2 基础设施层 · 关联 ADR-202611-036 · FB-20261103-03

机制性拦截 agent 将消息/任务注入 pinned/live 会话（`agent:main:dashboard:*`）的跨会话调用，杜绝串台事故复发。

## 快速开始

```bash
# 安装（managed install --link，写 openclaw.json 走 CLI 保护通道）
openclaw plugins install --link /Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard
openclaw plugins enable session-boundary-guard

# 配置（approve 默认；如需硬闸门）
openclaw plugins config session-boundary-guard --set '{"mode":"block"}'

# 验证
openclaw plugins list | grep session-boundary-guard
```

## 工作机制

| 层 | 机制 | 作用 |
|---|---|---|
| 第 1 层 | AGENTS.md「会话隔离铁律」 | 行为规则：旁路排查只能 spawn(isolated) |
| 第 2 层 | session-isolation 任务卡 | 任务身份锚定 |
| 第 3 层 | **本插件** | 技术护栏：想犯错也调不通 |

判据：sessionKey 前缀（稳定契约，不查询实时状态）——

| 目标 key 前缀 | 动作 |
|---|---|
| `agent:*:dashboard:` | **拦截**（approve 弹批准 / block 直接拒绝） |
| `agent:*:subagent:` | 放行（isolated 旁路 / resume 自己 child） |
| `agent:*:main` / `cron:` / `wecom:` | 放行 |

## 配置项

| 字段 | 默认 | 说明 |
|---|---|---|
| `mode` | `approve` | `approve`=软闸门，`block`=硬闸门 |
| `allowTargets` | `[]` | 精确 sessionKey 白名单 |
| `debug` | `false` | 审计记录全部决策 |

## 审计

拦截事件追加写 `~/.openclaw/state/session-boundary-guard.jsonl`（超 1MB 轮转，保留 5 份）。

## 测试

```bash
cd L2-infra/components/session-boundary-guard
node --test tests/
```

## 文档

- [PRD-v1.0](PRD-v1.0.md) · [DESIGN-OUTLINE-v1.0](DESIGN-OUTLINE-v1.0.md) · [DESIGN-DETAIL-v1.0](DESIGN-DETAIL-v1.0.md)
- [OPERATIONS-v1.0](OPERATIONS-v1.0.md) · [VERIFICATION-v1.0](VERIFICATION-v1.0.md)
