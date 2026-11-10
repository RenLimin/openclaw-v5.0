# DESIGN-OUTLINE — customer-delivery-intelligence（客户交付智能流水线）v1.0（待评审）

- 对应 PRD：`PRD-customer-delivery-intelligence-v1.0.md`（已通过 2026-11-10）
- 落层：**L4** `L4-proprietary/components/customer-delivery-intelligence/`
- 状态：**待 Rex 评审** · 2026-11-10

---

## 1. 需求复述

把「客户项目/合同相关事项处理」（如中国建设银行）固化为 L4 参数化流水线：输入仅「客户名 / 周期 / 受众」，经浏览器自动化从 OA、ONES 获取原始文件（数据），综合处理后产出（但不限于）项目汇总、签约项目汇总（含合同条款）、履约义务汇总、验收条件核查表、验收单/交付说明、回款跟踪、汇报材料（md/docx/PPT）。操作方式与输出标准跨客户一致，客户名是唯一主变量。

## 2. 定位：在既有资产矩阵中的位置

L4 综合业务资产，作为 `bangcle-project-manager-expert` 与 `contract-manager-expert` 之外的**第三条业务主链路**（交付→验收→回款闭环），复用既有原子能力，不重造轮子：

```
                     L4  既有专家入口（PJME / 合同专家）
                       │
      ┌────────────────┼───────────────────────────┐
      ▼                ▼                           ▼
project-summary  obligation-summary          contract-manager-expert
(事实台账)        (履约/到期)                  (合同条款/OCR/风险)
      │                │                           │
      └────────► customer-delivery-intelligence ★新增（本资产）
                    │  编排：薄 runner 状态机
                    ├── F2 取数   ← ones-browser-export / clm-oa-recon
                    ├── F6 条款   ← contract-manager-expert / bangcle-contract
                    ├── F7 履约   ← obligation-summary / project-summary
                    ├── F11 汇报  ← bangcle-project-report / bangcle-ppt
                    └── F10 回款  ← bdms-revenue-forecast / revenue-recognition
```

- **数据依赖方向**：本资产只编排与汇总，取数/解析/产出复用手下既有技能；不复制其逻辑。
- **职责边界**：不替代客户签字/审批；不自动发起 OA 流程；不新增 Agent/角色；不建 DAG 引擎。

## 3. 总体架构

### 3.1 分层

```
┌────────────────────────────────────────────────────────────┐
│ L4  入口层   customer-delivery-intelligence SKILL          │
│      参数(客户/周期/受众) → 护栏 → 编排器                    │
├────────────────────────────────────────────────────────────┤
│ L4  编排层  薄 runner（Python 状态机，≈200 行核心）           │
│      节点：取数→齐套闸→解析→汇总→签发闸→渲染                  │
│      状态：SQLite 检查点 + job 表（继承进度条铁律）            │
│      人在环：两道人工闸（HITL），企微通知/回执                 │
├────────────────────────────────────────────────────────────┤
│ L3/L4 复用层  既有原子能力                                   │
│      ones-browser-export / clm-oa-recon（OA）               │
│      contract-manager-expert / bangcle-contract             │
│      obligation-summary / project-summary / customer-profile│
│      bangcle-project-report / bangcle-ppt / bdms-revenue    │
├────────────────────────────────────────────────────────────┤
│ 基础设施   session-recovery(task_tracker) / MCP / job表      │
└────────────────────────────────────────────────────────────┘
```

### 3.2 模块划分

| 模块 | 职责 | 关键接口 | 落点 |
|---|---|---|---|
| **M1 入口与护栏** | 参数校验（客户/周期/受众合法性）、启动任务、写检查点 | `start(customer, period, audience)` → task_id | 薄 runner 入口 |
| **M2 取数编排器** | 并行派发 ONES/OA 取数子任务；汇总文件清单；输出完整性证据（分页触顶+快照时间） | `collect(task_id)` → file_manifest | 编排器核心 |
| **M3 齐套校验闸（HITL 1）** | 校验文件齐套（类型/非空/来源）；不齐停等人工确认；确认后写检查点 | `verify_manifest()` + 审批回执 | 状态机节点 |
| **M4 解析与抽取** | 调用 contract-manager/bangcle-contract 解析合同条款；OCR 扫描件；结构化输出（schema 校验+重试上限 3） | `parse(contract)` → 条款 JSON | 复用既有 |
| **M5 汇总与成文** | 生成六类标准产物（schema 契约）；评估器自校验；审计血缘（原始文件→字段→结论） | `compose(parsed)` → 产物集 | 编排器 |
| **M6 签发闸（HITL 2）** | 合同条款/对外稿签发；人工确认后定稿 | `sign(artifacts)` + 审批回执 | 状态机节点 |
| **M7 渲染与交付** | md/docx（python-docx）/PPT（bangcle-ppt）；按受众适配（内部/对外脱敏） | `render(artifacts, audience)` | 复用既有 |
| **M8 状态与恢复** | SQLite 检查点持久化；断点精确恢复（不重跑已取文件）；trace 血缘 | `resume(task_id)` | 基础设施 |
| **M9 产物契约库** | 六类产物 JSON Schema + 黄金基准 + 校验脚本 | `schema/*.json` + `validate()` | 静态资产 |

## 4. 端到端数据流（对应 PRD §4 流程）

```
[输入] 客户名 / 周期 / 受众
   │
   ▼
M1 入口护栏 → 参数校验 + 任务启动
   │
   ▼
M2 取数编排（并行）  ONES分页取全(触顶校验+快照时间) ‖ OA合同台账/流程/附件
   │                  产出 raw JSON + file_manifest + 完整性证据
   ▼
M3 齐套校验闸(HITL1)  文件齐套确认（类型/非空/来源）→ 通过才继续
   │
   ▼
M4 解析与抽取        合同条款结构化(OCR/数字化) + schema校验重试
   │
   ▼
M5 汇总与成文        六类标准产物 + 评估器自校验 + 血缘标注
   │
   ▼
M6 签发闸(HITL2)     合同条款/对外稿签发 → 定稿
   │
   ▼
M7 渲染与交付        md / docx / PPT；受众适配脱敏
   │
   ▼
[输出] 六类产物 + raw + 审计 + 检查点
```

## 5. 六类标准产物（schema 契约要点，详见 PRD §3）

| 产物 | 定位 | 核心字段 |
|---|---|---|
| P1 项目汇总 | 一眼看板 | 项目编号(全局唯一)/客户/名称/类型/合同号/金额/PM/起止/阶段/健康度/验收状态/回款状态 |
| P2 签约项目汇总（含合同条款）★ | 合同级台账、下游唯一事实源 | 合同基本信息/范围/里程碑/验收/付款/质保/IP与数据/违约条款 + 原文摘录(条款号) |
| P3 履约义务汇总 | 义务拆分+确收口径 | 义务编号/描述/可区分性/价格分摊/确认方式(时段vs时点)/验收关联/已确认与剩余金额 |
| P4 验收条件核查表 | 验收翻译成可勾验清单 | 核查项编号/条款引用+原文/内容/判定标准(量化)/证据路径/方法/结论(三级)/核查人 |
| P5 验收单/交付说明 | 法律+财务双凭证 | 单据头/双方主体/交付物清单(齐套勾选)/结论(合格/需整改/不合格)/依据/签字栏/附件/确收关联 |
| P6 回款跟踪 | 现金流预测 | 回款计划(节点/金额/触发/日期)/验收触发/开票/应收已收未收/账龄/逾期/核销 |

> 五表共用「合同编号 + 条款号」外键；验收结论必须回溯到合同条款原文。验收=财务事件：每验收节点预映射付款比例、确收时点、开票计划。

## 6. 技术选型落地要点（承 PRD §6，薄 runner）

| 关注点 | 落地方式 |
|---|---|
| 编排 | 步骤=「纯函数 + 状态字典」接口；SQLite 检查点（thread_id=task_id）；预留 Temporal 适配面 |
| 浏览器 | Playwright 确定性主路径（session 持久化/下载拦截/截图取证）+ Playwright MCP 决策 + browser-use 兜底 |
| 解析 | Docling（PDF/DOCX→结构化）+ MarkItDown（Word 快路径）+ 既有 OCR |
| 人在环 | 两道闸走现有 Agent 审批流（job 状态 + 企微通知/回执），可跨天，从断点精确恢复 |
| 校验 | Pydantic/JSON Schema 契约 + 节点出口独立校验 + 失败回喂重试（上限 3）+ 升级人工 |
| 护栏 | 入口合法性自动护栏 + 交付前 PII/越权自动护栏（与人工闸分离） |
| 可观测 | 全链路 trace + 血缘（原始文件 URI → 抽取字段 → 结论），满足审计 |
| 成本 | 仅「并行取数 + 合同条款高价值抽取」用子 agent，其余确定性单步（token 15 倍纪律） |

## 7. 目录结构（拟）

```
L4-proprietary/components/customer-delivery-intelligence/
├── SKILL.md                       # L4 入口（意图识别/参数/路由）
├── docs/
│   ├── PRD-customer-delivery-intelligence-v1.0.md
│   ├── DESIGN-OUTLINE-…-v1.0.md   # 本文
│   ├── DESIGN-DETAIL-…-v1.0.md    # 后续
│   ├── VERIFICATION-…-v1.0.md
│   ├── OPERATIONS-…-v1.0.md
│   ├── IMPLEMENTATION-PLAN-…-v1.0.md
│   └── research/                  # 三份调研落盘
├── runner/                        # 薄 runner（Python）
│   ├── main.py                    # 状态机入口
│   ├── steps/                     # 每段=纯函数
│   ├── state.py                   # 检查点持久化
│   └── validate.py                # 产物校验
├── schema/                        # 六类产物 JSON Schema
├── templates/                     # 交付物模板（md/docx）
└── golden/                        # 黄金基准（建行实例产物）
```

## 8. 边界与不做

- 不新增 Agent/角色（复用 PM/合同专家入口）；不建 DAG 引擎（薄 runner 已满足）
- 不替代客户签字/审批（自动产出到「待确认」，签字必须人工）
- 不自动发起 OA 流程（停等人工确认）
- 不把凭据写入任何 markdown；浏览器会话/凭据留自有基础设施
- 不重跑已取文件（断点恢复幂等）

## 9. 验收要点（承 PRD AC，本层补充）

- AC-A：薄 runner 状态机可运行（6 节点 2 闸），检查点可断点恢复
- AC-B：M2 取数完整性自证（分页触顶校验+快照时间戳）落地
- AC-C：六类产物 schema 校验 100% 通过（黄金基准=建行实例）
- AC-D：血缘可验证（任一结论回溯到合同文件+条款号）
- AC-E：两道人工闸生效，闸后从断点精确恢复
- AC-F：换客户（如山东城商行联盟）重跑结构一致

## 10. 里程碑

```
DESIGN-OUTLINE（本文）→ 你审通过
  → DESIGN-DETAIL（接口契约+数据模型+技术方案）
  → VERIFICATION（测试用例+黄金基准）
  → OPERATIONS（安装/启动/故障排查）
  → IMPLEMENTATION-PLAN（Phase 拆分+工时）
  → 建设 → E2E 自测（真实浏览器）→ E2E 人工
首个实例 = 中国建设银行（业务目标 + 黄金基准）
```
