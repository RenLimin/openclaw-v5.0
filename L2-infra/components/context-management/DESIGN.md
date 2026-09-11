# L2 上下文管理组件 (context-management) — 设计

> **状态**: 已上线（2026-08-22 创建）
> **层级**: L2 基础设施层
> **组件类**: 上下文窗口估算与 subagent 保护

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 上下文窗口估算 / 分段策略 / subagent 保护 |
| 状态 | ✅ 已建设 |
| 设计依据 | AGENTS.md §"长任务隔离" + §"Subagent 上下文保护规范" |

## 2. 职责

为 subagent 任务提供**上下文窗口保护**能力：

1. **上下文窗口估算** — 根据任务描述和预估步数，计算 token 预算和分段策略
2. **分段策略生成** — 超过 50% ctx 安全线时自动建议分段数和每段预算
3. **模型 ctx 管理** — 支持多模型 ctx window 配置（内置默认值 + openclaw.json 读取）
4. **超时建议** — 根据任务规模推荐 `runTimeoutSeconds`
5. **实测探针** — 二分探边界法实测模型真实输入 token 上限

## 3. 核心设计

### 3.1 模块架构

```
context-management/
├── subagent_ctx_guard.py      ← 上下文保护评估（分段策略 + token 预算）
├── probe_context_window.py    ← 实测探针（二分探边界）
└── tests/
    ├── conftest.py
    └── test_smoke.py
```

### 3.2 上下文保护模型

```
┌─────────────────────────────────────────────────────────┐
│                  Subagent 上下文保护                        │
│                                                          │
│  ┌──────────────┐     ┌──────────────┐                  │
│  │  Token 预算   │     │  分段策略     │                  │
│  │  计算器       │ ──→ │  生成器       │                  │
│  └──────────────┘     └──────────────┘                  │
│         │                     │                          │
│         ▼                     ▼                          │
│  ┌──────────────┐     ┌──────────────┐                  │
│  │  每步开销模型 │     │  超时建议     │                  │
│  │  (经验值)     │      │  (分档)       │                  │
│  └──────────────┘     └──────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Token 预算计算

```
总 token = base_prompt + (per_step_cost × steps) + output_limit

其中:
  base_prompt    = 8,000   (system + AGENTS.md 摘要)
  per_step_cost  = exec_output(2,000) + tool_call(500) + thinking(1,000) = 3,500
  output_limit   = 2,000   (回传主会话限制)
```

**安全阈值**：有效 ctx window 的 50%

- 有效 ctx window = 标称值 × 80%（保守取值）
- 超过安全阈值 → 必须分段

### 3.4 分段策略

| 条件 | 策略 |
|---|---|
| 预估总量 ≤ 50% ctx | 单段执行 |
| 预估总量 > 50% ctx | 计算每段可用步数，向上取整分段 |
| 任务 > 50 步 | 强制拆成多个 subagent 串行执行 |

每段预算公式：
```
usable_per_seg = safe_threshold - base_prompt - output_limit
steps_per_seg  = usable_per_seg // per_step_cost
segments       = ceil(estimated_steps / steps_per_seg)
```

### 3.5 模型 ctx window 配置

| 模型 | 有效 ctx（标称 × 80%） |
|---|---|
| coding-plan/doubao-seed-2-1-turbo | 200,000 |
| coding-plan/doubao-seed-2-0-lite | 200,000 |
| coding-plan/doubao-seed-code-preview | 200,000 |
| coding-plan/deepseek-v4-flash | 800,000 |
| model-scheduling/auto | 200,000 |
| 其他（从 openclaw.json 读取） | contextWindow × 0.8 |
| 默认兜底 | 100,000 |

### 3.6 超时建议

| 任务规模 | 建议 runTimeoutSeconds |
|---|---|
| ≤ 10 步 | 600s |
| 11-30 步 | 1800s |
| > 30 步 | 3600s（且必须分段） |

### 3.7 实测探针（probe_context_window.py）

二分探边界法实测模型真实输入 token 上限：

```
原理: "hello " × N ≈ N tokens → 用 N 定位边界
方法: max_tokens=4 只探输入侧，避免 input+output 混淆

判定:
  - 400 + "context window exceeded" = 真边界
  - 429 AccountRateLimitExceeded = 频率限制，等 60~75s 重试
  - 200 OK = 未达边界，增大 N 继续探

容错:
  - openclaw.json 损坏 → 自动尝试 .bak 备份恢复
  - 大请求耗时 30s~2min，建议后台运行
```

方法论详见：`EXP-20260822-004-context-window-empirical-probe.md`

## 4. 接口与用法

```bash
# 上下文保护评估
python3 L2-infra/components/context-management/subagent_ctx_guard.py \
  "重构项目代码结构" 80
python3 L2-infra/components/context-management/subagent_ctx_guard.py \
  "批量处理 100 个文件" 120 --model coding-plan/doubao-seed-2-1-turbo
python3 L2-infra/components/context-management/subagent_ctx_guard.py \
  "任务描述" 50 --json   # JSON 格式输出

# 实测探针
python3 L2-infra/components/context-management/probe_context_window.py \
  glm-5.3 10          # 健全性检查
python3 L2-infra/components/context-management/probe_context_window.py \
  glm-5.3 1048550     # 探边界
```

### 4.1 退出码语义

`subagent_ctx_guard.py` 退出码：
- `0` — 单段可容纳
- `1` — 需要分段（方便脚本调用判断）

## 5. 依赖

| 依赖 | 用途 |
|---|---|
| Python 3 | 两个脚本均为纯 Python |
| `~/.openclaw/openclaw.json` | 读取模型 ctx 配置（可选，缺失时用默认值） |
| `urllib` | probe_context_window.py 直接调用 provider API |

## 6. 设计约束

1. **保守估算** — 有效 ctx 取标称值 80%，避免边界溢出
2. **50% 安全线** — 超过即分段，绝不含糊
3. **输出精简** — 回传主会话不超过 2,000 tokens（约 8,000 字符）
4. **详细结果写文件** — subagent 不粘贴完整内容到回复
5. **幂等** — 相同输入产生相同输出
6. **纯计算无副作用** — 不修改任何系统状态

## 7. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 实测值校准 | 中 | 积累更多 probe 数据后修正每步开销经验值 |
| 自动分段执行 | 低 | 与 sessions_spawn 集成，自动拆分长任务 |
| 动态 ctx 检测 | 低 | 运行时检测实际 ctx 使用量，动态调整分段 |
| 多模型支持 | 低 | 新增模型时自动从 openclaw.json 读取 ctx |

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-22 | 首版：subagent_ctx_guard.py + probe_context_window.py |
| 2026-08-23 | 多模型 ctx 配置 + openclaw.json 动态读取 |
