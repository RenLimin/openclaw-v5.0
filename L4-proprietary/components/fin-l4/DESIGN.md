# fin-l4

## 设计目标

为家庭及个人提供全本地、零外部依赖的理财管理系统。覆盖仪表盘、账户、记账、预算、贷款、保险、投资、理财建议、报表、利率、导入、设置 12 大功能页面。继承 L3 finance-engine 六大通用引擎，专注 CRUD、Web UI、数据持久化、权限、集成等业务逻辑。

## 架构决策

- **L4 继承 L3**：通过 `sys.path` 注入方式 import finance-engine，L4 调用 L3 计算能力，反向依赖禁止
- **全本地运行**：SQLite 单文件数据库，零外部 API 调用，数据完全本地掌控
- **Decimal 精度**：所有金额使用 `decimal.Decimal`，杜绝浮点误差
- **借贷记账法**：资产 = 负债 + 权益，恒等式保证数据一致性
- **三部署方式**：Docker / 裸机 systemd / macOS launchd，自动检测最优方案
- **Repository 层共享**：L3 和 L4 共享 DB 访问层，避免重复代码
- **银行流水导入**：支持招行/工行/支付宝/微信 4 种格式，CSV + Excel 双格式，智能规则分类

## 模块划分

```
fin-l4/
├── engine/                     # 独立部署包
│   ├── fin_l4/                 # L4 主应用
│   │   ├── web/                # Web 层（路由 + 模板 + 静态文件）
│   │   ├── services/           # L4 Service 层（10+ 服务）
│   │   ├── db/                 # Repository 层 + 数据库
│   │   ├── config.py           # 配置模块（env > .env > 默认）
│   │   ├── security/           # 安全模块（备份/加密/审计）
│   │   ├── run_web.py          # 启动入口
│   │   └── requirements.txt
│   ├── deploy/                 # 部署辅助
│   ├── scripts/                # 工具脚本
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── Makefile
│   └── docs/                   # 文档
├── src/fin_l4/                 # 开发态源码镜像
│   ├── web/                    # Web 层
│   │   ├── api.py              # REST API
│   │   ├── main.py             # Flask 入口
│   │   └── templates/          # Jinja2 模板（12 页面）
│   ├── services/               # 业务服务层
│   ├── security/               # 安全模块
│   │   ├── backup.py           # SQLite 热备份
│   │   ├── encryption.py       # 数据加密
│   │   └── audit.py            # 审计日志
│   ├── config.py               # 配置
│   └── load_demo_data.py       # 演示数据
└── tests/                      # 测试套件（78+ 用例）
```

## 关键接口/数据结构

- `fin_l4.web.api`：REST API 层，12 个页面对应路由
- `fin_l4.services.*`：10+ 业务服务（账户/记账/预算/贷款/保险/投资/报表等）
- `fin_l4.db.*`：Repository 层，SQLite 数据访问
- `fin_l4.security.backup`：`backup()` / `restore()` / `list_backups()`，14 份循环保留
- `fin_l4.security.encryption`：数据加密/解密
- `fin_l4.security.audit`：审计日志记录
- L3 引擎通过 `sys.path` 注入后直接调用：`AccountingEngine` / `LoanEngine` / `InsuranceEngine` / `RateEngine` / `PortfolioEngine` / `AdvisorEngine`

## 依赖关系

- **依赖**：L3 finance-engine（六大计算引擎）、Flask（Web）、Jinja2（模板）、Chart.js（图表）、SQLite
- **被依赖**：无（顶层应用组件）

## 演进方向

1. **v1.1 — 用户鉴权 + 多家庭切换 UI**
2. **v1.2 — 移动端适配（PWA + 响应式布局）**
3. **v1.3 — 数据加密 + 端到端加密同步**
4. **v1.4 — 消息通知（预算告警、账单提醒）**
5. **v1.5 — 税务管理模块**
6. **v2.0 — API 开放 + 插件市场**
