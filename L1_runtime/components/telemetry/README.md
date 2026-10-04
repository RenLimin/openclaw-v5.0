# Telemetry — 遥测与指标收集

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L1 Runtime
> **依赖**: L1 context-bus（事件总线）

---

## 1. 职责

系统级**可观测性数据收集与导出**。

- 指标（Metrics）：计数器 / 直方图 / 仪表盘 / 计时器
- 追踪（Tracing）：分布式链路追踪（基于 context-bus 的 trace_id）
- 日志（Logging）：结构化日志收集与分级
- 导出（Export）：Prometheus / OpenTelemetry / 文件 / 自定义导出器

## 2. 核心接口

### 2.1 TelemetryProvider (ABC)

```python
class TelemetryProvider(ABC):
    # metrics
    def counter(self, name: str, value: float = 1, labels: dict | None = None) -> None: ...
    def gauge(self, name: str, value: float, labels: dict | None = None) -> None: ...
    def histogram(self, name: str, value: float, labels: dict | None = None) -> None: ...
    def timing(self, name: str, duration: float, labels: dict | None = None) -> None: ...

    # tracing
    def start_span(self, name: str, parent_span_id: str | None = None) -> Span: ...
    def end_span(self, span: Span) -> None: ...

    # logging
    def log(self, level: str, message: str, **kwargs) -> None: ...

    # export
    def register_exporter(self, exporter: MetricsExporter) -> None: ...
    def collect(self) -> MetricsSnapshot: ...
```

### 2.2 标准指标命名

| 指标名 | 类型 | 说明 |
|---|---|---|
| `tool.calls_total` | Counter | 工具调用总次数 |
| `tool.errors_total` | Counter | 工具调用失败次数 |
| `tool.duration_seconds` | Histogram | 工具调用耗时 |
| `session.active` | Gauge | 当前活跃会话数 |
| `agent.requests_total` | Counter | Agent 请求总数 |
| `gateway.messages_total` | Counter | 网关消息总数 |
| `bus.events_published` | Counter | 总线发布事件数 |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 指标模型 | ✅ 骨架 | `models.py`（MetricPoint / Span / MetricsSnapshot） |
| TelemetryProvider ABC | ✅ 骨架 | `telemetry.py` |
| MetricsExporter ABC | ✅ 骨架 | `exporter.py` |
| 内存实现 | 📋 待开发 | InMemoryTelemetry |
| Prometheus 导出 | 📋 待开发 | PrometheusExporter |
| 与 context-bus 集成 | 📋 待开发 | 自动埋点总线上的事件 |

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_telemetry_skeleton.py` | 6 | ABC 契约 / 指标模型 / Span |
