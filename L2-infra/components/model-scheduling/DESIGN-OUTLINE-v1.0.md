# model-scheduling — 产品概要设计（DESIGN-OUTLINE）

> 版本：v1.0（2026-09-28）
> 层级：L2 基础设施层
> 状态：⏳ 待 Rex 审核

---

## 1. 整体架构

### 1.1 系统定位

model-scheduling 是 L2 基础设施层的**模型调度组件**，
位于 OpenClaw Gateway 与外部 AI Provider 之间，
提供智能路由、多级 fallback、健康探测、用量追踪能力。

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OpenClaw   │────▶│  model-scheduling │────▶│  AI Providers   │
│  Gateway    │◀────│  proxy (:3000)    │◀────│  (coding-plan/  │
│             │     │                   │     │   longcat/       │
│             │     │  路由 + fallback  │     │   deepseek)      │
└─────────────┘     └──────────────────┘     └─────────────────┘
```

### 1.2 模块划分

| 模块 | 职责 | 文件 |
|------|------|------|
| **代理服务** | 接收请求 → 路由 → 转发 → fallback | `scripts/proxy.py` |
| **路由引擎** | 任务分类 → 模型选择 → fallback 链构建 | `scripts/router.py` + `config/routing.yaml` |
| **配置管理** | 外部配置加载 + 热更新监听 | `scripts/config_watcher.py` + `config/*.yaml` |
| **健康探测** | Provider 延迟/错误率检测 | `scripts/health_check.py` |
| **用量追踪** | Token 用量获取 + 预算告警 | `scripts/fetch_usage.py` + `scripts/budget_alert.py` |
| **模型同步** | openclaw.json → models.yaml 自动同步 | `scripts/sync_models.py` |
| **Provider 注册** | 注册为 OpenClaw custom provider | `scripts/register_provider.py` |

### 1.3 数据流

```
请求 → proxy.py → classify_task() → build_fallback_chain() → select_model()
                                                      ↓
                                              健康检查 + 能力匹配
                                                      ↓
                                              forward_to_provider()
                                                      ↓
                                              成功 → 返回响应
                                              失败 → fallback → 下一个模型
```

---

## 2. 接口契约

### 2.1 对外接口（OpenAI-compatible）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | 聊天补全（主要入口） |
| GET | `/v1/models` | 列出可用模型 |
| GET | `/health` | 健康检查 |

### 2.2 管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/reload` | 手动触发配置重载 |
| GET | `/admin/status` | 查看路由状态 + 模型健康 |
| GET | `/admin/usage` | 查看用量统计 |

### 2.3 配置接口（文件）

| 文件 | 格式 | 说明 |
|------|------|------|
| `config/models.yaml` | YAML | 模型注册表（id/provider/input_types/priority） |
| `config/routing.yaml` | YAML | 任务路由规则（任务类型 → fallback 链） |
| `config/providers.yaml` | YAML | 供应商配置（baseUrl/apiType/auth） |
| `config/config.yaml` | YAML | 系统配置（端口/热更新/日志/阈值） |

---

## 3. 技术方案

### 3.1 任务分类算法

基于关键词匹配（可扩展为 ML 分类）：

| 任务类型 | 关键词 | 路由策略 |
|---------|--------|---------|
| coding | code/debug/refactor/function/class | code 模型优先 |
| reasoning | 分析/架构/设计/推理/规划 | reasoning 模型优先 |
| research | 搜索/研究/文档/信息收集 | 多模态模型优先 |
| multimodal | 含 image_url 消息 | 多模态模型优先 |
| chat | 其他 | 便宜模型优先 |

### 3.2 Fallback 策略

```
L1（主模型）─── 400/429/402/超时 ──→ L2（降级模型）
                                          │
                                          ├─── 成功 → 返回
                                          └─── 失败 ──→ L3（保底模型）
                                                          │
                                                          ├─── 成功 → 返回
                                                          └─── 失败 → 返回错误
```

**Fallback 触发条件**：
- HTTP 400：参数不兼容（如图片传给纯文本模型）
- HTTP 429：限流
- HTTP 402：余额不足
- 超时：> 15 秒无响应
- 流式中断：SSE 连接断开

**Fallback 不触发条件**：
- HTTP 401/403：认证错误（break，不继续 fallback）
- HTTP 404：模型不存在（继续 fallback）

### 3.3 热更新机制

```
config_watcher.py → 监听文件变更（watchdog）
                  → 防抖（500ms）
                  → 验证配置格式
                  → 原子替换（先写 .tmp → rename）
                  → proxy.py 内存更新（≤ 10 秒）
```

---

## 4. 依赖关系

### 4.1 外部依赖

| 依赖 | 用途 | 故障影响 |
|------|------|---------|
| coding-plan provider | 主要 AI 模型 | fallback 到 longCat/deepseek |
| longCat provider | 大 ctx 文本模型 | fallback 到 deepseek |
| deepseek provider | 推理模型 | fallback 到 coding-plan |

### 4.2 内部依赖

| 依赖 | 用途 |
|------|------|
| OpenClaw Gateway | 模型注册 + 请求转发 |
| LaunchAgent | 自动启动 + KeepAlive |

---

## 5. 演进路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 基础 proxy + 路由 + fallback | ✅ 完成 |
| Phase 2 | 健康探测 + 用量追踪 | ✅ 完成 |
| Phase 3 | 热更新 + 预算告警 | ✅ 完成 |
| Phase 4 | 智能路由（ML 分类替代关键词） | 📋 规划中 |
| Phase 5 | 多租户 + 成本分摊 | 📋 规划中 |
