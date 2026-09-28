# FIN-L4 家庭理财管理系统 — 设计大纲（DESIGN-OUTLINE）

> 组件 ID：FIN-L4
> 版本：v1.0（2026-09-28 补录）
> 依据：PRD-v1.0 + ADR-202609-026/027
> 详细设计：`L4-proprietary/components/fin-l4/DESIGN.md`（模块划分 + 接口）+ README.md（架构图）

---

## 1. 整体架构

```
L4 FIN-L4（Web UI + CLI + skill 三通道）
  web/（FastAPI + Jinja2 12 页面 + Chart.js）
  cli.py（finctl，click，14 命令组）
  services/（10+ 业务服务）
  security/（backup / encryption / audit）
  db/（Repository 层，SQLite）
        │ sys.path 注入 import（L4 → L3）
        ▼
L3 finance-engine（六大纯计算引擎）
  fin001_account 核算 / fin002_loan 贷款 / fin003_insurance 保险
  fin004_rate 利率 / fin005_portfolio 投资 / fin006_advisor 建议
        │
        ▼
L2 持久化（SQLite + Repository 模式）+ Office 生成（openpyxl/python-docx）
```

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| `web/main.py + api.py` | FastAPI 入口 + REST API，12 页面路由 |
| `cli.py` | finctl 命令行：family/account/txn/category/budget/loan/insurance/portfolio/report/rate/export/advise/imp/rules 14 组 |
| `services/` | 10+ 业务服务（账户/交易/预算/贷款/保险/投资/报表/导入/分类引擎） |
| `db/` | Repository 层 + init_db + 14 张表 |
| `security/backup.py` | SQLite 热备份，14 份循环保留 |
| `security/encryption.py` | 敏感字段加密 |
| `security/audit.py` | 审计日志 |
| `config.py` | 配置（env > .env > 默认） |
| `run_web.py` | Web 启动入口（FIN4_HOST/PORT/DB_DIR 环境变量） |
| `load_demo_data.py` | 演示数据 |

## 3. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| L3/L4 边界 | L3 纯计算零副作用 / L4 CRUD+UI+持久化 | ADR-026/027；L3 可被其他理财场景复用 |
| 记账模型 | 借贷记账法 + Decimal | 恒等式保证一致性；杜绝浮点误差 |
| DB | SQLite 单文件 + Repository 模式 | 全本地数据主权；L2 持久化契约 |
| 三通道 | Web / CLI / skill 同一 service 层 | 数据一致，入口冗余 |
| 导入 | 4 银行模板 + 智能规则分类 + 去重 | 手动导入为主，不连银行 |
| 部署 | Docker/systemd/launchd | 跨平台 |

## 4. 数据模型（摘要）

- 14 张表：family / account / transaction / category / budget / loan / loan_payment / insurance_policy / portfolio / holding / rate / audit_log / backup_meta / import_rule
- 金额字段统一 Decimal 存储
- family_id 全表隔离（多家庭预留）

## 5. 接口契约（摘要）

- REST：`/api/<module>/<action>`，12 页面各有对应路由
- CLI：`finctl <group> <command>`（click 14 组）
- skill：OpenClaw 对话触发（`L4-proprietary/skills/fin-l4/SKILL.md`）

## 6. 演进方向

v1.1 用户鉴权 → v1.2 PWA → v1.3 端到端加密同步 → v1.4 消息通知 → v1.5 税务 → v2.0 API 开放

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-28 | v1.0 | 补录归档 |
