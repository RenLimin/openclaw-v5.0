# context-management

**定位：** L2 基础设施层 — Subagent 上下文保护，防止长任务溢出 token 窗口。

## 功能列表

- Subagent 分段策略计算（根据任务步数和模型 ctx window）
- Token 预算分配（每段 < 50% ctx window）
- 模型 contextWindow 实测探测（二分探边界）
- 与 AGENTS.md 中的 subagent 上下文保护规范对齐

## 目录结构

```
context-management/
├── subagent_ctx_guard.py      # 分段策略 + token 预算计算
├── probe_context_window.py    # 模型 contextWindow 实测探测
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
└── DESIGN.md
```

## 使用方式

```bash
# 计算 subagent 分段策略
python3 subagent_ctx_guard.py "任务描述" <预估步数>
python3 subagent_ctx_guard.py "批量处理 100 个文件" 120 --model coding-plan/doubao-seed-2-1-turbo

# 探测模型真实 token 上限
python3 probe_context_window.py <model-id> <approx-token-count>
python3 probe_context_window.py glm-5.3 1048550
```

## 依赖

- Python 3
- `openclaw` CLI（probe_context_window.py 读取配置）
