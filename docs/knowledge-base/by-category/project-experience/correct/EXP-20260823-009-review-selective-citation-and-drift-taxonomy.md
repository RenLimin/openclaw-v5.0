---
type: experience
id: EXP-20260823-009
date: 2026-08-23
title: 建设期全盘 review — 选择性引用官方文档导致 ADR 核心论证错误
layers: [L1, L2]
stage: manage
severity: high
category: correct
tags: [review, documentation-drift, adr, confirmation-bias, secretref, plugins-allow, self-learning]
status: active
related: [ADR-202608-009, ADR-202608-007, ADR-202608-008, EXP-20260822-005]
---

# [EXP-20260823-009] 建设期全盘 review：13 项偏差的分类与根因

## 1. 背景

L2 七个组件建成后（3 天，10 ADR + 8 EXP），Rex 要求「全盘 review 系统，
务必与 openclaw 官方文档 + 系统架构文档保持一致」。

四路并行核查（3 个 subagent + 主会话实测），发现 13 项偏差。

## 2. 关键发现：13 项里只有 2 项是真错误

**混在一起谈"偏差很多"会掩盖真问题。** 分类后性质完全不同：

| 类型 | 数量 | 性质 | 可避免性 |
|---|---|---|---|
| **推断错误** | 2 | 写进 ADR 当决策依据 | ✅ 完全可避免 |
| 系统自己在动 | 4 | 文档是快照，系统是活的 | ❌ 结构性必然 |
| 建设速度 > 文档速度 | 5 | 3 天 7 组件，边建边写 | ⚠️ 部分可避免 |
| 官方文档缺口 | 2 | WeCom 无官方页、`dashboard` 无条目 | ❌ 不可控 |

## 3. 真错误 A：选择性引用官方文档 ★ 最值得记

### 3.1 事件

ADR-009 的**核心决策依据**写：

> `provider: "local"` —— 不存在"不可用"

依据是官方 `reference/memory-config.md` 这句：

> Explicit non-local providers fail closed.

**读到这句就停止检索了** —— 因为它正好支持想选的方案（local 为主）。
由此推断"既然显式远程会 fail closed，那 local 就不会降级"。

**而官方在同一份文档体系的另一处明确否定了这个推断**
（`concepts/memory-search.md:118-121`）：

> Leaving `provider` unset or set to `"auto"` falls back to keyword-only ranking
> when embedding setup or a request fails, **as does `provider: "local"`
> (the GGUF/llama.cpp provider)**.

### 3.2 真实影响

选 `local` **没有消除**静默降级，只是换了触发条件：

| 原触发条件（远程） | 新触发条件（local） |
|---|---|
| 缺 API key / 网络故障 / 额度耗尽 | 模型文件被改名或移动 / 插件失效 / GGUF 加载失败 |

**风险形状变了，风险没消失。** 而 ADR-009 §7.1 记录的两个坑
（不可改文件名、不可设 `modelPath`）恰恰就是新触发条件 ——
它们的危害被低估了：不只是"索引身份不匹配"，而是**静默退回关键词检索**，
且系统指令强制每次记忆查询都调 `memory_search`。

### 3.3 根因

**confirmation bias**：在为已选定的方案找依据，而不是让依据决定方案。
更糟的是用了引用格式让它看起来很严谨。

### 3.4 规则（可推广）

1. **引用官方文档作为决策依据时，必须读完相关章节全文**，不能引到支持自己的那句就停
2. ADR 的「依据」应标注**检索范围**（读了哪个文件的哪几节），让后人能验证有无选择性引用
3. 官方文档同一主题常散布在 `concepts/` + `reference/` + `gateway/` 多处，**至少交叉两处**
4. 决策结论可以不变（本例仍选 local），但**理由中站不住的那条必须作废**

## 4. 真错误 B：两次决策只改配置没改文档

架构文档 §L2 上下文管理写「各模型自治（自身 ctx 内独立压缩）」，
但同文件配了 `compaction.model = longcat/LongCat-2.0` —— **把压缩委托出去了**。

根因：EXP-003 变更历史里有一次"决策撤销，改为模型自治"，后来又改回委托。
**配置改了两次，文档只跟了第一次。**

→ 规则：**决策反复时，每次都要回头改文档**，否则文档记录的是中间态。

## 5. 结构性漂移（11 项，不可完全避免）

三天实际节奏：

```
08-21  4 层架构 + 知识库三维 + 演进路径 + Tavily          (3 ADR)
08-22  可观测性 + 凭据 + 持久化 + 配置 + 工具策略 + 记忆检索  (6 ADR)
08-23  知识库工具链 + LaunchAgent 清理 + 全盘 review        (1 ADR)
```

典型漂移与成因：

| 漂移 | 成因 |
|---|---|
| EXP-005 的「本机零 channel」前提失效 | WeCom 中途上线 |
| 5 个 LaunchAgent 孤儿从未入档 | `openclaw reset` 清了业务代码，服务层从未记录过 |
| 资产清单缺 4 个技能 | self-learning **自动生成**了 3 个，生成器不知道 skills 会自己长 |
| contextWindow 改了 3 轮 | 实测持续推翻早先推断 |

**这些不是"没写好"，是文档描述 T 时刻而系统在 T+1 已变。**

→ 结论：**不追求零漂移，改为定期强制核对**。本次 review 是第一次全盘核对，
而它应该在第 3 个组件时就做一次 —— **机制启动太晚了**。

## 6. 治理暴露面（本次新发现）

### 6.1 self-learning 自动生成技能未经审批 ★

今天清理 LaunchAgent 时，系统自动生成了 **3 个技能**（10:05 / 10:06 / 10:26），
我完全不知情。加上手动创建的 1 个，四者主题高度重叠。

根因：两个开关都是官方默认放开的

| 配置 | 官方默认 | 含义 |
|---|---|---|
| `skills.workshop.autonomous.mode` | `"auto"` | 自动捕获并走 apply 路径落盘 |
| `skills.workshop.approvalPolicy` | `"auto"` | agent 可自行 apply 无需批准 |

而 `<workspace>/skills` 是**最高优先级** skill 源（`tools/skills.md:34-42`），
会覆盖同名 bundled skill。等于系统在自动往最高优先级位置写东西。

**已改为** `mode: "propose"` + `approvalPolicy: "pending"`。

### 6.2 `plugins.allow` 为空 → 已停用插件仍可自动加载

`doctor --lint` 报 `llama-cpp` 与 `openclaw-weixin` 可自动加载，
而后者已明确停用（`plugins.entries.openclaw-weixin.enabled=false`）。

**实测重要发现**：`plugins.allow` 是**严格白名单** ——
设置后 enabled 插件从 **57 骤降到 5**。

必须在设置后立即验证核心功能，本次实测：
Gateway HTTP 200 / memory-core + llama-cpp enabled / WeCom 仍启用 /
`memory_search` 向量召回正常（`textScore: 0` + `vectorScore` 0.60）。

→ 规则：**`plugins.allow` 属高影响面配置，改后必须逐项验证依赖它的能力**，
不能只看 `config get` 读回成功。

### 6.3 `tools.elevated` 全无文档记录

工作区 grep 零命中，而 WeCom 已接入外部渠道。
`tools.elevated.allowFrom.<channel>` 是外部渠道触发提权 exec 的**唯一白名单门禁**。

已补入 `tool-policy/DESIGN.md` §4.1，含实测教训：
**口头授权无法绕过配置层门禁**（`exec(elevated=true)` 报 `Failing gates: allowFrom`，
`sudo -n` 报 `a password is required`）。

## 7. 凭据迁移：两个工具都有漏报

明文凭据实测 **5 处**，而两个来源各有遗漏：

| 来源 | 报告 | 漏报 |
|---|---|---|
| `openclaw secrets audit --check` | 4 处 | `channels.wecom.secret` |
| `openclaw doctor --lint` | 3 处 | `channels.wecom.secret` + `models.json` |
| subagent 独立扫描 | 4 处 | `agents/main/agent/models.json` |

**根因**：`channels.wecom.secret` **不在官方 SecretRef 覆盖矩阵内**
（`reference/secretref-credential-surface.md` 列了 telegram/slack/feishu 等
内置渠道，**无 wecom** —— 它是第三方插件渠道）。

→ 规则：**审计工具的覆盖范围本身要审计**。第三方插件的凭据字段
可能落在官方矩阵之外，需人工补查。

### 迁移范式（照 tavily 已有正确做法）

```json5
// 1. 注册 provider
{ secrets: { providers: {
    codingplankey: { source: "file",
      path: "/Users/x/.openclaw/secrets/coding-plan.apiKey", mode: "singleValue" } } } }
// 2. 字段改为引用
{ models: { providers: { "coding-plan": {
    apiKey: { source: "file", provider: "codingplankey", id: "value" } } } } }
```

凭据文件 `chmod 600`，目录 `700`。

**已迁 2 处**（两个 model apiKey），明文从 4 → 1（`secrets audit` 口径）。
`gateway.auth.token` 暂留 —— 它是当前会话认证凭据，
改动若解析失败会断连，需在可容忍中断的窗口执行。

## 8. 工具链改进：让漂移不再隐形

`kb_index.py` 新增两项检测（**均已实测生效**）：

| 检测 | 为何必要 |
|---|---|
| frontmatter **重复键** | `yaml.safe_load` 按"后值覆盖"**静默处理**，ADR-006 的 `supersedes` 重复了两次却无人发现 |
| ADR/EXP **缺 `status`** | 原 soft 检查只覆盖 layers/tags/stage；2 篇 EXP 缺 status，资产清单显示 `—` 却不报警 |

自检验证：造 `tags` 重复 + 无 status 的临时文件 → 两项均被捕获。

> 与「缺 stage」同类：**静默失败**。文档看上去正常、能读能引用，
> 但机器处理时被跳过或取错值，不报错。

## 9. 教训汇总

1. **引用官方文档必须读完章节全文** —— 别引到支持自己的那句就停（真错误 A）
2. **决策反复时每次都回头改文档** —— 否则文档是中间态（真错误 B）
3. **不追求零漂移，建立定期核对机制** —— 建设期漂移是必然，机制缺位才是问题
4. **审计工具的覆盖范围本身要审计** —— 第三方插件字段可能在官方矩阵外
5. **高影响面配置改后必须验证依赖能力** —— `plugins.allow` 让 enabled 57→5
6. **官方默认值不等于合理默认值** —— `autonomous.mode: auto` + `approvalPolicy: auto`
   意味着系统自动往最高优先级 skill 目录写东西
7. **静默失败是最贵的 bug** —— 重复键、缺 status、provider 降级，三者共性是"看起来正常"

## 10. 相关

- **ADR-009**: 记忆语义检索（§3.1 已修正核心论证 + 新增决策 4 监控）
- **ADR-007**: 配置管理（本次沿用四步流程：dry-run → apply → 读回 → 实测）
- **ADR-008**: 工具策略治理（`tools.elevated` 已补入 DESIGN §4.1）
- **EXP-005**: cron delivery（§6.2 已补 `--no-deliver` 不移除 `message` 工具）
- **官方依据**: `concepts/memory-search.md:118-121` · `tools/skills-config.md:339,350`
  · `gateway/config-tools.md:184-203` · `reference/secretref-credential-surface.md`
  · `plugins/manage-plugins.md:51` · `tools/skills.md:34-42`

## 11. 变更历史

- 2026-08-23: 创建 —— 全盘 review 的 13 项偏差分类、2 项真错误根因、7 条教训
