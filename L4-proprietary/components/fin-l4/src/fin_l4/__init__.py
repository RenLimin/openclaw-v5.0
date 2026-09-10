"""
FIN-L4 家庭理财管理系统

L4 专有业务层：
- 数据持久化 (SQLite + Repository)
- 服务层 (8 个业务服务 + 3 个新增模块)
- 外部数据接入 (external: 利率 / 行情 / 汇率)
- 外部系统链接 (integration: bank/broker/fund/other)
- 安全模块 (security: 加密 / 备份 / 审计)
- Web UI (FastAPI + Jinja2)
- CLI (Click)
- 复用 L3 通用理财引擎 (FIN-001~006)

端口: 8500 (不与 OpenClaw 18789 冲突)
"""

import sys
import os

# 将 L3 通用理财引擎加入 Python 路径
# fin_l4/ -> engine/ -> fin-l4/ -> components/ -> L4-proprietary/ -> repo/ -> L3-business/...
_L3_FINANCE_ENGINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__),
                 '..', '..', '..', '..', '..',
                 'L3-business', 'components', 'finance-engine')
)
if _L3_FINANCE_ENGINE not in sys.path:
    sys.path.insert(0, _L3_FINANCE_ENGINE)

__version__ = "0.1.0"
__layer__ = "L4"
