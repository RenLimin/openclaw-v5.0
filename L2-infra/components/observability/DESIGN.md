# 可观测性适配组件设计

> L2 基础设施层 · 可观测性适配（logging、metrics、tracing、agent 行为观察）

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 可观测性适配 |
| 状态 | ✅ 已建设 (2026-08-24) — 持续迭代 |
| ADR | ADR-009 (记忆语义检索监控) |
| 验证 | smoke test + cron 集成 |

## 2. 设计约束

1. **零外部依赖**：纯 Python 标准库 + OpenClaw CLI，不引入 OpenTelemetry SDK 等重型框架。
2. **遵循 OpenTelemetry GenAI semantic conventions**：日志字段命名对齐 `gen_ai.*` 规范（如 `gen_ai.agent.input_tokens`）。
3. **敏感数据脱敏**：所有日志输出经过 `redact_sensitive()` / `redact()` 处理，API key / token / secret 等字段替换为 `[REDACTED]`。
4. **行为探针优先**：`memory_search_monitor` 采用行为探针（behavioral probe）而非状态字段判断健康度——实测 `openclaw memory status --index` 会报告健康但检索实际停摆（2026-08-24 事故教训）。
5. **三态模型**：探针结果为 `ok` / `degraded` / `down` 三态，退出码分别对应 0 / 1 / 2。
6. **线程安全**：tracing 模块使用 `threading.local()` 保存当前 trace/span，避免多线程污染。

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     observability 组件                       │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   logging    │   tracing    │   agent      │   memory       │
│   (Layer 1)  │   (Layer 2)  │   observer   │   search       │
│              │              │              │   monitor      │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                    cron 定时任务层                           │
│   provider-health-check.py  │  daily-summary-delivery.py     │
├─────────────────────────────────────────────────────────────┤
│                    shell 脚本层                              │
│              gateway_watchdog.sh                            │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| logging | `scripts/logging.py` | 结构化日志：JSONL 格式、敏感字段 redact、按日分文件 |
| tracing | `scripts/tracing.py` | 步骤级 span 追踪：Trace/Span 数据模型、线程本地存储、因果链 |
| agent_observer | `scripts/agent_observer.py` | Agent 行为观测：会话快照、每日摘要、token 用量统计 |
| memory_search_monitor | `scripts/memory_search_monitor.py` | 记忆语义检索监控：行为探针、三态判据、status 一致性检查 |
| cron | `cron/provider-health-check.py` | Provider 健康探测（定时调用 health_check.py） |
| cron | `cron/daily-summary-delivery.py` | 每日观测摘要投递（生成摘要 → 发送到 WeCom） |
| shell | `gateway_watchdog.sh` | 网关进程存活检查 + 端口响应检查 |

### 3.2 数据流

```
OpenClaw CLI ──JSON──→ agent_observer.py ──JSONL──→ logs/observability/
                                              ──stdout──→ 人类可读
openclaw memory search ──→ memory_search_monitor.py ──→ 三态判定
openclaw gateway ──→ gateway_watchdog.sh ──→ 日志文件
provider API ──→ provider-health-check.py ──→ memory/YYYY-MM-DD.md
```

## 4. 核心模块详解

### 4.1 logging.py — 结构化日志

- 日志根目录：`logs/observability/`
- 错误日志单独存放：`logs/observability/errors/`
- 文件格式：`<YYYY-MM-DD>.jsonl`（每日一轮）
- 文件权限：`0o600`（仅所有者可读写）
- 敏感字段集合：`api_key`, `token`, `secret`, `password`, `credential`, `private_key`, `access_token`, `refresh_token`
- 日志条目结构：`{timestamp, level, component, event, trace_id, span_id, session_id, attributes}`

### 4.2 tracing.py — 步骤级追踪

- 数据模型：`Trace {trace_id, session_id, start_time, end_time, root_spans, attributes}` + `Span {span_id, name, start_time, end_time, attributes, children}`
- 线程本地存储：`threading.local()` 保存 `current_trace` / `current_span`
- 因果链：span 支持嵌套（parent → children），root_span 挂在 trace 下
- 自动隐式 trace：`start_span()` 在无 trace 环境时自动创建
- 事件记录：span 开始/结束时调用 `log_event()` 写入日志

### 4.3 agent_observer.py — Agent 行为观测

- 数据源：`openclaw sessions list --json` + `openclaw cron list --json`
- 采集维度：token 用量（input/output/total）、context tokens、异常中断标记、会话年龄
- 输出模式：
  - 默认：当前会话快照（最近 1h 活跃）
  - `--daily`：24h 每日摘要
  - `--all`：所有活跃会话快照
  - `--jsonl`：追加写入 JSONL 日志
- 敏感信息脱敏：正则匹配 API key / token / Bearer 等模式

### 4.4 memory_search_monitor.py — 记忆语义检索监控

- **核心洞察**：`openclaw memory status --index` 报告健康但检索实际停摆（2026-08-24 实测），因此必须用行为探针实查
- 探针查询：`"如何避免把密钥泄露到开源代码仓库"` — 与目标文档无关键词重叠，只能靠语义召回
- 三态判据：
  - `ok`：有结果且存在 `textScore==0` 而 `vectorScore≥0.35` 的纯向量命中
  - `degraded`：有结果但全部 `vectorScore==0`（静默降级为 keyword-only）
  - `down`：无结果 / 命令失败 / JSON 解析失败 / 检索被禁用
- 一致性检查：status 报告健康但探针失败时标记 `statusMisreportsHealth=true`
- 退出码：ok=0, degraded=1, down=2, 脚本自身错误=3

### 4.5 cron 定时任务

| 脚本 | 触发 | 产出 |
|---|---|---|
| `provider-health-check.py` | cron 调度 | 调用 `model-scheduling/scripts/health_check.py --force`，结果写入 `memory/YYYY-MM-DD.md` |
| `daily-summary-delivery.py` | 每天 23:50 | 调用 `agent_observer.py --daily` 生成摘要 → `openclaw message send --channel wecom --target 1313` 投递 |

### 4.6 gateway_watchdog.sh — 网关看门狗

- 检查 1：`pgrep -f "openclaw.*gateway"` 进程存活检查
- 检查 2：`curl http://127.0.0.1:<PORT>/health` 端口响应检查（接受 200/401/403/404）
- 设计说明：gateway 主进程由 launchd 管理（KeepAlive=true），本脚本仅做健康观测，不负责重启

## 5. 存储格式

| 路径 | 格式 | 说明 |
|---|---|---|
| `logs/observability/<YYYY-MM-DD>.jsonl` | JSONL | 每日结构化日志 |
| `logs/observability/errors/<YYYY-MM-DD>-errors.jsonl` | JSONL | 错误级别日志（单独存放） |
| `logs/observability/memory-search-<YYYY-MM-DD>.jsonl` | JSONL | 记忆检索监控日志 |
| `~/.openclaw/logs/gateway-watchdog-cron.log` | 文本 | 网关看门狗日志 |

## 6. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| OpenClaw CLI | 外部命令 | `openclaw sessions list --json`、`openclaw cron list --json`、`openclaw memory search --json`、`openclaw memory status --index`、`openclaw message send` |
| Python 3.14+ | 运行时 | 标准库（json, logging, subprocess, threading, argparse, re, hashlib, datetime） |
| model-scheduling | 内部组件 | `model-scheduling/scripts/health_check.py`（provider 健康检查） |
| WeCom 渠道 | 外部服务 | `daily-summary-delivery.py` 投递目标 |

## 7. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| OpenTelemetry SDK 集成 | 低 | 需要跨服务分布式追踪时 |
| 日志轮转清理 | 中 | 日志目录 > 1GB |
| 指标时序数据库 | 低 | 需要历史趋势分析时 |
| tracing 持久化 | 中 | Trace 数据需要跨会话保留和回放 |
| 告警升级 | 中 | 三态持续 degraded > 1h 时自动通知 Rex |

## 8. 验证

- **smoke test**：`L2-infra/components/observability/tests/test_smoke.py` — 验证目录结构和 Python 文件存在
- **cron 集成**：provider-health-check 和 daily-summary-delivery 已注册为 OpenClaw cron job
- **行为探针**：memory_search_monitor 退出码可直接被 cron 捕获判断状态

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-24 | memory_search_monitor.py 首版（ADR-009 决策 4 落地，行为探针 + 三态判据） |
| 2026-08-24 | logging.py + tracing.py 首版（结构化日志 + 步骤级追踪） |
| 2026-08-24 | agent_observer.py 首版（会话快照 + 每日摘要） |
| 2026-08-24 | gateway_watchdog.sh 首版（进程存活 + 端口检查） |
| 2026-08-24 | cron 脚本首版（provider-health-check + daily-summary-delivery） |
