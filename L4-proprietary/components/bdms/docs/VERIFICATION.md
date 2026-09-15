# BDMS 交付管理系统 — 端到端验证报告

> 生成时间：2026-09-15
> 验证环境：`/Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms`

## 1. 验证结论摘要

| 验证项 | 结果 | 证据 |
|---|---|---|
| 模块1 交付月报 | ✅ 通过 | 24252 行落盘，Excel 导出 10.7MB |
| 模块2 确认收入 | ✅ 通过 | **对比手工报表 18/18 零误差** |
| 模块4 统计看板 | ✅ 通过 | pytest 18/18，KPI/趋势/状态/异常/部门/下钻 |
| Web UI | ✅ 通过 | 7 个页面全部 HTTP 200 |
| CLI | ✅ 通过 | 7 个子命令实测 |
| 表头自适应 | ✅ 通过 | 202606（93列）/ 202608（44列）同一映射器 |

## 2. 核心验证：对比测试（黄金基准）

**基准**：`2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx`（202606 手工报表）

```
期间     维度    我方计划    手工计划   Δ    我方实际    手工实际   Δ
202601  递延    836.92     836.92   OK    794.09     794.09   OK
202601  新签    319.33     319.33   OK     89.38      89.38   OK
202601  合计  1,156.25   1,156.25   OK    883.47     883.47   OK
...
202606  合计  1,069.07   1,069.07   OK  1,236.16   1,236.16   OK
───────────────────────────────────────────────────────────────
结果: 18 匹配 / 0 差异
```

**口径说明**：同口径区间 = 手工报表月份（202606）及之前。7-12 月在手工报表中是"当时预测"，
数据随月份演进，不参与判定（202608 数据中 202612 新签计划已从 699.78 万更新为 912.38 万）。

## 3. Web UI 验证

```bash
$ for p in / /report /revenue /revenue/compare /master-data /dashboard /settings; do
    curl -s -o /dev/null -w "%{http_code} $p\n" http://127.0.0.1:8811$p; done
200 /
200 /report
200 /revenue
200 /revenue/compare
200 /master-data
200 /dashboard
200 /settings
```

**API 验证**
```bash
$ curl -s http://127.0.0.1:8811/api/health
{"status":"ok","component":"bdms-web"}

$ curl -s http://127.0.0.1:8811/api/dashboard/202608
KPI 合同总额: 257851166.92
趋势月数: 12

$ curl -s http://127.0.0.1:8811/api/revenue/compare/202606
scope_month: 202606
matched/comparable: 18 / 18
all_match: True
```

## 4. CLI 验证

```bash
$ ./bdms report list
   202608: {"签约": 16872, "POC&提前实施": 5174, "异常项目": 362, ...}

$ ./bdms revenue summary 202608
期间        递延计划    递延实际    新签计划    新签实际
202601     836.92    794.09    319.33     89.38
...
202612   1,281.29      0.00    912.38      0.00

$ ./bdms revenue compare 202606 --manual "...xlsx"
结果: 18 匹配 / 0 差异 / 6 月无基准

$ ./bdms settings get
{"view.default_months_back":12, "report.auto_overwrite":false, ...}
```

## 5. 表头自适应验证（方案 B 核心能力）

| 月份 | 表结构 | 表头行 | 合同编号列 | 归档月列 |
|---|---|---|---|---|
| 202606 | 93 列 | 第 3 行 | col2 | col7 |
| 202608 | 44 列 | 第 3 行 | col2 | col4 |

**同一映射器自动适配两种完全不同的表结构。**

导入量：
- 202606 → 计划确收底稿 36397 行 + 预算执行表 8985 行
- 202608 → 计划确收底稿 37329 行 + 预算执行表 9897 行

## 6. 发现并修复的缺陷

| # | 缺陷 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | `summary_engine.py` 缺 `from pathlib import Path` | 模块4 agent 报告 | 补 import |
| 2 | 包级相对导入 `from ...core` 越界顶层包 | Web 启动 ImportError | 统一改绝对导入 |
| 3 | 手工报表列序为「新签在前、递延在后」 | 对比测试 12 项差异 | 修正列映射 |
| 4 | `base_layout` 宏不接受 `brand_desc` | Web 500 | 移除该参数 |
| 5 | `index.html` 中 `endblock` 应为 `endcall` | Web 500 | 修正 |
| 6 | web-common 路径 `parents[6]` 层级错误 | Web TemplateNotFound | 改向上查找 |

## 7. 复现命令

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms
export PYTHONPATH=src

# 1) CLI 对比验证（关键）
./bdms revenue compare 202606 --manual \
  "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"

# 2) Web 启动
./bdms web --port 8811
# 浏览器打开 http://127.0.0.1:8811

# 3) 模块测试
python3 -m pytest tests/ -v
```
