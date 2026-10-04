# BDMS 交付管理系统 — 产品操作手册（OPERATIONS）

> 版本：v2.1（2026-09-28）
> 依据：PRD-v2.1 + DESIGN-OUTLINE-v2.1 + 7 份 DESIGN-DETAIL-v2.1
> 组件路径：`L4-proprietary/components/bdms/`
> 架构文档：`docs/architecture/00-system-architecture.md` §L4

---

## 1. 安装与启动

### 1.1 环境依赖

- Python ≥ 3.10
- 依赖清单（`requirements.txt`）：fastapi / uvicorn / pydantic / openpyxl / pandas / httpx / jinja2

### 1.2 安装步骤

```bash
cd ~/.openclaw/workspace/L4-proprietary/components/bdms
pip install -r requirements.txt
```

### 1.3 初始化

```bash
# 方式一：CLI（推荐）
PYTHONPATH=src python3 -m bdms.cli.main init
# → ✅ DB 初始化: data/bdms.db

# 方式二：直接调 core
PYTHONPATH=src python3 -c "from bdms.core import db; db.init_db()"
```

首次运行任意 CLI 命令也会自动建表（幂等）。

### 1.4 启动 Web UI

```bash
# 默认 127.0.0.1:8800
PYTHONPATH=src python3 -m bdms.cli.main web

# 自定义端口
PYTHONPATH=src python3 -m bdms.cli.main web --host 0.0.0.0 --port 8811
```

> **端口约定**：v1.0 历史端口 8811；v2.1 默认 8800。E2E 测试使用 18811（避免与生产冲突）。

### 1.5 健康检查

```bash
curl -s http://127.0.0.1:8800/health        # Web API v1
curl -s http://127.0.0.1:8800/api/health    # 同上（别名）
# → {"status": "ok"}
```

---

## 2. 操作指南

### 2.1 场景一：生成交付月报（月度例行）

```bash
# 生成 2026-06 月报（auto 模式：有缓存读缓存，无则重新生成）
PYTHONPATH=src python3 -m bdms.cli.main report generate 202606

# 强制重新生成
PYTHONPATH=src python3 -m bdms.cli.main report generate 202606 --mode regenerate

# 只读缓存（不重算）
PYTHONPATH=src python3 -m bdms.cli.main report generate 202606 --mode read

# 导出 Excel（15 Sheet）
PYTHONPATH=src python3 -m bdms.cli.main report export 202606 --out output/交付月报_202606.xlsx

# 查看已有哪些月份
PYTHONPATH=src python3 -m bdms.cli.main report list
```

**月份格式**：同时兼容 `202606` 和 `2026-06`（后端统一规范化，勿依赖前端转换）。

### 2.2 场景二：确认收入

```bash
# 导入源数据
PYTHONPATH=src python3 -m bdms.cli.main revenue import 202606

# 生成确认收入（--mode 幂等：auto/read/regenerate）
PYTHONPATH=src python3 -m bdms.cli.main revenue generate 202606

# 汇总
PYTHONPATH=src python3 -m bdms.cli.main revenue summary 202606

# 与手工报表对比（黄金基准校验）
PYTHONPATH=src python3 -m bdms.cli.main revenue compare 202606 --manual <手工报表.xlsx>
```

### 2.3 场景三：统计看板

```bash
# CLI 查看某月 KPI
PYTHONPATH=src python3 -m bdms.cli.main dashboard show 202606
```

Web UI 路径：`http://127.0.0.1:8800/dashboard`

### 2.4 场景四：基础数据维护

```bash
# 列出基础数据（客户/项目/合同等）
PYTHONPATH=src python3 -m bdms.cli.main master-data list
PYTHONPATH=src python3 -m bdms.cli.main master-data list customer
```

### 2.5 场景五：系统设定

```bash
# 读
PYTHONPATH=src python3 -m bdms.cli.main settings get

# 写（例：设定确收口径）
PYTHONPATH=src python3 -m bdms.cli.main settings set <key> <value>
```

### 2.6 黄金基准对比（回归验证）

```bash
# 交付月报对比（202606 手工报表黄金基准）
python3 tools/compare_delivery_report.py --generated output/交付月报_202606.xlsx --baseline <手工报表>

# 确收汇总对比
python3 tools/compare_revenue_summary.py
```

> **对比口径铁律**：手工报表覆盖全年 12 个月，其中 7-12 月是"当时预测"。对比必须在**报表月份及之前的同口径区间**内判定，否则会误报差异（2026-09-15 实测教训）。

### 2.7 全量测试

```bash
python3 -m pytest tests/ -q
# 当前基线（2026-09-28 实测）：306 passed, 16 skipped
```

---

## 3. 故障排查

### 3.1 Web 启动失败：端口占用

```bash
lsof -nP -iTCP:8800 -sTCP:LISTEN
# 换端口启动
PYTHONPATH=src python3 -m bdms.cli.main web --port 8801
```

### 3.2 月报生成报"月份不存在"

- 先 `report list` 确认月份已注册
- 月份写入会统一规范化（`YYYY-MM`），脏数据已清理（2026-09-28 修复，备份 `bdms.db.bak-month-fix`）
- 若仍异常：检查 `report_month` 表是否有非规范化残留

### 3.3 数据不一致 / 回归失败

1. 确认对比区间是否同口径（见 §2.6 铁律）
2. 用 `--mode regenerate` 强制重算后再对比
3. 检查是否 E2E 测试写入的脏数据（历史踩坑：测试数据混入生产表）

### 3.4 数据库损坏恢复

- 备份链：`data/bdms.db.bak-*`（月度修复前快照）
- 恢复：`cp data/bdms.db.bak-month-fix data/bdms.db`（先停 Web）
- revenue 侧备份：`revenue.db.bak-20260916-*`

### 3.5 测试环境隔离

- E2E 测试固定用 18811 端口 + 独立测试 DB（`revenue_test.db` / `rr_test.db`）
- 单元/集成测试用 `tmp_path` 临时 DB，不碰生产库

---

## 4. FAQ

**Q1: 为什么 7-12 月数据和手工报表对不上？**
A: 手工报表的 7-12 月是 2026-06 时点的预测值，数据随月份演进。只对比报表月份及之前。

**Q2: 表头为什么 202606 是 93 列、202608 是 44 列？**
A: 表头自适应（方案 B）：同一映射器适配两种表结构，属正常行为。

**Q3: Web UI 和 CLI 数据会不一致吗？**
A: 不会。Web API 与 CLI 走同一 service 层（2026-09-16 修过 CLI 漏改的回归，现已有调用点扫描保障）。

**Q4: 如何新增一个月份的数据？**
A: Web UI 的月份控件是 input+datalist（可直接输入新月份）→ 导入源数据 → `report generate <month>`。

---

## 5. 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r1 | 2026-09-28 | 初版：安装/启动/5 场景操作/故障排查/FAQ，基于 v2.1 全量交付（306 测试基线） |
