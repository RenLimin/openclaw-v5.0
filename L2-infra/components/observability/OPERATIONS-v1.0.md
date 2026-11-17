# observability — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
python3 agent_observer.py --daily --jsonl
python3 memory_search_monitor.py
```

### 健康检查

```bash
python3 L2-infra/components/observability/scripts/agent_observer.py --health
```

## 操作指南

### 场景一：每日观测

```bash
python3 L2-infra/components/observability/scripts/agent_observer.py --daily
```

### 场景二：记忆检索监控

```bash
python3 L2-infra/components/observability/scripts/memory_search_monitor.py
```

## 配置说明

- 日志: 结构化 JSON
- 指标: 计数器/直方图/计时器

## 故障排查

### 日志丢失

- **症状**: 部分日志缺失
- **原因**: 日志级别过滤
- **解决**: 检查日志级别配置

---

# Channel 主动恢复（v1.0 · 2026-11-17）

> 详见 `DESIGN-DETAIL-channel-recovery-v1.0.md`

## 用途

检测 WeCom channel「断连且未自愈」，主动重启该 channel（轻量 RPC，不重启 gateway）。

## 命令

```bash
# 只读判定（不动作）
python3 L2-infra/components/observability/scripts/channel_recovery.py --check

# 查看内部状态
python3 L2-infra/components/observability/scripts/channel_recovery.py --status

# 调度入口（launchd 每 5min 自动调用）
python3 L2-infra/components/observability/scripts/channel_recovery.py --recover

# 完整看门狗（进程 + 端口 + 恢复）
bash L2-infra/components/observability/gateway_watchdog.sh
```

## 日志

```bash
tail -f L2-infra/components/observability/logs/channel-recovery.log   # JSONL
tail -f L2-infra/components/observability/logs/gateway-watchdog.log   # 看门狗
```

## 开关与阈值（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `OPENCLAW_WATCHDOG_RECOVERY` | `1` | 设 `0` 关闭恢复（仅观测） |
| `CHANNEL_RECOVERY_CHANNEL` / `_ACCOUNT` | `wecom` / `default` | 目标 channel |
| `CHANNEL_RECOVERY_STABLE_SECONDS` | `600` | 断连多久才介入 |
| `CHANNEL_RECOVERY_COOLDOWN_SECONDS` | `600` | 两次恢复最小间隔 / lastStartAt 新鲜守卫 |
| `CHANNEL_RECOVERY_MAX_LIGHT_PER_DAY` | `5` | 每日轻量恢复上限 |
| `CHANNEL_RECOVERY_VERIFY_TIMEOUT` | `45` | 恢复后等鉴权成功的超时 |

## 回滚

```bash
# 关闭恢复（保留观测）
launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway-watchdog.plist
launchctl load   ~/Library/LaunchAgents/ai.openclaw.gateway-watchdog.plist
```

## 故障排查

| 症状 | 排查 |
|---|---|
| 判定长期 `down` 但实际已恢复 | 检查 `channel_recovery_state.json` 的 `log_offset` 是否落后；确认 gateway.log 路径 |
| 一直 `stale` | streak 未清零（无 `Authentication successful`）；或日志无新行 |
| 恢复后仍失败 | 看 `channel-recovery.log` 的 `recovery.light.failed` 详情；连续 2 次会升级全量 |
| `another instance is running` | 锁未释放：`rm logs/channel_recovery.lock` |

## 电源与睡眠（第 1 层 · 未启用，仅记录）

> 本层是**根因预防**，需 sudo，默认不做。第 2 层（channel 恢复）是兜底。

### 现状（2026-11-17 实测）

```bash
pmset -g custom
```

| 电源 | `sleep` | 说明 |
|---|---|---|
| AC Power | **0** | 插电已抑制「闲置睡眠」——无需变更 |
| Battery Power | 1 | 保持不动，保护电池 |

其他相关：`ttyskeepawake 1`、`tcpkeepalive 1`、`hibernatemode 3`、`womp` AC=1 / Batt=0、`displaysleep 0`。

### 关键结论：`sleep 0` 挡不住合盖睡眠

- `sleep 0` 只抑制**闲置（idle）睡眠**。
- 断连根因是 `Entering Sleep state due to 'Clamshell Sleep'`——**合盖动作触发**，`sleep 0` 不抑制。
- 真正能压住合盖睡眠的是 `sudo pmset -b disablesleep 1`（或 `-a`）。它会连合盖都不睡，影响散热/电池，需人工拍板。

### 排查命令

```bash
pmset -g custom              # 当前设置
pmset -g ps                  # 当前电源（AC / Battery）
pmset -g log | grep -i "clamshell\|Sleep"   # 历史睡眠原因
```

### 与第 2 层的关系

| 层 | 手段 | 作用 | 状态 |
|---|---|---|---|
| 1 | `pmset` 防睡眠 | 预防冻结 | 未启用（需 sudo） |
| 2 | channel 主动恢复 | 冻结唤醒后自动恢复 WeCom | ✅ 已交付 |
| 3 | DNS 备用 | 唤醒瞬间 DNS 缓冲 | 人工已生效 |

> 未做第 1 层 ⇒ 冻结仍会发生；第 2 层负责「发生后自动恢复」。
