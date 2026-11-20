# fin-l4 — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 对应 **L4 家庭及个人理财管理系统**（FIN-L4），
> 实现位于组件 `L4-proprietary/components/fin-l4`（继承 L3 `finance-engine`）。
> 本文件为 skill 层验收，测试取自该组件测试集。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 数据全本地 SQLite | 无外发网络（利率源除外），表前缀 `fin4_` |
| 2 | 复式记账与试算平衡 | 每笔有借+贷，试算平衡通过 |
| 3 | Decimal 精度 | ROUND_HALF_UP，2 位 |
| 4 | 服务层全覆盖 | 10 服务（账户/记账/预算/分类/导入/贷款/保险/投资/报表/建议）有测试 |
| 5 | L3 引擎零副作用 | fin001~fin006 测试全绿 |
| 6 | E2E 全链路 | `test_fin_l4_e2e.py` 通过 |
| 7 | 回归全绿（排除 visual） | 0 failed |

## 测试范围

组件 `L4-proprietary/components/fin-l4/tests/`，**203** 用例：
`test_fin001~006.py`（L3 引擎）、`test_fin_l4_{db,services,e2e,m2,m3,pf01}.py`、
`test_bank_import.py`、`test_dashboard_api.py`、`visual/`（需 Web 预览服务）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | L3 引擎 | `tests/test_fin001~006.py` | 纯计算零副作用 | ✅ 含于 #6 |
| 2 | 数据层 | `test_fin_l4_db.py` | 14 表 + Repository | ✅ 含于 #6 |
| 3 | 服务层 | `test_fin_l4_services.py` | 10 服务 | ✅ 含于 #6 |
| 4 | E2E | `test_fin_l4_e2e.py` | 全链路 | ✅ 含于 #6 |
| 5 | M2/M3/PF01 | `test_fin_l4_m2/m3/pf01.py` | 分类/预算/贷款保险投资 | ✅ 含于 #6 |
| 6 | 非 visual 全量 | `pytest tests -q --ignore=tests/visual` | 0 failed | ✅ 189 passed（1.55s） |
| 7 | 全量（含 visual） | `pytest tests -q` | 仅 visual 失败 | 14 failed, 189 passed（visual 环境性） |
| 8 | 用例总数 | `--collect-only` | 203 | ✅ 203 tests collected |

## 实测结果

- 命令: `cd L4-proprietary/components/fin-l4 && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider --ignore=tests/visual`
- 输出摘要: `189 passed in 1.55s`。
- 命令: `pytest tests -q`（全量）→ `14 failed, 189 passed in 10.78s`；14 例失败全部为 `tests/visual/test_pages.py`（Dashboard/Budget/Import/Loans/Insurance/CoverageGap/Portfolio/Accounts/Transactions/Rates/Rules/Settings/Reports/Advise 共 13 个页面类），属 Web 预览服务未启动的环境性失败。
- 结论: **通过**。功能测试 189 全绿，覆盖 SKILL.md 声明的账/预算/贷款/保险/投资/报表/导出与 L3 引擎。

## 遗留与后续

- visual 14 例需先启动 Web 预览服务（端口 8500 侧）；建议 `conftest` 前置检查缺失时 `skip`，与 bangcle-ppt 同类问题一并治理。
- 组件已有 `VERIFICATION-v1.0.md`（2026-09-28，189 passed），本文件为 skill 层补充，二者口径一致。
