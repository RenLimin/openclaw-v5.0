# Tool Policy — 工具策略审计组件

> L2 基础设施层 · 工具可见性治理 + 六项审计
>
> **2026-09-11**：基于 `tool_policy_audit.sh` 实际代码重写。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 工具策略治理 |
| 状态 | ✅ 已建设 (2026-08-22) |
| 关联 ADR | ADR-202608-008 (工具策略治理) |

## 2. 设计约束

1. **"允许" ≠ "可用"**：`tools.profile/allow/deny` 只治理授权边界，不保证工具真能干活。审计同时检查两者。
2. **三态模型**：每个工具有且仅有三种状态 — `denied`（策略拒绝，明确失败）/ `allowed-but-broken`（允许但缺依赖，静默失败★高危）/ `allowed-and-working`（真实可用）。
3. **静默降级是最危险的故障**：配置了 provider 但缺凭据，不报错只是召回变差，必须主动探测。
4. **CI 友好**：脚本输出结构化，退出码 0/1，可被 cron 或 pre-commit 集成。
5. **零外部依赖**：仅依赖 `openclaw` CLI + Python 3 标准库。

## 3. 架构

```
┌─────────────────────────────────────────────────────────┐
│              tool_policy_audit.sh (单一脚本)             │
│                                                         │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 第 1 段  │ │ 第 2 段   │ │ 第 3 段   │ │ 第 4 段   │   │
│  │ 策略配置 │ │ allow/   │ │ 技能可用  │ │ memory_  │   │
│  │ profile │ │ alsoAllow│ │ 性检查    │ │ search   │   │
│  │ 检查    │ │ 冲突检查  │ │          │ │ 真实状态  │   │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘   │
│                                                         │
│  ┌─────────┐ ┌──────────┐                              │
│  │ 第 5 段  │ │ 第 6 段   │                              │
│  │ 媒体工具 │ │ plugin   │                              │
│  │ provider│ │ 解锁状态  │                              │
│  └─────────┘ └──────────┘                              │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 汇总输出 → exit 0 (健康) / exit 1 (发现问题)    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          │
                          │ 调用
                          ▼
┌─────────────────────────────────────────────────────────┐
│  openclaw CLI                                           │
│  ├── openclaw config get tools                          │
│  ├── openclaw skills check                              │
│  ├── openclaw config get memory.search                  │
│  ├── openclaw plugins list                              │
│  └── openclaw config get agents.defaults.mediaModels    │
└─────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 审计脚本 | `tool_policy_audit.sh` | 六段审计 + 汇总输出，单一入口 |

本组件为单一脚本组件，无子模块拆分。

## 4. 六项审计详解

### 4.1 第 1 段 — 策略配置 (profile)

**检查目标**：`tools.profile` 的值

| profile | 判定 | 说明 |
|---|---|---|
| `coding` / `messaging` / `minimal` | ✅ 通过 | 非 full，符合最小权限原则 |
| `full` | ❌ 问题 | 违反最小权限原则 |
| 未设置 | ⚠️ 警告 | 依赖默认值，未显式声明 |

**实现**：`openclaw config get tools` → 解析 JSON → 取 `profile` 字段

### 4.2 第 2 段 — allow / alsoAllow 冲突

**检查目标**：同一 scope 内 `allow` 与 `alsoAllow` 并存

- config 校验会拒绝此配置，但审计提前拦截更友好
- 检查三个 scope：`tools` 根级、`tools.byProvider.*`、`tools.toolsBySender.*`

**实现**：Python 内嵌脚本解析 JSON，逐 scope 检查

### 4.3 第 3 段 — 技能可用性 (allowed-but-broken)

**检查目标**：`openclaw skills check` 输出中 "Missing requirements" 段

- 这些技能在策略上允许，但缺少二进制/环境变量/配置
- 高危：agent 尝试调用时静默失败，不报错

**修复建议**：`openclaw doctor --fix`（禁用不可用技能，减少误调用）

### 4.4 第 4 段 — memory_search 真实状态 ★

**检查目标**：语义检索是否真正可用

分三条路径探测：

| provider | 检查项 | 通过条件 |
|---|---|---|
| `openai` (默认) | `OPENAI_API_KEY` 或 `models.providers.openai.apiKey` | 任一已配置 |
| `local` | ① llama-cpp 插件已加载 ② GGUF 模型文件存在且 magic 正确 ③ 未误设 `local.modelPath` | 全部满足 |
| 其他 | — | 默认通过 |

**关键陷阱**（ADR-009 §7.1）：
- `local.modelPath` 设绝对路径 → 索引身份与 gateway 不匹配
- 模型文件名被重命名 → 索引身份变化，需重建

### 4.5 第 5 段 — 媒体工具 provider

**检查目标**：`agents.defaults.mediaModels` 是否配置

- 未配置 → `image_generate` / `music_generate` / `video_generate` 在 coding profile 内但不会出现
- 这是官方预期行为，非故障

### 4.6 第 6 段 — plugin 工具解锁状态

**检查目标**：`tools.alsoAllow` 列表

- plugin 工具在 coding profile 下可能默认 deny
- 新增 plugin 后需显式确认是否可用

## 5. 三态模型

```
             ┌───────────────────────────────────┐
             │         工具可见性三态             │
             └───────────────────────────────────┘

  denied                allowed-but-broken         allowed-and-working
  (策略拒绝)            (允许但缺依赖)              (真实可用)
      │                      │                          │
      ▼                      ▼                          ▼
  明确报错               静默失败                    正常执行
  低危 ★                高危 ★★                    —
                        最难发现
```

**核心区分**：
- `denied` = config 策略拒绝，agent 调用时明确报错，容易发现
- `allowed-but-broken` = 策略允许但缺依赖，静默失败，agent 以为调了但没效果 ★
- `allowed-and-working` = 策略允许 + 依赖满足，真实可用

## 6. 接口与调用

```bash
# 直接运行审计
bash L2-infra/components/tool-policy/tool_policy_audit.sh

# 退出码
# 0 = 健康（全部通过）
# 1 = 发现问题（输出问题分类统计）
```

### 6.1 输出格式

```
════════════════════════════════════════════
 L2 工具策略审计
════════════════════════════════════════════

▶ 策略配置
    ✅ profile=coding（非 full，符合最小权限）

▶ allow / alsoAllow 冲突检查
    ✅ 无冲突

▶ 技能可用性（allowed-but-broken）
    ⚠️ 12 个技能允许但缺依赖

▶ memory_search 真实能力
    ✅ 本地 GGUF 模型正常

▶ 媒体工具 provider
    ✅ 无需处理

▶ plugin 工具解锁状态
    alsoAllow 已解锁 3 项

════════════════════════════════════════════
⚠️ 发现 X 类问题
```

## 7. 与其他组件的关系

```
tool-policy (本组件)
    │
    ├── 依赖 ─── openclaw CLI (config / skills / plugins)
    │
    ├── 被调用 ─ AGENTS.md §异常自动处置 (统一扫描入口)
    │
    ├── 被调用 ─ L2-infra/scripts/error_handler/scan_errors.sh
    │
    └── 协作 ── knowledge-base (审计结果可写入知识库经验)
```

## 8. 集成方式

| 集成点 | 方式 | 频率 |
|---|---|---|
| Cron 定时审计 | OpenClaw cron job 调用 | 每 2 小时（通过 scan_errors.sh 统一入口） |
| 手动巡检 | 直接执行脚本 | 按需 |
| Pre-commit | 可被 Git hook 集成 | 提交前（当前未接入） |

## 9. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 自动修复 allowed-but-broken | 中 | `openclaw doctor --fix` 稳定后 |
| 审计结果写入结构化 JSON | 低 | 需要程序化消费时 |
| 新增 provider 探测路径 | 中 | 接入非 openai/local 的 provider |
| 与 pre-commit 集成 | 低 | 团队规模扩大，需强制审计 |

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-22 | tool_policy_audit.sh 首版，六段审计 |
| 2026-08-22 | 接入 scan_errors.sh 统一扫描入口 |
| 2026-09-11 | 基于实际代码重写 DESIGN.md |
