# DESIGN-DETAIL — customer-delivery-intelligence v1.0（待评审）

- 对应：PRD v1.0 / DESIGN-OUTLINE v1.0（已通过 2026-11-10）
- 资产：`customer-delivery-intelligence`（L4）
- 黄金基准：中国建设银行实例产物
- 状态：**待 Rex 评审** · 2026-11-10

---

## 1. 总体契约

```
Input{customer, period, audience, scope?}
  → 管线 N1..N7（每节点产出可校验中间产物 + 检查点）
  → Output{artifacts(6 类), raw_json, completeness_proof, audit_result, render_pack}
```

- `audience ∈ {internal, external}`；`period` 为必填区间；每节点 **纯函数 + 状态字典**，可独立重跑。
- 对外副作用（OA 流程发起、邮件、发送）一律停等人工确认；内部操作（读、整理、生成）可自动执行。

## 2. 输入 / 输出数据模型

### 2.1 Input

| 字段 | 类型 | 必填 | 约束 / 示例 |
|---|---|---|---|
| customer | string | 是 | 客户官方名，如 "中国建设银行股份有限公司" |
| period | object | 是 | `{start:"YYYY-MM-DD", end:"YYYY-MM-DD"}`（含端点） |
| audience | enum | 是 | `internal` / `external` |
| scope | object | 否 | `{includeH5Maint:true, extraContractNos:[], onlyProjects:[]}` |
| teamUUID | string | 否 | ONES 团队默认值，可按客户覆盖 |

### 2.2 Output 交付包

| 字段 | 类型 | 说明 |
|---|---|---|
| artifacts | object | 六类产物对象（见 §3） |
| raw | object | `{onesRaw, oaRaw, fetchedAt}` 原始快照 |
| completeness | object | 完整性证据（分页触顶校验 + 快照时间 + 文件清单 hash） |
| audit | object | `{status:"PASS/BLOCK", checks:[], missing:[], warnings:[]}` |
| renders | object | `{md, docx?, pptx?}` |
| trace_id | string | 全链路血缘 ID，可回溯到原始文件 |

## 3. 核心数据模型（六类产物 IR）

所有中间步骤围绕统一 IR 工作；**签约项目汇总 Contract 是唯一事实源**，其余五类通过外键引用。

### 3.1 ProjectRegister（项目汇总 P1）

```jsonc
{
  "projectId": "PROJ-2026-CCB-001",     // 全局唯一编码
  "customer": "中国建设银行股份有限公司",
  "projectName": "AI 安全攻防实训平台",
  "projectType": "software_service|consulting|saas|delivery",
  "contractNo": "XSZS2511110886",
  "contractAmount": 1200000.00,
  "currency": "CNY",
  "projectManager": "张三",
  "startDate": "2025-11-01",
  "endDate": "2026-12-31",
  "phaseStatus": "in_progress|done|blocked",
  "health": "green|yellow|red",
  "acceptanceStatus": "not_started|in_progress|initial_pass|final_pass|failed",
  "paymentStatus": "not_invoiced|invoiced|partial_paid|paid|overdue",
  "lastUpdated": "iso8601"
}
```

### 3.2 ContractRegister（签约项目汇总 P2，★核心事实源）

```jsonc
{
  "contractNo": "XSZS2511110886",
  "officialName": "AI 安全攻防实训平台建设合同",
  "signDate": "2025-11-01",
  "contractType": "fixed_price|time_materials|framework",
  "amount": 1200000.00,
  "taxRate": 0.06,
  "currency": "CNY",
  "partyA": "中国建设银行股份有限公司",
  "partyB": "北京梆梆安全科技有限公司",
  "customerContractNo": "建科（2025）XXX号",
  "scope": {                                    // 范围条款
    "deliverables": ["模型训练平台", "攻防演练系统", "验收测试报告"],
    "exclusions": ["硬件采购", "驻场运维"],
    "techSpecRef": "SOW-AI-SEC-2025-11"
  },
  "milestones": [                              // 里程碑与交付物条款
    {"id":"M1","name":"需求确认","deliverables":["需求规格书"],"dueDate":"2025-12-01","deliveryForm":"docx+签字扫描件"}
  ],
  "acceptance": {                              // 验收条款
    "method": "initial_and_final|one_time",
    "initialAcceptance": {
      "criteria": "功能测试通过率≥95%，无1、2级缺陷",
      "process": "乙方提交→甲方10个工作日内组织→出具初验报告",
      "documentsRequired": ["测试报告", "用户手册", "部署文档"],
      "disputeResolution": "双方协商，第三方测评机构仲裁"
    },
    "finalAcceptance": {
      "criteria": "质保期满无重大遗留问题",
      "process": "质保期满30日内出具终验报告"
    }
  },
  "payment": {                                 // 付款条款
    "schedule": [
      {"node":"contract_sign","ratio":0.30,"amount":360000,"triggerCondition":"合同签订且收到发票后10个工作日内","daysAfterTrigger":10}
    ],
    "invoiceRequirements": "增值税专用发票，6%",
    "overdueClause": "逾期按日万分之三支付违约金"
  },
  "warranty": {                                // 质保维保条款
    "startFrom": "final_acceptance_date",
    "durationMonths": 12,
    "scope": "缺陷修复、技术支持、版本升级",
    "finalAcceptanceOnExpiry": true
  },
  "ipAndData": {                               // IP 与数据条款
    "ownership": "乙方享有知识产权，甲方获非独占许可",
    "license": "perpetual, non-exclusive, non-transferable",
    "dataIsolation": "符合 JR/T 0068-2020 外包软件开发数据安全要求"
  },
  "breach": {                                  // 违约与终止条款
    "delayPenalty": "按日万分之三，累计不超过合同金额5%",
    "terminationForCause": "一方严重违约，另一方有权终止合同"
  },
  "complianceRefs": ["JR/T 0071-2020", "JR/T 0072-2020", "JR/T 0068-2020"],
  "clauseExtracts": [                          // 原文摘录 + 条款号（追溯用）
    {"clauseNo":"5.2.1","text":"初验标准：功能测试用例通过率不低于95%...","sourceFile":"contract_XSZS2511110886.pdf","page":12}
  ],
  "sourceFileUri": "oa://contracts/XSZS2511110886.pdf",   // 原始文件 URI
  "extractedAt": "iso8601",
  "extractionConfidence": 0.95,
  "reviewStatus": "auto|human_reviewed"
}
```

### 3.3 PerformanceObligation（履约义务汇总 P3）

```jsonc
{
  "obligationId": "PO-XSZS2511110886-01",
  "contractNo": "XSZS2511110886",
  "description": "AI 安全攻防实训平台软件开发",
  "isDistinct": true,                           // IFRS15 步骤2 可区分性
  "allocatedPrice": 800000.00,                  // 步骤4 价格分摊
  "recognitionMethod": "point_in_time|over_time", // 确认方式
  "acceptanceMilestoneId": "M3",                // 验收节点关联
  "recognizedAmount": 0.00,
  "remainingAmount": 800000.00,
  "recognizedAt": "iso8601|null"
}
```

### 3.4 AcceptanceChecklist（验收条件核查表 P4）

```jsonc
{
  "checklistId": "ACL-XSZS2511110886-INI",
  "contractNo": "XSZS2511110886",
  "acceptanceType": "initial|final|one_time",
  "items": [
    {
      "itemId": "ITEM-001",
      "clauseRefs": ["5.2.1"],                  // 外键：合同条款号
      "clauseText": "功能测试用例通过率不低于95%",
      "checkContent": "功能测试通过率核查",
      "criteria": "≥95%（量化阈值）",
      "evidenceUri": "ones://attachments/test-report-2026.pdf",
      "method": "test|inspection|review|demo|walkthrough",
      "conclusion": "pass|fail|conditional_pass",
      "outstandingIssues": ["issue_id 或描述"],
      "reviewedBy": "string|null",
      "reviewedAt": "iso8601|null"
    }
  ],
  "summaryConclusion": "pass|fail|conditional",
  "generatedAt": "iso8601"
}
```

### 3.5 AcceptanceReport（验收单/交付说明 P5）

```jsonc
{
  "reportNo": "ACPT-XSZS2511110886-2026-06",
  "contractNo": "XSZS2511110886",
  "acceptanceType": "initial|final|one_time",
  "date": "2026-06-15",
  "location": "北京",
  "partyA": "中国建设银行股份有限公司",
  "partyB": "北京梆梆安全科技有限公司",
  "deliverablesChecklist": [
    {"name":"需求规格书","delivered":true,"version":"v1.0","remark":""}
  ],
  "conclusion": "qualified|needs_rectification|unqualified",
  "outstandingList": ["遗留问题描述"],
  "basis": ["合同第5.2条", "GB/T 28035-2011", "JR/T 0213-2021"],
  "signatures": {
    "acceptanceTeam": {"signed":false,"name":null,"date":null},
    "partyARep": {"signed":false,"name":null,"date":null},
    "partyBRep": {"signed":false,"name":null,"date":null}
  },
  "attachments": ["附件清单，含原文 URI"],
  "revenueRecognition": {                      // 验收=财务事件
    "recognized": true,
    "obligationIds": ["PO-XSZS2511110886-01"],
    "recognizedAmount": 800000.00,
    "recognizedDate": "2026-06-15"
  }
}
```

### 3.6 PaymentTracker（回款跟踪 P6）

```jsonc
{
  "contractNo": "XSZS2511110886",
  "paymentPlan": [
    {"node":"contract_sign","ratio":0.30,"amount":360000,"triggerCondition":"合同签订","triggerDate":"2025-11-01","expectedDate":"2025-11-15","status":"paid"}
  ],
  "acceptanceTriggers": [
    {"milestoneId":"M3","paymentNode":"milestone_3","amount":360000,"triggered":false}
  ],
  "invoices": [
    {"invoiceNo":"","date":"2025-11-05","amount":360000,"status":"issued"}
  ],
  "receivables": {
    "totalReceivable": 1200000,
    "received": 360000,
    "outstanding": 840000
  },
  "aging": {
    "current": 0,
    "days0_30": 0,
    "days31_60": 0,
    "days61_90": 0,
    "days90_plus": 840000
  },
  "overdueItems": [
    {"paymentNode":"milestone_3","amount":360000,"overdueDays":45,"collectionStatus":"reminder_sent"}
  ],
  "writeOffs": []
}
```

## 4. 管线节点设计（N1–N7）

每节点 = `step(state) → state'`，纯函数，输入输出强类型，失败抛异常（上层状态机捕获→重试/升级）。

### N1 入口护栏（M1）
- 输入：`Input{customer, period, audience, scope}`
- 处理：参数校验（客户名非空/格式、period 合法、audience 枚举、scope 字段白名单）；客户名标准化（查已知客户映射表）；创建 task_id；写初始检查点
- 输出：`state.task_id / state.input_norm / state.guard_pass`
- 失败：参数非法 → 直接返回错误，不写检查点

### N2 取数编排（M2）
- 输入：`state.input_norm`
- 处理：
  - **ONES 分支**（复用 ones-browser-export）：按客户名枚举项目→逐项目分页取全→校验触顶（最后页 size < pageSize）→记录快照时间→raw JSON 落盘
  - **OA 分支**（复用 clm-oa-recon）：按合同号从 OA 拉合同台账→验收流程状态→附件原文（PDF/DOCX）→下载即校验（类型/非空/大小）
  - 两分支并行执行，等待全部 settle 后合并 file_manifest
- 输出：`state.raw{ones, oa}` / `state.file_manifest` / `state.completeness`
- 失败：任一源连续 3 次失败 → 标记 `failed` + 原因，升级人工（不继续）

### N3 齐套校验闸（M3，HITL 1）
- 输入：`state.file_manifest`
- 处理：
  - 自动校验：合同文件是否齐全（按项目汇总合同号清单对齐）、文件类型是否合规（PDF/DOCX/扫描件 OCR 标识）、文件非空
  - 齐套 → `pass` 自动继续
  - 不齐 → 生成缺失清单，发企微通知等人工确认（可选择「补文件后重跑本步」或「跳过继续」）
- 输出：`state.manifest_verified=true` / `state.hitl1_decision`
- 等待：人工回执 → 写检查点 → 继续

### N4 解析与抽取（M4）
- 输入：`state.file_manifest` / 原始文件
- 处理：
  - 扫描件 → OCR（复用既有 OCR）
  - PDF/DOCX → Docling 结构化（条款+表格→JSON）；Word 用 MarkItDown 快路径
  - 合同条款映射到 ContractRegister 9 大维度
  - **Schema 校验**：Pydantic 模型校验 ContractRegister → 失败回喂 LLM 重试（上限 3 次）→仍失败升级人工
  - 每条抽取结果记录 `sourceFileUri + clauseNo + confidence + extractor`
- 输出：`state.contracts[]`（ContractRegister IR）
- 失败：抽取失败单条 `review_status=needs_human`，不阻塞整体

### N5 汇总与成文（M5）
- 输入：`state.contracts[]` / `state.raw.ones`
- 处理：
  - 从 ContractRegister 派生 ProjectRegister（项目级汇总）
  - 履约义务识别（IFRS15 五步法映射）→ PerformanceObligation
  - 验收条款翻译为核查清单 → AcceptanceChecklist
  - 验收单草稿生成 → AcceptanceReport（签字栏为空，status=draft）
  - 回款计划生成 → PaymentTracker
  - **评估器自校验**：数字一致性核对（金额合计=各节点金额之和；比例和=1；账龄合计=未收余额）；无源项清单 fail-closed
- 输出：`state.artifacts{6 类 IR}`
- 失败：校验失败 → 自动重试（重新汇总，不改原始抽取），上限 2 次

### N6 签发闸（M6，HITL 2）
- 输入：`state.artifacts`
- 处理：
  - 合同条款类对外产物 → 必须人工签发
  - 对内产物 → 自动通过
  - 生成预览（md）+ 签发通知（企微）→ 等人工回执
- 输出：`state.artifacts_signed=true` / `state.hitl2_decision`
- 等待：人工回执 → 写检查点 → 继续

### N7 渲染与交付（M7）
- 输入：`state.artifacts_signed` / `state.input_norm.audience`
- 处理：
  - md 渲染：每类产物一份 md（带血缘链接）
  - docx：复用 python-docx + 模板（内部版/对外版）；对外版脱敏系统名/商务敏感条款
  - PPT：复用 bangcle-ppt 技能（如用户需要）
  - 打包交付包：`{artifacts, raw, completeness, audit, renders, trace_id}`
- 输出：最终交付包

## 5. 状态机与检查点（薄 runner 核心）

### 5.1 状态机

```python
states = [
    "N1_guard",
    "N2_collect",
    "N3_manifest_gate",     # HITL 等待点
    "N4_parse",
    "N5_compose",
    "N6_sign_gate",         # HITL 等待点
    "N7_render",
    "done",
    "failed",
]

transitions = {
    "N1_guard":        {"pass": "N2_collect", "fail": "failed"},
    "N2_collect":      {"pass": "N3_manifest_gate", "fail": "failed"},
    "N3_manifest_gate":{"approve": "N4_parse", "reject": "N2_collect", "skip": "N4_parse"},
    "N4_parse":        {"pass": "N5_compose", "partial": "N5_compose", "fail": "failed"},
    "N5_compose":      {"pass": "N6_sign_gate", "fail": "failed"},
    "N6_sign_gate":    {"approve": "N7_render", "revise": "N5_compose"},
    "N7_render":       {"pass": "done"},
}
```

### 5.2 检查点持久化

- 存储：SQLite（表 `cdi_checkpoints`，主键 `task_id`）
- 写入时机：每节点跃迁成功后，原子写入全量 state JSON
- 恢复逻辑：`resume(task_id)` → 读取最新 checkpoint → 从下一节点继续（不重跑已完成节点）
- 幂等：同一 task_id 重跑同一节点，若已成功则跳过
- 保留策略：成功任务保留 90 天；失败任务保留 30 天

### 5.3 状态字典 schema

```jsonc
{
  "task_id": "cdi-20261110-ccb-001",
  "current_state": "N3_manifest_gate",
  "input_norm": {...},
  "raw": {"ones": {...}, "oa": {...}, "fetchedAt": "iso8601"},
  "file_manifest": [{"uri":"...","type":"pdf","size":12345,"sha256":"..."}],
  "completeness": {"onesPagesTouched":12,"oaFilesFetched":5,"proof":{...}},
  "contracts": [ContractRegister...],
  "artifacts": {"projectRegister":[], "contractRegister":[], ...},
  "hitl_decisions": {"gate1":"approve", "gate2":null},
  "audit": {"status":"in_progress", "checks":[]},
  "errors": [],
  "createdAt": "iso8601",
  "updatedAt": "iso8601"
}
```

## 6. 取数完整性自证（落实 11-08 整改）

### 6.1 ONES 取数完整性证据
- 分页：每次分页请求记录 `pageSize/pageNo/totalCount/returnedCount`
- 触顶校验：最后一页 `returnedCount < pageSize` 且累计 `sum(returned) == totalCount`
- 字段枚举：取数前先 `fields` 定义查询，确认挂载实体（合同号挂在 Project 还是 Issue）
- 查无数据：先举证「已触顶 + 关键词已穷尽 + 无数据来源可信」，再给结论
- 快照：`fetchedAt` 时间戳 + 原始响应全量落盘（raw JSON）

### 6.2 OA 取数完整性证据
- 合同台账：从合同列表页拉取，记录总条数与实际条数
- 附件：每合同对应附件清单，文件类型/大小/sha256
- 流程：验收流程状态来自流程详情页，记录流程 ID

## 7. 血缘与审计

- **trace_id**：每个 task 唯一；六类产物每条记录带 `_meta.trace_id`
- **两级血缘**：
  - Level 1（文件级）：产物 → 原始文件 URI（合同 PDF 路径、ONES 项目 UUID）
  - Level 2（字段级）：关键结论字段 → 条款号 + 原文摘录（clauseNo + clauseText + sourceFileUri + page）
- **审计命令**：`trace.py <trace_id> <field_path>` → 返回从最终字段到原始文件的完整路径
- **fail-closed**：无源项清单（`audit.missing`）非空 → `audit.status=BLOCK`，不进入渲染

## 8. 人在环（HITL）

| 闸 | 触发时机 | 决策选项 | 决策方式 | 超时策略 |
|---|---|---|---|---|
| gate1 齐套闸 | N3 文件不齐 | approve / reject(重跑取数) / skip | 企微通知 + 回执 | 24h 未回执 → 暂停（不自动继续） |
| gate2 签发闸 | N6 对外产物 | approve / revise(重跑汇总) | 企微通知 + 回执 | 24h 未回执 → 暂停 |

- 所有决策带 `decidedBy` + `decidedAt`，写入检查点
- 决策后从下一节点继续（精确断点恢复，不重跑已完成节点）

## 9. 安全与合规

- **凭据**：浏览器会话存储于既有 `~/.openclaw/data/clm-oa-recon/` 机制；不写任何 markdown
- **PII**：对外版自动脱敏（系统内部编号、商务敏感比例条款可配置白名单）
- **数据出境**：Docling/MarkItDown 本地运行；不调用云 OCR（AWS Textract 等）
- **权限**：SKILL 入口走既有权限体系；非授权客户拒绝
- **越权护栏**：交付前自动校验 — 产物不得包含非请求客户的数据

## 10. 接口清单（对外 / 对内）

### 10.1 SKILL 入口
- `run(customer, period, audience, scope?)` → `task_id`（异步启动）
- `status(task_id)` → `{state, progress, artifacts?}`
- `resume(task_id, decision)` → 从 HITL 闸继续
- `trace(task_id, field_path?)` → 血缘查询

### 10.2 节点级接口（内部）
- `step_N1_guard(input) → state'`
- `step_N2_collect(state) → state'`
- `step_N3_gate_wait(state) → state'`（HITL 等待）
- `step_N4_parse(state) → state'`
- `step_N5_compose(state) → state'`
- `step_N6_gate_wait(state) → state'`（HITL 等待）
- `step_N7_render(state) → state'`

## 11. 数据来源铁律（Rex 2026-11-10 强调）

**原始数据必须从 OA、ONES 等 Bangcle 相关系统直接获取，禁止：**

1. ❌ 禁止从二手汇总表/Excel/邮件附件倒推原始数据
2. ❌ 禁止把历史产物（如之前生成的 md/docx）当作输入再加工
3. ❌ 禁止人工录入或口头转述的数据不经系统验证直接入库
4. ❌ 禁止用「经验值」「大概」填充缺失字段

**强制执行机制：**

| 数据项 | 唯一合法来源 | 验证方式 |
|---|---|---|
| 项目清单、工作项、履约义务 | ONES（经 ones-browser-export 浏览器自动化） | ONES UUID / 分页触顶校验 / 快照时间 |
| 合同文本、条款、金额、双方主体 | OA 合同台账附件（PDF/DOCX 原文） | OA 附件 URI / 文件 sha256 / 下载即校验 |
| 验收流程状态、签字版、归档 | OA 验收流程详情页 + 附件 | OA 流程 ID / 附件 URI |
| 回款、开票 | OA 财务模块 / 银行回单附件 | 凭证号 / 附件 URI |
| 客户主体信息 | OA 客户主数据 | 客户编码 |

**产物溯源约束：**
- 六类产物中，任何事实类字段（金额、日期、条款内容、状态）必须有 `sourceUri` 指向原始系统记录
- 无来源字段的产物，schema 校验直接失败，不进入下一节点
- `audit.status` 中 `missing_sources` 计数，>0 即 BLOCK

**唯一例外**：模板类元数据（如报告标题、版式）可配置，但不得影响事实数据。

---

## 12. 边界（重申）

- 不替代客户签字：验收单/交付说明签字栏默认 `signed:false`，仅生成草稿
- 不自动发起 OA 流程：停等人工确认
- 不重造 DAG 引擎：薄 runner 状态机满足；Temporal 留适配面
- 不新增 Agent/角色：复用 PM 专家 / 合同专家入口
- 不重跑已取文件：断点恢复幂等
