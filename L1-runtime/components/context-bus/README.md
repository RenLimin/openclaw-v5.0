# Context Bus — 上下文总线

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L1 Runtime
> **依赖**: 无（横切组件，被其他 L1/L2 组件依赖）

---

## 1. 职责

跨层、跨组件的**消息传递与事件总线**。

- 事件发布/订阅：组件间解耦通信
- 请求/响应：同步的跨组件调用
- 上下文传播：trace_id / 会话上下文 / 用户身份随消息传递
- 消息过滤：按类型 / 主题 / 标签过滤
- 死信队列：处理失败的消息

## 2. 核心接口

### 2.1 ContextBus (ABC)

```python
class ContextBus(ABC):
    def publish(self, topic: str, event: BusEvent) -> None: ...
    def subscribe(self, topic: str, handler: Callable) -> str: ...  # 返回 subscription_id
    def unsubscribe(self, subscription_id: str) -> bool: ...
    def request(self, topic: str, request: BusEvent, timeout: float) -> BusEvent: ...  # 同步请求
    def get_context(self) -> dict: ...  # 获取当前上下文（trace_id/session_id/user_id）
    def set_context(self, **kwargs) -> None: ...
```

### 2.2 BusEvent (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | str | 全局唯一事件 ID |
| `event_type` | str | 事件类型 |
| `topic` | str | 主题（用于路由） |
| `source` | str | 来源组件 |
| `payload` | dict | 事件负载 |
| `context` | dict | 传播上下文（trace_id / session_id / user_id） |
| `timestamp` | datetime | 发生时间 |

### 2.3 标准主题

| 主题 | 说明 |
|---|---|
| `system.*` | 系统级事件（启动/关闭/错误） |
| `session.*` | 会话事件（创建/结束/状态变化） |
| `tool.*` | 工具事件（调用前/调用后/错误） |
| `agent.*` | Agent 事件（创建/销毁/状态） |
| `error.*` | 错误事件（分级错误） |
| `metric.*` | 指标事件（遥测数据） |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 事件模型 | ✅ 骨架 | `models.py` |
| ContextBus ABC | ✅ 骨架 | `bus.py` |
| 内存实现 | 📋 待开发 | InMemoryContextBus |
| 分布式实现 | 📋 待开发 | Redis Pub/Sub 或 Kafka |

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_context_bus_skeleton.py` | 6 | ABC 契约 / 事件模型 / 订阅接口 |
