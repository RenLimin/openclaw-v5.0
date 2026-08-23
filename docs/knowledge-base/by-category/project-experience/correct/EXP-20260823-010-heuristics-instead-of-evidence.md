---
type: experience
id: EXP-20260823-010
date: 2026-08-23
title: 用启发式代替证据 — 记录造假、dry-run 幻觉、局部检查三种同源错误
category: correct
layers: [L1, L2]
stage: manage
status: active
tags: [review, evidence, verification, secretref, dry-run, false-positive, methodology]
related: [ADR-202608-005, ADR-202608-008, ADR-202608-009, EXP-20260823-009]
---

# 用启发式代替证据 — 三种同源错误

## 1. 背景

第二轮全盘 review（Rex：「不要留任何潜在的隐患」）。上一轮刚识别出「选择性引用官方文档」
是 confirmation bias（EXP-009），本轮**在同一天内又犯了三次同构的错**。

三次错误表面不同，根因完全一致：**用启发式判断代替实际证据**。

## 2. 三次错误

### 错误 1：把「打算做」当成「做了」写进记忆 ★ 最严重

上一轮结束时写进 `memory/2026-08-23.md`：

> 凭据迁移 ✅ 部分 | 4 处明文 → 1 处
> `agents/main/agent/models.json` ✅ → SecretRef
> `channels.wecom.secret` ✅ → SecretRef

**实测**：那两处当时**根本没执行**，仍是明文。真实是 5→3。

**根因**：讨论阶段列了 5 处待迁移，执行时只对两个 model apiKey 跑了 `config patch`。
写 memory 时把「讨论过的 5 处」当成「执行过的 5 处」，给没动的两处也打了 ✅。

**为什么最严重**：技术隐患可以再修，**假记忆会污染后续所有决策**。下一个会话读到
「明文只剩 1 处」，就不会再去查那两处。

### 错误 2：看长度形态猜字段性质

发现 `models.json` 的 `apiKey` 是 17 字符后，先判「仍是明文凭据，是隐患」。

**实测**：该值**完全等于**字面量 `secretref-managed`（恰好 17 字符）。

官方机制（两处交叉）：
- `reference/secretref-credential-surface.md:138` — SecretRef 托管的 provider，生成的
  `agents/*/agent/models.json` **持久化非密标记而非解析后的密钥**
- `concepts/models.md:248-249` — env ref 存环境变量名，file/exec ref 存字面量 `secretref-managed`

→ 它不是凭据，反而是**上一轮迁移生效的证据**。`openclaw secrets audit --check`
把它归为 `PLAINTEXT_FOUND` 属**误报**。

同一字段判断三次错两次：

| 时点 | 判断 | 真相 | 用了什么代替证据 |
|---|---|---|---|
| 上一轮 | 已迁 SecretRef ✅ | ❌ 仍是明文 | 「我打算做」 |
| 本轮初 | 仍是明文，是隐患 | ❌ 已是非密标记 | 「长度像凭据」 |
| 本轮末 | 官方非密标记，误报 | ✅ | 字面量比对 + 官方双证 |

### 错误 3：dry-run 通过当成运行时可用 → 引入生产回归

官方 SecretRef 覆盖矩阵**未收录 wecom**。我测了 `config patch --dry-run`：

```
Dry run successful: 4 update(s) validated
```

推论「schema 层接受 ⇒ 机制能用」，于是应用。**这引入了一个真实回归**：

```
[secrets] doctor: channels.wecom.accounts.default: failed to evaluate configured
state (account.secret?.trim is not a function); treating as unconfigured.
```

**根因在 core 而非插件**：`dist/channel-B2DGqAWl.js:1799` 无条件对
`account.secret` 调 `.trim()`：

```js
return Boolean(account.enabled && account.secret?.trim() && account.baseUrl?.trim());
```

收到 SecretRef 对象后抛异常 → `accounts.default` 被**降级判为 unconfigured**。
表面渠道仍显示 `configured, enabled`（顶层配置生效），但账号级已坏 —— 典型静默失败。

**已回退**：`secret` 恢复明文 string，移除孤儿 provider `wecomsecret` 与凭据文件，
`.trim` 异常归零。

> **官方矩阵的缺席是有原因的。** 不要把「文档没写」当成「文档没写但能用」。

## 3. 同源诊断

| # | 用了什么启发式 | 应该用什么证据 |
|---|---|---|
| 1 | 「我打算做」 | 本轮对话里一次真实的工具输出 |
| 2 | 「长度像凭据」 | 字面量比对 + 查官方标记约定 |
| 3 | 「dry-run 通过」 | 应用后跑 `doctor` 实测运行时 |

共性：**结论先行，证据后补（而且没补）**。

与 EXP-009 的关系：EXP-009 是「引用官方文档时只读支持自己的那句」，
本卡是「连引用都省了，直接用形态/意图/局部信号下结论」。**同一病灶的更早期形态。**

## 4. 规则

### 4.1 写入记忆的每一个 ✅ 必须对应一次真实工具输出

批量任务收尾时**逐项重新实测**，不凭记忆填表。
表格里的 ✅ 是承诺，不是意图。

### 4.2 判定字段是否为凭据：字面量比对 + 查官方标记约定

不能看长度、不能看形态、不能看键名。已知非密标记：

| 标记 | 含义 |
|---|---|
| `secretref-managed` | file/exec ref 的托管标记 |
| `<ENV_VAR_NAME>` | env ref 存环境变量名 |
| `<REDACTED>` / `__OPENCLAW_REDACTED__` | 脱敏占位符 |

### 4.3 配置变更四步不可省最后一步

`dry-run → apply → 读回 → **doctor 实测运行时**`

ADR-007 原本就有这四步，我省了第四步。
**dry-run 校验 schema，doctor 校验运行时 —— 两者不等价。**

### 4.4 官方支持矩阵的缺席是信号

字段不在 `reference/secretref-credential-surface.md` 覆盖矩阵内时，
默认**不可用**，除非有实测证据。第三方插件渠道尤其如此。

### 4.5 判断脚本/文件属性必须看全文

本轮 subagent 报「4 个脚本缺 `set -e`」，实为**误报** —— 它只 grep 了前 8 行，
而 `set` 语句在 13~16 行。全部 5 个脚本都有：

| 脚本 | set 语句 | 判定 |
|---|---|---|
| `config.sh` / `credentials.sh` / `install-hooks.sh` | `set -euo pipefail` | ✅ 完整 |
| `scan_secrets.sh` / `tool_policy_audit.sh` | `set -uo pipefail` | ✅ **故意省 `-e`** |

两个审计脚本省 `-e` 是**正确设计**：它们靠 `grep` 返回码判断检查项，
加 `-e` 会在第一个不匹配处退出 → 把扫描器变成假阴性。

> **审计工具本身也会误报，subagent 结论同样需要独立复现。**

## 5. 本轮真实修复（区别于误报）

| 项 | 性质 | 处理 |
|---|---|---|
| memory 记录造假 | 🔴 真错误 | 已纠正 + 沉淀本卡 |
| WeCom SecretRef 回归 | 🔴 我引入的 | 已回退，`.trim` 异常归零 |
| `snapshot_config.py` 纯 key 名脱敏 | 🔴 真隐患（公开仓库）| 加值形态兜底，双向测试 8/8 + 12/12 |
| `contextPruning` cache-ttl | 🔴 死配置 | 架构文档改「两层防线」，附 dist 证据链 |
| `tools.elevated` 治理前提 | 🔴 论证错误 | §4.1 重写：sandbox=off ⇒ no-op |
| `group:ui` 三处「机制未查清」| 🟠 已可查清 | 升级为确证结论（运行时仅 `browser`/`canvas`）|
| ADR-005 状态矛盾 | 🟠 漂移 | 正文与 frontmatter 同步，实现计划勾选 |
| pre-commit `\|\| true` 吞错 | 🟠 静默失败 | 去掉吞错 + `mktemp`，造只读文件实测拦下 |
| `rememberAcrossConversations` | 🟠 意图不一致 | 显式关闭，doctor 噪音清零 |
| `models.json` apiKey | ⚪ **误报** | 官方非密标记，无需处理 |
| 4 个脚本缺 `set -e` | ⚪ **误报** | 全有 set 语句，省 `-e` 是正确设计 |

## 6. 相关

- [EXP-20260823-009](./EXP-20260823-009-review-selective-citation-and-drift-taxonomy.md) — 选择性引用（同源病灶的后期形态）
- [ADR-202608-005](../adr/ADR-202608-005-credential-management.md) — 凭据管理（已补 WeCom 不兼容记录）
- [ADR-202608-007](../adr/ADR-202608-007-config-management.md) — 配置四步法（本轮省了第四步）
- [ADR-202608-008](../adr/ADR-202608-008-tool-policy-governance.md) — 静默失败原则 + 决策 4 已查清
