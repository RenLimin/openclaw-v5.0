# L0 Gateway — 消息网关与接入层设计

> 组件：L0 Gateway (L0)
> 版本：v1.0
> 日期：2026-10-04

## 1. 定位

L0 Gateway 是系统的流量入口与出口，负责所有外部通道的接入、认证、会话生命周期管理与消息路由。

## 2. 架构模式

管道-过滤器模式。每条入站消息经过处理链：
```
认证 → 限流 → 协议转换 → 路由 → 会话绑定 → L1 Agent
```

## 3. 三大组件

### 3.1 auth-gateway — 身份认证与限流

| 类 | 职责 |
|---|---|
| `AuthProvider` (ABC) | 认证提供者抽象基类 |
| `TokenAuthProvider` | Bearer Token / JWT 认证 |
| `SignatureAuthProvider` | 签名认证（WeCom/钉钉等） |
| `ApiKeyAuthProvider` | API Key 认证 |
| `RateLimiter` (ABC) | 限流器抽象基类 |
| `TokenBucketRateLimiter` | 令牌桶（支持突发） |
| `SlidingWindowLimiter` | 滑动窗口（精确限流） |

### 3.2 channel-router — 消息路由

| 类 | 职责 |
|---|---|
| `ChannelAdapter` (ABC) | 通道适配器抽象基类 |
| `WebChatAdapter` | OpenClaw WebChat 适配 |
| `WeComAdapter` | 企业微信适配 |
| `DiscordAdapter` | Discord 适配（预留） |
| `MessageRouter` | 消息路由器（优先级路由） |
| `PriorityRouter` | 优先级路由器 |

### 3.3 session-manager — 会话管理

| 类 | 职责 |
|---|---|
| `SessionStore` (ABC) | 会话存储抽象基类 |
| `InMemorySessionStore` | 内存存储（开发/测试） |
| `L1MemorySessionStore` | 基于 L1 Memory 的存储 |

## 4. 数据模型

### 4.1 auth-gateway

- `AuthRequest` — 认证请求
- `AuthResult` — 认证结果
- `Identity` — 已认证身份

### 4.2 channel-router

- `InternalMessage` — 统一内部消息
- `RouteTarget` — 路由目标
- `SendResult` — 发送结果

### 4.3 session-manager

- `Session` — 会话
- `SessionStatus` — 会话状态（CREATING/ACTIVE/IDLE/ARCHIVED/DELETED）

## 5. 入站流程

```
1. 通道适配器接收原始消息
2. 转为统一 InternalMessage
3. AuthProvider 验证身份
4. RateLimiter 检查速率
5. SessionManager 获取或创建会话
6. Router 路由到目标 Agent
```

## 6. 依赖关系

- `auth-gateway` ← L1 MemoryInterface（持久化 Identity）
- `channel-router` ← L1 ChannelInterface（发送消息）
- `session-manager` ← L1 MemoryInterface（持久化 Session）

## 7. 演进方式

- 新增运行时 = 新增 channel 适配器
- 新增认证方式 = 新增 AuthProvider 实现
- 新增通道 = 新增 ChannelAdapter 实现

## 8. 测试方案

- 单元测试：认证/限流/路由/会话状态流转
- 集成测试：完整入站→处理→出站链路
- E2E 测试：多通道并发消息处理
