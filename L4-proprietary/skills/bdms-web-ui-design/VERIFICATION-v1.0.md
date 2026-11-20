# bdms-web-ui-design — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 是**前端设计最佳实践沉淀文档**（无脚本、无实现代码、无测试）。
> 内容为 BDMS Web UI 设计规范与既有开发约定，验收以「内容自洽 + 与实际实现一致」为准。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 内容自洽 | 文档结构完整（原则/UX-UI/已对齐规范/本次改动） |
| 2 | 与 L2 共享组件库口径一致 | 声明复用 `web-common/macros/components.html`，不自定义弹窗/Toast/Modal |
| 3 | 单一来源原则 | 月份选择仅左侧栏一个入口 |
| 4 | 动效参数可执行 | 150–400ms、ease-out 入场 / ease-in 出场 |
| 5 | 无编造实现 | 文档未声称存在未落地的组件/脚本 |

## 测试范围

- skill 自身：`SKILL.md`（1977 字节），无 `scripts/`、无 `tests/`。
- 相关实现：`L4-proprietary/components/bdms`（本 skill 是经验沉淀，不直接测其代码）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | 文档存在与结构 | 读 `SKILL.md` | 四节齐全 | ✅ 技能目标 / 最佳实践 / 已对齐规范 / 本次改动 |
| 2 | 组件库引用路径 | 查 `web-common/macros/components.html` 引用 | 路径存在 | ⛔ 本次未逐层定位：BDMS Web 具体前端目录未在本 skill 中给出绝对路径 |
| 3 | 自动化测试 | `pytest tests` | — | ⛔ 无 `tests/` 目录：**无自动化测试** |

## 实测结果

- 命令: `ls -la L4-proprietary/skills/bdms-web-ui-design/ && find ... -type f`
- 输出摘要: 目录仅含 `SKILL.md` 一个文件（1977 字节）；`find` 未发现 `scripts/`、`tests/`、`references/`。
- 结论: **通过（文档完整性验收）**。文档结构自洽，设计规范条目可执行；属沉淀类 skill，无代码与自动化测试为合理状态。

## 可复现手动验证步骤（无自动化测试）

1. 通读 `SKILL.md`，确认四条最佳实践与三条已对齐规范无自相矛盾；
2. 在 BDMS Web 前端核对月份选择入口唯一（左侧栏），无第二处入口；
3. 核对所有弹窗/Toast/Modal 均引用 L2 `web-common/macros/components.html`，无原生 `alert()`/`confirm()` 残留；
4. 核对动效时长落在 150–400ms，同页无多路并发动画。

## 遗留与后续

- 文档未给出所沉淀的 BDMS 前端绝对路径；建议补一行「适用实现位置」，便于后续回归定位。
- 若该 skill 后续承接具体改造，应在组件侧补 `tests/` 而非在 skill 目录堆脚本。
