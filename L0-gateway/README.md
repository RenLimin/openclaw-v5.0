# L0 — Gateway 层（消息网关与接入层）

> **状态**: 📐 骨架阶段 (v0.1, 2026-09-11)
> **层级**: L0 — 系统最外层，所有消息的入站/出站枢纽
> **同级**: L0-install（安装部署侧，同属 L0 但职责不同）

---

## 1. 层定位

L0 Gateway 是系统的**流量入口与出口**，负责所有外部通道（WeCom / WebChat / Discord / Slack / REST API 等）的接入、消息路由、会话生命周期管理与身份认证。

```
┌──────────────────────────────────────────────────────────────┐
│                    External Channels                          │
│   WeCom  ·  WebChat  ·  Discord  ·  Slack  ·  REST API       │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────┐
│                     L0  Gateway Layer                         │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────────┐    │
│  │ auth-gateway│  │channel-router │  │ session-manager  │    │
│  │ (认证鉴权)   │  │ (消息路由)     │  │  (会话管理)       │    │
│  └─────────────┘  └───────────────┘  └──────────────────┘    │
└─────────────────────────────┬────────────────────────────────┘
                              │ L1 RuntimeAdapter
┌─────────────────────────────▼────────────────────────────────┐
│                     L1  Runtime Layer                         │
└──────────────────────────────────────────────────────────────┘
```

### 与 L0-install 的关系

| 模块 | 职责 | 阶段 |
|---|---|---|
| **L0-install** | 运行时选型、安装、适配层初始化、验证 | 部署 / 运维阶段 |
| **L0-gateway** | 消息接入、路由、会话、认证 | 运行时 / 流量阶段 |

两者同属 L0 层（系统边界），但一个面向**部署**，一个面向**流量**。

---

## 2. 核心职责

| 职责 | 归属组件 | 说明 |
|---|---|---|
| 通道接入与协议转换 | channel-router | 把各通道的消息格式统一为内部消息模型 |
| 入站/出站路由 | channel-router | 消息从哪来、到哪去，支持单播/广播/组播 |
| 会话生命周期 | session-manager | 创建/恢复/归档/销毁会话，维护会话状态 |
| 身份认证 | auth-gateway | 验证消息发送者身份、通道签名、API Key |
| 权限判定（粗粒度） | auth-gateway | 通道级 / 用户级的接入权限 |
| 速率限制 | auth-gateway | 防刷、限流、熔断 |

---

## 3. 组件清单

| 组件 | 路径 | 状态 | 说明 |
|---|---|---|---|
| **channel-router** | `components/channel-router/` | 📐 骨架 | 消息路由与通道适配 |
| **session-manager** | `components/session-manager/` | 📐 骨架 | 会话生命周期管理 |
| **auth-gateway** | `components/auth-gateway/` | 📐 骨架 | 认证鉴权与速率限制 |

---

## 4. 与 L1 的接口契约

L0 Gateway 只依赖 L1 Runtime 的以下能力：

| L1 能力 | 用途 | 调用方向 |
|---|---|---|
| `get_channel(name)` | 出站消息投递 | L0 → L1 |
| `execute_tool(name, params)` | 触发 Agent 执行 | L0 → L1 |
| `get_memory(scope)` | 会话状态持久化 | L0 → L1 |
| `health_check()` | 网关健康探针 | L0 → L1 |

**反向调用**：L1 不主动调用 L0。L1 的出站消息通过 ChannelInterface 回调到 L0 的出站路由。

---

## 5. 设计约束

1. **无状态优先** — 网关组件尽量无状态，会话状态持久化到 L1 Memory
2. **协议无关内核** — 路由内核不感知具体通道协议，所有协议转换在 adapter 层完成
3. **失败隔离** — 单通道故障不影响其他通道
4. **可观测** — 所有入站/出站消息埋点，接入 L1 telemetry
5. **安全边界** — L0 是系统安全第一道防线，认证/限流在此完成

---

## 6. 演进路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| v0.1 | 骨架 + 接口定义 + 基础测试 | ✅ 当前 |
| v0.2 | channel-router 内存实现 + 单通道 e2e | 📋 待排期 |
| v0.3 | session-manager 持久化 + 会话恢复 | 📋 待排期 |
| v0.5 | auth-gateway 签名验证 + 限流 | 📋 待排期 |
| v1.0 | 多通道接入 + 灰度路由 | 📋 待排期 |

---

## 7. 目录结构

```
L0-gateway/
├── README.md                        # 本文件
├── docs/
│   └── architecture.md              # L0 详细架构设计
└── components/
    ├── channel-router/              # 消息路由
    │   ├── README.md
    │   ├── src/
    │   │   ├── __init__.py
    │   │   ├── models.py            # 消息模型
    │   │   ├── router.py            # 路由 ABC
    │   │   └── channel_adapter.py   # 通道适配 ABC
    │   └── tests/
    │       ├── __init__.py
    │       └── test_router_skeleton.py
    ├── session-manager/             # 会话管理
    │   ├── README.md
    │   ├── src/
    │   │   ├── __init__.py
    │   │   ├── models.py            # 会话模型
    │   │   └── session_store.py     # 会话存储 ABC
    │   └── tests/
    │       ├── __init__.py
    │       └── test_session_skeleton.py
    └── auth-gateway/                # 认证网关
        ├── README.md
        ├── src/
        │   ├── __init__.py
        │   ├── models.py            # 身份模型
        │   └── auth_provider.py     # 认证提供者 ABC
        └── tests/
            ├── __init__.py
            └── test_auth_skeleton.py
```
