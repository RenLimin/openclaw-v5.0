# 凭据管理通用化 (L2 基础设施组件)

> 本文档是 [系统架构](../00-system-architecture.md) 的 L2 组件设计文档。
> 决策记录: [ADR-202608-005](./ADR-202608-005-credential-management.md)

## 1. 定位

**层级**: L2 基础设施层
**类型**: 横切关注点 (Cross-Cutting Concern)
**状态**: ✅ 已上线 (2026-08-23) — ADR-005 已实现,SecretRef 落地,secrets audit plaintext=0

凭据管理通用化是把 EXP-001（Tavily SecretRef）和 EXP-002（GitHub credential helper）的**经验沉淀为 L2 通用能力**——任何新服务接入凭据时，有标准流程可遵循。

## 2. 问题定义

### 2.1 现状（已有实践）

| 凭据 | 存储方式 | 引用方式 | 问题 |
|---|---|---|---|
| Tavily API key | `~/.openclaw/secrets/tavily.apiKey` (chmod 600) | SecretRef provider `tavilykey` | ✅ 标准 |
| GitHub token | `~/.openclaw/secrets/github.token` (chmod 600) | 自定义 credential helper 直接读文件 | ⚠️ 绕过了 SecretRef |

**不一致**：Tavily 走 OpenClaw SecretRef 标准路径，GitHub 走自定义 helper 直接读。两种方式都能工作，但：
- 新接入第 3 个、第 4 个服务时，选哪种？
- 凭据轮换、权限审计、漂移检测没有统一流程
- 凭据文件散落在 `~/.openclaw/secrets/`，没有索引

### 2.2 核心矛盾

| 需求 | 现状 |
|---|---|
| 凭据存储标准化 | 有的走 SecretRef，有的走自定义 helper |
| 凭据引用标准化 | 有的在 `plugins.entries.<id>.config`，有的在 credential helper |
| 凭据生命周期管理 | 无（手动轮换、无过期提醒） |
| 凭据清单 | 无（只有 `ls ~/.openclaw/secrets/`） |

### 2.3 设计目标

1. **统一存储**：所有凭据文件遵循同一套目录结构、命名规范、权限要求
2. **统一引用**：优先使用 OpenClaw SecretRef（标准路径），特殊场景才用自定义 helper
3. **统一生命周期**：接入、轮换、撤销有标准流程
4. **统一清单**：凭据清单自动更新（与资产清单集成）

## 3. 架构设计

### 3.1 凭据管理 4 层模型

```
┌─────────────────────────────────────────────────────────────┐
│  4. Governance (治理)                                       │
│     凭据审计 / 轮换策略 / 合规检查                           │
├─────────────────────────────────────────────────────────────┤
│  3. Lifecycle (生命周期)                                    │
│     接入 / 轮换 / 撤销 / 过期检测                            │
├─────────────────────────────────────────────────────────────┤
│  2. Reference (引用)                                        │
│     SecretRef provider 注册 / credential helper             │
├─────────────────────────────────────────────────────────────┤
│  1. Storage (存储)                                          │
│     文件存储 / 权限控制 / 命名规范 / 目录结构                │
└─────────────────────────────────────────────────────────────┘
```

**当前范围**（阶段一）：**Layer 1 (Storage) + Layer 2 (Reference)**
**未来扩展**（阶段二~三）：Layer 3 (Lifecycle) → Layer 4 (Governance)

### 3.2 存储规范 (Layer 1)

#### 3.2.1 目录结构

```
~/.openclaw/secrets/
├── INDEX.md              # 凭据清单 (人机共读)
├── github.token          # GitHub PAT
├── tavily.apiKey         # Tavily API key
├── <service>.token       # 未来: 新服务凭据
└── <service>.apiKey      # 未来: 新服务凭据
```

#### 3.2.2 命名规范

| 类型 | 命名 | 示例 |
|---|---|---|
| API Token | `<service>.token` | `github.token` |
| API Key | `<service>.apiKey` | `tavily.apiKey` |
| 证书 | `<service>.pem` | `custom-ca.pem` |
| JSON 配置 | `<service>.json` | `gcp-service-account.json` |

**规则**：
- 全小写（服务名 + 类型）
- 用 `.` 分隔（不用 `-` 或 `_`）
- 服务名用官方简称（github / tavily / openai / ...）

#### 3.2.3 权限规范

| 项目 | 要求 |
|---|---|
| 文件权限 | `chmod 600`（仅 owner 读写）|
| 目录权限 | `chmod 700`（仅 owner 访问）|
| 所有权 | `chown $(whoami)` |
| 无尾换行 | `printf '%s' "$value" > file`（避免 `\n` 混入）|
| 无 `.DS_Store` | `.gitignore` 式排除（macOS 自动文件）|

#### 3.2.4 INDEX.md（凭据清单）

```markdown
# 凭据清单

| 服务 | 文件名 | 类型 | SecretRef provider | 引用方 | 轮换周期 |
|---|---|---|---|---|---|
| GitHub | github.token | PAT | — (credential helper) | git push | 90 天 |
| Tavily | tavily.apiKey | API Key | tavilykey | plugins.entries.tavily | 无 |
```

### 3.3 引用规范 (Layer 2)

#### 3.3.1 两种标准引用方式

| 方式 | 适用场景 | 配置 |
|---|---|---|
| **A. SecretRef provider**（优先） | OpenClaw 原生支持（plugins, config） | `secrets.providers.<alias>` + `plugins.entries.<id>.config.<field>: {provider, source, id}` |
| **B. Credential helper**（特殊） | 非 OpenClaw 场景（git push, curl, 自定义脚本） | 自定义 helper 脚本（如 `git-credential-openclaw-file`）|

#### 3.3.2 选择决策树

```
新凭据接入
  ├── 被 OpenClaw plugin/config 引用？
  │   ├── 是 → 方式 A: SecretRef provider
  │   └── 否 → 方式 B: Credential helper
  └── 特殊场景（git, curl, 外部工具）→ 方式 B
```

#### 3.3.3 SecretRef Provider 注册模板

```bash
# 1. 创建凭据文件
printf '%s' '<token>' > ~/.openclaw/secrets/<service>.token
chmod 600 ~/.openclaw/secrets/<service>.token

# 2. 注册 provider
openclaw config set secrets.providers.<service>key \
  --provider-source file \
  --provider-path ~/.openclaw/secrets/<service>.token \
  --provider-mode singleValue

# 3. 引用
openclaw config set plugins.entries.<plugin>.<field> \
  --ref-provider <service>key \
  --ref-source file \
  --ref-id value
```

#### 3.3.4 Credential Helper 模板

```bash
# 自定义 helper 脚本 (~/.openclaw/bin/git-credential-openclaw-file 已有)
# 配置 git 使用它
git config --local credential.https://<host>.helper \
  '!/Users/bangcle/.openclaw/bin/git-credential-openclaw-file'
```

### 3.4 生命周期规范 (Layer 3 — 预留)

| 阶段 | 操作 | 触发 |
|---|---|---|
| **接入** | 创建文件 → chmod 600 → 注册 provider → 更新 INDEX.md | 新服务需要凭据 |
| **轮换** | 更新文件内容 → 验证 → 更新 INDEX.md | 定期（90 天）或泄露时 |
| **撤销** | 删除文件 → 注销 provider → 更新 INDEX.md | 服务下线或凭据泄露 |
| **检测** | 权限检查 + 过期检测 | 每日 cron |

### 3.5 与资产清单集成

凭据清单是 [系统资产清单](../../01-asset-inventory.md) 的一部分：
- 资产清单的 `L2 — 凭据资产` 区自动扫描 `~/.openclaw/secrets/`
- INDEX.md 作为人机共读的补充（含轮换周期等元信息）

## 4. 技术选型

### 4.1 业界工具对比

| 类型 | 代表 | 适合我们? | 原因 |
|---|---|---|---|
| 企业 Vault | HashiCorp Vault / Infisical | ❌ | 太重，单人团队不需要 |
| 云原生 | AWS Secrets Manager / GCP Secret Manager | ❌ | 绑定云厂商，违反跨系统移植目标 |
| 开源自托管 | Infisical / OpenBao | ⏸️ 未来 | 团队扩张时考虑 |
| **文件 + SecretRef** | **OpenClaw 原生** | ✅ **当前** | 零依赖、已有案例验证 |

### 4.2 当前决策：文件 + SecretRef

**理由**：
1. **已有案例验证**：Tavily + GitHub 两个成功案例
2. **零依赖**：不需要额外服务
3. **OpenClaw 原生支持**：SecretRef 是标准路径
4. **渐进式**：未来可平滑迁移到企业 Vault

## 5. 与其他组件的关系

```
凭据管理通用化 (本组件)
  ↑ 被依赖
  ├── Tavily 集成 (plugins.entries.tavily)
  ├── GitHub 凭据 (credential helper)
  ├── 未来: 所有需要凭据的 L2/L3/L4 组件
  └── 可观测性适配 (凭据访问日志)
  
  ↓ 依赖
  ├── L1 OpenClaw (SecretRef 机制)
  └── L2 可观测性 (凭据操作审计)
```

## 6. 实施计划

### 阶段 1: 标准化现有凭据 + 建立规范 (当前)
- [ ] ADR-005 锁定设计决策
- [ ] 将 GitHub token 迁移到 SecretRef provider（统一引用方式）
- [ ] 创建 INDEX.md（凭据清单）
- [ ] 创建接入/轮换/撤销的标准操作脚本
- [ ] 更新资产清单生成器（集成 INDEX.md）

### 阶段 2: 生命周期管理
- [ ] 实现凭据权限检查（每日 cron）
- [ ] 实现过期检测（INDEX.md 中的轮换周期）
- [ ] 实现轮换提醒

### 阶段 3: 治理
- [ ] 实现凭据审计日志
- [ ] 实现合规检查（如：所有凭据文件权限 = 600）

## 7. 参考

- **OWASP**: Secrets Management Cheat Sheet
- **StrongDM**: What Is Secrets Management (Best Practices 2026)
- **GitGuardian**: Top Secrets Management Tools (2026)
- **OpenClaw**: SecretRef documentation
- **EXP-001**: Tavily file-based SecretRef
- **EXP-002**: GitHub file-based credential helper
