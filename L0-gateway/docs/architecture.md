# L0 Gateway 架构设计

> **版本**: v0.1 (骨架)
> **状态**: design
> **更新**: 2026-09-11

---

## 1. 架构总览

L0 Gateway 采用 **管道-过滤器** 架构模式。每条入站消息经过一条处理链：

```
入站消息 → [认证] → [限流] → [协议转换] → [路由] → [会话绑定] → L1 Agent
                                                           ↓
出站消息 ← [协议转换] ← [路由] ← [格式化] ← [限流] ← L1 Agent
```

### 1.1 核心设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 架构模式 | 管道-过滤器 | 各环节职责单一，可独立替换/扩展 |
| 消息模型 | 统一内部 Message 模型 | 通道协议差异在 adapter 层消化 |
| 会话存储 | 抽象 SessionStore 接口 | 默认内存实现，可切换到 Redis/L1 Memory |
| 认证模型 | 可插拔 AuthProvider | 不同通道用不同认证方式 |
| 限流策略 | 令牌桶 + 漏桶组合 | 突发流量用令牌桶，持续流量用漏桶 |

---

## 2. 数据流

### 2.1 入站流程

```
1. 通道适配器接收原始消息（各通道格式不同）
2. 转换为统一 InternalMessage 模型
3. AuthProvider 验证身份
   ├→ 失败 → 拒绝响应 + 计数
   └→ 成功 → 继续
4. RateLimiter 检查速率
   ├→ 超限 → 排队 / 拒绝
   └→ 通过 → 继续
5. SessionManager 获取或创建会话
6. Router 路由到目标 Agent（通过 L1 RuntimeAdapter 触发执行）
```

### 2.2 出站流程

```
1. L1 Agent 通过 ChannelInterface 发送消息
2. Router 查找到目标通道 + 会话
3. 格式化（Markdown → 通道原生格式）
4. 出站限流检查
5. 通道适配器投递
6. 结果回传（成功/失败/重试）
```

---

## 3. 组件详细设计

### 3.1 Channel Router

**职责**：消息路由分发 + 通道适配注册。

**核心抽象**：
- `Router` — 路由策略（按通道/按用户/按会话）
- `ChannelAdapter` — 通道协议转换（收 / 发 / 格式转换）
- `Message` — 统一内部消息模型

**扩展点**：新增通道 = 新增一个 ChannelAdapter 实现 + 注册

### 3.2 Session Manager

**职责**：会话生命周期管理 + 状态持久化。

**核心抽象**：
- `SessionStore` — 会话存储接口（CRUD + 查询）
- `Session` — 会话数据模型

**会话状态机**：
```
creating → active → idle → archived → deleted
              ↑        ↓
              └── resuming
```

### 3.3 Auth Gateway

**职责**：身份认证 + 接入授权 + 速率限制。

**核心抽象**：
- `AuthProvider` — 认证提供者接口（verify / issue / revoke）
- `Identity` — 身份模型
- `RateLimiter` — 限流器接口

---

## 4. 与各层的契约

### 4.1 向上（外部通道）

- 通过 Channel Adapter 对接，新增通道不修改内核
- 每个通道必须实现：收消息、发消息、错误上报

### 4.2 向下（L1 Runtime）

- 通过 RuntimeAdapter 触发 Agent 执行
- 通过 MemoryInterface 持久化会话状态
- 通过 ChannelInterface 回传出站消息

---

## 5. 非功能需求

| 维度 | 目标 |
|---|---|
| 吞吐量 | 单实例 ≥ 100 msg/s |
| 延迟 | p99 < 200ms（不含 Agent 执行时间） |
| 可用性 | ≥ 99.9%（单通道故障不影响全局） |
| 可观测 | 全链路 trace_id，消息级指标 |

---

## 6. 待决事项

- [ ] 消息队列选型（内存 / Redis / Kafka）
- [ ] 会话存储默认实现选择
- [ ] 认证中间件链的扩展机制
- [ ] 与现有 L2-infra 中 observability 组件的埋点对齐
