# FIN-L4 Web UI 仪表盘

轻量级家庭理财 Web 仪表盘，基于 FastAPI + 原生 JS + ECharts，零构建工具链。

## 快速启动

```bash
cd L4-proprietary/components/fin-l4/engine

# 方式一：直接启动
python3 fin_l4/run_web.py

# 方式二：配置端口和数据目录
FIN4_PORT=8501 FIN4_DB_DIR=~/.fin-l4 python3 fin_l4/run_web.py
```

启动后访问：
- **仪表盘**: http://localhost:8500
- **API 文档 (Swagger)**: http://localhost:8500/docs
- **健康检查**: http://localhost:8500/health

### 加载 Demo 数据

```bash
# 先加载模拟数据（会清空已有数据）
python3 fin_l4/load_demo_data.py

# 再启动 Web
python3 fin_l4/run_web.py
```

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python + FastAPI | 异步 Web 框架 |
| 数据层 | SQLite + Repository 模式 | 本地文件数据库 |
| 前端 | 原生 JS + ECharts 5 | 零构建、零依赖 |
| 模板 | Jinja2 | 服务端渲染基础布局 |
| 样式 | 原生 CSS | 支持深色/浅色主题 |

## 功能特性

### 📊 仪表盘首页 (`/`)

**顶部总览卡片（6 项）**
- 总资产、总负债、净资产
- 本月收入、本月支出、储蓄率

**图表区域**
- 月度收支趋势图（柱状图 + 折线面积图，近 12 个月）
- 当月支出/收入分类饼图（可切换类型）

**预算与投资**
- 预算执行进度条（分类进度、剩余日均预算、状态标识）
- 投资组合概览（市值、成本、收益、持仓明细）

**交易与记账**
- 最近 20 条交易记录（带分类）
- 快捷记账表单（支持支出/收入类型切换、分类选择、备注）

**其他特性**
- 🌙 深色 / 浅色主题切换（记忆用户偏好）
- 📱 响应式设计，适配桌面和移动端
- ⚡ 原生 JS + ECharts CDN，零构建步骤

## API 接口清单

所有接口前缀：`/api/v1`

### 仪表盘专用 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/dashboard/overview` | 总览数据（总资产、负债、本月收支、储蓄率） |
| GET | `/dashboard/categories` | 分类统计（支持 `type=income/expense` 和 `month=YYYY-MM`） |
| GET | `/dashboard/monthly-trend` | 月度收支趋势（默认 12 个月，`months` 参数可调） |
| GET | `/dashboard/budget` | 预算执行情况（按月） |
| GET | `/dashboard/investments` | 投资组合持仓 + 收益 |
| GET | `/dashboard/transactions` | 最近交易记录（默认 20 条，`limit` 参数可调） |

### 通用 API（已有）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/transactions` | 交易列表 / 新增交易 |
| GET/POST | `/accounts` | 账户列表 / 新增账户 |
| GET | `/accounts/trial-balance` | 试算平衡表 |
| GET/POST | `/budgets` | 预算列表 / 设置预算 |
| GET | `/budgets/status` | 预算执行状态 |
| GET/POST | `/loans` | 贷款列表 / 创建贷款 |
| GET/POST | `/insurance` | 保险列表 / 创建保单 |
| GET/POST | `/portfolios` | 投资组合列表 / 创建 |
| GET | `/reports/balance-sheet` | 资产负债表 |
| GET | `/reports/income` | 收支汇总表 |
| GET | `/reports/cashflow` | 月度现金流 |
| GET | `/export/balance-sheet` | 导出 Excel 资产负债表 |
| GET | `/export/transactions` | 导出 Excel 交易明细 |
| GET | `/export/report` | 导出 Word 财务报告 |

## 项目结构

```
fin_l4/
├── web/
│   ├── main.py              # FastAPI 主应用 + 页面路由
│   ├── api.py               # REST API 路由（含仪表盘专用 API）
│   ├── templates/           # Jinja2 模板
│   │   ├── base.html        # 布局模板（sidebar + theme）
│   │   ├── dashboard.html   # 仪表盘首页（ECharts 单页）
│   │   └── ...              # 其他页面
│   └── static/
│       ├── style.css        # 全站样式（含响应式 + 深色主题）
│       └── vendor/chartjs/  # Chart.js（旧版页面用）
├── services/
│   ├── report_svc.py        # 报表服务（含仪表盘专用方法）
│   ├── budget_svc.py        # 预算服务
│   ├── txn_svc.py           # 交易服务
│   └── ...                  # 其他服务
├── db/
│   ├── __init__.py          # 数据库连接 + 迁移
│   └── repositories.py      # Repository 层
└── run_web.py               # 启动脚本
```

## 运行测试

```bash
cd engine
python3 -m pytest tests/test_dashboard_api.py -v
```

17 个 API 测试覆盖：
- ✅ 健康检查
- ✅ 总览接口（结构 + 数据验证）
- ✅ 月度趋势（数量 + 结构）
- ✅ 分类统计（支出 + 收入 + 全部）
- ✅ 预算执行（结构 + 单条字段）
- ✅ 投资组合（结构 + 持仓收益计算）
- ✅ 最近交易（数量 + 字段）
- ✅ 新增交易（快捷记账）
- ✅ Swagger UI 可访问
- ✅ 仪表盘页面渲染

## 配置项

通过环境变量配置（也可在项目根目录放 `.env` 文件）：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `FIN4_HOST` | `127.0.0.1` | 监听地址 |
| `FIN4_PORT` | `8500` | 监听端口 |
| `FIN4_DB_DIR` | `~/.fin-l4` | 数据库文件目录 |
| `FIN4_FAMILY_ID` | `default` | 默认家庭 ID |
| `FIN4_DEBUG` | `0` | 调试模式 |

## 快捷记账说明

快捷记账通过以下规则自动选择对方账户：

- **支出**：借方 = 费用类账户（如餐饮费），贷方 = 第一个资产类账户
- **收入**：借方 = 第一个资产类账户，贷方 = 收入类账户（如工资收入）

系统自动选取第一个 `ASSET` 类型账户作为资金中转账户。

## 主题切换

点击侧栏底部的「🌙 深色 / ☀️ 浅色」按钮切换主题，偏好保存在 `localStorage`。
ECharts 图表会跟随主题自动重绘。
