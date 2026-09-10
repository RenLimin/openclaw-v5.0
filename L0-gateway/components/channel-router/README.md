# Channel Router — 消息路由组件

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L0 Gateway
> **依赖**: L1 RuntimeAdapter (get_channel / execute_tool)

---

## 1. 职责

负责所有消息的**入站接收、协议转换、路由分发、出站投递**。

- 入站：从各通道接收消息 → 转为统一内部模型 → 路由到目标 Agent
- 出站：从 Agent 接收响应 → 转为通道原生格式 → 投递到目标通道
- 路由策略：按通道 / 按用户 / 按会话 / 自定义规则
- 通道注册：动态注册/注销通道适配器

---

## 2. 核心接口

### 2.1 Router (ABC)

```python
class Router(ABC):
    def route_inbound(self, message: InternalMessage) -> RouteTarget: ...
    def route_outbound(self, message: InternalMessage, target: RouteTarget) -> ChannelAdapter: ...
    def register_adapter(self, name: str, adapter: ChannelAdapter) -> None: ...
    def unregister_adapter(self, name: str) -> None: ...
    def list_adapters(self) -> list[str]: ...
```

### 2.2 ChannelAdapter (ABC)

```python
class ChannelAdapter(ABC):
    name: str
    def receive(self, timeout: float | None = None) -> InternalMessage | None: ...
    def send(self, target: str, message: InternalMessage) -> SendResult: ...
    def to_internal(self, raw: Any) -> InternalMessage: ...
    def from_internal(self, msg: InternalMessage) -> Any: ...
    def health_check(self) -> HealthStatus: ...
```

### 2.3 InternalMessage (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `message_id` | str | 全局唯一消息 ID |
| `channel` | str | 来源通道 |
| `sender` | IdentityRef | 发送者引用 |
| `session_id` | str | 会话 ID |
| `content` | str | 消息文本内容 |
| `attachments` | list[Attachment] | 附件列表 |
| `metadata` | dict | 扩展元数据 |
| `timestamp` | datetime | 消息时间 |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 数据模型 | ✅ 骨架 | `models.py` 定义 InternalMessage / RouteTarget / SendResult |
| Router ABC | ✅ 骨架 | `router.py` 定义路由抽象基类 |
| ChannelAdapter ABC | ✅ 骨架 | `channel_adapter.py` 定义通道适配抽象基类 |
| 内存实现 | 📋 待开发 | InMemoryRouter + 简单路由策略 |
| 通道适配器 | 📋 待开发 | WeCom / WebChat / Discord 等 |

---

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_router_skeleton.py` | 9 | ABC 不可实例化 / 接口签名 / 模型序列化 |

运行：`pytest components/channel-router/tests/`
