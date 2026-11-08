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
