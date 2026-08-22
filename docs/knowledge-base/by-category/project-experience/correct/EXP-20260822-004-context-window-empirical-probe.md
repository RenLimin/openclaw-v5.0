---
type: experience-card
id: EXP-20260822-004
date: 2026-08-22
title: contextWindow 实测法 — 二分探边界定官方声明的真实上限
layer: [L1]                    # OpenClaw 系统层：模型能力声明契约
stage: manage
severity: high                 # 声明过大 → 真实溢出；声明过小 → 浪费容量
kind: correct
tags: [openclaw, context-window, ark, volcengine, glm, minimax, probe, empirical]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260822-004] contextWindow 实测法：不要相信文档，去打端点

## 1. 背景

`openclaw.json` 里每个模型都要声明 `contextWindow`。声明错误的双向代价：

- **声明过大** → 真实请求被 provider 拒（400），且比本地预判溢出更难排查
- **声明过小** → 浪费可用容量，过早触发 compaction

前一轮（EXP-20260821-003）我靠**文档 + 第三方资料**推断这些值，结果 3 个模型全错。本卡记录实测方法与结论。

## 2. 问题：文档不可靠的三种方式

| 情况 | 具体案例 | 后果 |
|---|---|---|
| **厂商文档描述的是直连 API，不是转售通道** | 第三方 issue 实测 MiniMax 直连拒绝 `>512000`，我据此把 ARK 的 `minimax-m3` 下调到 512000 | 白扔一半容量（真实 1M） |
| **厂商文档的启用条件不适用于转售通道** | 智谱官方：1M ctx 需模型名加 `[1m]` 后缀（`glm-5.3[1m]`） | 差点为不存在的问题改配置 |
| **官方 CLI 查不到尝鲜/别名模型** | `arkcli models get glm-5.3 / minimax-m3 / kimi-k2.7-code / ark-code-latest` 全部返回 `{ok, error}` | 无一手数据可依赖 |

`arkcli models get` 只对**一方模型 + GA 版第三方模型**有 `limits` 字段（`glm-5-2`、`deepseek-v4-flash-ga`、`doubao-*` 可查）。尝鲜版与 coding 端点别名查不到。

## 3. 方案：二分探边界

### 3.1 探测脚本

```python
#!/usr/bin/env python3
"""探测 ARK coding 端点某模型的真实输入上限。
用法: probe_ctx.py <model-id> <approx-token-count>
"""
import json, os, sys, urllib.request, urllib.error

MODEL, NTOK = sys.argv[1], int(sys.argv[2])
d = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
pr = d["models"]["providers"]["coding-plan"]
KEY, BASE = ***"apiKey"), pr["baseUrl"].rstrip("/")

body = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "hello " * NTOK + "\n\nReply with only: OK"}],
    "max_tokens": 4,          # 关键：输出设极小，只探输入侧
    "temperature": 0,
}
req = urllib.request.Request(
    f"{BASE}/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        u = json.load(r).get("usage", {})
    print(f"OK   {MODEL} req~{NTOK} prompt_tokens={u.get('prompt_tokens')}")
except urllib.error.HTTPError as e:
    print(f"FAIL {MODEL} req~{NTOK} http={e.code}\n     {e.read().decode()[:300]}")
```

### 3.2 关键技巧

1. **`"hello " * N` ≈ N tokens**。实测 `prompt_tokens` 与 N 差值恒定（+18~+182，即模板开销），比例 1:1，可直接用 N 定位边界。
2. **`max_tokens: 4`** — 只探输入侧。若输出设大，报错可能来自 `input+output > ctx`，边界会偏移。
3. **先小请求做健全性检查**（N=10），确认模型 ID 可用、key 有效，再加压。
4. **报错信息区分两类**：
   - `context window exceeded` / `exceeds limit` → 真的到上限
   - `AccountRateLimitExceeded` (429) → 请求太频，**不是**容量问题，等 60~75s 重试
5. **大请求要后台跑**。1M token 的请求 body 约 6MB，耗时 30s~2min，用 `yieldMs` + `process poll`。

### 3.3 实测结果（ARK Coding Plan 端点，2026-08-22）

| 模型 | 通过 | 拒绝 | 判定上限 | 配置最终值 |
|---|---|---|---|---|
| `glm-5.3` | 1,048,568 | 1,048,618 | **1,048,576** (1M) | 1048576 ✅ 无需改 |
| `minimax-m3` | 1,046,182 | 1,048,550* | **~1,048,576** (1M) | 1048576（512000 → 修正） |
| `ark-code-latest` | 224,051 | 230,051 | **229,376** (224k) | 229376（262144 → 修正） |

\* minimax-m3 在 1048550 处报 `exceeds limit`，比 glm-5.3 的边界略紧，但远高于 512000。

**边界精度示例**（glm-5.3）：
```
OK   req~1048550  prompt_tokens=1048568   # 距 1048576 仅 8 tokens
FAIL req~1048600  http=400 "context window exceeded"
```

## 4. 三个关键发现

### 4.1 `glm-5.3` 在 ARK 端点原生 1M，无需 `[1m]` 后缀

智谱官方文档要求 `glm-5.3[1m]` 才能启用 1M。**ARK 转售通道不套用此规则** —— 裸 `glm-5.3` 实测跑到 1,048,568 tokens。

**推论**：转售通道（火山方舟、OpenRouter 等）的模型行为与厂商直连**可能不同**，必须独立验证。

### 4.2 `ark-code-latest` 的真实上限是 224k，不是 262k

之前按"Auto 路由池最小值 = 262k（kimi-k2.7-code / doubao-seed）"推断，但实测 **230k 就被拒**：

```
OK   req~224000  prompt_tokens=224051
FAIL req~230000  "Total tokens of image and text exceed max message tokens"
```

224k 正是 `arkcli models get doubao-seed-2-0-lite-260215` 返回的 `max_input_token_length = 224k`（其 `context_window` 是 256k，但**输入侧只有 224k**）。

**关键区分**：
- `context_window` = 输入 + 输出总和
- `max_input_token_length` = **输入侧单独上限**，通常 = ctx − max_output

`contextWindow` 在 OpenClaw 里用于判断"历史能塞多少"，应对齐 **max_input**，不是 context_window。

### 4.3 报错文案能区分路由目标

`ark-code-latest` 的拒绝信息是 `Total tokens of image and text exceed max message tokens` —— 这是**豆包系**的文案。而 `glm-5.3` / `minimax-m3` 报 `context window exceeded` / `exceeds limit`。

说明请求实际落到了豆包系模型上，Auto 池确实在动态路由，且**上限由当次路由目标决定**。保守声明是必需的。

## 5. 教训

**规则**（可推广）：

1. **`contextWindow` 只信实测**。文档、第三方博客、其他 agent 的配置都是二手信息。打一次端点 5 分钟，配错要排查几小时。
2. **区分 `context_window` 与 `max_input_token_length`**。声明 `contextWindow` 时用后者。差值通常是 max_output（如 256k ctx − 32k out = 224k input）。
3. **转售通道要独立验证**。厂商文档描述直连行为；ARK/OpenRouter 等可能有不同的窗口策略、启用条件、路由行为。
4. **Auto/路由类模型 ID 按实测最小值声明**。`ark-code-latest` 声明 229376（224k），不是池内最大值也不是理论最小值，而是实测拒绝点下方的档位。
5. **二分探测要区分 400 和 429**。429 是频率限制，间隔 60~75s 重试；只有 400 + `context/limit` 文案才是真边界。
6. **保留探测脚本**。模型升级、套餐变更、provider 调整策略后需要重跑。脚本在 `/tmp` 会丢，应入库。

**监控点**：
- ⚠️ 火山方舟调整 Coding Plan 的 Auto 路由池 → `ark-code-latest` 的 224k 可能变化，需重测
- ⚠️ 新增模型入配置时，**先跑探测再声明 ctx**，不要照抄兄弟模型
- ⚠️ 智谱若把 `[1m]` 规则同步到 ARK 通道 → `glm-5.3` 需改 ID 或下调 ctx

**升级判断**：
- [x] 涉及 L1 契约（模型能力声明）
- [ ] 影响 ≥2 层
- [ ] 多模块对齐
- **决定**：保持经验卡片。这是操作方法论，非架构决策。

## 6. 相关

- **前序卡片**：`EXP-20260821-003`（compaction 死锁 — 本卡修正了其 §3.3 的推断值）
- **探测脚本**：`scripts/probe_context_window.py`
- **配置**：`~/.openclaw/openclaw.json` → `models.providers.coding-plan.models[].contextWindow`
- **一手数据源**：`arkcli models get <model-id>` 的 `limits` 字段（仅一方 + GA 模型可查）
- **套餐模型池**：`arkcli plans model-list`

## 7. 变更历史

- 2026-08-22: 创建（实测 glm-5.3 / minimax-m3 / ark-code-latest 三个模型的真实上限）
