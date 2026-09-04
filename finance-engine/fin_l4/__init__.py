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
- 继承 L3 引擎 (FIN-001~006)

端口: 8500 (不与 OpenClaw 18789 冲突)
"""

__version__ = "0.1.0"
__layer__ = "L4"
