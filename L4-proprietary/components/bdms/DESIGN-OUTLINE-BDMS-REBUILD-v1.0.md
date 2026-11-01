# DESIGN-OUTLINE-BDMS-REBUILD-v1.0.md

> 日期：2026-11-01 ｜ 状态：**待 Rex 拍板** ｜ 基准：原型定稿 commit `1a5934a`
> 范围：仅重建 BDMS 活系统**前端**；后端 API 与数据层**零改动**；原前端资产已归档可回滚

## 1. 背景与目标

Rex 验收通过定稿原型（方形 B 标 / 全中文 4 字导航 / 月报四步工作流 / 侧栏折叠 / 数字右对齐 / 焦点环），要求**按该原型重新建设 BDMS 活系统**，原系统对应资产归档。

## 2. 现状摸底结论（已实测）

### 2.1 后端 API 已全覆盖原型工作流（无需新建）
| 原型工作流 | 现有 API | 状态 |
|---|---|---|
| 月报生成/进度 | `/report/generate` `generate-progress` `months` `sheets` `data/{month}/{sheet}` | ✅ |
| 数据校准 | `/report/calibrations/{month}`(+overview/revoke) `enum-options` `calibration-ledger` | ✅ |
| 问题清单 | `/report/review-issues/{month}` `review-status` `batch-resolve` `resolve` | ✅ |
| 审批历史 | `/report/review-months` `review-approve/{month}` `review-reject/{month}` `revalidate` | ✅ |
| 确收/对比 | `/revenue/summary` `import` `generate` `export` `compare/{month}` | ✅ |
| 基础数据/看板/设定 | `/master-data/*` `/dashboard/*` `/settings` | ✅ |

### 2.2 前端差距（本次重建核心）
| 维度 | 原型 | 现状（web-common v2） | 差距 |
|---|---|---|---|
| 品牌侧栏 | 深藏青 #00122B、方形 B 标 40×40、236px | 白底、logo.png 横版、200px、可拖拽 | **中**（theme-bangcle.css 已存在，需启用+调宽+换 logo） |
| 侧栏折叠 | 236→68、tooltip、localStorage | 200→56、tooltip、localStorage+拖拽 | 低（已具备，仅调数值） |
| 导航 | 4 字中文 + 分组 | sidebar_items 分组已支持中文 | 低 |
| 月报页 IA | 常驻账期条 + 阶段步骤条 + **4 子页签**（导入/校准/问题清单/审批） | 3 个平级 Tab（生成/浏览/问题清单）+ 顶部数据范围卡 | **高**（需重构为 ctxbar+steps+subtabs 工作流） |
| 数字对齐 | 定量数字右对齐 + tabular-nums | 左对齐 | 低（补 CSS） |
| 焦点环 | 品牌色 :focus-visible | 浏览器默认 | 低（补 CSS） |
| 三态 | 加载/空/错误展示 | 已有骨架屏/空态/错误态 | 低 |
| 其余页面 | 确收/对比/基础数据/看板/设定 | 各页已有对应功能 | 中（按原型统一视觉语言） |

## 3. 重建方案（推荐 A）

### 方案 A：模板 + 样式重建（推荐）
- **后端 API 零改动**，仅重写 `src/bdms/web/templates/*` 与 `static/css/style.css`
- 复用 web-common 布局宏（`base_layout` 已含折叠/拖拽/主题/移动端），BDMS 传参启用 `data-theme="bangcle"` + 方形 B 标
- 月报页重构为原型工作流：ctxbar（账期/状态常驻）→ steps 步骤条 → 4 subtabs；**原生成/浏览/校准/审批 JS 逻辑保留复用**，仅重组 DOM 结构
- 数字右对齐/焦点环等增强写进 BDMS 本地 style.css（不污染 web-common 全局）
- 工作量：约 4-6 个模板 + 1 个 CSS；风险低、可回滚（已归档）

### 方案 B：整页替换为原型静态 HTML（不推荐）
- 把原型 HTML 直接转 Jinja 模板，交互全部重写对接 API
- 视觉 100% 一致，但 mock 数据全部要换真实 API 调用，JS 重写量大、回归风险高

### 方案 C：仅换皮肤（不推荐）
- 只改配色/logo/导航，月报页仍保持 3 Tab 旧 IA
- 达不到"按原型重建"的验收要求

## 4. 分页改造清单

| 页面 | 原型基准 | 改造动作 |
|---|---|---|
| base 布局 | 方形 B 标 + 深蓝侧栏 + 4 字导航 | 启用 bangcle 主题、换 favicon 为侧栏标、调宽 236/68、导航项改 4 字 |
| report.html | ctxbar+steps+4 subtab | **重构 IA**：导入/校准/问题清单/审批历史，复用现有 JS |
| revenue.html | KPI 4 卡 + 明细表（金额右对齐） | 视觉统一 + 数字对齐 |
| revenue_compare.html | 3 KPI + 双图表 + 差异表 | 视觉统一 + 数字对齐 |
| master_data.html | 工具栏+枚举表 | 视觉统一 |
| dashboard.html | KPI 4 卡 + 图表 + 分布表 | 视觉统一 + 数字对齐 |
| settings.html | 阈值/集成/三态展示 | 视觉统一 |
| index.html | 功能导航 + 系统状态 | 视觉统一 |

## 5. 关键决策点（请 Rex 拍板）

1. **方案选择**：推荐 A（模板+样式重建，后端零改动）
2. **侧栏宽度**：原型 236/68，web-common 默认 200/56 —— 按原型调 236/68？
3. **月报旧功能保留**：现有"报告生成/数据浏览/问题清单"3 Tab 中，数据浏览(15 sheet 明细)在新 IA 里放哪？建议并入「数据校准」或保留为第 5 个子页签「数据浏览」？
4. **web-common 回改**：宽度/焦点环等是写进 web-common（影响其他应用）还是 BDMS 本地覆盖（推荐本地，零影响他人）？

## 6. 验收标准

- [ ] 活系统页面视觉与原型一致（同屏对比截图）
- [ ] 月报四步工作流：导入→校准→问题清单→审批全链路可用（真实 API）
- [ ] 侧栏折叠/拖拽/主题切换不回归
- [ ] 全站数字列右对齐 + tabular-nums
- [ ] 键盘 Tab 焦点环可见
- [ ] 现有测试全绿（tests/）
- [ ] 回滚可用（backups/pre-rebuild-20261101）

## 7. 实施计划

| Phase | 内容 | 预估 |
|---|---|---|
| P0 | 归档（已完成）+ 本方案拍板 | — |
| P1 | base 布局品牌化（主题/logo/侧栏/导航） | 0.5d |
| P2 | report.html 重构为 4 子页签工作流 | 1d |
| P3 | 其余 6 页视觉统一 + 数字对齐 + 焦点环 | 0.5d |
| P4 | E2E 自测（真实 HTTP）+ 现有测试回归 | 0.5d |
| P5 | 人工验收 + 提交 | 0.5d |
