# P2 验收：report.html 月报工作流重构

## 变更概要

**范围**：仅 `src/bdms/web/templates/report.html`（+ 少量 style.css 已有 token 复用）
**后端**：零改动。API 契约、校验逻辑、DB schema 均不变。
**原则**：复用全部现有 JS 函数与元素 id，平移面板不重写，新增 ctxbar/steps/timeline 只追加不破坏。

## DOM 结构变化

| 位置 | 旧 | 新 |
|---|---|---|
| page_header | 标题 + 副标题（旧）+ 导出按钮 | 标题 + 新副标题「月度交付数据导入、校验与人工审核 · 按阶段推进」 |
| report-page 顶部 | 数据范围卡 + 审核概览 KPI（外层，所有 tab 可见） | ctxbar（sticky 账期条）+ steps（4 步步骤条）→ 子页签 |
| Tab 容器 | 3 tab：generate / browse / issues | 4 tab：import / calibrate / issues / approval |
| Tab 1 (generate→import) | 生成状态卡 + Sheet 明细 | 数据范围卡 + 审核概览 KPI + 生成状态卡 + Sheet 明细（全部平移） |
| Tab 2 (browse→calibrate) | 数据浏览 + 校准台账入口 | 数据校准（全部内容平移 + 台账入口保留） |
| Tab 3 (issues) | 问题清单 | 问题清单（不变） |
| Tab 4 (新增) | — | 审批历史：左审批操作卡 + 右审批记录时间线 |
| 生成状态卡 actions | 审批通过/驳回（无 id，旧 bug：禁用态失效） | 去掉（审批操作已移至 ctxbar + approval panel） |
| 导出按钮位置 | page_header + 生成状态卡各一个（重复） | ctxbar 一个（统一入口） |

## JS 适配

| 函数/位置 | 变化 |
|---|---|
| `tabs:change` 监听 | `browse` → `calibrate`；新增 `approval` → `loadApprovalTimeline()` |
| `initTabFromHash` 白名单 | `generate/browse/issues` → `import/calibrate/issues/approval` |
| `selectMonth` | `activeTab === 'browse'` → `calibrate`；新增 approval 分支 |
| `saveCalibration` | 同 `activeTab === 'browse'` → `calibrate` |
| `loadReviewStatus` 按钮管控 | 单 id 查询 → `data-role="btn-*"` 统一多实例禁用（修旧 bug：原审批按钮无 id，从未正确禁用） |
| `updateCtxbarAndSteps(d)` | 新增：根据 review status 更新 ctxbar 标签、步骤条 done/active 态、按钮禁用态 |
| `loadApprovalTimeline()` | 新增：拉取 review-status，按时间倒序渲染生成/校验/审批通过/驳回节点 |
| `_fmtDate / _statusTagClass / _stepForStatus` | 新增：辅助函数 |
| `switchToTab / switchTab / getActiveTab` | 不变（基于 data-tab click，自动适配新名字） |
| 生成流程全套 (doGenerate/pollGenerateProgress/handle*) | 不变（元素 id 全部保留：status-text/progress-container/btn-revalidate/btn-regenerate/status-card 等） |
| 审批操作 (doApprove/doReject/doRevalidate) | 不变（函数本体未改，按钮 data-role 统一管控禁用） |

## 新增 CSS（内联 <style>，不污染 web-common）

`.ctxbar` / `.ctxbar .seg` / `.ctxbar-divider` / `.ctxbar .spacer`
`.tag .blue/.green/.amber/.red/.gray`
`.steps` / `.step` / `.step .dot` / `.step.done / .step.active` / `.step-line / .step-line.done`
`.timeline` / `.tl-item` / `.tl-item.ok/.gray` / `.tl-item .t / .m`

颜色 token 全部对齐 BDMS 既有变量（`--c-primary / --c-success / --c-danger / --c-warning / --c-muted / --c-border / --c-text / --r-md`），不引入新的 design token。

## 逐子页签验证（Playwright + 真实 HTTP）

| 用例 | 结果 | 证据 |
|---|---|---|
| 页面加载 HTTP 200 | ✅ | curl 200 |
| 初始 tab = import | ✅ | aria-selected + 内容 4 张卡 |
| import：数据范围卡 + 审核概览 + 生成状态 + Sheet 明细 | ✅ | 4 张 card 全在 |
| calibrate：数据加载 50 行 / 7 Sheet 选项 / 台账按钮 | ✅ | table tbody 50 tr，select 7 options |
| calibrate：切换 tab 自动 loadTable | ✅ | 点 tab 后数据即渲染 |
| issues：18 问题 / 17 待处理 / 82 行（含明细展开行） | ✅ | review-issues-stats 文本匹配 |
| approval：时间线 2 节点（导入+校验） | ✅ | .tl-item 数 = 2 |
| KPI 卡点击跳 issues | ✅ | click 后 active=issues |
| 键盘 ArrowRight 切换 tab | ✅ | 按 2 次从 import→calibrate→issues |
| localStorage 记忆 tab | ✅ | tabs.js 原生行为 |
| 侧栏折叠后 tab 仍可切换 | ✅ | 折叠 68px 后 issues 可点 |
| console 错误 | ✅ 0 条 | 全程无 error/pageerror |

## 按钮禁用态联动

旧 bug：生成状态卡的 actions 审批按钮（card macro 渲染的 `<button>`）没有 id，`loadReviewStatus` 里的 `getElementById('btn-approve')` 一直拿不到，按钮从未正确禁用。

修复：统一用 `data-role` 属性 + `querySelectorAll` 管控所有同类按钮（ctxbar + approval panel 各一对审批按钮），状态映射与旧契约一致（validating/reviewing 可审批；not_started/generating 禁用）。

## 遗留 / 需 Rex 拍板

1. **审批时间线只有"生成 + 校验"两个节点**（因当前 review-status 只有 generated_at / validated_at 字段）。`approved_at / rejected_at / reviewer` 字段虽然表里有，但现有数据都是 null——后端审批 API 写完状态有没有写这些时间戳，需后端层面确认。如果需要完整时间线，后续可补：审批通过/驳回时回填 approved_at/rejected_at/reviewer 字段（API 层改 service）。
2. **驳回按钮在 ctxbar 默认隐藏**（无数据时 display:none），只在 validating/reviewing 状态显示。approval panel 里的驳回按钮始终显示但禁用——两边表现略有差异，要不要统一？
3. **import panel 里已去掉"导出 Excel"按钮**（ctxbar 已有），减少重复。如果觉得 import 阶段也该有快捷导出，可再加回来（data-role 已支持多实例）。

## 截图路径

`tmp/qa-rebuild-p2/01-import.png` / `02-calibrate.png` / `03-issues.png` / `04-approval.png`
