"""BDMS - Bangcle 交付管理系统

基于 L3 交付管理通用业务层，实现 Bangcle 专有业务。

组件：
  collectors/  - 数据采集层（ONES/OA/企业微信/工时）
  engines/     - 业务逻辑引擎（关联/状态/考核/统计）
  generators/  - 报告生成器（交付月报/确收月报/审批）
  config/      - 配置文件（图例映射）
  main.py      - 主入口
  db.py        - 数据库连接
"""

__version__ = "1.0.0"
__author__ = "Jerry (AI Assistant for Bangcle)"
