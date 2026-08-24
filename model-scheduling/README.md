# model-scheduling — 智能模型调度组件

综合模型/供应商调度系统。参考 9router / OpenRouter / Portkey 业界最佳实践。

## 快速开始

```bash
# 1. 一次性初始化(首次部署) — 同步模型 + 获取用量 + 健康探测
bash model-scheduling/setup.sh

# 2. 注册会话 agent(一次性写入 openclaw.json)
bash model-scheduling/setup_agents.sh

# 3. 查看推荐模型
python3 model-scheduling/scripts/router.py "你的任务描述"

# 4. 指定任务类型
python3 model-scheduling/scripts/router.py --task-type coding --json
```

## 会话中调用

### 方式 1:路由到专用 agent(推荐)

初始化后,4 个专用 agent 已注册到 openclaw.json:

| Agent | 适用任务 | 主模型 |
|---|---|---|
| `ms-coding` | 编码/调试/重构 | ark-code-latest |
| `ms-research` | 搜索/研究/分析 | doubao-seed-2.1-turbo |
| `ms-reasoning` | 推理/架构/设计 | deepseek-v4-flash |
| `ms-chat` | 闲聊/日常 | doubao-seed-2.0-lite |

通过 `sessions_send` 将任务路由到对应 agent,自动使用推荐的模型和 fallback chain。

### 方式 2:运行时切换(不写配置)

```bash
# 切换到推荐模型
openclaw sessions patch --session agent:main:main --model coding-plan/deepseek-v4-flash
```

## 调用方式

### 1. 路由引擎 — 获取推荐模型

```bash
# 自动任务分类
python3 model-scheduling/scripts/router.py "帮我写一个 Python 函数"

# 指定任务类型
python3 model-scheduling/scripts/router.py --task-type coding
python3 model-scheduling/scripts/router.py --task-type reasoning
python3 model-scheduling/scripts/router.py --task-type research
python3 model-scheduling/scripts/router.py --task-type chat

# JSON 输出(供程序调用)
python3 model-scheduling/scripts/router.py --task-type coding --json
# 输出: {"task_type": "coding", "selected_model": "coding-plan/ark-code-latest", ...}
```

**输出示例**:
```
=== 智能路由引擎 ===
[1/3] 加载配置 ...
  模型: 10 个
  Provider 用量: 2 个
[2/3] 任务分类 ...
  任务类型: coding
[3/3] 选择模型 ...
  推荐模型: coding-plan/ark-code-latest
  Provider: coding-plan
  上下文窗口: 229376
  原因: 任务类型 coding → fallback chain 第 1 个可用模型
```

### 2. 模型同步 — 从 openclaw.json 同步模型注册表

```bash
# 预览(不写入)
python3 model-scheduling/scripts/sync_models.py --dry-run

# 正式同步
python3 model-scheduling/scripts/sync_models.py

# 跳过确认直接写入
python3 model-scheduling/scripts/sync_models.py --force
```

### 3. 用量获取 — 从 provider API 获取用量

```bash
# 预览
python3 model-scheduling/scripts/fetch_usage.py --dry-run

# 正式获取
python3 model-scheduling/scripts/fetch_usage.py --force
```

### 4. 健康探测 — 检测 provider 网络状态

```bash
# 预览
python3 model-scheduling/scripts/health_check.py --dry-run

# 正式探测
python3 model-scheduling/scripts/health_check.py --force
```

### 5. 完整初始化

```bash
# 一次性初始化(同步 + 用量 + 健康)
bash model-scheduling/setup.sh

# 预览模式
bash model-scheduling/setup.sh --dry-run
```

## 定期任务(建议通过 cron 调度)

| 任务 | 频率 | 命令 |
|---|---|---|
| 模型同步 | 每周 | `python3 model-scheduling/scripts/sync_models.py --force` |
| 用量获取 | 每周 | `python3 model-scheduling/scripts/fetch_usage.py --force` |
| 健康探测 | 每小时 | `python3 model-scheduling/scripts/health_check.py --force` |

## 配置文件

| 文件 | 说明 | 是否手动编辑 |
|---|---|---|
| `config/models.yaml` | 模型注册表(10 个模型) | ✅ 可手动编辑标签/状态 |
| `config/routing.yaml` | 路由规则(fallback chain + 压缩规则) | ✅ 可手动编辑规则 |
| `config/usage.json` | 用量/健康状态(自动更新) | ❌ 自动生成 |

## 路由策略

### 任务分类 → 模型映射

| 任务类型 | 首选模型 | fallback chain |
|---|---|---|
| **coding** | ark-code-latest | ark-code → deepseek-v4-flash → doubao-lite |
| **reasoning** | deepseek-v4-flash | deepseek-v4 → glm-5.3 → ark-code |
| **research** | doubao-seed-2.1-turbo | doubao-2.1 → ark-code → doubao-lite |
| **chat** | doubao-seed-2.0-lite | doubao-lite → ark-code |

### Token 压缩规则

| 规则 | 匹配 | 动作 |
|---|---|---|
| git_diff | `git diff` 输出 | > 200 行截断为 100 行 |
| grep_output | `grep/find/ls` 输出 | > 100 行截断为 50 行 |
| file_read | 文件读取 | > 500 行截断为 200 行 |

## 设计约束

- ✅ **不频繁改核心配置**: 所有脚本只读 `openclaw config get`,绝不 `patch/set`
- ✅ **不影响系统运行**: 外部文件存储状态,故障降级到 OpenClaw 原生 fallback
- ✅ **变更前验证**: 所有脚本支持 `--dry-run`

## 与其他组件的关系

```
model-scheduling(模型选择) → OpenClaw 原生 fallback(故障切换)
                           → 会话错误自动处理(错误监控)
                           → 上下文管理(溢出防护)
```

model-scheduling **选择**最优模型,OpenClaw fallback **保障**模型可用,两者互补。
