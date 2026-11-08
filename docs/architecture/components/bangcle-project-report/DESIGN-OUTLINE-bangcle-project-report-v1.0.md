# DESIGN-OUTLINE — Bangcle 项目汇报材料生成技能 v1.0（待评审）

- 对应 PRD：`PRD-bangcle-project-report-v1.0.md`
- 落层：**L3** `L3-business/skills/bangcle-project-report/`
- 状态：**待 Rex 评审** · 2026-11-08

---

## 1. 需求复述

把建行年度汇报实战的取数与成文做法，固化为 L3 可复用技能：输入「客户 + 周期 + 受众」，经"完整取数 → 口径清洗 → 多维汇总 → 目标闭环 → 溯源审计 → 受众适配"，产出数字可点账、结论可溯源的项目汇报材料。

## 2. 定位：在既有 PM 技能矩阵中的位置

L4 专家 `bangcle-project-manager-expert` 统一路由，下挂 L3 专项能力。本技能是其中**面向"汇报成文"**的新能力：

```
                 L4  bangcle-project-manager-expert (PJME-001)  统一路由/协调
                                      │
   ┌───────────────┬───────────────┬──┴───────────────┬──────────────────┐
   ▼               ▼               ▼                  ▼                  ▼
project-summary obligation-summary retrospective customer-profile   project-report ★新增
 (事实台账)       (履约/到期)      (复盘改进)         (客户/需求画像)    (汇报材料成文)
   │                                                              │
   └────────── 台账/取数方法  ──────────────►  复用，不重造 ◄───────┘
```

- **数据依赖方向**：`project-report` 复用 `project-summary` 的台账与 ONES 取数参考；`product-kb` 提供标准产品基线。
- **职责不重叠**：复盘诊断、履约到期、客户画像分别归各自技能（PRD N2–N4）。

## 3. 数据流（端到端管线）

```
[输入] 客户 / 周期 / 受众
   │
   ▼
S1 范围界定   合同+项目枚举；服务期/未验收规则；输出范围清单+排除理由
   │
   ▼
S2 完整取数   逐项目分页拉全(校验触顶) + Project合同编号字段(CAaTom7U)
   │           产出 raw JSON + 快照时间 + 完整性证据
   ▼
S3 口径清洗   剔除履约义务/建档记录；时间戳归一(μ/ms/s)；按createTime卡周期
   │           实际工作5分类：定制/缺陷/工单/产研/专项
   ▼
S4 汇总与明细 三维汇总(类别/产品/周期) + 时间排序逐条明细(可反推)
   │
   ▼
S5 目标闭环   维保类←服务事项；采购新建类←部署/授权交付记录；目标实现状态
   │           在途事项→进展+方案
   ▼
S6 价值论述   基于事实的推断(可配置保留/降级)
   │
   ▼
S7 溯源审计   机器核对数字/名词/日期命中 → 无源项清单(fail-closed, exit≠0即返工)
   │
   ▼
S8 受众适配   内部/对外；对外脱敏系统名编号/商务条款；名称取官方名
   │
   ▼
[输出] 汇报MD + raw JSON + 审计结果；可选 docx（PPT 走 bangcle-ppt）
```

## 4. 输出文档章节模型（模板，可按受众裁剪）

| 章 | 内容 | 数据来源 |
|---|---|---|
| 一、服务概览 | 三维汇总（类别/产品方向/周期）+ 口径说明 | S3/S4 |
| 二、涉及合同清单 | 合同编号 / 官方合同名 / 服务期 | S1 + 合同台账 |
|三、交付明细 | 时间排序、逐条：日期/合同/产品方向/工作类别/事项/状态 | S4 |
| 四、在推进事项与方案 | 在途归并：方向/进展/处理安排 | S5 |
| 五、交付价值与目标实现 | 目标支撑 + **目标实现状态**；整体建设增强（推断标注） | S5/S6 |
| 六、关键节点 | 周期内里程碑 | S4 |
| 七、后续安排 | 与在途事项呼应 | S5 |

> 对外版隐藏内部口径/系统名；对内版可附溯源链与对账附录。

## 5. 技能目录结构（拟）

```
L3-business/skills/bangcle-project-report/
├── SKILL.md                       # 触发/硬规则/工作流 S1-S8/验证
├── references/
│   ├── data-pipeline.md           # 取数分页/触顶/合同字段/时间戳归一细则
│   ├── audience-redaction.md      # 内部vs对外：脱敏词表、官方名规则
│   └── goal-realization-matrix.md # 目标实现状态映射规则与受限词表
├── scripts/
│   ├── fetch_project_tasks.py     # 逐项目分页取全+触顶校验(S2)
│   ├── normalize_and_classify.py  # 时间戳归一/口径分类/周期切分(S3)
│   ├── aggregate.py               # 三维汇总+可反推校验(S4)
│   └── audit_provenance.py        # 溯源审计 fail-closed(S7)
└── assets/
    ├── report-template-internal.md
    └── report-template-external.md
```

- 确定性逻辑入 `scripts/`，分支细则入 `references/`，模板入 `assets/`，与 skill-creator 规范一致。
- 脚本优先**复用/薄封装** `bangcle-project-summary`、`ones-browser-export` 既有能力，避免复制数据访问代码。

## 6. 关键技术决策

- **D1 取数完整性**：禁用单次全局 `name_match` 作为最终口径；改为逐项目枚举 + 分页 + 触顶断言（本次漏数根因）。
- **D2 合同编号取 Project 实体**：`Project._7KF6tXvk`（uuid `CAaTom7U`），并实时拉取，不靠本地快照。
- **D3 单一事实源 = 明细行**：所有汇总数由明细行反推，禁止并行第二套计数器。
- **D4 两类目标凭证**：维保类挂服务事项、采购新建类挂部署/授权履约完成记录；解决"目标看似未实现"。
- **D5 溯源 fail-closed**：审计 exit≠0 不得交付；价值论述与事实在文档中视觉区分。
- **D6 受众适配为显式开关**：脱敏在成文最后一步强制执行，对外版 `grep` 必为 0。

## 7. 与既定规则/契约的对齐

- 遵循开发流程铁律：PRD→OUTLINE（本阶段）→DETAIL→测试→手册→计划→建设→自测→人工验收。
- 应答契约：P1 `L2-infra/prompts/answer-spec-base.md` + P2 `prompts/project-answer-spec.md`；
  落盘后跑 `L2-infra/prompts/tools/check_answer_contract.py`。
- 证据三档【已验证/推断/缺失】；对外不泄露内部系统与 MEMORY。

## 8. Phase 拆分（建议，评审通过后细化进 IMPLEMENTATION-PLAN）

| Phase | 内容 | 产出 |
|---|---|---|
| P1 | 取数与完整性（S1-S2） | fetch 脚本 + 完整性证据，复用 summary |
| P2 | 清洗/分类/汇总/明细（S3-S4） | normalize + aggregate + 可反推校验 |
| P3 | 目标闭环 + 在途 + 价值（S5-S6） | 目标矩阵 + 模板 |
| P4 | 溯源审计 + 受众适配（S7-S8） | audit 脚本 + 脱敏词表 |
| P5 | SKILL 装配 + E2E（以建行为黄金基准回放） | 技能目录 + 测试 + OPERATIONS |

## 9. 红线

1. 未完成设计评审不得写技能文件（SKILL.md 等）。
2. 不得复制/重造数据底座；取数必复用既有。
3. 溯源审计未 PASS 不得宣称完成。
4. 对外版零内部系统名/编号/商务条款；名称必取官方名。
5. 不触发任何对外发送副作用。

## 10. 待 Rex 拍板

- Q1 技能名 `bangcle-project-report` 是否采纳？
- Q2 落层 **L3**、由 L4 PJME-001 路由，是否认可？
- Q3 章节模型（§4）7 章结构是否作为标准模板？
- Q4 黄金基准是否就用本次建行材料回放（数字应复现 113/104/9）？
- Q5 docx 导出是否纳入 v1.0（PPT 明确走 bangcle-ppt）？
