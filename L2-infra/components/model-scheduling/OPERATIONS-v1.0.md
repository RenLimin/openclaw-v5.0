# model-scheduling — 产品操作手册（OPERATIONS）

> 版本：v1.0（2026-09-28）
> 层级：L2 基础设施层
> 状态：⏳ 待 Rex 审核

---

## 1. 安装与启动

### 1.1 环境依赖

| 依赖 | 最低版本 | 用途 | 安装命令 |
|------|---------|------|---------|
| Python | 3.14+ | 运行时 | `brew install python@3.14` |
| pyyaml | 6.0 | YAML 解析 | `pip install pyyaml` |
| httpx | 0.25 | HTTP 客户端 | `pip install httpx` |
| watchdog | 3.0 | 文件监听（热更新） | `pip install watchdog` |

一键安装：
```bash
pip install pyyaml httpx watchdog
```

### 1.2 安装步骤

```bash
# 1. 进入组件目录
cd ~/.openclaw/workspace/L2-infra/components/model-scheduling

# 2. 安装依赖
pip install pyyaml httpx watchdog

# 3. 初始化配置（一次性）
bash setup.sh

# 4. 注册为 OpenClaw provider
python3 scripts/register_provider.py --force
```

### 1.3 启动命令

```bash
# 前台启动（调试用）
cd ~/.openclaw/workspace/L2-infra/components/model-scheduling
python3 scripts/proxy.py --host 127.0.0.1 --port 3000

# 后台启动（生产用）
nohup python3 scripts/proxy.py --host 127.0.0.1 --port 3000 > /tmp/model-scheduling.log 2>&1 &

# 自动启动（LaunchAgent）
launchctl load ~/Library/LaunchAgents/ai.openclaw.model-scheduling.plist
```

### 1.4 健康检查

```bash
# 基础健康
curl -s http://127.0.0.1:3000/health | python3 -m json.tool
# 预期：{"status": "ok", "requests": <数字>, "errors": <数字>}

# 模型列表
curl -s http://127.0.0.1:3000/v1/models | python3 -m json.tool

# 启动探活（一次性检测所有 provider）
python3 scripts/proxy.py --host 127.0.0.1 --port 3000
# 日志中查看探活结果

# 跳过探活启动（调试用）
python3 scripts/proxy.py --skip-probe
```

---

## 2. 操作指南

### 2.1 场景一：日常使用（自动路由）

> 作为用户，我只需要发请求，系统自动选模型。

```bash
# 发送请求（自动路由）
curl -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "coding-plan/auto",
    "messages": [{"role": "user", "content": "写一个 Python 函数"}]
  }'
```

**路由决策**：
- 含代码关键词 → `coding-plan/doubao-seed-2-0-lite`（便宜快速）
- 含"分析/架构" → `deepseek/deepseek-reasoner`（推理能力强）
- 含图片 → `coding-plan/doubao-seed-2-1-turbo`（多模态）
- 其他 → `coding-plan/doubao-seed-2-0-lite`（默认）

### 2.2 场景二：手动指定模型

> 作为高级用户，我想用特定模型。

```bash
# 直接指定模型（跳过自动路由）
curl -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "longCat/LongCat-2.0",
    "messages": [{"role": "user", "content": "分析这个架构"}]
  }'
```

### 2.3 场景三：添加新模型

> 作为管理员，我想添加新的 AI 模型。

```bash
# 1. 编辑 config/models.yaml，添加新模型：
#  - id: "my-provider/my-model"
#    provider: "my-provider"
#    model_id: "my-model-name"
#    input_types: ["text", "image"]
#    priority: 25

# 2. 编辑 config/routing.yaml，在对应任务的 fallback_chain 中加入新模型

# 3. 等待 ≤ 10 秒，配置自动热更新

# 4. 验证新模型可用
curl -s http://127.0.0.1:3000/v1/models | python3 -m json.tool
```

### 2.4 场景四：调整路由策略

> 作为运维，我想调整路由顺序。

```bash
# 1. 编辑 config/routing.yaml
vim config/routing.yaml

# 示例：把 coding 任务的 L1 改为 longCat
# coding:
#   fallback_chain:
#     - "longCat/LongCat-2.0"               # L1: 改为 LongCat
#     - "coding-plan/doubao-seed-2-0-lite"  # L2: 原 L1 降为 L2
#     - "deepseek/deepseek-chat"            # L3: 不变

# 2. 保存文件，≤ 10 秒自动生效

# 3. 验证
curl -s -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"coding-plan/auto","messages":[{"role":"user","content":"def test()"}],"max_tokens":5}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('model','ERROR'))"
# 预期：longCat/LongCat-2.0
```

### 2.5 场景五：查看用量

> 作为管理员，我想看 token 用量和费用。

```bash
# 获取用量
python3 scripts/fetch_usage.py

# 查看预算告警
python3 scripts/budget_alert.py

# 查看 usage.json
cat config/usage.json | python3 -m json.tool
```

---

## 3. 配置说明

### 3.1 配置文件清单

| 文件 | 用途 | 热更新 |
|------|------|--------|
| `config/config.yaml` | 系统配置（端口/日志/阈值） | ✅ |
| `config/models.yaml` | 模型注册表（10 个模型） | ✅ |
| `config/routing.yaml` | 路由规则（5 种任务类型） | ✅ |
| `config/providers.yaml` | 供应商配置（3 个 provider） | ✅ |
| `config/usage.json` | 用量/健康（自动更新） | ✅ |

### 3.2 关键配置字段

#### models.yaml

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| id | string | 模型唯一标识（provider/model-name） | `coding-plan/doubao-seed-2-0-lite-260215` |
| provider | string | 所属供应商 | `coding-plan` |
| model_id | string | 供应商侧模型 ID | `doubao-seed-2-0-lite-260215` |
| input_types | list | 支持的输入类型 | `["text", "image", "video"]` |
| priority | int | 优先级（越小越优先） | `20` |
| status | string | active/inactive | `active` |
| context_window | int | 上下文窗口大小 | `262144` |

#### routing.yaml

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| fallback_chain | list | 模型 fallback 顺序 | `["model-a", "model-b", "model-c"]` |
| requires_input_types | list | 能力过滤（可选） | `["text"]` |
| preferred_context | int | 偏好上下文窗口 | `200000` |

---

## 4. 故障排查

### 4.1 服务无法启动

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| `Address already in use` | 端口 3000 被占用 | `lsof -i :3000` → kill 占用进程 |
| `ModuleNotFoundError: yaml` | 缺依赖 | `pip install pyyaml httpx watchdog` |
| `Permission denied` | 权限不足 | `chmod +x scripts/*.py` |

### 4.2 请求全部失败

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 所有请求返回 502 | proxy 未启动 | 检查进程：`ps aux \| grep proxy.py` |
| 所有请求返回 401 | provider API key 失效 | 检查 providers.yaml 的 apiKey |
| 所有请求超时 | 网络不通 | `curl -s https://api.longcat.chat/health` |

### 4.3 路由不正确

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 图片请求走了纯文本模型 | routing.yaml 缺 requires_input_types | 检查 coding 任务的 requires_input_types |
| 每次都先试一个失败的模型 | models.yaml 缺 priority | 给所有模型加 priority |
| 路由随机不稳定 | select_model 兜底排序不稳定 | 确认排序 key 包含 (priority, id) |

### 4.4 热更新不生效

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 修改配置后不生效 | config_watcher 未启动 | 检查日志：`tail -f logs/model-scheduling.log` |
| 配置格式错误 | YAML 语法错误 | `python3 -c "import yaml;yaml.safe_load(open('config/routing.yaml'))"` |

### 4.5 日志位置

| 日志 | 路径 |
|------|------|
| 主日志 | `logs/model-scheduling.log` |
| 错误日志 | `logs/proxy.stderr.log` |
| 健康检查 | `logs/health-check.log` |

---

## 5. FAQ

### Q1: 如何完全禁用 model-scheduling？
```bash
# 停止服务
pkill -f "proxy.py.*3000"

# 卸载 LaunchAgent
launchctl unload ~/Library/LaunchAgents/ai.openclaw.model-scheduling.plist
```

### Q2: 如何回退到 OpenClaw 原生模型？
```bash
# 在 OpenClaw 中切换模型（绕过 model-scheduling）
/model longcat/LongCat-2.0
```

### Q3: 如何添加新的 provider？
1. `config/providers.yaml` 添加 provider 配置
2. `config/models.yaml` 添加该 provider 下的模型
3. `config/routing.yaml` 在 fallback_chain 中引用新模型
4. 等待 ≤ 10 秒热更新

### Q4: 如何查看当前路由决策？
```bash
# 发送测试请求，查看返回的 model 字段
curl -s -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"coding-plan/auto","messages":[{"role":"user","content":"test"}],"max_tokens":1}' \
  | python3 -m json.tool | grep '"model"'
```

---

## 6. 附录

### 6.1 API 接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | 聊天补全（主要入口） |
| GET | `/v1/models` | 列出可用模型 |
| GET | `/health` | 健康检查 |
| POST | `/admin/reload` | 手动配置重载 |
| GET | `/admin/status` | 路由状态 + 模型健康 |
| GET | `/admin/usage` | 用量统计 |

### 6.2 模型清单

| ID | Provider | 能力 | 优先级 | 用途 |
|---|---------|------|--------|------|
| coding-plan/doubao-seed-2-0-lite-260215 | coding-plan | text+image+video | 20 | 通用编码 |
| coding-plan/doubao-seed-2-1-turbo | coding-plan | text+image+video | 30 | 多模态 |
| coding-plan/doubao-seed-code-preview-251028 | coding-plan | text only | 10 | 纯文本 code |
| longCat/LongCat-2.0 | longcat | text | 15 | 大 ctx 文本 |
| deepseek/deepseek-chat | deepseek | text | 25 | 推理 |
| deepseek/deepseek-reasoner | deepseek | text | 35 | 深度推理 |

### 6.3 外部依赖

| 依赖 | 地址 | 用途 |
|------|------|------|
| coding-plan | api.volcengine.com | 主要 AI 模型 |
| longCat | api.longcat.chat | 大 ctx 文本模型 |
| deepseek | api.deepseek.com | 推理模型 |
