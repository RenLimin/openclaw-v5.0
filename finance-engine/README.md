<svg>
<p align="center">
  <img src="https://img.shields.io/badge/version-v1.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Python-3.12%2B-yellow?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/tests-78%20passed-brightgreen?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/Docker-ready-2496ed?style=for-the-badge&logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/last--commit-2026--09--04-orange?style=for-the-badge" alt="Last Commit">
</p>

<h1 align="center">🦞 FIN-L4 家庭理财管理系统</h1>

<p align="center">
  <strong>全本地 · 零外部依赖 · 私有化部署的家庭理财管家</strong><br>
  基于 OpenClaw L4 专有业务层架构，继承 L3 六大财务通用引擎
</p>

---

## ✨ 特性

- **🏦 借贷记账法** — 专业复式记账，资产 = 负债 + 权益 恒等式保证数据一致性
- **📊 12 个功能页面** — 仪表盘 / 账户 / 记账 / 预算 / 贷款 / 保险 / 投资 / 理财建议 / 报表 / 利率 / 导入 / 设置
- **🔒 全本地运行** — SQLite 单文件数据库，零外部 API 调用，数据完全掌控在自己手里
- **🐳 一键部署** — Docker / 裸机 systemd / macOS launchd 三种方式，自动检测最优方案
- **💸 贷款引擎** — 等额本息/等额本金、提前还款模拟、节省利息测算
- **🛡️ 保险管理** — 保单管理、现金价值测算、保障缺口分析、退保模拟
- **📈 投资组合** — 持仓管理、资产配置、再平衡建议、收益率曲线
- **🎯 理财建议** — 财务健康评分、应急储备分析、负债健康度诊断
- **📋 三大报表** — 资产负债表 / 利润表 / 现金流量表，支持 Excel / Word 导出
- **💰 Decimal 精度** — 所有金额使用 `decimal.Decimal**，杜绝浮点误差
- **📥 CSV 导入** — 支持银行/券商账单批量导入，自动分类规则引擎
- **🔄 数据备份** — SQLite 热备份，自动保留最近 14 份，支持一键恢复

---

## 🏗️ 架构概览

FIN-L4 基于 OpenClaw 5 层架构中的 L4 专有业务层应用，继承 L3 六大通用财务引擎。

```mermaid
graph TB
    subgraph L4[L4 专有业务层]
        WEB[Web UI<br/>12 页面]
        SVC[L4 Service 层<br/>10+ 服务]
    end

    subgraph L3[L3 通用业务层]
        F1[fin001_account<br/>核算引擎]
        F2[fin002_loan<br/>贷款模块]
        F3[fin003_insurance<br/>保险模块]
        F4[fin004_rate<br/>利率模块]
        F5[fin005_portfolio<br/>投资组合]
        F6[fin006_advisor<br/>理财建议]
    end

    subgraph L2[L2 基础设施层]
        DB[(SQLite<br/>14 张表]
        TPL[Jinja2 模板]
        CHART[Chart.js 图表]
    end

    WEB --> SVC
    SVC --> F1 & F2 & F3 & F4 & F5 & F6
    F1 & F2 & F3 & F4 & F5 & F6 --> DB & TPL & CHART

    style L4 fill:#f9d371,stroke:#d49c10,color:#000
    style L3 fill:#a8dadc,stroke:#457b9d,color:#000
    style L2 fill:#f1faee,stroke:#1d3557,color:#000
```

> **设计原则**：L4 调用 L3（继承通用能力），L3 不感知 L4（反向依赖禁止），Repository 层共享 DB 访问。

---

## 🚀 快速开始

### 三步上手：

```bash
# 1. Clone 项目
git clone https://github.com/RenLimin/openclaw-v5.0.git
cd openclaw-v5.0/finance-engine

# 2. 一键部署（自动检测 Docker，无则回退裸机）
make install

# 3. 打开浏览器
# 👉 http://localhost:8500
```

就这么简单。

---

## 📦 部署方式

### Docker（推荐）

```bash
# docker compose 一键启动
docker compose up -d --build
```

### 裸机（Linux / macOS）

```bash
./scripts/setup.sh   # 交互式一键安装
# 或
make install
```

### 开发运行

```bash
# Python 直接运行（本地开发
make run
```

---

## 📁 项目结构

```
finance-engine/
├── fin_l4/                  # L4 主应用（框架 + Web + 服务）
│   ├── web/                  # Web 层（路由 + 模板 + 静态文件）
│   ├── services/             # L4 Service 层（10+ 服务）
│   ├── db/                   # Repository 层 + 数据库
│   ├── config.py             # 配置模块（env > .env > 默认）
│   ├── run_web.py            # 启动入口
│   └── requirements.txt      # Python 依赖
├── fin001_account/          # L3 核算引擎
├── fin002_loan/             # L3 贷款模块
├── fin003_insurance/          # L3 保险模块
├── fin004_rate/              # L3 利率模块
├── fin005_portfolio/         # L3 投资组合
├── fin006_advisor/          # L3 理财建议
├── fin_l4_pf01/             # L4 实例（家庭专有数据）
├── tests/                    # 测试套件（78 用例）
├── docs/                     # 文档
│   ├── ARCHITECTURE.md       # 架构说明
│   ├── OPERATIONS.md         # 操作手册
│   ├── TEST_REPORT.md        # 测试报告
│   └── DELIVERY.md           # 交付清单
├── deploy/                   # 部署辅助
│   ├── backup.sh             # 数据备份脚本
│   └── fin-l4.service.template
├── scripts/                  # 工具脚本
│   └── setup.sh              # 一键安装脚本
├── Dockerfile                # 生产镜像
├── docker-compose.yml        # compose 编排
├── deploy.sh                 # 部署脚本（自动检测）
├── Makefile                  # 统一命令入口
├── .env.example             # 配置示例
├── CHANGELOG.md              # 变更日志
├── CONTRIBUTING.md           # 贡献指南
├── DEPLOYMENT.md             # 部署指南
├── VERSION                   # 版本号
└── README.md                 # 本文件
```

---

## 🧪 测试

```bash
# 运行全部测试
make test

# 详细输出
make test-verbose

# 或直接调用 pytest
python3 -m pytest tests/ -v
```

- **测试用例**：78 个，100% 通过
- **覆盖范围**：数据库层 / 服务层 / 端到端流程
- **测试隔离**：每个用例使用独立内存数据库

---

## 📚 文档索引

| 文档 | 受众 | 说明 |
|---|---|---|
| [架构说明](docs/ARCHITECTURE.md) | 开发 / 架构师 | 系统架构、模块划分、设计决策 |
| [操作手册](docs/OPERATIONS.md) | 用户 / 运维 | 功能使用、日常运维、FAQ |
| [部署指南](DEPLOYMENT.md) | 运维 | 部署方式、配置、备份恢复 |
| [测试报告](docs/TEST_REPORT.md) | QA / 验收 | 测试用例、结果、验收结论 |
| [交付清单](docs/DELIVERY.md) | 全部 | 交付物清单、关键指标 |

---

## 🛣️ Roadmap

- [ ] **v1.1 — 用户鉴权 + 多家庭切换 UI
- [ ] **v1.2 — 移动端适配（PWA + 响应式布局
- [ ] **v1.3 — 数据加密 + 端到端加密同步
- [ ] **v1.4 — 消息通知（预算告警、账单提醒）
- [ ] **v1.5 — 税务管理模块
- [ ] **v2.0 — API 开放 + 插件市场

---

## 🤝 贡献

欢迎贡献代码、报告 Bug、提出功能建议都非常欢迎！请阅读 [贡献指南](CONTRIBUTING.md) 了解详细流程。

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE) 文件。

---

<p align="center">
  Made with ❤️ + <a href="https://github.com/RenLimin/openclaw-v5.0">OpenClaw</a> 架构
</p>
