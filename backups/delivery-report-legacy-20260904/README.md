# 交付月报 — 旧资产备份清单

> 备份时间：2026-09-04 23:30（Asia/Shanghai）
> 备份原因：Rex 决定重新开发设计交付月报功能，旧资产全部作为备份参考
> 备份位置：`backups/delivery-report-legacy-20260904/`

## 备份内容

| 资产 | 备份位置 | 说明 |
|------|---------|------|
| 交付中心代码 | `delivery_center_code/` | 69 个文件（collectors/engines/generators/config 全量） |
| 设计文档 | `docs_l4-delivery-center/` | DESIGN.md + PLAN.md + references/ |
| 任务记录 | `tasks/` | task-20260902-bdms-delivery-report 的 CONTEXT.md + TASK.yml |

## 数据源清单（供重开发参考）

| 数据 | 位置 | 说明 |
|------|------|------|
| ONES 签约项目统计 | `~/.openclaw/data/ones_exports/签约项目统计.csv` | ⚠️ 仅 40 列（参考报表 83 列，缺 43 列） |
| ONES POC&提前实施 | `~/.openclaw/data/ones_exports/poc_提前实施.csv` | ⚠️ 仅 40 列（参考报表 84 列，缺 44 列） |
| ONES 异常处置 | `~/.openclaw/data/ones_exports/异常处置.csv` | 38 列 ✅ |
| 确收交接 CSV | `~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/202606确收凭证交接-确收.csv` | 524 行 |
| 验收交接 CSV | `~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/202606确收凭证交接-验收.csv` | |
| BDMS SQLite | `~/.openclaw/data/bdms.db` | revenue_vouchers / acceptance_vouchers / oa_contracts |
| 手工参考报表 | `~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx` | 15 Sheet，签约 83 列 |
| 已生成报告 | `~/.openclaw/data/reports/交付月报-202606.xlsx` | 旧逻辑产物 |

## 已知问题（重开发必须解决）

1. **签约/POC 数据源不完整**：当前导出的 ONES CSV 仅 40 列，参考报表 83/84 列，缺 40+ 列
2. **签约统计右表、产品-授权&维保统计**等复杂透视表逻辑是反推出来的，无书面定义
3. **对比脚本有 bug**：一方为空就跳过，掩盖了数据源不匹配
4. 之前多次宣布"全部完成"但实际未完成——根因是规格不明确 + 试错式开发

## git

- 代码已 git 跟踪（历史 commit 见 `git log`）
- 建议重开发从干净规格出发，旧代码仅作参考
