# logs

**定位：** L2 基础设施层 — 日志管理与聚合。

## 功能列表

- 日志聚合器（`src/aggregator.py`，216 行）：多源日志采集、级别过滤、时间窗口聚合
- observability 子目录（预留给可观测性日志）

## 目录结构

```
logs/
├── src/
│   ├── aggregator.py           # 日志聚合器实现
│   └── __init__.py
└── observability/              # 预留目录
```

## 状态

✅ 已实现（聚合器核心可用）；日志查询 DSL、轮转策略为演进方向，尚未实现。

## 依赖

- 暂无（Python 标准库）
