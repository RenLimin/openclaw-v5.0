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
**proposed** — 待 Rex 确认后改为 accepted

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

- [ ] ADR-005 accepted（本文件）
- [ ] 将 GitHub token 迁移到 SecretRef provider
- [ ] 创建 INDEX.md
- [ ] 创建标准操作脚本（add / rotate / revoke）
- [ ] 更新资产清单生成器

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
