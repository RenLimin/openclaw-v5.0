---
type: experience-card
id: EXP-20260821-002
date: 2026-08-21
title: GitHub token 用 file-based credential helper 配置（避免明文入 git config）
layer: [L2]
stage: develop
severity: high
kind: correct
tags: [git, github, credentials, security, secretref]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260821-002] GitHub token 安全配置：file-based credential helper

## 1. 背景

需要把 workspace（含架构文档、知识库、ADR）推送到 GitHub 私有/公开仓库。

**安全要求**：
- token 不能明文出现在 `git config`、`git remote` URL、或任何被版本控制的文件中
- 与已有的 Tavily SecretRef 模式保持一致（file-based + chmod 600）

**环境**：
- macOS 26.5.2
- git 默认 `credential.helper = osxkeychain`
- Token 已存放：`~/.openclaw/secrets/github.token` (40 bytes, chmod 600, 无换行)

## 2. 问题

**为什么不能直接用现成方案**：

| 方案 | 问题 |
|---|---|
| `https://ghp_xxx@github.com/...` | ❌ token 明文进 `.git/config`，会被 `git config --list` 打印 |
| `credential.helper = store` | ❌ token 明文写到 `~/.git-credentials` |
| `credential.helper = osxkeychain` | ⚠️ 需要交互输入（首次会弹窗），不适合自动化；且 token 存 keychain 后难以与 file-based secret 统一管理 |
| 环境变量 `GH_TOKEN` | ⚠️ 只对 `gh` CLI 有效，`git push` 不读 |

**核心矛盾**：git 需要 credential，但所有内置 helper 都不支持"从指定文件读"。

## 3. 方案

**自定义 credential helper 脚本**，从 file-based secret 读取。

### 3.1 Helper 脚本

路径：`~/.openclaw/bin/git-credential-openclaw-file` (chmod 700)

```bash
#!/usr/bin/env bash
set -euo pipefail

TOKEN_FILE="${GITHUB_TOKEN_FILE:-$HOME/.openclaw/secrets/github.token}"

case "${1:-}" in
  get)
    if [[ ! -f "$TOKEN_FILE" ]]; then
      echo "credential helper: token file not found: $TOKEN_FILE" >&2
      exit 1
    fi
    # 权限校验：拒绝读取权限过宽的 token
    perms=$(stat -f "%Lp" "$TOKEN_FILE" 2>/dev/null || stat -c "%a" "$TOKEN_FILE" 2>/dev/null)
    if [[ "$perms" != "600" ]]; then
      echo "credential helper: refusing to read token with permissions $perms (expected 600)" >&2
      exit 1
    fi
    echo "username=git"
    printf 'password=%s\n' "$(cat "$TOKEN_FILE")"
    ;;
  store|erase)
    exit 0   # 只读 helper
    ;;
  *)
    echo "credential helper: unknown operation '${1:-}'" >&2
    exit 1
    ;;
esac
```

### 3.2 配置命令

```bash
chmod 700 ~/.openclaw/bin/git-credential-openclaw-file

# repo-local，只针对 github.com，不影响全局或其他 remote
cd <repo>
git config --local credential.https://github.com.helper \
  '!/Users/bangcle/.openclaw/bin/git-credential-openclaw-file'

git remote add origin https://github.com/<owner>/<repo>.git
```

**关键点**：
- helper 值前的 `!` 表示"执行这个命令"（而非查找 `git-credential-<name>`）
- 用**绝对路径**（helper 执行时 cwd 不确定）
- `credential.https://github.com.helper` 限定 host，不污染其他 remote

## 4. 验证

### 4.1 Helper 单独测试
```bash
echo "protocol=https
host=github.com
" | ~/.openclaw/bin/git-credential-openclaw-file get
# 期望输出：
# username=git
# password=ghp_...
```

### 4.2 连通测试
```bash
git ls-remote origin
# 成功返回 refs 即认证通过
```

### 4.3 实际结果（2026-08-21）
- ✅ Helper 输出格式正确
- ✅ `git ls-remote origin` 返回远端 refs
- ✅ `git push -u origin main` 成功
- ✅ `git config --list` 中**无 token 明文**（只有 helper 路径）

## 5. 教训

### 5.1 可推广做法
1. **权限校验写进 helper**：拒绝读取非 600 权限的 token（防止误配置导致泄露）
2. **只读 helper**：`store`/`erase` 直接 exit 0，避免 git 尝试写入
3. **host 限定**：用 `credential.https://github.com.helper` 而非全局 `credential.helper`
4. **repo-local 优先**：`--local` 而非 `--global`，避免影响其他项目
5. **token 文件无尾换行**：`printf '%s'` 写入而非 `echo`，避免 `\n` 混入 password

### 5.2 踩过的坑
- ❌ `git pull origin main --allow-unrelated-histories -m "msg"` → `-m` 是 fetch 选项，报错。正确做法：`git fetch` + `git merge --allow-unrelated-histories -m "msg"`
- ❌ GitHub 新建仓库时勾选 "Add README/LICENSE" → 与本地历史无共同祖先，需要 `--allow-unrelated-histories`
- ⚠️ 已入版本的文件（如 `business/*/logs/*.err`）加 `.gitignore` 无效，需 `git rm --cached`

### 5.3 监控点
- ⚠️ Token 轮换时只需替换 `~/.openclaw/secrets/github.token` 内容，无需改 git 配置
- ⚠️ Token 过期时 `git push` 会报 403，检查 token 有效期
- ⚠️ 如果换机器，需重新创建 helper 脚本（路径是绝对路径，需调整）

## 6. 升级判断

- [x] 涉及 L2 基础设施（凭据管理）
- [ ] 影响 ≥ 2 个层级 — 仅 L2
- [ ] 涉及 L1 契约 — 不涉及（git 是外部工具，非 OpenClaw 契约）
- **决定**：保持经验卡片
  - 理由：这是"凭据管理的实施方法"，与 EXP-20260821-001（Tavily SecretRef）同类
  - 如未来需要统一多个服务的凭据管理策略（GitHub + Tavily + 其他），再升级为 ADR

## 7. 相关

- **同类经验**：EXP-20260821-001（Tavily file-based SecretRef）
- **git 文档**：https://git-scm.com/docs/gitcredentials
- **仓库**：https://github.com/RenLimin/openclaw-v5.0
- **helper 路径**：`~/.openclaw/bin/git-credential-openclaw-file`
- **token 路径**：`~/.openclaw/secrets/github.token`

## 8. 变更历史

- 2026-08-21: 创建（含 helper 脚本 + 配置命令 + 验证步骤 + 3 个坑）
