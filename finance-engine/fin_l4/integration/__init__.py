"""外部系统链接管理模块

功能:
- 外部系统链接 CRUD（银行 / 券商 / 基金 / 其他）
- 链接信息存储在 fin4_integrations 表
- 不存储敏感凭证（凭证由 security.encryption 模块独立管理）

设计原则:
- 纯 Python 库，不注册 OpenClaw 工具
- 通过 IntegrationRepository 访问数据库
- 链接类型: bank / broker / fund / other
"""

from fin_l4.integration.links import LinkManager

__all__ = ["LinkManager"]
