# model-scheduling — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3

### 启动命令

```bash
# 启动代理服务
python3 proxy.py

# 或后台启动
nohup python3 proxy.py &
```

### 健康检查

```bash
curl http://127.0.0.1:3000/health
```

## 操作指南

### 场景一：获取推荐模型

```bash
python3 router.py "任务描述"
```

### 场景二：模型同步

```bash
python3 sync_models.py
```

### 场景三：健康探测

```bash
python3 health_check.py
```

### 场景四：用量获取

```bash
python3 fetch_usage.py
```

## 配置说明

- 模型注册: config/models.yaml
- 路由规则: config/routing.yaml
- 用量追踪: config/usage.json

## 故障排查

### 代理不可达

- **症状**: proxy 无响应
- **原因**: 端口被占用或进程崩溃
- **解决**: 重启 proxy 或检查端口

### 模型不可用

- **症状**: 路由失败
- **原因**: 模型未配置或 API key 错误
- **解决**: 检查模型配置和凭据

### deepseek/longCat 额度耗尽（402）

- **症状**: 请求返回 402，系统反复撞 402
- **原因**: 余额不足，exhausted 状态未自愈
- **解决**: 等待 1h TTL 自动重试探，或充值后执行恢复脚本

```bash
# 手动检查并恢复（--detail 强制输出）
python3 L2-infra/components/model-scheduling/scripts/check_quota_and_restore.py --detail

# 调度状态（每 6h 自动执行）
launchctl list ai.openclaw.quota-restore
```

### 调度资产审计

```bash
# 核对 manifest 与 launchctl 实际调度一致性
python3 L2-infra/components/scheduler-guard/audit.py

# 预期: 总计 17 | 已调度 16 | 未调度 0 | 不一致 0
```

### 长回合请求失败 / "malformed tool call"（2026-11-12）

- **症状**: 长回合（>120s）报 `Provider returned an incomplete or malformed tool call`，日志出现 `流式传输中断: ... after N bytes`
- **根因**: 流式请求误用 `aiohttp.ClientTimeout(total=120)` 总时长超时，长回合 SSE 输出超 120s 被 proxy 主动砍断 → gateway 收到半截 tool call
- **已修复**: 流式请求改用 `sock_read=120` 空闲超时（总时长不设限）；非流式 `total=300`
- **排查**: 若仍出现，先确认 proxy 进程是否已重启加载新代码（`ps -o lstart=,pid= -p <pid>` 启动时间应晚于修复时间）
- **验证命令**:

```bash
# 确认代码中已是 sock_read（非 total=120）
grep -n "ClientTimeout" L2-infra/components/model-scheduling/scripts/proxy.py
# 预期: total=None, sock_connect=30, sock_read=120

# 运行超时回归测试
python3 -m pytest L2-infra/components/model-scheduling/tests/test_stream_timeout.py -v
```

### proxy 重启（加载代码/配置变更）

```bash
# 查看当前 pid
pgrep -f "proxy.py --host 127.0.0.1 --port 3000"

# kickstart 重启（LaunchAgent KeepAlive 会自动拉起）
launchctl kickstart -k gui/$(id -u)/ai.openclaw.model-scheduling

# 确认新 pid + 探活结果
tail -10 L2-infra/components/model-scheduling/logs/proxy.stderr.log
# 预期: 探活完成: N/M healthy + 代理服务已启动: 127.0.0.1:3000
```

> ⚠️ 注意: 改 `config/routing.yaml` / `models.yaml` / `providers.yaml` 是**热更新**（无需重启）；改 `scripts/proxy.py` 代码才需要重启。
