---
title: 合同审查智能化增强 PRD — 条款拆解 · 风险点识别 · 历史交付问题盘点
component: bangcle-contract (L4, CME-001)
layer: L4
stage: build
version: v1.0
date: 2026-11-24
author: Jerry
supersedes: []
---

## 0. 背景与问题（实测，非推测）

Rex 2026-11-24 反馈「处理 OA 销售合同审批流程」结果粗糙。侦察结论（证据见 §1）：

| # | 问题 | 根因 | 证据 |
|---|---|---|---|
| P1 | 757 链只做 5 条字段核查，不做全文条款/风险分析 | `oa-approval` 链未接 `ReviewService`（L3 22 条风险 + product-kb 全闲置） | `services/oa/enhance/orchestrator.py` 无 `run_risk`/`parse_contract` 调用 |
| P2 | 3/5 核查项恒「转人工」 | 合同附件 REST 下载无权限（`FileDownload?fileid=` 返回「对不起，您暂时没有权限！」）；`--contract-file` 未提供即 fail-closed | `services/oa/enhance/checks.py` 头注释（实测 2026-11-19） |

> ⚠️ **P2 已于 2026-11-27 修正**（历史记录保留）：上记「REST 下载无权限」为**会话过期误判**——未登录时返回的是登录跳转 HTML，非权限文案。会话有效时 `loadlink` 可直接下载真实附件（实测 4 张单全部成功）。现已由编排层自动取原文，`checks.py` 头注释同步更正。详见 `VERIFICATION-contract-review-intelligence-v1.0.md` §口径修正。
| P3 | 「合同编号缺失」误报 | L1 只认表单标签 `合同编号！`，而合同名常含编号（887756 合同名含 `20261106-01KP`） | `checks.py::run_fixed_checks` L1-a |
| P4 | 757 链未入能力注册表 | `registry.yaml` 的 `bangcle-contract` entry 仅 `--help`/`oa-fetch`/`oa-project-mgmt`，grep `oa-approval` 零命中 | `capability-registry/registry.yaml:382-391` |
| P5 | R1「未知」不透明 | 真因 `project_not_found` 只进 `missing`，备注正文只写「未知」 | `ones_obigation.py::check_obligations` + `remark.py` |
| P6 | 条款拆解能力存在但从未被使用 | L3 `contract_parser` 24 提取器/28 类条款（含法条·原文·摘要·问题·建议）；L4 `ReviewService` 只用 `parse_shallow`，`ReviewReport.clauses` 恒 `[]` | `L3 .../contract_parser.py` vs `contract_review/pipeline.py` step 3 |
| P7 | 风险识别缺「缺失条款」维度 | L3 `risk_engine` 22 条全是「文本中存在性」判断；required 条款整条缺失不会报 | `risk_engine.py::CHECK_RULES` |
| P8 | 履约义务不查历史交付问题 | R1 只读 ONES 实时「项目履约义务」任务状态，从不关联 BDMS 历史异常/验收 | `ones_obigation.py` |

## 1. 调研来源

### 1.1 本地已建成能力（先查表，避免重复建设）
- `capability-registry/registry.yaml`（权威索引）：`bangcle-contract` / `contract-management(L3)` / `product-kb` / `bdms` / `oa-contract-fetch`
- L3 `contract_management`：`contract_parser`（条款）、`risk_engine`（22 条规则+法条）、`state_machine`、`amount_utils`
- L4 `bangcle-contract`：`contract_review/{ingest,digitize,parser,extract_items,risk,kb_match,pipeline,report}`、`services/oa/*`（CubeClient / browser_fallback / ledger / enhance）
- L4 `bdms` 数据：`dr_sheet_row` sheet=`异常项目`(17177) / `签约`(17181) / `验收交接`，字段含 `销售合同编号`/`异常项目-类别`/`项目异常内容`/`合同验收条款`/`项目验收状态`

### 1.2 业界最佳实践（外部检索 2026-11-24，tavily）
| 来源 | 要点 | 本方案采纳 |
|---|---|---|
| ContractEval（arXiv 2508.03080，CUAD 基准，19 个 LLM） | 条款级法律风险识别；开源模型倾向「过度选取」，**精准度优于召回**；必须评估 false "no related clause" | 条款抽取走确定性规则（L3 受控库）为主，LLM 语义轨本期关闭；每条风险必须挂原文证据（防过度选取） |
| eBrevia Clause Extraction | 风险不只看条款「是否存在」，而是「缺失/异常/与标准不一致/与同类合同不同」；每条结果须连回源文供人工验证 | 新增「required 条款缺失」维度（P7）；所有结论带原文片段 |
| LlamaIndex《Contract Clause Extraction》 | 抽取精度取决于三因素：解析质量、条款识别准确度、哪些条款类型承载风险；OCR 质量差会级联漏检 | 复用既有 `digitize`（PDF/docx/OCR），在报告中标注 `ocr_method`/置信度 |
| EMNLP 2022 ConReader | 合同结构复杂，按固定抽取区+关系建模优于纯 plain-text LM | 保留 L3 的类别→提取器映射（结构化处理），不引 plain LM |
| GitHub topic `contract-analysis`（clause-tracer / hermes-legal / LexReviewer 等） | 主流形态 = 条款标注 + 证据回链 + 风险评分 + 修改建议 | 输出结构对齐：条款/证据/风险/建议四元组 |

> 结论：**不引公网 LLM**（数据安全红线：合同原文不外发），走「L3 受控规则 + L4 编排」的确定性路线；语义轨保留接口，默认关。

## 2. 目标（What / Why）

1. **修 P1–P5**：让 757 链可用、可信、可发现。
2. **条款拆解**（需求 2）：`contractctl clauses` 输出结构化条款清单（类别/法条/摘要/原文/问题/建议），并并入合同智能审查报告。
3. **风险点识别**（需求 3）：报告以「风险点」为主视角 —— L3 22 条 + 新增「条款缺失」维度，逐条挂原文证据 + 法条 + 建议。
4. **历史交付问题盘点**（需求 4）：R1 升级为「历史签约项目/合同交付问题盘点」—— 查 BDMS 历史异常/应交未交/应验未验/验收异常，判断是否由合同风险/缺失条款引起。

### 非目标（本期不做）
- 不做 OA 写操作（提交/审批/退回），维持 USER.md#97 拍板。
- 不引公网 LLM 做语义判断（原文不外发红线）。
- 不重写 L3 组件（单向依赖，L4→L3）。

## 3. 方案

### 3.1 分层与复用
```
L4 bangcle-contract
 ├─ contract_review/clause_extract.py   [新] 调 L3 parse_contract → 结构化条款
 ├─ contract_review/risk_points.py      [新] 合并 L3 risk_engine + 条款缺失 → 风险点视图
 ├─ contract_review/report.py           [改] 报告新增「条款拆解」「风险点」两章
 ├─ contract_review/pipeline.py         [改] 接 clause_extract / risk_points，填 clauses
 ├─ services/oa/enhance/history_delivery.py [新] R1b：BDMS 历史交付问题盘点
 ├─ services/oa/enhance/ones_obigation.py  [改] 保留 ONES 实时（R1a），原因显式化
 ├─ services/oa/enhance/orchestrator.py    [改] R1a+R1b 合并 → 备注
 ├─ services/oa/enhance/checks.py          [改] 合同编号回退提取（消误报）
 ├─ services/oa/enhance/remark.py          [改] 风险点/历史交付段落 + 降级原因
 └─ cli/contractctl.py                    [改] 新增 clauses / history-delivery 子命令
```

### 3.2 关键取舍
| 决策 | 选项 | 选择 | 理由 |
|---|---|---|---|
| 条款抽取实现 | A 自研 NLP / B 复用 L3 parser | **B** | L3 已有 24 提取器+法条，自研=重复建设（违反铁律） |
| 语义风险 | A 上 LLM / B 确定性规则 + 人工闸 | **B** | 原文不外发红线；ContractEval 显示确定性证据链更适法务复核 |
| 历史数据源 | A 重新采集 / B BDMS 现有快照 | **B** | `dr_sheet_row` 已有 17k+ 行带合同编号，无需新采集 |
| 合同编号判定 | A 仅表单 / B 表单→合同名→正文 回退 | **B** | 消除 P3 误报；回退命中须在 evidence 注明来源 |
| 条款缺失是否算风险 | A 只提示 / B 计入风险点 | **B**（warn 级） | eBrevia 口径：缺失本身是风险；但不阻断（warn 非 block） |

### 3.3 风险点数据模型
```
RiskPoint {
  source: "L3_CHECK_RULES" | "CLAUSE_MISSING"
  rule_id / category / item
  level: high | medium | low
  status: pass | warning | fail | missing
  law: str                 # 仅来自 L3 受控库
  evidence: str            # 原文片段或「未检出」
  suggestion: str
}
```

### 3.4 历史交付盘点数据模型
```
DeliveryIssue {
  sheet: 异常项目 | 签约 | 验收交接
  contract_no / project_code / end_user
  issue_type: 应交未交 | 交付异常 | 应验未验 | 验收异常 | 异常项目 | 履约项异常/变更
  status / 异常项目-类别 / 项目异常内容 / 合同验收条款
  verdict: 正常 | 关注 | 异常
}
```
判定：命中 `异常项目` 表 或 交付状态 ∈ {应交未交,交付异常,应验未验,验收异常} → 关注/异常；否则正常。

## 4. 验收标准（Definition of Done，先于编码）

| AC | 标准 | 验证方式 |
|---|---|---|
| AC1 | `contractctl clauses --file <docx/txt>` 输出结构化条款，类别/法条/原文/摘要齐全；抽样真实合同 ≥15 类 | 单元测试 + 真实样本跑通 |
| AC2 | `contractctl review` 报告含「条款拆解」「风险点」两章；风险点含原文证据 + 法条；L3 22 条结果不丢 | 回归 + 新测试 |
| AC3 | 对「required 条款整条缺失」的构造样本，风险点出现 `CLAUSE_MISSING` 且 status=missing | 构造样本测试 |
| AC4 | `history-delivery --contract-no XSZS...` 能从 BDMS 查到该合同历史交付问题（异常/应验未验等），无则输出「未见异常」而非报错 | 真实合同编号实测 |
| AC5 | 757 备注含「历史交付盘点」段（verdict + 命中明细）；R1 降级时写明真因 | 887770/887756 重跑 |
| AC6 | 887756 类「合同名含编号但表单空」不再判 block，evidence 注明编号来源 | 回归测试 |
| AC7 | `check_answer_contract.py` 对全部新产出 PASS | 门禁 |
| AC8 | `registry.yaml` 补 `oa-approval` / `clauses` / `history-delivery` 入口，`--coverage` 100% | pre-commit |
| AC9 | 组件单元测试全绿（现有 + 新增） | pytest |

## 5. 风险与边界
- BDMS 快照为 202606 月度，可能过期 → 产出必须标数据基准日期（沿用 ADR-035）。
- 条款缺失判定依赖 L3 提取器召回；漏抽 ≠ 真缺失 → 一律 `missing(warn)` + 人工复核提示，不判 block。
- 合同原文仍可能拿不到（P2）→ L2 原文核查维持 manual，新能力在「无原文」时显式输出「未做全文分析」，不得伪造。
