# DESIGN-DETAIL — Bangcle 项目汇报材料生成技能 v1.0（待评审）

- 对应：PRD v1.0 / DESIGN-OUTLINE v1.0（已通过）
- 技能：`bangcle-project-report`（L3）
- 状态：**待 Rex 评审** · 2026-11-08
- 黄金基准：建行材料回放，须复现 **113 / 104 / 9**

---

## 1. 总体契约

输入三元组 → 标准管线 → 汇报包：

```
Input{customer, period, audience, scope?}
  → 管线 S1..S8（每段产出可校验中间产物）
  → Output{report_md, raw_json, audit_result, docx?}
```

- `audience ∈ {external, internal}`；`period` 为必填区间。
- 每段脚本 **stdin/stdout JSON、零对外副作用、可独立重跑**；中间产物落 `analysis_output/ones_raw/`。

## 2. 输入 / 输出数据模型

### 2.1 Input

| 字段 | 类型 | 必填 | 约束 / 示例 |
|---|---|---|---|
| customer | string | 是 | 客户官方名，如"中国建设银行股份有限公司" |
| period | object | 是 | `{start:"2026-01-01", end:"2026-12-31"}`（含端点，按 createTime） |
| audience | enum | 是 | `external` / `internal` |
| scope | object | 否 | `{includeUnsignedAcceptance:true, extraContracts:[]}` |
| teamUUID | string | 否 | 默认 `RZxvwUZ8`（可按客户覆盖） |

### 2.2 Output 汇报包

| 字段 | 类型 | 说明 |
|---|---|---|
| report_md | path | 主交付（7 章） |
| docx | path? | F12，audience 适配后导出 |
| raw | object | `{tasks, projects, contracts, fetchedAt}` |
| completeness | object | 完整性证据（见 §4） |
| audit | object | `{status:"PASS/BLOCK", missing:[], checks:{}}` |

## 3. 核心数据模型（中间表示 IR）

所有脚本围绕统一 IR 工作，**明细行 `WorkItem` 是唯一事实源**。

### 3.1 Project

```jsonc
{
  "projectUUID": "string",
  "projectCode": "SSXM-2026-1022-2826",   // 从 name 解析
  "projectName": "string",
  "contractNo": "XSZS...|null",            // Project._7KF6tXvk (CAaTom7U)
  "standardProduct": "string|null",
  "status": "string"
}
```

### 3.2 Contract（台账合并）

```jsonc
{
  "contractNo": "XSZS...",
  "officialName": "string",                // 仅取台账官方名；空则 null，由 projectName 兜底并标记
  "serviceStart": "YYYY-MM-DD|null",
  "serviceEnd":   "YYYY-MM-DD|null",
  "archiveDate":  "YYYY-MM-DD|null",
  "customer": "string", "endUser": "string",
  "nameSource": "ledger|project_fallback"  // 审计可见，不进对外正文
}
```

### 3.3 WorkItem（明细行 = 单一事实源）

```jsonc
{
  "number": 394290,
  "uuid": "string",
  "name": "string",
  "projectCode": "SSXM-...",
  "contractNo": "XSZS...|null",
  "issueType": "客户定制需求|缺陷修复|问题工单|产研支持|专项任务|项目履约义务|...",
  "productDirection": "安全监测|合规检测|安卓/SDK 加固|应用安全测评|小程序加固|H5/API 安全|鸿蒙 NEXT 加固",
  "statusCategory": "done|in_progress|to_do",
  "createTime": "iso8601",                 // 归一后
  "createEpochUs": 0,
  "inPeriod": true,
  "isWork": true,                          // false=履约/建档记录
  "excludeReason": "string|null"
}
```

### 3.4 GoalRealization

```jsonc
{
  "direction": "string",
  "contracts": ["XSZS..."],
  "goal": "string",
  "support": "string",
  "realizationLevel": "已实现|基本实现|部分实现/推进中|能力已落地|能力已建成|往年已达成",
  "evidence": { "workDone": 0, "workTotal": 0, "deliveryRecords": ["string"] }
}
```

## 4. 接口契约（脚本级）

> 全部脚本：`python3 script.py`，JSON 入 stdin、JSON 出 stdout；退出码 0=成功，2=数据/BLOCK。

### 4.1 fetch_project_tasks.py（S1+S2）

- 入：`Input`
- 出：`{projects:[Project], tasks:[raw Task], completeness:{...}}`
- 契约：
  - 逐项目枚举，分页 `page/pageSize`（建议 pageSize=200），累计 `fetched == total` 方可停；
  - 每页断言 `len(page) <= pageSize`；若末页满页，**强制再拉一页确认**（防触顶）；
  - Project 合同字段实时查询 `Project._7KF6tXvk`，禁止用本地快照判定"无"；
  - `completeness={fetchedAt, perProject:{code:{fetched,total,hitCap:false}}, globalTruncated:false}`。
- 复用：薄封装 `tmp/sdcbank/ones.py` 的浏览器注入 `gql()`（鉴权 `localStorage['ct']`）。

### 4.2 normalize_and_classify.py（S3）

- 入：raw tasks
- 出：`WorkItem[]` + 分类统计
- 契约：
  - 时间戳归一：`v>1e14 → μ/1e6`；`v>1e11 → ms/1e3`；否则秒。Asia/Shanghai。
  - 口径：`issueType ∈ {客户信息,合同信息,项目信息,设备领用情况,外包/外采情况,项目履约义务}` → `isWork=false`（不计工作量）；其余 5 类 → true。
  - 周期：`period.start <= createTime <= period.end` → inPeriod。
  - 产品方向：映射表（§6.2）；无命中→`【缺失】`并列入审计。

### 4.3 aggregate.py（S4）

- 入：`WorkItem[]`（仅 isWork & inPeriod）
- 出：`{byCategory, byProduct, byPeriod, detail:[], reconciliation:{}}`
- 契约：
  - 三维汇总全部由明细行 `Counter` 生成，**禁止第二计数器**；
  - `reconciliation` 断言：各维 total 相等且 = `len(detail)`；done+wip=total，不符 exit=2。

### 4.4（目标闭环，S5）build_goal_matrix.py

- 入：`WorkItem[]` + Contract[] + 履约完成记录
- 出：`GoalRealization[]` + 在途归并
- 契约：
  - 维保类：evidence 取该方向 inPeriod 服务事项 done/total；
  - 采购新建类：evidence 取「部署/授权」履约义务 `statusCategory=done` 记录；
  - 实现等级仅可由 §6.3 规则映射，不接受自由文本等级。

### 4.5 audit_provenance.py（S7，fail-closed）

- 入：report_md + raw 语料
- 出：`{status, missing:[{token, where}]}`；**exit≠0 即 BLOCK，禁止交付**
- 检查：
  1. 全部数字（含日期）在原始语料命中或可由明细复算；
  2. 技术/业务名词在任务名/描述命中；
  3. 价值论述句均在标注区；
  4. external 版脱敏词表 grep=0、合同名 == 台账官方名。

### 4.6 render / export（S6/S8/F12）

- 模板：`assets/report-template-{internal,external}.md`。
- external 末步强制脱敏（词表见 `references/audience-redaction.md`）。
- docx：pandoc（优先）；不可用则 python-docx 保结构。导出后行数/标题校验。

## 5. 取数 GraphQL 契约（实测语法）

端点：`POST .../team/<teamUUID>/items/graphql`，头 `Ones-Auth-Token: <ct>`。

```graphql
# 项目枚举 + 合同字段
{ projects { uuid name _7KF6tXvk } }

# 逐项目分页任务（对象必带选择集）
tasks(filter:{project_in:["<pUUID>"]}, page:1, pageSize:200) {
  number uuid name statusCategory createTime
  status { name category }
  owner { name }
  issueType { name }
  project { uuid name }
  products { uuid name }
  descriptionText
}
```

- 分页/排序字段以 ONES 实际 schema 为准（实现期用 `__schema` 内省确认；`__type` 被禁）。
- 时间戳：Task 微秒；评论秒。

## 6. 规则与词表

### 6.1 不计数 issueType（建档/范围记录）

`项目履约义务 / 客户信息 / 合同信息 / 项目信息 / 产品信息 / 设备领用情况 / 外包（外采）情况 / 外包/外采情况`。

> 实测校准（2026-11-08 黄金回放）：ONES 真实类型名含「外包（外采）情况」与「外包/外采情况」两种变体；「产品信息」也是建档类。

### 6.2 实际工作 5 类（ONES 真实类型名 → 标准类别）

| ONES 真实 issueType | 标准类别 |
|---|---|
| 客户定制需求 | 客户定制需求 |
| 缺陷 | 缺陷修复 |
| 工单 | 问题工单 |
| 客户项目产研支持需求 | 产研支持 |
| 任务 | 专项任务 |

> ⚠️ 不要用概念名（缺陷修复/问题工单/产研支持/专项任务）匹配真实数据——ONES 里是「缺陷/工单/客户项目产研支持需求/任务」，黄金回放验证过逐项计数。

### 6.3 产品方向映射

**双通道：**
1. 任务编号命中 `assets/golden/ccb-2026-product-override.json`（黄金人工核定 fixture，113 条）→ 用 fixture 值
2. 未命中 → 关键字规则（任务名 + products 字段）：

| 关键字（任务名/产品） | 产品方向 |
|---|---|
| 监测、客户端、SDK 在线、Root、APatch、SukiSU | 安全监测 |
| 合规、检测报告、Stim、监管 | 合规检测 |
| 加固、加壳、16KB、防代理、崩溃（非测评） | 安卓/SDK 加固 |
| 测评、TDSQL（测评上下文）、V5.x 测评 | 应用安全测评 |
| 小程序、ZIP 小程序 | 小程序加固 |
| H5、API、设备指纹(H5) | H5/API 安全 |
| 鸿蒙、NEXT | 鸿蒙 NEXT 加固 |

> 黄金产品方向含人工核定（如「SDK 闪退修复」→合规检测、「SDK 升级」→安卓/SDK 加固），无法仅靠 name+products 还原，故固化 fixture 可审计、可回归。
> `XSZS2509180700` 跨测评/加固：以 issue 上下文产品方向判定，不用合同号一刀切。

### 6.4 目标实现等级映射

| 条件 | 等级 |
|---|---|
| 维保方向 done/total 全覆盖且工单闭环 | 已实现 |
| 完成、仅 1 项集成类在途 | 基本实现 |
| 研发完成、系统测试多在途 | 部分实现/推进中 |
| 采购类 部署+授权 done，验收手续在途 | 能力已落地/已建成 |
| 能力建于 prior 周期、本周期仅维护 | 往年已达成 |

### 6.5 external 脱敏词表（grep 必须为 0）

`ONES / OA / BDMS / GraphQL / harbor / SSXM / 内部任务号 / 回款 / 结算 / 验收条款`，
以及非官方合同名；合同/项目一律正式名。

## 7. 错误处理与防呆

- 取数：触顶未确认 → exit 2；限流(801) → 指数退避，最多 3 次（3 次失败停手）。
- 字段缺失：`null` 显式保留 + `【缺失】`，不留空、不臆造。
- 合同名空：`nameSource=project_fallback`，对内可见标注，对外用项目正式名。
- 审计 BLOCK：流水线中断，返回 missing 清单，禁止产出"完成"结论。

## 8. 验证钩子（落盘后强制）

1. `python3 ../../../L2-infra/prompts/tools/check_answer_contract.py <report_md>`
2. `python3 scripts/audit_provenance.py`（本技能）
3. 黄金基准回放断言：`work=113 done=104 wip=9`，三维 Counter 与建行版一致。
4. 幂等：同 Input 连跑 3 次，输出 hash 稳定（时间戳字段除外）。

## 9. 受影响/新增文件清单（建设期）

见 OUTLINE §5 技能目录；新增脚本 4、参考 3、模板 2。
不改动既有 4 个 PM 技能与 `openclaw.json`（extraDirs 已含 L3）。
