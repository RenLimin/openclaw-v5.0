# Session Manager — 会话管理组件

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L0 Gateway
> **依赖**: L1 MemoryInterface (持久化会话状态)

---

## 1. 职责

管理所有会话的**生命周期与状态**。

- 会话创建：新用户/新通道首次交互时创建
- 会话查找：按 session_id / 用户 / 通道查找
- 会话恢复：从持久化存储恢复活跃会话
- 会话状态流转：active → idle → archived → deleted
- 会话元数据：用户信息、通道、创建时间、最后活跃时间、上下文引用

---

## 2. 核心接口

### 2.1 SessionStore (ABC)

```python
class SessionStore(ABC):
    def get(self, session_id: str) -> Session | None: ...
    def create(self, session: Session) -> Session: ...
    def update(self, session_id: str, **kwargs) -> Session: ...
    def delete(self, session_id: str) -> bool: ...
    def list_by_user(self, user_id: str) -> list[Session]: ...
    def list_by_channel(self, channel: str) -> list[Session]: ...
    def find_active(self, user_id: str, channel: str) -> Session | None: ...
    def cleanup_idle(self, idle_seconds: int) -> int: ...
```

### 2.2 Session (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | str | 全局唯一会话 ID |
| `channel` | str | 所属通道 |
| `user_id` | str | 用户标识 |
| `status` | SessionStatus | 状态枚举 |
| `created_at` | datetime | 创建时间 |
| `last_active_at` | datetime | 最后活跃时间 |
| `context_ref` | str | 上下文引用（传给 L1 的 session scope） |
| `metadata` | dict | 扩展元数据 |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 数据模型 | ✅ 骨架 | `models.py` 定义 Session / SessionStatus |
| SessionStore ABC | ✅ 骨架 | `session_store.py` 定义存储抽象基类 |
| 内存实现 | 📋 待开发 | InMemorySessionStore |
| L1 Memory 实现 | 📋 待开发 | MemorySessionStore（复用 L1 MemoryInterface） |

---

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_session_skeleton.py` | 8 | ABC 契约 / 模型序列化 / 状态流转合法性 |

运行：`pytest components/session-manager/tests/`
