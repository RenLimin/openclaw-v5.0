# session-boundary-guard — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-11-03 · 关联: ADR-202611-036

## 1. 安装与启动

### 1.1 环境依赖

- OpenClaw Gateway（插件 SDK 兼容 `>=2026.3.24-beta.2`，实测 2026.9.8）
- Node.js ≥ 20（实测 v26.7.0）

### 1.2 安装步骤

```bash
# 1) 插件落盘（managed install --link；写 openclaw.json 走 CLI 保护通道，禁止手改）
openclaw plugins install --link /Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard

# 2) 启用
openclaw plugins enable session-boundary-guard

# 3) 配置（approve 默认；如需硬闸门）
openclaw plugins config session-boundary-guard --set '{"mode":"approve","allowTargets":[],"debug":false}'

# 4) 重载（插件变更后生效）
openclaw plugins reload session-boundary-guard
```

### 1.3 启动/重载

- 插件随 Gateway 启动自动加载（`activation.onStartup: true`）
- 修改源码后：`openclaw plugins reload session-boundary-guard`

### 1.4 健康检查

```bash
# 插件已启用
openclaw plugins list | grep session-boundary-guard
# 应显示 enabled

# 黄金用例回归（纯逻辑零依赖）
cd /Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard
node --test tests/test_classify.js
# 预期: 13 pass / 0 fail

# 审计文件可写
test -w ~/.openclaw/state/session-boundary-guard.jsonl && echo "audit writable"
```

## 2. 操作指南

### 2.1 场景一：确认护栏拦截生效（软闸门 approve 模式）

1. 主会话发起 `sessions_send` 指向 `agent:main:dashboard:*` 会话
2. 预期：弹批准窗（title=「跨会话注入拦截」，allowedDecisions=allow-once/deny）
3. 选择 deny → 调用不生效，目标会话 transcript 无新增
4. 检查审计：`tail ~/.openclaw/state/session-boundary-guard.jsonl` 应出现 `"decision":"approval"` 行

### 2.2 场景二：切换硬闸门（block 模式）

```bash
openclaw plugins config session-boundary-guard --set '{"mode":"block"}'
```

- 预期：`sessions_send` → dashboard 会话直接被拒（blockReason 含「pinned/live」），无批准窗
- 审计出现 `"decision":"blocked"` 行

### 2.3 场景三：合法通知目标放行（allowTargets 白名单）

```bash
openclaw plugins config session-boundary-guard --set '{"mode":"block","allowTargets":["agent:main:dashboard:7c526e0d-eed2-444a-919a-8e6700c1df30"]}'
```

- 预期：指向该 key 的 `sessions_send` 直接放行（不拦截）
- ⚠️ 白名单最小集原则：只加确有合法通知需求的会话，默认留空

### 2.4 场景四：旁路排查（合法路径，不受影响）

```bash
sessions_spawn(mode="run", context="isolated")  # 普通 subagent → 放行
sessions_send → agent:main:subagent:*           # resume 自己 child → 放行
```

## 3. 配置说明

| 配置项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `mode` | `approve` / `block` | `approve` | 软闸门（弹批准）/ 硬闸门（直接拒绝） |
| `allowTargets` | string[] | `[]` | 精确 sessionKey 白名单 |
| `debug` | bool | `false` | 审计记录全部决策（含放行），排查用 |

配置位置：`~/.openclaw/openclaw.json` → `plugins.entries.session-boundary-guard.config`（由 CLI 写入，勿手改）

## 4. 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| 批准窗不出现，调用直接成功 | 插件未启用 / matcher 未生效 | `openclaw plugins list` 确认 enabled；`openclaw plugins reload` |
| Gateway 启动报插件错误 | 源码语法 / SDK 兼容问题 | `node --check index.js`；查 Gateway 日志 |
| 审计文件无内容 | 尚无拦截事件；或 debug=false 不记录放行 | 触发一次拦截验证；排查期开 debug |
| 拦截导致正常流程卡住 | approve 模式误拦了合法调用 | 用 allowTargets 白名单放行该目标；或临时 `mode` 保持 approve 手动 allow-once |
| 升级 OpenClaw 后行为异常 | hook 契约或 key 格式变化 | 跑黄金用例 + E2E 场景回归（VERIFICATION §4） |

## 5. FAQ

### Q1: 为什么用 sessionKey 前缀判断，不查实时状态？
`api.runtime.gateway.request` 拒绝 external plugin 的调用（ADR-036 §3 选项 C 否决），实时状态查询不可行；且 key 前缀是 OpenClaw 稳定契约，`dashboard:` = pinned/live 会话，判据充分。

### Q2: 插件没加载时护栏失效吗？
是 —— matcher 未注册则无拦截。这是配置层问题（不是 fail-closed 违约：hook 自身的 15s 超时仍是拒绝方向）。缓解：健康检查 §1.4 定期验证。

### Q3: 为什么默认 approve 而非 block？
避免误拦合法调用。硬闸门（block）可在 Rex 拍板后随时切换。

### Q4: 审计文件会无限膨胀吗？
不会。超 1MB 自动轮转归档，保留最近 5 份。

## 6. 附录

### 6.1 文件清单

```
L2-infra/components/session-boundary-guard/
├── index.js                  # 插件注册入口（SDK）
├── core.js                   # 纯逻辑（判据/决策/审计，零依赖）
├── package.json              # npm 清单 + openclaw 兼容声明
├── openclaw.plugin.json      # 插件清单 + configSchema
├── README.md                 # 组件说明 + 快速开始
├── PRD-v1.0.md               # 产品需求
├── DESIGN-OUTLINE-v1.0.md    # 概要设计
├── DESIGN-DETAIL-v1.0.md     # 详细设计
├── OPERATIONS-v1.0.md        # 本手册
├── VERIFICATION-v1.0.md      # 验收
└── tests/test_classify.js    # 黄金用例（13 个）
```

### 6.2 审计字段

| 字段 | 说明 |
|---|---|
| `ts` | ISO8601 决策时间 |
| `sourceSessionKey` | 来源会话 |
| `toolName` | sessions_send / sessions_spawn |
| `targetSessionKey` | 目标会话 key |
| `decision` | blocked / approval / allowed / error |
| `mode` | 当前配置模式 |
