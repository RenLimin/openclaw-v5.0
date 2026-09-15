# System Health Check — 系统全量检测技能

> L2 基础设施层技能。一键运行系统全量健康检查，输出结构化报告。
>
> **触发场景**：定期巡检、故障排查、变更后验证、环境确认。

## 使用方式

```bash
python3 L2-infra/skills/system-health-check/scripts/health_check.py [选项]
```

选项：
- `--json` — 输出 JSON 格式（便于程序处理）
- `--brief` — 只输出摘要（通过/失败数）
- `--skip <category>` — 跳过某类检查（可多次使用）
- `--only <category>` — 只跑某类检查

检查类别：`gateway` / `channels` / `model-scheduling` / `components` / `cron` / `tests` / `secrets` / `git`

## 检查项清单

### 1. Gateway & 系统基础
- OpenClaw Gateway 运行状态
- 版本号
- 插件加载状态
- 内存使用

### 2. 通道 (Channels)
- WeCom 配置状态
- 其他已知通道状态

### 3. 模型调度 (Model Scheduling)
- proxy 服务进程存在
- /health 端点响应
- 真实请求测试（选轻量模型）
- 配置文件完整性（models.yaml / routing.yaml / providers.yaml）

### 4. L2 组件健康
- 每个 L2 组件有 DESIGN.md
- 核心组件有可执行入口
- 依赖检查（Python 包）

### 5. Cron 调度任务
- 所有 cron 任务状态
- 最近一次执行结果
- 失败任务告警

### 6. 业务测试
- DMS 框架测试
- FIN-L4 测试
- 其他组件测试（如存在）

### 7. 凭据安全
- secrets audit 结果
- plaintext 数量
- 已知合理场景验证

### 8. Git & 仓库
- 当前分支
- 工作区是否干净
- 与远程是否同步
- 最近 commit

## 输出格式

### 人类可读
```
=== 系统健康检查报告 ===
时间: 2026-09-15 15:00:00
总检查项: 28 | 通过: 26 | 失败: 2 | 跳过: 0

✅ Gateway: running (pid 68199)
✅ WeCom: configured
⚠️  model-scheduling: 健康但 30 分钟内有 2 次错误
❌ Cron: 仓库健康检查最近一次 timeout
...
```

### JSON
```json
{
  "timestamp": "2026-09-15T15:00:00+08:00",
  "summary": { "total": 28, "passed": 26, "failed": 2, "skipped": 0 },
  "checks": [
    { "category": "gateway", "name": "gateway-status", "status": "pass", "detail": "pid 68199" },
    { "category": "cron", "name": "repo-health-last-run", "status": "fail", "detail": "timeout" }
  ]
}
```

## 退出码
- `0` — 全部通过
- `1` — 有失败项
- `2` — 检查本身出错（无法运行）

## 与 Cron 的关系
本技能可以手动执行，也可以被 cron 调度任务调用。cron 负责调度频率，技能负责检查逻辑。
