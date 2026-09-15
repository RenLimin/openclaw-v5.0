# System Health Check — 系统全量检测技能

> L2 基础设施层技能。一键运行系统全量健康检查，输出结构化报告。
>
> **触发场景**：定期巡检、故障排查、变更后验证、环境确认。

## 模块组成

本技能包含两个子模块，按需使用：

| 模块 | 脚本 | 定位 |
|---|---|---|
| 系统全量检查 | `scripts/health_check.py` | 广覆盖、多维度（8 大类 ~30 项），侧重配置完整性和组件健康 |
| 服务健康检测 | `scripts/service_health_check.py` | 聚焦常驻服务存活 + 业务路径验证，支持自动修复 |

---

## 一、系统全量检查 (`health_check.py`)

### 使用方式

```bash
python3 L2-infra/skills/system-health-check/scripts/health_check.py [选项]
```

选项：
- `--json` — 输出 JSON 格式（便于程序处理）
- `--brief` — 只输出摘要（通过/失败数）
- `--skip <category>` — 跳过某类检查（可多次使用）
- `--only <category>` — 只跑某类检查

检查类别：`gateway` / `channels` / `model-scheduling` / `components` / `cron` / `tests` / `secrets` / `git`

### 检查项清单

#### 1. Gateway & 系统基础
- OpenClaw Gateway 运行状态
- 版本号
- 插件加载状态
- 内存使用

#### 2. 通道 (Channels)
- WeCom 配置状态
- 其他已知通道状态

#### 3. 模型调度 (Model Scheduling)
- proxy 服务进程存在
- /health 端点响应
- 真实请求测试（选轻量模型）
- 配置文件完整性（models.yaml / routing.yaml / providers.yaml）

#### 4. L2 组件健康
- 每个 L2 组件有 DESIGN.md
- 核心组件有可执行入口
- 依赖检查（Python 包）

#### 5. Cron 调度任务
- 所有 cron 任务状态
- 最近一次执行结果
- 失败任务告警

#### 6. 业务测试
- DMS 框架测试
- FIN-L4 测试
- 其他组件测试（如存在）

#### 7. 凭据安全
- secrets audit 结果
- plaintext 数量
- 已知合理场景验证

#### 8. Git & 仓库
- 当前分支
- 工作区是否干净
- 与远程是否同步
- 最近 commit

### 输出格式

#### 人类可读
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

#### JSON
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

### 退出码
- `0` — 全部通过
- `1` — 有失败项
- `2` — 检查本身出错（无法运行）

---

## 二、服务健康检测 + 自动修复 (`service_health_check.py`)

### 设计理念

不只是 ping 端口，而是**两层检测**：
- **L1 存活检测**（< 5s）：端口/进程/健康端点是否活着
- **L2 业务路径检测**（< 30s）：核心 API 能不能真的干活

异常时**自动修复**：按配置的修复命令尝试恢复，修复后自动重测。

### 使用方式

```bash
# 检测所有服务
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all

# 检测单个服务
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py bdms-web

# 检测多个服务
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py openclaw-gateway model-scheduling-proxy

# 检测并自动修复
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all --fix

# 只跑 L1 快速检测
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all --l1-only

# 输出 JSON
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all --json

# 输出报告到文件
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all --output /tmp/health-report.json

# 列出所有已注册服务
python3 L2-infra/skills/system-health-check/scripts/service_health_check.py --list
```

### 选项说明

| 选项 | 说明 |
|---|---|
| `services` | 服务名，`all` 表示全部，可多个 |
| `--fix` | 检测失败时自动尝试修复 |
| `--output <file>` | 将结构化 JSON 报告写入文件 |
| `--json` | 输出 JSON 到 stdout |
| `--brief` | 只输出摘要 |
| `--list` | 列出所有已注册服务 |
| `--config <path>` | 指定服务配置文件路径 |
| `--l1-only` | 只跑 L1 层检测（快速模式，< 5s） |

### 已注册服务

| 服务 ID | 名称 | 优先级 | L1 检测 | L2 检测 | 自动修复 |
|---|---|---|---|---|---|
| `openclaw-gateway` | OpenClaw Gateway | critical | `openclaw status` 命令 | Dashboard HTTP 200 | `openclaw gateway restart` |
| `model-scheduling-proxy` | Model Scheduling Proxy | critical | `/health` 端点 | chat/completions 真实请求 | launchctl unload + load |
| `bdms-web` | BDMS Web UI | high | `/health` 端点 | 首页 HTTP 200 | pkill + nohup 重启 |
| `llama-cpp-embedding` | Llama-cpp Embedding 服务 | high | `/health` 端点 | embeddings API 真实调用 | pkill + nohup 重启 |

### 输出格式

#### 人类可读
```
==================================================
📊  服务健康检测报告
==================================================
🕐  检测时间: 2026-09-15T21:34:32+08:00
📋  服务总数: 4
   ✅  健康: 4  ⚠️  降级: 0  ❌ 失败: 0  🔧 已修复: 0

✅ OpenClaw Gateway (openclaw-gateway)
   优先级: critical | 分类: infra | 耗时: 791ms
  ├─ ✅ Gateway 进程存活 (openclaw status) (783ms) — 包含 'Dashboard' (exit=0)
  ├─ ✅ Dashboard HTTP 可访问 (7ms) — HTTP 200 (18488 bytes)
...
```

#### JSON 结构
```json
{
  "timestamp": "2026-09-15T21:34:32+08:00",
  "summary": {
    "total": 4, "healthy": 4, "degraded": 0, "failed": 0, "fixed": 0
  },
  "services": {
    "openclaw-gateway": {
      "name": "OpenClaw Gateway",
      "priority": "critical",
      "category": "infra",
      "overall": "healthy",
      "checks": {
        "l1_process_status": {
          "status": "pass",
          "label": "Gateway 进程存活",
          "detail": "包含 'Dashboard' (exit=0)",
          "duration_ms": 783
        },
        "l2_dashboard_http": {
          "status": "pass",
          "label": "Dashboard HTTP 可访问",
          "detail": "HTTP 200 (18488 bytes)",
          "duration_ms": 7
        }
      },
      "fix_attempted": false,
      "fix_result": null,
      "total_duration_ms": 791
    }
  }
}
```

服务状态：
- `healthy` — 所有检测项通过
- `degraded` — L1 通过但 L2 失败（进程活着但业务有问题）
- `failed` — L1 失败（服务挂了）

### 添加新服务

编辑 `config/services.json`，在 `services` 下添加：

```json
"my-service": {
  "name": "我的服务",
  "description": "服务描述",
  "category": "business",
  "priority": "high",
  "checks": {
    "l1_xxx": {
      "type": "http",
      "url": "http://127.0.0.1:PORT/health",
      "expect_status": [200],
      "timeout": 5,
      "label": "健康端点检测"
    },
    "l2_xxx": {
      "type": "command",
      "command": "curl -s -m 10 http://127.0.0.1:PORT/api/test",
      "expect_contains": "\"ok\"",
      "timeout": 15,
      "label": "核心 API 测试"
    }
  },
  "fix": {
    "command": "重启命令",
    "cooldown_seconds": 30,
    "max_attempts": 2,
    "label": "重启说明"
  },
  "dependencies": []
}
```

**检测类型**：
- `http` — HTTP GET 请求，检查状态码和响应内容
- `command` — 执行 shell 命令，检查退出码或输出包含字符串

**命名规范**：
- 检测项 ID 以 `l1_` / `l2_` 开头，标识检测层级
- `priority`：`critical` / `high` / `medium` / `low`
- `category`：`infra` / `business` / `data` / `other`

**修复原则**：
- 修复命令必须幂等（重复执行不会出问题）
- `cooldown_seconds` 防止频繁重启
- `max_attempts` 限制最大尝试次数

---

## 退出码（两个模块通用）
- `0` — 全部通过（或修复后全部通过）
- `1` — 有失败项
- `2` — 检查本身出错（无法运行）

## 与 Cron 的关系
本技能可以手动执行，也可以被 cron 调度任务调用。cron 负责调度频率，技能负责检查逻辑。

典型 cron 场景：
- 每小时跑一次 `service_health_check.py all --l1-only` — 快速存活巡检
- 每天跑一次 `service_health_check.py all --fix` + 写报告 + 异常告警
- 每天跑一次 `health_check.py` — 全量系统健康审计
