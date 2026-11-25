# report.yaml 内容骨架（六章四附件）

```yaml
meta:
  client_full: "山东省城市商业银行合作联盟有限公司"   # 客户全称
  vendor_full: "北京梆梆安全科技有限公司"            # 我方全称
  title: "项目复盘与整改报告"
  subtitle: "问题整改 · 服务承诺 · 实施计划"
  dept: "安服中心"
  date: "2026-11-23"
  version: "V1.0"
  classification: "内部"        # 内部 | 对外
  trigger_meeting: "2026-11-16 现场沟通"
  issue_count: 20

contracts:                     # 第二章背景表
  - {no: "XSZS...", name: "...", amount: 0, period: "..."}
  program_amount: 0            # 合同总额（与原件核对）

issues:                        # 第三章，逐条；group=deliver|tech
  - {id: 1, group: deliver, cat: "", question: "", action: "", owner: "", due: "", acceptance: "", ref: "附件1", ones: ""}
  # due 白名单：已完成 | YYYY-MM-DD | YYYY-MM-DD~YYYY-MM-DD | YYYY-MM-DD 起按日/周跟进 | 跟进中
  # ref 对外版挂附件；ones 仅内部版渲染，对外版整列删除

mechanism: []                  # 第四章要点（项目集统筹/工单应急/SLA/版本变更/质量门禁/计划沟通）
phases:                        # 第五章
  - {stage: "", window: "", focus: ""}
actions:                       # 第六章（due 必须能由 issues 窗口推导）
  - {"no": 1, action: "", owner: "", due: "", issue_refs: [10,11,13]}

deliverables:                  # 附件2，type 必须落在三大类
  - {type: "大版本发布", name: "", requirement: ""}
  - {type: "小版本", name: "", requirement: ""}
  - {type: "周期性", name: "", requirement: ""}

ab_roles:                      # 附件3，禁止待指定
  - {domain: "", a: "", b: "", lead: ""}

notify:                        # 附件4
  - {stage: "", trigger: "", action: "", sla: "", owner: ""}

annex1_fields:                 # 附件1 变更模板字段
  - {field: "", content: ""}
```

## 填写要点
- issues[].action 只写动作；附件引用放 ref，不内联在 action。
- actions[].due 推导：issue_refs 多个时取最晚完成日；起算类取最早起始日+"起"；不同到期日混合必须拆多条 action。
- deliverables 不写合同号/§条款/商务数量；只写"交什么、达到什么要求"。
- 客户指代"贵司"、自称"我司"；部门用规范名；禁词见 style-spec.banned_terms。
