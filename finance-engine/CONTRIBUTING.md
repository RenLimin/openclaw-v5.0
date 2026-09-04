# 贡献指南

感谢你对 FIN-L4 家庭理财管理系统的关注！无论你是提交 Bug、提出新功能、改进文档，还是贡献代码，我们都非常欢迎。

---

## 目录

- [环境搭建](#环境搭建)
- [代码规范](#代码规范)
- [测试规范](#测试规范)
- [提交规范](#提交规范)
- [分支模型](#分支模型)
- [PR 流程](#pr-流程)
- [调试技巧](#调试技巧)
- [常见问题](#常见问题)

---

## 环境搭建

### 前置要求

- **Python** >= 3.12
- **Git** >= 2.30
- **Docker** >= 20.10（可选，用于容器化开发）

### 步骤

```bash
# 1. Fork 并 Clone
git clone https://github.com/<your-username>/openclaw-v5.0.git
cd openclaw-v5.0/finance-engine

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux

# 3. 安装依赖
pip install -r fin_l4/requirements.txt
pip install pytest

# 4. 运行开发服务器
make run
```

服务启动后访问 `http://localhost:8500`。

### 验证安装

```bash
# 运行测试套件，确保环境正常
make test
```

预期输出：`78 passed`

---

## 代码规范

### 风格

- 遵循 **PEP 8**
- 最大行宽 **100 字符**
- 使用 4 空格缩进，不用 Tab

### 类型提示

- 所有函数必须添加**类型注解**（Type Hints）
- 使用 `from __future__ import annotations`（如需）
- 复杂类型用 `typing` 模块

```python
# 正确示例
def calculate_interest(principal: Decimal, rate: Decimal, months: int) -> Decimal:
    pass
```

### Docstring

- 所有公开函数、类、模块必须有 docstring
- 格式：**Google 风格**，保持一致
- 包含：功能说明、参数、返回值、异常（如有）

```python
def record_transaction(
    self,
    family_id: str,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    description: str = "",
) -> dict:
    """记录一笔双分录交易。

    Args:
        family_id: 家庭 ID
        debit_account: 借方账户 ID
        credit_account: 贷方账户 ID
        amount: 交易金额（正数）
        description: 交易描述

    Returns:
        包含交易 ID 和借贷分录的字典

    Raises:
        ValueError: 借贷账户相同或金额不合法
    """
    pass
```

### 财务计算规范

- **严禁使用 `float`** 处理金额，必须使用 `decimal.Decimal`
- 除法使用 `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` 保留两位小数
- 所有金额计算在 Service 层及以上必须为 `Decimal` 类型

---

## 测试规范

### 框架

使用 **pytest** 作为测试框架。

### 编写要求

- **新功能必须附带测试**，核心逻辑测试覆盖率不下降
- 测试文件命名：`test_<模块>.py`
- 测试函数命名：`test_<场景>_<预期结果>`
- 使用 **Arrange-Act-Assert** 模式组织测试

### 测试隔离

- 每个测试用例使用**独立内存数据库**，互不干扰
- 测试之间不得共享状态
- 使用 fixture 管理公共资源

```python
import pytest

@pytest.fixture
def db():
    # setup
    yield db
    # teardown
```

### 运行测试

```bash
# 全部测试
make test

# 详细输出
make test-verbose

# 运行指定文件
pytest tests/test_fin_l4_services.py -v

# 运行单个测试用例
pytest tests/test_fin_l4_services.py::TestAccountService::test_create_account -v
```

### 覆盖率

核心业务逻辑（Service 层 + Engine 层）覆盖率目标：**>= 80%**

```bash
# 安装 pytest-cov
pip install pytest-cov

# 查看覆盖率
pytest --cov=fin_l4 --cov-report=term-missing
```

---

## 提交规范

遵循 **Conventional Commits** 规范。

### 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 类型（type）

| 类型 | 说明 |
|---|---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 代码重构（不改变功能） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖更新 |
| `style` | 代码风格（不影响功能） |
| `ci` | CI/CD 配置 |

### 示例

```
feat(loan): 新增提前还款模拟功能

- 支持期限不变、月供减少两种模式
- 计算节省利息和新还款计划
- 添加提前还款审计日志

Closes #123
```

---

## 分支模型

### 主要分支

- **`main`** — 主分支，始终保持可发布状态
- **`feat/*`** — 功能分支，用于开发新特性
- **`fix/*`** — Bug 修复分支
- **`docs/*`** — 文档分支
- **`chore/*`** — 杂项分支

### 工作流

1. 从 `main` 创建功能分支
2. 开发并提交（遵循提交规范）
3. 确保测试全部通过
4. 提交 Pull Request
5. Code Review 通过后合并到 `main`

---

## PR 流程

### 提交 PR 前检查清单

- [ ] 本地测试全部通过（`make test`）
- [ ] 新功能已添加对应测试
- [ ] 代码符合 PEP 8 规范
- [ ] 文档已更新（如有必要）
- [ ] Commit message 符合 Conventional Commits 规范
- [ ] 已从最新 `main` 分支 rebase

### Code Review

- 至少 1 位维护者 Review 通过才能合并
- Review 反馈请在 3 个工作日内响应
- 小的 stylistic 建议可以标记为 `nit:`，不强制

### 合并

- 使用 **Squash and Merge** 方式合并
- Squash 后的 commit message 需符合 Conventional Commits 规范

---

## 调试技巧

### 启用调试模式

```bash
# 环境变量
FIN4_DEBUG=1 make run

# 或写入 .env
FIN4_DEBUG=1
```

调试模式下会输出更详细的日志。

### 查看数据库

```bash
# 使用 sqlite3 直接查看
sqlite3 ~/.fin-l4/fin_l4.db

# 查看所有表
sqlite> .tables

# 查看表结构
sqlite> .schema fin4_accounts
```

### 导入演示数据

开发时导入演示数据便于调试：

```bash
python3 fin_l4/load_demo_data.py
```

> 注意：会清空当前家庭数据，仅用于开发环境。

### 常用调试命令

```bash
# 查看服务状态
make status

# 查看日志
make logs

# 重启服务
make stop && make run
```

---

## 常见问题

### Q: 测试全部通过但页面打不开？

检查：
1. 服务是否启动（`make status`）
2. 端口是否被占用（`lsof -i :8500`）
3. 浏览器控制台是否有报错

### Q: 数据库迁移怎么做？

当前版本使用 SQLite，schema 变更需要手动处理。建议：
1. 在 `db/` 目录下编写迁移脚本
2. 升级前先备份
3. 迁移脚本提供 rollback 能力

### Q: 如何添加新的 L3 模块？

1. 在项目根目录创建 `fin00X_<name>/` 目录
2. 实现纯业务逻辑（不依赖 L4 概念）
3. 在 L4 Service 层封装调用
4. 添加对应测试
5. 更新 `Dockerfile` 和架构文档

### Q: 如何添加新页面？

1. 在 `fin_l4/web/main.py` 添加路由
2. 在 `fin_l4/web/templates/` 添加模板
3. 在侧边栏导航添加链接
4. 添加对应 Service 方法（如需）

---

## 联系方式

- **Issue**: GitHub Issues
- **架构参考**: `docs/architecture/00-system-architecture.md`
- **L4 架构文档**: `finance-engine/docs/ARCHITECTURE.md`

再次感谢你的贡献！
