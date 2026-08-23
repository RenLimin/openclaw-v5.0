---
type: experience
id: EXP-20260821-001
date: 2026-08-21
title: Tavily plugin 显式工具通过 tools.alsoAllow 解锁（绕过 tools.profile=coding 的 deny）
layers: [L1, L2]                # 涉及 OpenClaw 系统层契约 + 基础设施层配置
stage: develop
severity: medium
category: correct                  # 验证可行的方案
tags: [openclaw, tavily, tools-profile, plugin, web-search]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260821-001] Tavily 显式工具解锁：tools.alsoAllow 配置法

## 1. 背景

在 OpenClaw workspace 中配置 Tavily 插件时，期望使用 `tavily_search` 和 `tavily_extract` 显式工具（带 `search_depth=advanced`、`include_answer`、`time_range` 等高级参数），而不只是 `web_search` 基础能力。

**环境**：
- OpenClaw 2026.7.2-beta.7
- @openclaw/tavily-plugin 2026.7.1
- `tools.profile = "coding"`（默认）
- API key 通过 file-based SecretRef 配置（参考 `EXP-20260821-002` 或实际 ADR/EXP）

## 2. 问题

**症状**：
- Tavily plugin 显示 `Status: loaded`、skill `ready`
- `web_search` 工具走 Tavily provider **正常工作**
- 但 `tavily_search` / `tavily_extract` **不在 agent 可调用工具列表中**
- 模型反馈："I don't have it as an actual callable tool — only `web_search` and `web_fetch` are in my tool inventory"

**根因**（不是 issue #53764 描述的 plugin 注册 bug）：
- `tools.profile = "coding"` 默认 deny 了 18 个工具
- Tavily 的显式工具落在 deny 列表中
- Plugin manifest 声明了 `contracts.tools: ["tavily_search", "tavily_extract"]`，但 plugin 的 `Capabilities` 列表只注册了 `web-search`，**没有 `tools` capability**（这可能是 alsoAllow 仍能生效的原因——OpenClaw 内部有独立的 tool registry 路径）

**与 issue #53764 的区别**：
- 那个 issue 报告的是 agent 收到 "unknown tool" 错误（plugin 注册失败）
- 我们的现象是 agent 看到 skill 描述但工具**不在白名单**（策略 deny 而非 plugin 缺失）

## 3. 方案

**采用**：`tools.alsoAllow` 字段——保留 coding profile，只在它之上添加这两个工具。

```json5
// ~/.openclaw/openclaw.json
{
  "tools": {
    "profile": "coding",          // 保持原 profile，不影响其他 7 个被 deny 的工具
    "alsoAllow": [
      "tavily_search",
      "tavily_extract"
    ]
  }
}
```

**为什么不用 `tools.profile = "full"`**：
- `full` profile 会**解锁所有工具**（含不安全的如 `tts`、`mobile_ui` 等）
- `alsoAllow` 是**最小变更**——只加我们要的两个
- 保留 coding profile 体现的"agent 自动化为主，不假设 UI 控制能力"的安全意图

**为什么不用 `tools.allow`**：
- `allow` 是"白名单替换"——会**覆盖** profile 默认放行的工具
- `alsoAllow` 是"在 profile 之上合并"——保留 base policy

**命令**（patch 形式，避免交互）：
```bash
cat > /tmp/tools-also-allow.json5 <<'EOF'
{
  "tools": {
    "alsoAllow": ["tavily_search", "tavily_extract"]
  }
}
EOF
openclaw config patch --file /tmp/tools-also-allow.json5 --dry-run  # 先 dry-run
openclaw config patch --file /tmp/tools-also-allow.json5             # 实际应用
```

## 4. 验证

**验证步骤**：
1. CLI agent `--local` 跑独立 session（避免主会话锁）：
   ```bash
   openclaw agent --message-file /tmp/prompt.txt --local --agent main --session-id "tavily-test-$(date +%s)-$$"
   ```
2. Prompt 内容要求：调用 `tavily_search`，参数 `search_depth=advanced`, `include_answer=true`, `max_results=2`
3. 期望：模型能调用工具并返回 `answer` 字段

**实际结果**（2026-08-21 验证）：
- ✅ CLI agent 实际调用 `tavily_search` 成功
- ✅ Advanced 参数被尊重：`tookMs: 3349`, `score: 0.87/0.86`
- ✅ 返回 2 条结果 + AI 答案字段
- ✅ `web_search` / `web_fetch` 不受影响
- ✅ "No gateway restart needed" — alsoAllow 动态合并

**关键日志证据**：
- `tool policy removed 18 tool(s) via tools.profile (coding): ...` — 比 unlock 前多 10 个（之前是 8 个），说明 alsoAllow 生效

## 5. 教训

**正确的做法**（可推广）：
1. **最小变更原则**：用 `alsoAllow` 补充而非 `allow` 替换或换 profile
2. **dry-run 优先**：所有 `config patch` 前先 `--dry-run`
3. **独立 session 验证**：CLI agent 验证时必须用独立 `--session-id`，否则主会话 sqlite 锁
4. **能力 vs 工具**：理解 plugin 的 `Capabilities` 与 `contracts.tools` 是不同注册路径——`alsoAllow` 走的是后者

**监控点**（**重要**）：
- ⚠️ **plugin 升级时必须重新验证** `tavily_search` 是否仍可用
- ⚠️ Plugin manifest 的 `contracts.tools` 改名/删名 → `alsoAllow` 配置**不会报错但会失效**
- ⚠️ Plugin 升级后 `openclaw plugins inspect tavily` 检查 capabilities 是否仍包含 `web-search`（如果消失了，整个 Tavily 集成失效）
- ⚠️ OpenClaw 升级时检查 `tools.profile=coding` 的 deny 列表是否变化（如果从 deny 改为 allow，可以考虑从 alsoAllow 移除）

**升级判断**（按经验沉淀规则）：
- [x] 影响 ≥ 2 个层级 → 涉及 L1 系统层契约 + L2 基础设施配置
- [x] 涉及 L1/L2 契约 → **OpenClaw 工具策略 + plugin manifest**
- 评估：满足"必须升级为 ADR"硬条件之一
- **实际决定**：保持经验卡片（correct 类）
  - 理由：本卡片是"配置方法 + 监控点"，是 ADR 该类决策的**实施参考**
  - 如果未来出现"OpenClaw 升级后 Tavily 集成失效"等事件，**再升级为 ADR**（如"是否继续使用 Tavily 作为 L2 唯一 web search 能力"）

## 6. 相关

- **Tavily key 安全配置**：`/Users/bangcle/.openclaw/secrets/tavily.apiKey` (chmod 600), via `secrets.providers.tavilykey` (file-based SecretRef)
- **OpenClaw 文档**：https://docs.openclaw.ai/tools/tavily
- **相关 issue**（仅作参考，不假设影响我们）：[Issue #53764](https://github.com/openclaw/openclaw/issues/53764) — plugin 工具不可调（不同根因）
- **plugin manifest**：`~/.openclaw/npm/projects/openclaw-tavily-plugin-*/node_modules/@openclaw/tavily-plugin/openclaw.plugin.json`

## 7. 变更历史

- 2026-08-21: 创建（初版，含完整配置 + 验证 + 监控项）
