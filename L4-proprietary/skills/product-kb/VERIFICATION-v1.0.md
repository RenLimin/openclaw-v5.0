# product-kb — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是 **L4 Bangcle 产品知识库**（PKB-001），实现位于组件
> `L4-proprietary/components/product-kb`（8 产品线 / 37 分类 / 193 产品 / 385 SKU / 1046 文档）。
> 测试取自该组件测试集；另附 skill 声明的「检索召回」与「OA 增量同步」手动验证。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 产品查询可用 | `python3 -m product_kb.cli query/list` 正常返回 |
| 2 | 合同标的三态 | satisfied/partial/unsatisfied + 停售红线 |
| 3 | 幂等导入 | 重复导入不产生重复行 |
| 4 | 数据规模 | 193 产品（与 SKILL.md 口径一致） |
| 5 | 回归全绿 | 组件 `tests/` 0 failed |
| 6 | OA 增量同步 | 水位过滤 + 备份可回滚（依赖 OA 会话） |

## 测试范围

组件 `L4-proprietary/components/product-kb/tests/`，**19** 用例：
`test_contract_match.py`(7) / `test_identity.py`(10) / `test_import_idempotent.py`(2)。
DB：`components/product-kb/data/product_kb.db`。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 合同标的匹配 | `test_contract_match.py` | 7 项断言通过 | ✅ 7 passed（0.04s） |
| 2 | 实体唯一性 | `test_identity.py` | 10 项断言通过 | ✅ 10 passed（0.08s） |
| 3 | 幂等导入 | `test_import_idempotent.py` | 重复导入无重复 | ✅ 2 passed（0.21s） |
| 4 | 全量回归 | `pytest tests -q` | 0 failed | ✅ 19 passed（0.37s） |
| 5 | CLI 查询 | `python3 -m product_kb.cli list --search 鸿蒙` | 返回产品列表 | ✅ Found 193 products |
| 6 | 文档规模核对 | DB count | 与 SKILL.md 口径一致 | ⛔ 未跑 DB count（避免写库/加锁；如需以只读连接另验） |
| 7 | OA 增量同步 | `oa_sync_pipeline.sh --dry-run` | 预览候选不落盘 | ⛔ 需 OA 会话，本次未执行（环境性） |

## 实测结果

- 命令: `cd L4-proprietary/components/product-kb && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider`
- 输出摘要: `19 passed, 1 warning in 0.37s`（warning 为 PyPDF2 弃用，非失败）。
- 命令: `python3 -m product_kb.cli list --search 鸿蒙`
- 输出摘要: `Found 193 products`，含 ID/Name/Version/Type/Status 列（如「全渠道应用安全监测软件V6.0 / 6.0 / product / 正常销售」）。
- 结论: **通过**。19 项测试全绿，CLI 查询正常，产品总数 193 与 SKILL.md 口径一致。

## 可复现手动验证步骤（环境性未验项）

1. 查询：`python3 -m product_kb.cli query "鸿蒙NEXT安全键盘"`，核对命中产品与 SKU；
2. 标的匹配：`python3 -m product_kb.cli match "<产品名>"`，核对三态与停售 hard-fail；
3. OA 增量同步：`./scripts/oa_sync_pipeline.sh --dry-run` 预览 → 正式跑 → 核对 `~/.openclaw/data/product-kb-oa-sync/state.json` 水位与 `manifests/run-<ts>.json`；
4. 覆盖更新时确认旧版备份进 `trash/<run-ts>/`。

## 遗留与后续

- 测试未覆盖「中文 FTS 完整词组匹配」与「近似名 prefix 召回」两类 SKILL.md 强调的坑，建议补回归用例。
- OA 同步依赖 `~/.openclaw/data/clm-oa-recon/state.json` 登录态，失效需先重建会话。
