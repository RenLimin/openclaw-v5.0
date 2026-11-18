# context-guardian 修复版 — 操作手册 (OPERATIONS)

## 1. 安装

本插件随 workspace 托管，无需额外安装；仅需让 host 通过 `plugins.load.paths` 选中本目录。

### 1.1 前置检查

```bash
# 确认本目录存在且 manifest 合法
ls -l L2-infra/components/context-guardian/{index.js,core.js,openclaw.plugin.json,package.json}

# 单测
cd L2-infra/components/context-guardian && node --test tests/test_core.js
```

### 1.2 备份

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.ctxguardian-v6-$(date +%Y%m%d-%H%M%S)
```

## 2. 启动 / 启用

### 2.1 配置变更（两步）

```bash
cd ~/.openclaw/workspace

# ① 将本目录加入 load.paths（config-selected → 最高优先级，shadow 上游 v5.1.1）
openclaw config patch --stdin <<'JSON5'
{ plugins: { load: { paths: [
  "/Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard",
  "/Users/bangcle/.openclaw/workspace/L2-infra/components/context-guardian",
] } } }
JSON5

# ② 会话访问授权 + 阈值对齐 host 上限
openclaw config patch --stdin <<'JSON5'
{ plugins: { entries: { "context-guardian": {
  enabled: true,
  hooks: { allowConversationAccess: true },
  config: {
    effectiveContextWindow: 196608,
    microCompactMaxChars: 3000,
    warnThreshold: 0.3,
    debug: true,
  },
} } } }
JSON5
```

> **注意**：`microCompactMaxChars` 必须 < host 持久化 cap（当前 32000）。host cap = `min(floor(ctx×0.3)×4, 分档hardCap)`，与插件配置无关；`8014` 只是插件自身 `maxToolResultChars=8000` 的告警值，不是 host 上限。

### 2.2 热加载

```bash
# 只用不带 --wait 的形式（60s drain 预算，超时快速失败）
# 活跃 turn 存在时严禁 --wait（会持全局锁阻断所有新 turn）
openclaw plugins reload context-guardian --json
```

### 2.3 回滚

```bash
# 从 load.paths 移除本目录，恢复上游 v5.1.1
openclaw config patch --stdin <<'JSON5'
{ plugins: { load: { paths: [
  "/Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard",
] } } }
JSON5
openclaw plugins reload context-guardian --json
```

## 3. 故障排查

| 现象 | 排查 |
|---|---|
| 未出现 `v6 loaded` | `openclaw plugins list` 看是否两个 manifest 冲突；确认 load.paths 含本目录 |
| 出现 `blocked because non-bundled` | `plugins.entries.context-guardian.hooks.allowConversationAccess` 未生效；确认 patch 已写入且新代际已加载 |
| 日志有 `Micro-compacted` 但 transcript 无变化 | 仍在跑 v5 代际（reload 未生效）；看 `Plugin replacement applied` 时间戳 |
| 压缩不触发 | 检查 `microCompactMaxChars` 是否 > host 上限；看 `Persist-compressed` 日志 |
| 会话状态内存增长 | 确认 `MAX_TRACKED_SESSIONS=200` 生效（v5 无上限） |

## 4. 维护

- 修改 `core.js` 后必须重跑单测
- 修改后通过 `plugins reload` 生效；验证方式见 VERIFICATION
- 上游 `openclaw plugins update` **不会**覆盖本目录（load.paths 优先级最高）
- 定期确认 `debug` 已改回 `false`（验证完成后）
