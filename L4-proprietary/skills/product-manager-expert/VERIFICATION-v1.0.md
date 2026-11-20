# product-manager-expert — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是 **L4 产品相关统一入口**（PME-001），核心职责为产品咨询/
> 跨产品方案/**知识库检准维护**，数据查询路由到 `product-kb`。
> 本文件验收 skill 自身的检准脚本与路由表，数据层回归见 product-kb 验收文档。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 检准脚本可复跑 | `audit_kb.py` 退出码语义：0 无异常 / 1 有警告 / 2 有错误 |
| 2 | 报告分级齐全 | 含 error / warn / info 三级与汇总行 |
| 3 | 第三方占位桶豁免 | id 191-193「非梆梆」桶被自动豁免 |
| 4 | 报告可落盘 | 同时产出 JSON + Markdown |
| 5 | 产品需求路由唯一 | §一 路由表条目可解析 |
| 6 | 非产品需求正确分流 | §边界外 6 条指向存在资产 |
| 7 | embedding 重建脚本可用 | `rebuild_embeddings.py --help` exit 0 |

## 测试范围

- skill 自身：`scripts/audit_kb.py`、`scripts/rebuild_embeddings.py`、`docs/kb-audit-20261029.{md,json}`。
- 无 `tests/` 目录；检准脚本以真实 DB 实跑作为实测。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 检准实跑（真实 DB） | `audit_kb.py --db .../product_kb.db --json --report` | 退出码与分级一致 | ✅ 汇总 error=1 warn=2 info=3 |
| 2 | 退出码 | 同上 | error>0 → 2 | ✅ `AUDIT_EXIT=2` |
| 3 | 第三方豁免 | 同上 | 191-193 标注 info 豁免 | ✅ `THIRDPARTY: [191, 192, 193]` |
| 4 | 报告分级 | 同上 | error/warn/info 均出现 | ✅ PATH(error=1)/COVERAGE(warn=2)/THIRDPARTY·NULL·RELATION(info=3) |
| 5 | embedding 脚本契约 | `rebuild_embeddings.py --help` | 参数列出 | ✅ exit 0 |
| 6 | 路由表自洽 | 比对 SKILL.md §一/§边界外 | 条目完整 | ✅ 8 条路由 + 6 条边界外 |
| 7 | 自动化测试 | `pytest tests` | — | ⛔ 无 `tests/` 目录：**无自动化测试** |

## 实测结果

- 命令: `python3 scripts/audit_kb.py --db .../components/product-kb/data/product_kb.db --json /tmp/pkb_audit.json --report /tmp/pkb_audit.md`
- 输出摘要: 🔴 `PATH: 源文件缺失(共1)`（id 2639，`~/Downloads/梆梆安全flutter加固V2.1.0-用户使用手册.docx`）；🟡 `COVERAGE: 无文档产品(共142)`、`无chunk文档(共32)`；🔵 `THIRDPARTY: [191,192,193]`、`NULL: version_latest 为空(共138)`、`RELATION: kb_relation 空(0行)`；汇总 `error=1 warn=2 info=3`；退出码 **2**。
- 命令: `python3 scripts/rebuild_embeddings.py --help` → usage 正常（`--db/--server/--batch/--limit`），exit 0。
- 结论: **通过（检准脚本功能验收）**。脚本可复跑、分级清晰、退出码语义正确、第三方占位桶按规则豁免。检准发现的 1 个 error 是**真实数据问题**（源文件缺失），非脚本缺陷，按 SKILL.md 应由维护者核实路径/补录。

## 可复现手动验证步骤（无自动化测试）

1. 备份 DB：`cp data/product_kb.db data/product_kb.db.bak-<日期>`；
2. 跑检准：`python3 scripts/audit_kb.py --db <db> --json out.json --report out.md`，记录退出码；
3. 按报告分级处置：error 修源文件/清理孤儿；warn 按文件名强规则重分类 doc_type；embedding 为空则跑 `rebuild_embeddings.py`；
4. 产品咨询：`product-kb` 检索 → **打开原始 docx/pptx 读章节** → 结论附文档名与章节；
5. 交付闸门：报告落盘后跑 `python3 L2-infra/prompts/tools/check_answer_contract.py <报告路径>`，exit=0。

## 遗留与后续

- **无自动化测试**：`audit_kb.py` 的分级/退出码语义建议补 pytest（可用临时 DB fixture），把「error→2 / 有 warn→1 / 干净→0」固化为回归。
- 检准报 `RELATION: kb_relation 空`（info）：知识图谱关系未构建，按 SKILL.md 属记录项，不影响主流程。
- 检准发现的源文件缺失（id 2639）建议单独立项跟进补录。
