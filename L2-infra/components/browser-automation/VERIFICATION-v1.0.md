# browser-automation — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20

## 验收标准（Definition of Done）

1. 如实记录组件定位（空占位 vs 真实能力），不虚构架构。
2. 指向真实浏览器能力入口（注册表条目 + 既有组件）。
3. 组件存在根级 DESIGN.md 与 VERIFICATION.md，完成生命周期闭环。

## 测试范围

- 目录状态核查（空占位确认）
- 注册表交叉引用（真实能力入口定位）

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 目录内容核查 | `ls browser-automation/` | 空占位（无代码） | ✅ 仅 DESIGN.md/VERIFICATION.md，无虚构代码 |
| TC02 | 真实入口定位 | 注册表 `--query browser` | 指向真实能力 | ✅ browser-isolated-chrome + delivery-center collectors + bdms BrowserAdapter |
| TC03 | 设计文档存在 | 根级 `DESIGN.md` | 存在 | ✅ 131 行（2026-11-20 补写） |
| TC04 | 生命周期闭环 | `--lifecycle` | 不再列入缺设计/缺验收 | ✅ 本文件补齐后出列 |

## 实测结果

- 命令: `ls L2-infra/components/browser-automation/` + `capability_registry.py --query browser`
- 输出摘要: 目录为空占位（0 代码文件）；真实浏览器能力登记在 registry 条目 `browser-isolated-chrome`（隔离 Chrome/CDP）与 L4 delivery-center collectors、bdms browser_adapter.py
- 结论: **通过（占位定位）**——本组件如实标记为占位目录，不承载代码；真实能力以注册表 entry 为准，避免后续会话重复建设浏览器自动化
