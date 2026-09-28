# FIN-L4 家庭理财管理系统 — 产品操作手册（OPERATIONS）

> 版本：v1.0（2026-09-28）
> 组件：FIN-L4（L4 专有业务层）
> 代码：`L4-proprietary/components/fin-l4/`
> 三通道：Web UI / CLI（finctl）/ OpenClaw skill

---

## 1. 安装与启动

### 1.1 依赖安装

```bash
cd L4-proprietary/components/fin-l4
pip install -r src/fin_l4/requirements.txt
# 核心：fastapi uvicorn click jinja2 openpyxl python-docx
```

### 1.2 启动 Web UI

```bash
cd L4-proprietary/components/fin-l4/src

# 默认 127.0.0.1:8500，数据目录 ~/.fin-l4
python3 fin_l4/run_web.py

# 自定义
FIN4_HOST=0.0.0.0 FIN4_PORT=8501 FIN4_DB_DIR=/data/fin4 python3 fin_l4/run_web.py
```

访问 `http://127.0.0.1:8500` → 仪表盘。

### 1.3 快速初始化

```bash
cd L4-proprietary/components/fin-l4/src

# 创建家庭（首次必须）
python3 -m fin_l4.cli family create --name "我家"

# 载入演示数据（可选）
python3 fin_l4/load_demo_data.py
```

### 1.4 健康检查

```bash
curl -s http://127.0.0.1:8500/api/health
```

---

## 2. 操作指南

### 2.1 CLI（finctl，14 命令组）

```bash
cd L4-proprietary/components/fin-l4/src
alias finctl="python3 -m fin_l4.cli"

# 家庭
finctl family create --name "我家"
finctl family list

# 账户
finctl account list
finctl account add --name "招行储蓄" --type asset --balance 100000

# 记账（复式）
finctl txn add --date 2026-09-28 --desc "午餐" --amount 35 --category 餐饮

# 预算
finctl budget set --month 2026-09 --category 餐饮 --limit 3000
finctl budget status --month 2026-09

# 贷款
finctl loan add --name "房贷" --principal 1000000 --rate 0.0385 --years 30 --method 等额本息
finctl loan schedule --id <loan_id>
finctl loan prepay --id <loan_id> --amount 100000        # 提前还款模拟

# 保险
finctl insurance add --name "重疾险" --premium 8000 --years 20
finctl insurance cash-value --id <id>                    # 现金价值测算

# 投资
finctl portfolio add --name "股票账户"
finctl portfolio buy --id <id> --code 600519 --price 1500 --qty 100

# 报表 + 导出
finctl report balance-sheet          # 资产负债表
finctl report income --month 2026-09
finctl report cashflow --month 2026-09
finctl export excel --report balance-sheet --out 资产负债表.xlsx
finctl export word --report income --out 收支.docx

# 理财建议
finctl advise health                 # 财务健康评分
finctl advise allocation             # 资产配置建议

# 银行流水导入
finctl rules bank                    # 查看支持的银行模板
finctl imp csv --bank cmb --file 流水.csv

# 利率
finctl rate list
```

### 2.2 Web UI（12 页面）

仪表盘 `/` / 账户 `/accounts` / 记账 `/transactions` / 预算 `/budget` / 贷款 `/loans` / 保险 `/insurance` / 投资 `/portfolio` / 建议 `/advice` / 报表 `/reports` / 利率 `/rates` / 导入 `/import` / 设置 `/settings`

### 2.3 OpenClaw skill（对话触发）

对 Jerry 说：「记一笔午餐 35 元」「看这个月预算执行」「房贷提前还款 10 万能省多少利息」→ 自动走 fin-l4 skill。

### 2.4 备份与恢复

```bash
# 备份（SQLite 热备份，自动保留 14 份）
finctl backup
# 或 Web UI → 设置 → 立即备份

# 恢复
finctl restore --backup <备份文件名>
```

---

## 3. 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `尚未创建家庭` 报错 | 首次使用未初始化 | `finctl family create --name "我家"` |
| Web 启动失败端口占用 | 8500 被占 | `FIN4_PORT=8501 python3 fin_l4/run_web.py` |
| `No module named fin_l4` | 未在 src 目录 | `cd L4-proprietary/components/fin-l4/src` |
| 导入流水重复 | 预期防护（自动去重） | 查看导入报告的 skipped 计数 |
| L3 引擎 import 失败 | sys.path 未注入 | 确认从 src 目录启动；检查 finance-engine 路径 |
| 金额显示异常（精度） | 不会发生（全程 Decimal） | 若出现请提 issue，属 bug |

---

## 4. FAQ

**Q1: 数据存在哪？**
A: 默认 `~/.fin-l4/`（SQLite 单文件），可用 `FIN4_DB_DIR` 改路径。

**Q2: 会连银行/券商吗？**
A: 不会。全本地零外联，流水靠 CSV/Excel 手动导入。

**Q3: 多家庭怎么用？**
A: `finctl --family <id> <命令>` 切换；UI 多家庭切换在 v1.1 规划中。

**Q4: 报表能导出什么格式？**
A: Excel（openpyxl）+ Word（python-docx）。

---

## 5. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-28 | v1.0 | 初版归档（189 测试基线） |
