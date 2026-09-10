# Error Handler — 统一错误处理

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L1 Runtime
> **依赖**: L1 telemetry（错误埋点）、L1 context-bus（错误事件发布）

---

## 1. 职责

系统级**错误检测、分类、上报与自愈**。

- 统一错误模型：标准化错误码 / 严重级别 / 分类
- 错误捕获：try/except 装饰器 + context-bus 事件监听
- 错误分类：按严重级别（Sev1~Sev4）+ 按类型（网络/超时/配置/业务/未知）
- 自愈策略：重试 / 降级 / 切换备用路径
- 错误上报：Sev1~Sev2 主动通知，Sev3~Sev4 仅记录
- 死信队列：处理失败的请求归档，供事后分析

## 2. 与 L2 error-handling 的关系

| 层 | 组件 | 职责 |
|---|---|---|
| **L1** | error-handler | 框架级错误抽象、统一错误模型、基础重试/降级机制 |
| **L2** | error-handling | 业务级错误巡检脚本、cron 自动扫描、provider 健康探测 |

L1 是**底层机制**（错误模型 + 捕获 + 基础自愈），L2 是**上层应用**（巡检脚本 + 自动处置流程）。

## 3. 核心接口

### 3.1 ErrorHandler (ABC)

```python
class ErrorHandler(ABC):
    def handle(self, error: AppError, context: dict | None = None) -> ErrorOutcome: ...
    def register_strategy(self, error_type: str, strategy: RecoveryStrategy) -> None: ...
    def capture(self, exception: Exception, context: dict | None = None) -> AppError: ...
    def get_stats(self, window_seconds: int = 3600) -> ErrorStats: ...
```

### 3.2 AppError (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `error_id` | str | 全局唯一错误 ID |
| `code` | str | 错误码（统一错误码规范） |
| `message` | str | 错误信息 |
| `severity` | Severity | 严重级别（SEV1~SEV4） |
| `category` | str | 分类（network / timeout / config / business / unknown） |
| `source` | str | 来源组件 |
| `trace_id` | str | 关联 trace_id |
| `stack_trace` | str \| None | 堆栈信息 |

---

## 4. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 错误模型 | ✅ 骨架 | `models.py` |
| ErrorHandler ABC | ✅ 骨架 | `error_handler.py` |
| RecoveryStrategy ABC | ✅ 骨架 | `strategy.py` |
| 内存实现 | 📋 待开发 | InMemoryErrorHandler |
| 重试策略 | 📋 待开发 | RetryStrategy（指数退避） |
| 降级策略 | 📋 待开发 | FallbackStrategy |

## 5. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_error_handler_skeleton.py` | 7 | ABC 契约 / 错误模型 / 严重级别 |
