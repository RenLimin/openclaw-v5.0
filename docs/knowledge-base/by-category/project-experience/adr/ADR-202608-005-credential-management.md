---
type: adr
id: ADR-202608-005
date: 2026-08-21
title: L2 凭据管理通用化 — 文件存储 + SecretRef 引用 + 标准生命周期
status: accepted
deciders: [Rex, Jerry]
layers: [L1, L2]
stage: design
tags: [credentials, secrets, security, secretref, cross-cutting]
supersedes: null
superseded_by: null
---

# [ADR-202608-005] L2 凭据管理通用化决策

## 1. 状态

**accepted**（2026-08-21 Rex 确认；2026-08-23 第三轮 review 同步正文与 frontmatter）

> ⚠️ **修正记录**：本节原写 `proposed — 待 Rex 确认后改为 accepted`，与 frontmatter 的
> `status: accepted` 矛盾两天。根因：Rex 确认后只改了 frontmatter，没同步正文。
> → **教训**：状态字段在两处出现就会漂移，`kb_index.py` 应增加「frontmatter status
> 与正文 §1 一致性」校验（已列入待办）。

## 2. 背景

综合开放平台已接入 2 个外部服务（Tavily + GitHub），各自有不同的凭据管理方式：
- **Tavily**：走 OpenClaw SecretRef 标准路径（`secrets.providers.tavilykey`）
- **GitHub**：走自定义 credential helper 直接读文件

**问题**：新接入第 3、第 4 个服务时，选哪种方式？凭据轮换、权限审计、漂移检测没有统一流程。

**设计文档**: [components/credentials/DESIGN.md](../../../../architecture/components/credentials/DESIGN.md)

## 3. 核心决策

### 决策 1: 存储标准化

所有凭据文件统一存放在 `~/.openclaw/secrets/`，遵循：
- 命名规范：`<service>.token` / `<service>.apiKey`
- 权限：`chmod 600`，目录 `chmod 700`
- 无尾换行：`printf '%s'` 写入

**理由**：
- 已有案例验证（Tavily + GitHub）
- 集中管理，避免凭据散落
- 与资产清单自动集成

### 决策 2: 引用标准化（两种标准方式）

| 方式 | 适用场景 | 优先级 |
|---|---|---|
| **A. SecretRef provider** | OpenClaw plugin/config 引用 | 优先 |
| **B. Credential helper** | 非 OpenClaw 场景（git, curl） | 特殊 |

**理由**：
- SecretRef 是 OpenClaw 原生标准路径
- Credential helper 用于 OpenClaw 无法覆盖的场景
- 两种方式都基于同样的文件存储（Layer 1 统一）

### 决策 3: 生命周期标准化

| 阶段 | 操作 |
|---|---|
| 接入 | 创建文件 → chmod 600 → 注册 provider → 更新 INDEX.md |
| 轮换 | 更新文件内容 → 验证 → 更新 INDEX.md |
| 撤销 | 删除文件 → 注销 provider → 更新 INDEX.md |
| 检测 | 权限检查 + 过期检测（每日 cron，预留）|

### 决策 4: 凭据清单 (INDEX.md)

维护 `~/.openclaw/secrets/INDEX.md`，记录：
- 服务名、文件名、类型
- SecretRef provider 别名
- 引用方
- 轮换周期

**理由**：
- 人机共读（人类可快速了解有哪些凭据）
- 与资产清单互补（资产清单自动扫描，INDEX.md 含元信息）

## 4. 后果

### 4.1 正面
- **一致性**：所有凭据遵循同一套规范
- **可审计**：INDEX.md + 资产清单 = 双重保障
- **低摩擦**：新服务接入有标准流程可遵循
- **渐进式**：未来可平滑迁移到企业 Vault

### 4.2 负面
- **INDEX.md 维护负担**：每次接入/轮换需手动更新（可脚本化缓解）
- **文件存储限制**：不支持动态凭据、自动轮换（企业 Vault 特性）

### 4.3 风险
| 风险 | 缓解 |
|---|---|
| 凭据文件泄露（权限配置错误） | 每日权限检查 cron |
| INDEX.md 与实际不同步 | 资产清单自动扫描作为交叉验证 |
| 凭据过期未轮换 | INDEX.md 中记录轮换周期 + 过期提醒（预留）|

## 5. 实现计划

- [x] ADR-005 accepted（本文件）—— 2026-08-21 Rex 确认
- [x] ~~将 GitHub token 迁移到 SecretRef provider~~ → **无需迁移**：GitHub 走
      `credential.helper = osxkeychain`（实测 `~/.gitconfig:5`），属本 ADR 定义的
      **方式 B（外部凭据管理器）**，不属 SecretRef 覆盖面。
      `secrets/github.token`（40B, 600）保留供 skill 直读，**不注册为 provider**。
- [x] 创建 INDEX.md —— `~/.openclaw/secrets/INDEX.md`（2425B）
- [x] 创建标准操作脚本（add / rotate / revoke）—— `scripts/credentials.sh`（8025B）
- [x] 更新资产清单生成器 —— `scripts/gen_asset_inventory.py` 已含凭据段

### 实际完成的 SecretRef 迁移（实测@2026-08-23）

| 字段 | 状态 |
|---|---|
| `models.providers.coding-plan.apiKey` | ✅ SecretRef（provider `codingplankey`）|
| `models.providers.longCat.apiKey` | ✅ SecretRef（provider `longcatkey`）|
| `plugins.entries.tavily.config.webSearch.apiKey` | ✅ SecretRef（provider `tavilykey`）|
| `agents/main/agent/models.json` | ✅ 自动写入非密标记 `secretref-managed` |
| `gateway.auth.token` | ❌ **仍明文** —— fail-closed 风险，需维护窗口（见 §6 监控点）|
| `channels.wecom.secret` | ❌ **仍明文** —— core 代码对该字段调 `.trim()`，不兼容 SecretRef 对象（实测已回退）|

> ⚠️ **`channels.wecom.secret` 不得使用 SecretRef**（2026-08-23 实测教训）：
> `dist/channel-B2DGqAWl.js:1799` 无条件对 `account.secret` 调 `.trim()`，收到
> SecretRef 对象后抛 `account.secret?.trim is not a function`，将
> `channels.wecom.accounts.default` **降级判为 unconfigured**。
> **`config patch --dry-run` 会通过** —— schema 层接受，运行时才报错。
> → **教训：dry-run 通过 ≠ 运行时可用，配置变更必须跟 `doctor` 实测。**
> 官方 SecretRef 覆盖矩阵（`reference/secretref-credential-surface.md`）**未收录 wecom**，
> 这个缺席是有原因的，不要当成「文档没写但能用」。

## 6. 验证标准

1. 所有凭据文件权限 = 600
2. INDEX.md 与实际文件一致
3. 新服务接入遵循标准流程（有文档可参考）
4. 资产清单自动包含凭据资产

## 7. 相关决策

- **supersedes**: null
- **superseded_by**: null
- **相关 ADR**:
  - ADR-202608-001: 4 层架构（凭据管理是 L2 横切组件）
  - ADR-202608-004: 可观测性适配（凭据操作需要审计日志）
- **相关经验卡片**:
  - EXP-20260821-001: Tavily SecretRef（方式 A 案例）
  - EXP-20260821-002: GitHub credential helper（方式 B 案例）
- **相关文档**:
  - `docs/architecture/components/credentials/DESIGN.md`（完整设计）

## 8. 引用

- **OWASP**: Secrets Management Cheat Sheet
- **StrongDM**: What Is Secrets Management (Best Practices 2026)
- **GitGuardian**: Top Secrets Management Tools (2026)
- **OpenClaw**: SecretRef documentation

## 9. 变更历史

- 2026-08-21: proposed
