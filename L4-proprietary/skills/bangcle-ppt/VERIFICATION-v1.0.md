# bangcle-ppt — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本文件为 **skill 层验收**。该 skill 自身只有设计常量与模板占位，
> 真实实现位于组件 `L4-proprietary/components/bangcle-ppt`（CPT-012/CPT-004），
> 因此测试范围取 skill 目录 + 其声明依赖的组件。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | VI 设计常量可被外部引用且取值符合 Bangcle 规范 | `design-constants.js` 可被 `require`，主色 `#2D74BB`、背景 `#FFFFFF`/`#00122B`、16:9 画布常量存在 |
| 2 | 组件测试全绿（排除需本地 Web 预览服务的 visual 用例） | `pytest tests --ignore=tests/visual` → 0 failed |
| 3 | 模板/渲染器/DSL schema/CLI 四类能力可用 | 对应测试文件全绿 |
| 4 | 对外示例脚本不误报依赖 | SKILL.md 示例的 API（`Automizer`/`modify`/`pptxgenjs`）在示例语义下可解释 |

## 测试范围

- skill 自身：`scripts/*.cjs`（历史调试脚本，非测试框架）、`src/design-constants.js`、`templates/`（空占位）。
- 依赖组件：`L4-proprietary/components/bangcle-ppt/tests`（253 用例：templates / web / dsl_schema / template_engine / all_renderers / cli / visual）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 全量回归（含 visual） | `pytest tests -q` | 仅 visual 因预览服务未启动失败 | 3 failed, 249 passed, 1 skipped |
| 2 | 非 visual 全量 | `pytest tests -q --ignore=tests/visual` | 0 failed | ✅ 249 passed, 1 skipped（2.33s） |
| 3 | 设计常量引用 | `node -e "require('./src/design-constants.js')"` | 导出 colors/fonts/sizes/pageTypes | ✅ 导出 4 个键，`colors.primary=#2D74BB`、`colors.bg.light=#FFFFFF`、`colors.bg.dark=#00122B` |
| 4 | 模板引擎 | `pytest tests/test_template_engine.py -q` | 全绿 | ✅ 含于 #2 |
| 5 | 渲染器 | `pytest tests/test_all_renderers.py -q` | 全绿 | ✅ 含于 #2 |
| 6 | DSL schema | `pytest tests/test_dsl_schema.py -q` | 全绿 | ✅ 含于 #2 |
| 7 | CLI | `pytest tests/test_cli.py -q` | 全绿 | ✅ 含于 #2 |
| 8 | visual 页面 | `pytest tests/visual -q` | 需 `127.0.0.1:18806` 预览服务 | ⛔ 3 failed：`ERR_CONNECTION_REFUSED`（环境未起服务，非功能缺陷） |

## 实测结果

- 命令: `cd L4-proprietary/components/bangcle-ppt && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q --ignore=tests/visual -p no:cacheprovider`
- 输出摘要: `249 passed, 1 skipped, 1 warning in 2.33s`；另跑全量得 `3 failed, 249 passed, 1 skipped`（3 例均为 `tests/visual/test_pages.py` 的 `ERR_CONNECTION_REFUSED at http://127.0.0.1:18806/...`）。
- 命令: `node -e "const d=require('./L4-proprietary/skills/bangcle-ppt/src/design-constants.js'); ..."`
- 输出摘要: 导出 `colors/fonts/sizes/pageTypes`；`colors.primary=#2D74BB`、`colors.bg.light=#FFFFFF`、`colors.bg.dark=#00122B`、`colors.text.lightTitle=#2D74BB`。
- 结论: **通过**。功能测试 249 全绿；visual 3 例失败属环境前置（预览服务未启动），已在测试用例 #8 记录为环境性失败，不阻断 skill 验收。

## 遗留与后续

- visual 用例需先启动组件预览服务（端口 18806）再跑；建议补一条 `conftest` 前置检查，服务缺失时 `skip` 而非 `fail`。
- `scripts/test*.cjs`、`build_*.cjs` 为历史调试脚本，未纳入回归；如需复用应迁入组件 `tests/` 并去重。
