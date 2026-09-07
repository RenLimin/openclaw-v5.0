# Finance Engine — L3 通用理财引擎

L3 通用业务层组件：纯函数式理财计算引擎，不持有数据、不访问 DB、不做持久化。

L4 专有业务层（如 `fin-l4`）通过 import 复用本组件的计算能力，
自身负责 CRUD、Web UI、数据持久化、权限、集成等业务逻辑。

## 模块清单

| 模块 | 功能 | 核心类 |
|------|------|--------|
| `fin001_account` | 复式记账引擎 | `AccountingEngine` |
| `fin002_loan` | 贷款/借款核算（4 种还款方式 + 提前还款） | `LoanEngine` |
| `fin003_insurance` | 保险产品核算（现金价值/IRR/红利演示） | `InsuranceEngine` |
| `fin004_rate` | 利率服务（LPR/基准利率/利率转换/本地缓存） | `RateEngine` |
| `fin005_portfolio` | 投资持仓核算（收益/配置/再平衡） | `PortfolioEngine` |
| `fin006_advisor` | 理财建议引擎（KPI诊断/资产配置/债务优化） | `AdvisorEngine` |

## 设计原则

- **纯函数式**：输入 → 计算 → 输出，不修改全局状态
- **无持久化**：不直接读写数据库，数据由 L4 层注入
- **唯一副作用**：`fin004_rate` 含本地文件缓存（TTL 24h），是唯一允许 IO 的模块
- **无 L4 依赖**：不 import 任何 L4 层代码，保持单向依赖（L4 → L3）

## L4 使用方式

在 `fin_l4/__init__.py` 中已经注入了正确路径：

```python
# L3 通用理财引擎加入 Python 路径
import sys
import os
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),
    '../../../../../L3-business/components/finance-engine'))
```

然后在 service 文件开头也添加了正确路径，每个 service/external 模块可以正常导入 L3 引擎。

## 分层关系

```
L4-proprietary (fin-l4)
    ↓ import (单向依赖)
L3-business (finance-engine) ← 本组件
```
