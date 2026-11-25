---
name: customer-rectification-report
description: "客户《项目复盘与整改报告》正式 Word 交付物编制：把客户现场反馈的 N 条问题，编制成固定六章四附件、逐条含整改措施/责任方/时限/验收标准的对外承诺型报告；内置日期一致性、对外脱敏（ONES 剥离）、字体版式、修订残留等 fail-closed 机器门禁，区分内部版/对外版。当用户要针对某客户项目复盘出整改报告/整改承诺/问题整改措施表/对外复盘 Word 正式件时使用。"
user-invocable: true
metadata:
  openclaw:
    layer: L3
    domain: project-management
---

# 客户整改报告（项目复盘与整改报告）技能

> **业务目标**：把客户现场反馈的 N 条问题，产出一份**承诺型**正式 Word《项目复盘与整改报告》——
> N 条 100% 覆盖，每条有整改措施/责任方/时限/验收标准，近期行动日期与明细严格一致，对外版零内部标识，版式字体跨平台一致。

> **边界**：本技能产出**面向客户的正式件**。内部产品差异×PMBOK 复盘用 `bangcle-project-retrospective`；
> 周期性服务汇报 md 用 `bangcle-project-report`；台账/履约取数复用 `bangcle-project-summary`、`bangcle-obligation-summary`。

## When to Use
- 客户现场会后要求提交《项目复盘与整改报告》《整改承诺/方案》《问题整改措施表》正式 Word。
- 需要把客户 N 条问题逐条闭环（措施/责任/时限/验收）并对外发送。
- 需要在内部版基础上生成剥离 ONES 等内部信息的对外版。

## Hard Rules
1. **N 条全覆盖**：客户问题逐条入整改表，四必填（措施/责任方/完成时限/验收标准）非空；编号与客户反馈对应。
2. **日期唯一权威源 = 明细表**：近期行动日期必须由明细窗口推导（最晚完成日 / 最早起算日）；混合到期日拆多行；禁"技术复盘确定/尽快/待定"。
3. **附件2 只讲交付物**：按大版本/小版本/周期专项三类，禁止合同条款号、合同号、§引用、商务数量来源。
4. **双版本 fail-closed**：内部版禁外发；对外版 ONES 号/URL/内部列/工号必须为 0，校验不过禁止交付。
5. **承诺可兑现**：不写无授权日期/人选/数据；ONES deadline 为空不得编造；金额条款以合同原件为准，OCR 非最终依据。
6. **版本不覆盖**：新版本另存，历史稿与用户亲存稿只读；用户在 Word 打开的文件不碰。
7. **对外副作用（发客户）只准备不执行**，由人工发送。
8. **字体显式声明**：含文本 run 必须显式 ascii/hAnsi/eastAsia（宋体/黑体 + Times New Roman），字号仅用规范枚举。

## 编制要求
完整规范见 `references/authoring-standard.md`（V0.1，已经 Limin 审批），设计与取舍见 `DESIGN.md`。

## Workflow
1. **取数**：复用 project-summary / obligation-summary 得合同与履约台账；收集客户 N 条问题（现场会纪要/正式反馈）。
2. **结构化**：按 `assets/report-skeleton.md` 填 report.yaml（meta/contracts/issues/mechanism/phases/actions/deliverables/ab_roles/notify）。
3. **渲染内部版**：`python3 scripts/build_docx.py report.yaml --template <官方Word模板> --out internal.docx`。
4. **机器门禁**：`python3 scripts/validate_report.py internal.docx --n <N>`，exit≠0 修正重跑（G1–G7、G9）。
5. **评审/接受修订**：内部评审在 Word 修订；定稿用脚本接受全部修订得干净基线，再过 G7。
6. **人眼复核 G10**：两张宽表、附件2、附件4、落款逐页截图归档。
7. **审批**：交 Limin/负责人审批。
8. **对外版**：`--external` 渲染/脱敏 → validate 加 `--external` 强制 G8 → 人工发送。

## 机器门禁（validate_report.py）
G1 版面无越界/落款同页；G2 N条+四必填+时限白名单+禁词；G3 行动-明细日期一致；G4 附件2三类且无合同来源；
G5 字体字号合规；G6 称谓（甲方/附录=0、全称在）；G7 修订残留=0；G8 对外脱敏（仅 --external）；G9 页眉页脚页码。
docx 静态项（G2–G9）离线可跑；G1 越界需 PDF（用 Word 导出或 `--pdf` 传入）。

## 相关技能
`bangcle-project-summary`（台账）、`bangcle-obligation-summary`（履约义务）、`bangcle-project-retrospective`（内部复盘）、
`bangcle-project-report`（周期汇报）、`bangcle-project-manager-expert`（L4 统一入口）。

## 验证
- [ ] N 条问题全覆盖、四必填非空、时限命中白名单
- [ ] 近期行动日期可由明细推导且一致，混合到期已拆行
- [ ] 附件2 三类齐全、无合同号/条款/来源依据
- [ ] 字体仅宋体/黑体、字号在枚举、无越界
- [ ] 对外版 ONES/URL/内部列/工号 = 0
- [ ] 修订残留 0、页眉页脚页码齐全、关键页人眼复核
- [ ] `validate_report.py` exit=0
