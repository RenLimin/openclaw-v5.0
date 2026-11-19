# DESIGN-OUTLINE — OA 销售合同审批：触发 + 编排 + 标准审批备注 v1.0（待评审）

> 元信息：本文档由 Jerry 于 2026-11-19 生成；应答契约版本 ADR-035 P1 v1.2 / P2 contract-answer-spec；归属 Bangcle 合同管理域（L4 CME-001）；数据基准 2026-11-19。
>
> 【已验证 2026-11-19｜oa_todo_dist.py 实跑 + 单据 886377 raw 只读 + 附件下载探针】本设计所有结论均可复现。

## 0. 溯源链

```
数据源 A：oa_todo_dist.py 源码（TARGETS 登记 757）+ 2026-11-19 实跑输出（313 条）
   → 结论：§2.1 可复用待办发现逻辑；§1 口径
数据源 B：tmp/oa-pif/raw/886377/{xhrs.json,body.txt}
   → 结论：§2.2 单据字段映射；§2.3 合同原文不可读实证
数据源 C：CubeClient.download_attachment 探针（fileid 225493）
   → 结论：返回 HTML「对不起，您暂时没有权限！」→ §2.3 硬约束
数据源 D：services/oa/enhance/*（runner/verdict/oa_form）+ cli/contractctl.py
   → 结论：§2.1 既有能力；§3 增量落点
```

## 1. 需求复述（一句话）

Rex 说「处理OA销售合同审批」→ 自动发现 757 待办、逐张读单据、跑 R1/R2 + 固定核查项，输出**标准审批备注**（可贴 OA）；全程只读，写操作人工闸。

## 2. 真实代码盘点（实证）

### 2.1 已具备、可直接复用

| 能力 | 位置 | 复用方式 |
|---|---|---|
| 待办全量发现（列表口径） | `ones-browser-export/scripts/oa_todo_dist.py` | 抽 `discover_todos(workflowid)` 到 L4 `services/oa/enhance/todo.py`（自包含，不跨层 import skill） |
| 单据捕获 | `oa_workflow_ones.py --capture` | CLI 调用（subprocess），raw 落 `tmp/oa-pif/raw` |
| R1 履约义务 | `enhance/ones_obigation.py` + `runner.run_enhance` | 直接调用 |
| R2 概算 | `enhance/estimate.py` | 直接调用 |
| 备注渲染 | `enhance/verdict.py`（纯函数模式） | 仿写 `remark.py` 纯函数 |
| 报告串联 | `contract_review/report.py enhance_section` | 复用（可选） |

### 2.2 缺口（本设计要补）

| # | 缺口 | 落点 |
|---|---|---|
| G1 | 无 757 待办发现（L4 自包含） | `services/oa/enhance/todo.py` |
| G2 | 无固定核查项 | `services/oa/enhance/checks.py` |
| G3 | 无标准备注渲染 | `services/oa/enhance/remark.py` |
| G4 | 无一条链编排 | `services/oa/enhance/orchestrator.py` |
| G5 | 无 CLI 入口 | `cli/contractctl.py` 新增 `oa-approval` |
| G6 | 无触发词 | `contract-manager-expert/SKILL.md` 路由表 |

### 2.3 硬约束（实测）

- 757 单据合同附件 **REST 下载无权限**（`FileDownload?fileid=225493` → HTML 无权限页）。
- 886377 的 docx 是**人工上传**（`review` 报告头 `来源=upload`）。
- → 固定核查项 L2（原文层）**仅在调用方提供原文时**判定，否则 fail-closed 转人工。

## 3. 目标架构（增量，不动既有）

```
触发词「处理OA销售合同审批」（CME SKILL 路由表）
   ↓
contractctl oa-approval [--contract-no <编号>] [--raw-dir <dir>] [--contract-file <docx>]
   ↓
orchestrator.run_approval()
   ├─ todo.discover_todos("757")            → 待办 requestid 列表（0 条→输出无待办）
   ├─ 逐张：oa_workflow_ones --capture rid   → tmp/oa-pif/raw/<rid>/
   ├─ runner.run_enhance(rid, raw_dir)      → R1/R2（既有）
   ├─ checks.run_fixed_checks(form, body, contract_text)  → 固定核查项（L1/L2 分层）
   ├─ remark.render_remark(form, checks, r1, r2)          → 标准审批备注
   └─ 汇总：每张备注 + 报告路径；写操作提示人工
```

**兼容**：`oa-enhance` / `review` 语义**零改动**；新增 `oa-approval` 为纯增量。

## 4. 模块划分

| 模块 | 职责 | 依赖 |
|---|---|---|
| `enhance/todo.py` | 757 待办发现（Playwright + storage_state） | `services/oa` 会话 |
| `enhance/checks.py` | 固定核查项（L1 表单 / L2 原文，fail-closed） | `oa_form.OrderForm`、`body.txt`、可选 `contract_text` |
| `enhance/remark.py` | 标准备注渲染（纯函数） | form/checks/r1/r2 |
| `enhance/orchestrator.py` | 一条链编排 + 汇总 | 上述全部 |
| `cli/contractctl.py` | `oa-approval` 子命令 | orchestrator |
| `SKILL.md` | 触发词 + 编排说明 | — |

## 5. 关键设计决策（建议）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 待办发现**复制** `oa_todo_dist` 逻辑到 L4，不 import skill | 分层红线（L4→L3/L2 单向；skill 脚本非稳定 API） |
| D2 | 合同原文**不自动取**，改为可选入参 `--contract-file` | 实测无权限；fail-closed 优于伪造 |
| D3 | 备注结论 = 「退回项是否存在」 | 与 v3 §七 一致；R1/R2 降级不改变退回项逻辑 |
| D4 | L1 表单核查项**始终**判定（不依赖原文） | 合同编号/服务期在 `body.txt` 可读 |
| D5 | 0 条待办 → 输出「无待办」而非报错 | 实测 757 列表口径 0 条 |

## 6. Phase 拆分（建议）

| Phase | 内容 | 产出 |
|---|---|---|
| P1 | `todo.py` + `checks.py` | 单测（真实 886377 raw） |
| P2 | `remark.py` + `orchestrator.py` + CLI | 端到端 886377 |
| P3 | SKILL 触发词 + 文档 | 门禁 + 回归 |

## 7. 红线

- 全程只读；OA 写操作人工闸。
- 无原文不伪造 L2 判定。
- 既有 `oa-enhance`/`review` 零破坏。
- 提交用隔离 index，排除并行会话资产。

## 7b. 质量信号

- 757 待办为**列表口径**；与树口径不一致属正常。
- 备注结论绑定 requestid + 读取时间。
- ⚠️ OA 在审单据字段会随后续退回变化（数据源为查询时点快照，可能过期）。

## 8. Rex 拍板（2026-11-19）

- ① 备注格式：按草案（§N4）。
- ② 取数范围：仅「销售合同审核流程」= **workflowid 757**（文档已明确）。
- ③ 退回项来源：R1/R2 + 固定核查项**都包含**，后续逐渐优化。
