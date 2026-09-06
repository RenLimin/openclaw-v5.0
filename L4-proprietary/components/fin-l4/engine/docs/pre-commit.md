# pre-commit 使用指南

[pre-commit](https://pre-commit.com/) 是一个 Git 钩子框架，在代码提交前自动运行检查，确保代码质量。

## 安装

```bash
# 安装 pre-commit（推荐用 pipx）
pipx install pre-commit

# 或者用 pip
pip install pre-commit
```

## 启用

在项目根目录运行：

```bash
cd finance-engine
pre-commit install
```

安装后，每次 `git commit` 时都会自动运行配置的钩子。

## 钩子说明

本项目配置了以下钩子：

| 钩子 | 说明 |
|---|---|
| `trailing-whitespace` | 移除行尾空格 |
| `end-of-file-fixer` | 确保文件以换行结尾 |
| `check-yaml` | YAML 语法检查 |
| `check-json` | JSON 语法检查 |
| `check-added-large-files` | 防止提交大文件（>500KB） |
| `check-case-conflict` | 检查文件名大小写冲突 |
| `check-merge-conflict` | 检查合并冲突标记 |
| `mixed-line-ending` | 统一换行符 |
| `black` | Python 代码格式化 |
| `ruff` | Python lint + 自动修复 |
| `ruff-format` | Ruff 格式化（速度更快的 black 替代） |
| `mypy` | Python 类型检查 |

## 手动运行

```bash
# 运行所有钩子（针对已暂存的文件）
pre-commit run

# 运行所有钩子（针对所有文件）
pre-commit run --all-files

# 运行特定钩子
pre-commit run black --all-files

# 跳过钩子（紧急情况，不推荐）
git commit --no-verify
```

## 配置文件

配置文件位于项目根目录：`.pre-commit-config.yaml`

修改配置后，运行以下命令更新钩子版本：

```bash
pre-commit autoupdate
```

## 首次使用建议

第一次启用 pre-commit 时，建议先对整个代码库运行一次：

```bash
pre-commit run --all-files
```

这会格式化所有现有代码，确保后续提交的代码风格一致。

## 常见问题

### Q: 钩子修改了文件怎么办？

钩子自动修复的文件（如 black、ruff）会被修改但**不会自动暂存**。你需要：
1. 检查修改是否符合预期
2. 用 `git add` 重新暂存
3. 再次 `git commit`

### Q: 可以跳过某个钩子吗？

可以通过 `SKIP` 环境变量：

```bash
SKIP=mypy git commit -m "feat: xxx"
```

但不建议频繁跳过，应该优先修复问题。

### Q: 如何更新钩子版本？

```bash
pre-commit autoupdate
```

这会自动更新 `.pre-commit-config.yaml` 中的 `rev` 到最新稳定版。
