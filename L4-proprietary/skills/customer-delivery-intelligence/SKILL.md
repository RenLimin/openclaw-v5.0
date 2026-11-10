---
name: customer-delivery-intelligence
description: "Bangcle 客户交付智能工作流（L4）统一入口：输入客户官方名/周期/受众，工作流确定性地经已建成的 OA、ONES 自动化直接取原始文件，强制两道人工闸，产出项目汇总、签约项目汇总（含合同条款）、履约义务汇总、验收条件核查表、验收单草稿、回款跟踪，并渲染 Markdown+PPTX+DOCX 交付包。当用户要求按客户汇总项目/合同条款、推进验收与回款、生成客户交付汇报包时使用。确收预算预测、合同审批、产品/PPT 单独制作不属于本入口。"
user-invocable: true
metadata:
  openclaw:
    emoji: "🚚"
    os: ["darwin", "linux"]
    layer: L4
    component_id: CDI-001
    requires:
      components:
        - "delivery-center (L4, OA/ONES collector)"
        - "bangcle-ppt (L4, PPTX)"
        - "office-generation (L2, DOCX)"
---

# 客户交付智能工作流（customer-delivery-intelligence）

> **定位：这是一个工作流（workflow），本 SKILL 只是它的路由入口。**
> 流程拓扑、强制闸、fail-closed 校验的唯一权威是组件 `runner/` 代码；
> 本文件只回答「什么时候用、给什么参数、怎么启动」，不复述可被自由发挥的流程细节。

## When to Use

- 「汇总某客户全部项目 / 合同 / 合同条款」
- 「推进某客户验收与回款 / 验收条件核查」
- 「生成某客户交付汇报包（对内 internal / 对外 external）」

## 边界外（不属于本入口）

| 需求 | 去向 |
|---|---|
| 全公司确收预算 / 收入预估 | `bdms-revenue-forecast`（RF-001） |
| 合同审查 / 销售合同审批 | `contract-manager-expert`（CME-001） |
| 单独做 PPT | `bangcle-ppt`（CPT-012） |
| 单独取 ONES 原始数据 | `ones-browser-export` |

## 输入三元组

| 参数 | 必填 | 说明 |
|---|---|---|
| `customer` | ✅ | 客户**官方全名**（唯一主变量，用于精确匹配 OA/ONES） |
| `period` | ✅ | `{start, end}`，`YYYY-MM-DD` |
| `audience` | ✅ | `internal` / `external`（external 过闸2 更严，需脱敏） |
| `scope.liveExport` | 可选 | `true`=现场重跑浏览器导出（慢）；默认复用已导出原始文件 |
| `scope.extraContractNos` | 可选 | 追加台账未挂客户名的合同号 |

## 调用工作流

工作目录：`L4-proprietary/components/customer-delivery-intelligence`

```bash
# 启动（返回 task_id）
python3 -m runner.main start --customer "<客户官方全名>" \
  --period-start YYYY-MM-DD --period-end YYYY-MM-DD --audience internal

# 工作流会在两道闸口暂停，必须人工决策（不会自动跑完）：
python3 -m runner.main decide <task_id> --gate gate1 --decision approve
python3 -m runner.main decide <task_id> --gate gate2 --decision approve
```

辅助：`status <task_id>` 看卡在哪 · `resume <task_id>` 断点恢复 · `tasks` 列全部。

产物：`storage/artifacts/<task_id>/` = 6 份 Markdown + `*-项目交付汇报.pptx` + `*-项目交付说明.docx`。

## 红线（由工作流代码强制，非模型自觉）

- 原始数据**只**来自 OA、ONES；sourceUri 覆盖率必须 100%，否则失败。
- 不重写 OA/ONES 自动化——只调用既有 collector。
- 数字一致性 fail-closed；对外副作用（OA 流程/邮件/发送）与客户签字一律停等人工。

## 黄金基准

- 中国建设银行（14 合同，净额 5,621,800 元）：组件 `golden/ccb-2026/v1.0/`
