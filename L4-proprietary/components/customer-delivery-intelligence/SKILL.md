---
name: customer-delivery-intelligence
description: "Bangcle 客户交付智能【工作流】（L4）：确定性状态机编排已建成的 OA/ONES 自动化取数，强制两道人工闸，产出六类标准产物并渲染 Markdown+PPTX+DOCX。组件本地说明；自然语言路由入口见 L4 全局 skill。"
metadata:
  openclaw:
    layer: L4
    kind: workflow
    component_id: CDI-001
    owner: PM / 交付
---

# 客户交付智能工作流（CDI）

> **定位：L4 工作流（workflow），不是程序性 SKILL。**
>
> - **流程本体（唯一权威）= `runner/` 代码**：固定拓扑、强制 HITL、fail-closed、检查点恢复。
> - **自然语言入口 = 全局薄 skill**：`L4-proprietary/skills/customer-delivery-intelligence/SKILL.md`
>   （只做意图识别与参数归一，不含可自由发挥的流程细节）。
> - 两处不重复维护：拓扑/闸/校验以代码为准，本文件只描述契约与产物。

## 为什么是工作流而非 SKILL

| 必须被系统强制的约束 | 承载方式 |
|---|---|
| 固定拓扑 N1→N7 | runner 状态机硬编码 |
| 两道 HITL，不 approve 走不过去 | gate 状态 + 决策事件 |
| 数字一致性 / sourceUri 100% | fail-closed 校验 |
| 多实例、幂等、断点精确恢复 | SQLite 检查点 |

SKILL 只给"建议"，模型可跳步/换序/倒推；这些合规约束必须由代码强制，故本体是工作流。

## 拓扑

```
N1 入口护栏
N2 取数（调用既有 OA/ONES collector；默认复用其原始产出，scope.liveExport=true 现场重导）
[gate1 文件齐套确认 · HITL]
N4 解析（条款事实源=OA 台账/合同原文）
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

## 输出格式

- **Markdown**：六类产物各一份（本组件 render_md）
- **PPTX**：复用 L4 `bangcle-ppt` 引擎，Bangcle VI 模板
- **DOCX**：复用 L2 `office-generation` Word 引擎，微软雅黑

## 铁律（runner 代码强制）

- 原始数据一律直接来自 OA、ONES；禁止二手汇总/历史产物倒推/经验值。
- 不重复建设 OA/ONES 浏览器自动化（delivery-center / ones-browser-export / clm-oa-recon），只做上层编排。
- 对外副作用（OA 流程发起、邮件、发送）与客户签字一律停等人工。
- 断点恢复从检查点精确恢复，不重跑已取文件。

## 首个实例 / 黄金基准

- 中国建设银行（14 合同，净额 5,621,800 元）：`golden/ccb-2026/v1.0/`
