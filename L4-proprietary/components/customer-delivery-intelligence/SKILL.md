---
name: customer-delivery-intelligence
description: "Bangcle 客户交付智能流水线（L4）：输入客户名/周期/受众，经已建成的 OA、ONES 浏览器自动化直接获取原始文件，综合产出项目汇总、签约项目汇总（含合同条款）、履约义务汇总、验收条件核查表、验收单/交付说明、回款跟踪及汇报材料。当用户要求按客户汇总项目/合同条款、推进验收与回款、生成客户交付汇报包时使用。"
user-invocable: true
metadata:
  openclaw:
    layer: L4
    owner: PM / 交付
---

# 客户交付智能流水线（customer-delivery-intelligence）

## 触发条件
- 「汇总某客户全部项目 / 合同 / 合同条款」
- 「某客户验收与回款推进 / 验收条件核查」
- 「生成客户交付汇报包（对内/对外）」

## 输入（三元组）
- `customer`：客户官方名（唯一主变量）
- `period`：`{start, end}`
- `audience`：`internal` / `external`
- 可选 `scope`：`{liveExport, extraContractNos, onlyProjects}`

## 运行
```bash
python3 -m runner.main start --customer "<客户官方名>" \
  --period-start YYYY-MM-DD --period-end YYYY-MM-DD --audience internal
# 两道人工闸：
python3 -m runner.main decide <task_id> --gate gate1 --decision approve
python3 -m runner.main decide <task_id> --gate gate2 --decision approve
# 中断恢复：
python3 -m runner.main resume <task_id>
python3 -m runner.main status <task_id>
```

## 流水线（确定性 workflow + 两道 HITL）
```
N1 入口护栏
N2 取数（直接调用既有 OA/ONES 自动化；默认复用其原始产出，scope.liveExport=true 现场重导）
[gate1 文件齐套确认 · HITL]
N4 解析（条款事实源=OA 台账/合同原文，复用 contract-manager）
N5 汇总成文（六类产物 + 数字一致性自校验，fail-closed）
[gate2 对外稿签发 · HITL]
N7 渲染交付（Markdown + PPTX + DOCX，均复用既有引擎）
```

## 六类标准产物
1. 项目汇总（ProjectRegister）
2. 签约项目汇总（含合同条款）★核心事实源（ContractRegister）
3. 履约义务汇总（PerformanceObligation）
4. 验收条件核查表（AcceptanceChecklist）
5. 验收单/交付说明（AcceptanceReport，签字必须人工）
6. 回款跟踪（PaymentTracker）

## 铁律
- **数据来源**：原始数据一律直接来自 OA、ONES（见 `docs/DESIGN-DETAIL §11`）。禁止二手汇总/历史产物倒推/经验值。
- **不重复建设**：OA/ONES 浏览器自动化已完整建成（delivery-center / ones-browser-export / clm-oa-recon），本技能只做上层编排与汇总。
- **对外副作用**：OA 流程发起、邮件、发送一律停等人工。
- **不替客户签字**：验收单/交付说明仅产出草稿。
- **断点恢复**：从检查点精确恢复，不重跑已取文件。

## 首个实例 / 黄金基准
- 中国建设银行（14 合同，净额 5,621,800 元）
- 基准：`golden/ccb-2026/v1.0/`

## 输出格式
- **Markdown**：六类产物各一份（本组件渲染）
- **PPTX**：复用既有 L4 `bangcle-ppt` 引擎，Bangcle VI 模板（封面/目录/章节/KPI/明细表/结束）
- **DOCX**：复用既有 L2 `office-generation` Word 引擎，微软雅黑

### 增强 Bangcle 模板（2026-11-10）
- 修复 `bangcle-ppt` 表格页宽度 bug：`content_right`（右边界 x=12.33）被误当右边距，
  导致表框仅 0.44in；改为 `content_right - content_left`（11.57in）。
- PPT 布局用真实已装字体（Arial Unicode，字宽偏保守）经 fontTools hmtx 机器核算：
  全部表格单元格 ≤2 行、0 overflow（本机未装思源/雅黑，已规避字体替换假象）。
- 注：渲染器其余 5 处 `content_right` 同类误用本次未改（当前流水线只用 table 页），留待后续。

## 文档
`docs/`：PRD / DESIGN-OUTLINE / DESIGN-DETAIL / VERIFICATION / OPERATIONS / IMPLEMENTATION-PLAN + `research/`（三份业界调研）。
