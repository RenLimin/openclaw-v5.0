# observability

**定位：** L2 基础设施层 — 系统可观测性（会话监控、Provider 健康探测、每日摘要）。

## 功能列表

- 会话快照与每日摘要（token 用量/状态/时序）
- Gateway 健康检查（进程存活 + 端口响应，端口读 `gateway.port`）
- **Channel 主动恢复兜底**（检测断连未自愈 → 单 channel 重启，见 DESIGN-DETAIL-channel-recovery-v1.0）
- Provider 健康探测（API 连通性检查）
- 每日观测摘要投递（cron 定时）
- Memory search 监控
- JSONL 结构化日志输出
- 敏感信息自动脱敏（API key/token/secret 不记录）

## 目录结构

```
observability/
├── gateway_watchdog.sh               # 网关健康检查（进程 + 端口）+ 调用恢复兜底
├── scripts/
│   ├── __init__.py
│   ├── agent_observer.py             # 会话快照 / 每日摘要 / JSONL 日志
│   ├── channel_recovery.py           # Channel 主动恢复兜底（检测 + 分级恢复）
│   ├── logging.py                    # 日志工具
│   ├── tracing.py                    # 链路追踪
│   └── memory_search_monitor.py      # Memory search 监控
├── cron/
│   ├── provider-health-check.py      # Provider 健康探测（cron 入口）
│   └── daily-summary-delivery.py     # 每日摘要投递（cron 入口）
├── tests/
│   ├── conftest.py
│   ├── test_smoke.py
│   ├── test_channel_recovery.py      # 判定/节流/解析 单元测试
│   └── test_golden_replay.py         # 真实日志黄金回放（回归基线）
├── DESIGN-DETAIL-channel-recovery-v1.0.md
└── DESIGN.md
```

## 使用方式

```bash
# Gateway 健康检查 + channel 恢复兜底
bash gateway_watchdog.sh

# Channel 只读判定（不动作）
python3 scripts/channel_recovery.py --check

# Channel 恢复兜底（幂等，launchd 每 5min 调用）
python3 scripts/channel_recovery.py --recover

# 会话快照
python3 scripts/agent_observer.py

# 每日摘要
python3 scripts/agent_observer.py --daily

# 所有活跃会话
python3 scripts/agent_observer.py --all

# JSONL 日志
python3 scripts/agent_observer.py --jsonl

# Provider 健康探测
python3 cron/provider-health-check.py

# 每日摘要投递
python3 cron/daily-summary-delivery.py
```

## 依赖

- Python 3
- `openclaw` CLI（sessions/cron/status 命令）
- curl（端口健康检查）
- `gateway-safety` 组件（`safe_restart.sh`，仅全量兜底时使用）
