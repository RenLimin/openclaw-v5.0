# DESIGN-DETAIL-v1.0: model-scheduling

## 1. 概述

model-scheduling 是 L2 基础设施层组件，提供**智能模型路由**能力，基于任务类型动态选择最优模型，自动 fallback 处理失败/余额不足/健康问题。

## 2. 接口契约

### 2.1 OpenAI-compatible API

model-scheduling proxy 对外暴露完全兼容 OpenAI 的 API，Gateway 可直接当做 provider 使用：

| 端点 | 方法 | 说明 |
|---|------|------|
| `/v1/chat/completions` | `POST` | 聊天补全（和 OpenAI 完全一致） |
| `/v1/models` | `GET` | 获取模型列表 |
| `/health` | `GET` | 健康检查 |

### 2.2 请求参数（和 OpenAI 一致）

| 参数 | 类型 | 必填 | 说明 |
|---|------|------|------|
| `model` | `string` | ✅ | `model-scheduling/auto` 或 `model-scheduling/<task>` |
| `messages` | `array` | ✅ | 对话历史，支持 `content` 字符串或 `content` 数组（OpenAI 标准多模态） |
| `max_tokens` | `int` | ❌ | 最大生成 tokens |
| `stream` | `bool` | ❌ | 是否流式输出 |

### 2.3 响应格式

完全和 OpenAI `chat/completions` 一致，可直接兼容现有客户端。

### 2.4 内部配置接口

| 端点 | 方法 | 说明 |
|---|------|------|
| `/config/reload` | `POST` | 热重载配置（routing.yaml / models.yaml / usage.json） |

## 3. 核心数据模型

### 3.1 `config/routing.yaml`

任务类型路由规则：

```yaml
- task: "task_type"
  priority: int           # 优先级，越小越先选
  requires_input_types: ["text"] # 必须满足输入类型要求，缺则不筛选
```

示例：
```yaml
- task: coding
  priority: 20
  requires_input_types: ["text"]
- task: reasoning
  priority: 30
  requires_input_types: ["text"]
- task: chat
  priority: 10
- task: multimodal
  priority: 40
  requires_input_types: ["text", "image"]
```

### 3.2 `config/models.yaml`

模型定义：

```yaml
- id: "provider/model_id"
  provider: "provider_id"
  model_id: "remote_model_id"
  name: "Human-readable Name"
  context_window: int       # 上下文窗口大小，tokens
  max_tokens: int           # 最大输出 tokens
  input_types: ["text"]     # 支持的输入类型：text/image/video
  reasoning: bool           # 是否支持推理任务
  cost:
    input: float            # 每 1M 输入 tokens 价格（美元）
    output: float           # 每 1M 输出 tokens 价格（美元）
    cacheRead: float
    cacheWrite: float
  priority: int            # fallback 优先级（越小越先选）
```

### 3.3 `config/usage.json`

provider 健康状态持久化：

```json
{
  "provider_id": {
    "status": "healthy", // healthy / unreachable / exhausted / degraded
    "last_checked": "ISO-8601 timestamp",
    "requests": 0,
    "errors": 0
  }
}
```

### 3.4 任务类型判断（输入 → 任务类型）

任务类型由输入内容判断：

| 条件 | 任务类型 |
|---|------|
| 包含 `code` / `def ` / `function` / `class` 等编程关键词，超过 20% 字符 | `coding` |
| 包含 `分析` / `为什么` / `推理` / `架构` / `设计` 等推理关键词 | `reasoning` |
| 包含图片 / 视频内容 | `multimodal` |
| 默认 | `chat` |

## 4. 技术方案

### 4.1 整体架构图

```
OpenClaw Gateway
    ↓ POST /v1/chat/completions
model-scheduling proxy
    ↓ 1. 判断任务类型
    ↓ 2. 估算 tokens
    ↓ 3. 过滤：不满足输入类型 + ctx 不足 + 不健康
    ↓ 4. 排序：priority → degraded → id
    ↓ 5. 转发请求到第一个模型
    ↓ 成功 → 返回结果到 Gateway
    ↓ 失败 → fallback 下一个，直到成功或耗尽
    失败后标记 provider 状态（402 → exhausted）
```

### 4.2 核心模块

#### 模块 1: 任务分类器 (`scripts/classify_task.py`)

负责从输入消息判断任务类型：

- 特征：关键词匹配 + 字符占比统计
- 输出：`coding` / `reasoning` / `chat` / `multimodal`
- 优先级：`multimodal` > `coding` > `reasoning` > `chat`

#### 模块 2: 配置加载 (`scripts/config.py`)

负责加载并热重载配置：

- 启动时加载一次
- 监听文件变更，自动热重载（无需重启 proxy）
- 缓存配置，实时生效

#### 模块 3: 健康探测 (`scripts/health_check.py`)

负责定期探测 provider 健康状态：

- 频率：每小时一次
- 探测 URL: `/health` 或简单 GET
- 标记状态：`healthy` / `unreachable`
- 持久化到 `usage.json`

#### 模块 4: 路由引擎 (`scripts/proxy.py::select_model`)

负责构建 fallback 链：

1. 根据任务类型从 `routing.yaml` 拿到候选模型列表
2. 过滤：
   - 检查 provider 健康状态（`unreachable` → 跳过）
   - 检查输入类型要求（不满足 → 跳过）
   - 检查上下文窗口（估算 tokens > 90% ctx → 跳过）
3. 排序：
   - `priority` 升序（越小越优先）
   - 健康状态 → `healthy` < `degraded` < `exhausted` < `unreachable`
   - 稳定兜底：模型 id 升序
4. 返回 fallback 链

#### 模块 5: 代理转发 (`scripts/proxy.py::_forward_once`)

负责转发请求到目标 provider：

1. 消息格式转换：`content` 数组 → 提取纯文本 → 转为字符串（兼容 coding-plan API）
2. 转发请求到 provider API
3. 处理错误：
   - 402 → 标记 `exhausted` 写入 `usage.json`
   - 返回错误给 fallback
4. 返回成功结果到 Gateway

### 4.3 错误处理与 fallback

| 错误类型 | 处理方式 |
|---|------|
| 200 OK | 返回结果，成功 |
| 400 Bad Request | 立即 fallback 下一个 |
| 402 Payment Required | 标记 provider 为 `exhausted` → fallback |
| 429 Too Many Requests | fallback |
| 5xx | fallback |
| Network Error | fallback |

### 4.4 热更新机制

- 使用 `watchdog` 监听配置文件变更
- 变更触发后 1s 重新加载配置
- 无需重启 proxy，不影响当前请求
- 变更立即生效

### 4.5 上下文感知路由

- 入口请求 → 粗估 tokens（中文 ~1.5 字/token，英文 ~4 字符/token，图片 ~1.5k tokens）
- 如果 `估算 tokens > 90% * 模型 ctx` → 跳过该模型
- 保证请求不会因为上下文超限失败，大请求自动路由到大 ctx 模型

### 4.6 消息格式兼容

- OpenClaw 输入 `content` 是数组 → 提取 `type:text` 的内容拼接为字符串
- 转发给 provider，兼容 coding-plan API（只接受 `content` 字符串）
- `content` 已经是字符串 → 直接转发，不修改

## 5. 模块依赖

| 模块 | 依赖 |
|---|------|
| 分类器 | 无 |
| 配置 | 无 |
| 健康探测 | config |
| 路由 | 分类器 + 配置 + 健康探测 |
| 代理 | 路由 + 配置 |

## 6. 环境变量与运行

### 6.1 启动参数

| 参数 | 默认 | 说明 |
|---|------|------|
| `--host` | `127.0.0.1` | 监听地址 |
| `--port` | `3000` | 监听端口 |

### 6.2 依赖

`requirements.txt`：
- `aiohttp`
- `pyyaml`
- `watchdog`

### 6.3 开机自启（macOS LaunchAgent）

```
~/Library/LaunchAgents/ai.openclaw.model-scheduling.plist
```

配置：
- `KeepAlive` → 崩溃自动恢复
- `source ~/.zshenv` → 加载环境变量（解决 `longCat` key 环境继承问题）

## 7. 变更记录

| 日期 | 变更 | 作者 |
|---|------|------|
| 2026-09-28 | 首次创建详细设计 | Jerry |
