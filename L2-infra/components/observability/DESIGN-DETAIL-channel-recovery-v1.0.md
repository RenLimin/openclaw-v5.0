# Channel 主动恢复 — 详细设计 (DESIGN-DETAIL)

> 组件：observability (L2) · 模块：channel_recovery（第 2 层兜底）
> 版本：v1.0 · 日期：2026-11-17 · 状态：已通过 Rex 评审（2026-11-17 14:28）

## 1. 背景与问题

2026-11-17 08:11–10:28，WeCom 断连 **2h17m**。证据链：

| 证据 | 内容 |
|---|---|
| 进程冻结 | `[health] host timing gap detected: process was frozen ~935743ms`（15.6min） |
| 睡眠 | `Entering Sleep state due to 'Clamshell Sleep' ... Using Batt`（合盖睡眠） |
| 断连时序 | 08:11:29 DarkWake → 08:11:32 `ENOTFOUND` → 08:11:31 又睡回 → 08:28 再唤醒 |
| 内置恢复失效 | `host thaw channel restart deferred: gateway still has active work`（累计 2342 次） |

**根因**：合盖睡眠 → 进程冻结 → 唤醒后网络/DNS 未恢复 → WeCom 重连阶梯耗尽。DNS 是**次生现象**，不是根因。

**既有机制缺口**（实测）：

1. gateway 内置 `host thaw channel restart` 是 **defer 语义**：gateway 忙则让位，10min 后放弃 → 长期不落地。
2. `health-monitor`（300s 间隔）只在 `giving up after 10 restart attempts` 后接管；今天 **0 次触发**（自动重启阶梯不断重置 ladder，永远到不了 gave-up）。
3. 现有 `gateway_watchdog.sh` 只观测进程 + 端口，**不处理 channel**；且端口检查写死 `3000`（实际 `18789`）→ 1265 次假阳性。

**结论**：需要独立的第三层兜底——检测到 channel 持续未自愈 → 主动重启该 channel。

## 2. 目标 / 非目标

**目标**

- G1 检测 WeCom channel 处于「断连且未自愈」状态
- G2 分级恢复：轻量（`channels.stop` + `channels.start` 单 channel）→ 兜底（`safe_restart.sh`）
- G3 节流与防抖动，避免反复重启
- G4 修复 watchdog 既有缺陷（端口、死变量）

**非目标**

- ❌ 不修改系统睡眠设置（第 1 层，Rex 已否决）
- ❌ 不修改 `openclaw.json`
- ❌ 不与 gateway 内置 thaw / health-monitor 抢（只在其失败后兜底）
- ❌ 不做通用多 channel 框架（当前服务 `wecom/default`，channel/account 可环境变量覆盖）
- ❌ 不做对外通知（告警只落本地日志）

## 3. 架构

```
launchd: ai.openclaw.gateway-watchdog (StartInterval=300)
  └─ gateway_watchdog.sh
       ├─ 进程存活检查（pgrep）
       ├─ 端口探针（读 gateway.port，默认 18789）
       └─ python3 scripts/channel_recovery.py --recover
            ├─ channels.status (RPC)  → 交叉校验 + lastStartAt 守卫
            ├─ gateway.log 增量解析   → 状态机
            ├─ 判定 → 轻量 / 全量 / 仅告警
            └─ 写 state + JSONL 日志
```

**薄编排**：不重写既有逻辑。检测用 gateway 既有日志与 RPC；恢复复用既有 `safe_restart.sh`（含 pre-restart guard）。

## 4. 接口契约

### 4.1 CLI

| 命令 | 语义 | 退出码 |
|---|---|---|
| `--recover` | 检测并按需恢复（launchd 调用） | 0 正常/已恢复；2 gateway 不可达；3 恢复失败 |
| `--check` | 只判定不动作（人工验证） | 0 |
| `--status` | 打印内部状态 JSON | 0 |

### 4.2 依赖的既有能力

| 能力 | 用途 | 实测 |
|---|---|---|
| `openclaw gateway call channels.status --json` | channel 状态 + `lastStartAt` | ✅ 可用（需 PATH 注入） |
| `openclaw gateway call channels.stop` / `channels.start` | 单 channel 重启 | ✅ stop→start 后 3s 内 `Authentication successful` |
| `safe_restart.sh` | 全量兜底（含 guard） | ✅ 既有组件 |

### 4.3 环境约束

launchd 环境 `PATH=/usr/gnu/bin:/usr/local/bin:/bin:/usr/bin`，**无 `/opt/homebrew/bin`** →
裸调用 `openclaw` 报 `env: node: No such file or directory`（rc=127）。
脚本必须：① 用绝对路径 `/opt/homebrew/bin/openclaw`；② 向子进程注入 `/opt/homebrew/bin:/opt/homebrew/sbin` 到 PATH 前。

## 5. 状态机与判定

### 5.1 事件（增量解析 gateway.log）

| 事件 | 匹配 | 是否开启断连 streak |
|---|---|---|
| `auth_ok` | `Authentication successful` | 否（清零） |
| `conn_lost` | `Connection lost` / `WebSocket disconnected` | ✅ 是 |
| `gave_up` | `giving up after 10 restart attempts` / `Max reconnect attempts reached` | ✅ 是 |
| `reconnect` | `Connecting to WebSocket` | ❌ 否（见下） |

> **`reconnect` 不计入失败**：正常建连流程中 `Connecting to WebSocket` 会紧跟
> `Authentication successful` 之后打印。若计入 streak，健康期会被误判 `down`。
> 该事件仅用于「最近是否有活动」与 stale 判定。

### 5.2 判定（基于断连 streak，非「距上次鉴权时长」）

`down_since` = 本次断连 streak 起点（首个 `conn_lost`/`gave_up`，`auth_ok` 清零）。

```
down_since is None            → up            （自上次鉴权后无失败；安静是正常态）
now - down_since < STABLE     → down-unstable （给内置重连阶梯留机会）
now - last_event > STALE      → stale         （streak 中但日志静默，无法确认）
否则                           → down          （需恢复）
```

**为何不基于「距上次鉴权时长」**：长连接（如 00:59–08:11 稳定 7h）一旦断连，
按该口径会立刻判 `down`，与内置重连阶梯抢跑。

**日志不可用时的降级**：用 `channels.status` 的 `running=false` 或 `lastError` 非空，连续 2 个 tick → `down`。

### 5.3 为什么 `running` 不能作主信号

实测：断连期间 `channels.status` 仍报 `running=true`（插件进程活着、socket 已死）。
故 `running` 只用于**守卫**（`lastStartAt` 新鲜则不抢），不作检测主信号。

## 6. 数据模型

状态文件：`L2-infra/components/observability/logs/channel_recovery_state.json`

```json
{
  "version": 1,
  "log_offset": 12345678,
  "last_auth_ok": 1794882516.0,
  "last_conn_lost": 1794896250.0,
  "last_gave_up": null,
  "last_reconnect": 1794896250.0,
  "last_recovery_at": null,
  "last_recovery_kind": null,
  "light_day": "2026-11-17",
  "light_count": 0,
  "consecutive_light_failures": 0,
  "status_down_streak": 0
}
```

- 首次运行：从 EOF 回扫 `SEED_BYTES=8MB` 播种状态，`log_offset` 设为 EOF；之后增量读取。
- 日志 shrink/轮转（`size < offset`）：回退到 EOF 回扫 8MB。
- 并发保护：`logs/channel_recovery.lock` + `fcntl.flock(LOCK_EX|LOCK_NB)`。

## 7. 节流与安全

| 规则 | 值 | 目的 |
|---|---|---|
| 稳定期 | 600s | 容忍瞬时抖动与正常重连 |
| 冷却期 | 600s | 两次恢复最小间隔 |
| 每日轻量上限 | 5 次 | 防抖动循环 |
| 连续轻量失败 | ≥2 次 → 升级全量 | 小手段无效才动大手段 |
| 超限后 | 仅告警，不再自动动作 | 避免无人值守反复重启 |
| 新鲜守卫 | `lastStartAt` 600s 内不抢 | 不与内置 thaw/health-monitor 冲突 |

**恢复失败判定**：轻量恢复后 `VERIFY_TIMEOUT=45s` 内未出现 `Authentication successful` → 记为失败。

**告警**：写 `logs/channel-recovery.log`（JSONL）+ stdout（进入 `gateway-watchdog.log`）。

## 8. 测试方案

| 层 | 内容 |
|---|---|
| 单元 | PATH 注入；事件解析（播种/增量/轮转重置）；`evaluate` 四态转换；节流守卫；动作决策；端口解析回退 |
| 回归 | 用真实 `gateway.log` 片段离线回放，验证：08:11–09:15 窗口判 `down`，09:15 恢复后判 `up`，健康期不误报 |
| 冒烟 | 组件目录/文件存在（既有 `test_smoke.py`） |
| 人工 | `--check` 在线只读验证；观察一个 5min tick |

**黄金基准**：回放 2026-11-17 真实日志，期望：08:21 左右首次判 `down`，09:15 后转 `up`，其余时段不触发。

## 9. 操作手册

```bash
# 手动只读检查
python3 L2-infra/components/observability/scripts/channel_recovery.py --check

# 查看内部状态
python3 L2-infra/components/observability/scripts/channel_recovery.py --status

# 日志
tail -f L2-infra/components/observability/logs/channel-recovery.log
```

**回滚**：`launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway-watchdog.plist`（脚本无状态破坏性操作）。

## 10. 变更记录

- 2026-11-17：v1.0 创建；修复 watchdog 端口（3000→配置值）与 `LOG_FILE` 死变量。
