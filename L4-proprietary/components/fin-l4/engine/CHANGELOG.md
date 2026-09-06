# Changelog

All notable changes to this project will be documented in this file.

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，
版本号遵循 [Semantic Versioning](https://semver.org/lang/).

---

## [v1.0.0] — 2026-09-04

### Added

- **L4 主应用框架** — `fin_l4/` 核心框架，包含 Web 层、Service 层、Repository 层
- **L3 六大通用引擎** — fin001_account（核算）、fin002_loan（贷款）、fin003_insurance（保险）、fin004_rate（利率）、fin005_portfolio（投资组合）、fin006_advisor（理财建议）
- **12 个功能页面**
  - 仪表盘（Dashboard）— 资产概览 + 图表 + 最近交易
  - 账户管理 — 五大类账户 CRUD + 期初余额
  - 记账 — 借贷记账法 + 双分录校验
  - 预算管理 — 分类预算设置 + 执行跟踪
  - 贷款管理 — 贷款列表 + 还款计划 + 提前还款模拟
  - 保险管理 — 保单管理 + 现金价值 + 保障缺口分析
  - 投资组合 — 持仓管理 + 资产配置 + 再平衡建议
  - 理财建议 — 财务健康评分 + 优化建议
  - 报表中心 — 资产负债表 + 利润表 + 现金流量表
  - 利率中心 — LPR 存贷款利率快照 + 历史查询
  - 数据导入 — CSV 批量导入 + 字段映射 + 自动分类
  - 系统设置 — 家庭信息 + 分类管理 + 数据管理
- **14 张数据库表** — `fin4_` 前缀，家庭 ID 隔离
- **Docker 部署** — Dockerfile + docker-compose.yml，非 root 运行 + 健康检查 + 数据卷持久化
- **裸机部署** — Linux systemd + macOS launchd，开机自启 + 崩溃自愈
- **一键部署脚本** — `deploy.sh` 自动检测 Docker / 裸机环境
- **数据备份脚本** — `deploy/backup.sh` SQLite 热备，保留最近 14 份
- **配置系统** — 三级优先级：环境变量 > `.env` 文件 > 内置默认
- **78 个自动化测试** — 数据库层 / 服务层 / 端到端，100% 通过
- **5 份文档** — 架构说明 / 操作手册 / 测试报告 / 部署指南 / 交付清单
- **Decimal 精度** — 所有金额使用 `decimal.Decimal`，杜绝浮点误差
- **CSV 导入引擎** — 支持银行/券商账单格式，自动分类规则引擎
- **导出功能** — 报表支持 Excel / Word 导出

### Changed

- 无（首版发布）

### Fixed

- 无（首版发布）

### Security

- 默认监听 `127.0.0.1`，仅本机可访问
- 全本地 SQLite，零外部 API 调用，数据不离开本地
- 外部系统链接只读模式，不存储凭据，不自动同步
- Docker 非 root 用户运行，减小攻击面

---

[Unreleased]: https://github.com/RenLimin/openclaw-v5.0/compare/v1.0.0...HEAD
[v1.0.0]: https://github.com/RenLimin/openclaw-v5.0/releases/tag/v1.0.0
