# OA 项目实施流程 → ONES 字段映射（技术链路验证 2026-11-13；v2 2026-11-18）

## 一、OA 流程清单（workflowid 已验证）

> 标题原为「三类流程」（2026-11-13 视角，仅项目实施三流程）；2026-11-18 复核后改为
> **全量已验证清单**——`oa_todo_dist.py` 的 `TARGETS` 已登记 8 个 workflowid，
> 其中 757 即「销售合同审核流程」（本次需求新增确认）。

| 流程 | workflowid | 说明 |
|---|---|---|
| PoC需求申请流程 | 820 | POC 类待办 |
| 提前实施需求申请流程 | 815 | 提前实施类待办 |
| 销售合同下单流程（数据审核触发） | 916 | 签约项目类待办 |
| 销售合同验收文件归档流程 | 840 | 验收归档待办 |
| **销售合同审核流程** | **757** | **合同签署前商务/财务/法务联合评审**（2026-11-18 新增确认） |
| 差旅申请单 | 923 | 非项目流程（仅登记） |
| 销售合同验收文件归档流程（旧定义） | 778 | 被 840 取代，遗留单据未销 |
| 销售合同验收文件归档流程（旧定义） | 752 | 同上 |

**757 的两处独立证据**（2026-11-18）：
1. `scripts/oa_todo_dist.py` 的 `TARGETS` 明确登记 `("757", "销售合同审核流程")`；
2. `L4-proprietary/components/bangcle-contract/tests/fixtures/oa_log_882663.json`
   头部 `{"requestid": "882663", "workflowid": "757"}`——882663 即 757 流程单据，
   含 10 条真实审批链 + 2 处 AI 小助手意见（`AI_WORKFLOW_OPINION_CALLBACK`）。
   离线重放 `normalize_approval_chain` 得节点序列：商务→分管总监→部门经理→
   合同评审小组→AI小助手（批注）→申请人，与合同评审链一致。

**757 与既有链路的关系**：`ApprovalLogReader` 与 workflowid 解耦（读任意 requestid）；
`scripts/reconcile_oa.py`（P4.4）按 `oa_billid → 「合同审批流程→」= requestid` 驱动，
**无 workflowid 过滤**，故 757 与其他流程共用同一对账链路。
流程结构固化见 `docs/knowledge-base/oa-contract-review-workflow.md`。

> 2026-11-18 实时：待办总数 288；820=1（886291 中移金科 POC，用户已手动处理）、815=0、916=0、840=273、757=2、923=1 等。

## 二、OA 表单读取链路（只读）

- 单据页：`https://oa.bangcle.com/spa/workflow/static4form/index.html?_rdm=...#/main/workflow/req?requestid=<rid>&preloadkey=...`
- 捕获：Playwright + `storage_state`（`~/.openclaw/data/clm-oa-recon/state.json`），监听 response 抓 `/api/` JSON
- 关键端点：`/api/workflow/reqform/loadForm`、`detailData`、`getRequestLogList`、`/api/ec/dev/table/datas`（全量待办，dataKey 每次页面 POST 捕获）
- ⚠️ 泛微把 JSON 藏在 `text/plain`；`loadForm` 响应体大易截断，用 `detailData` + DOM 全文
- 会话过期自愈：`refresh_oa_session()`（L4-proprietary bangcle-contract，`/Users/bangcle/.openclaw/workspace/L4-proprietary/components/bangcle-contract/services/oa/browser_fallback.py`）
- 过期判定：`FINAL_URL` 落 `iam.bangcle.com/#/login`
- ⚠️ OA 写入（审批/提交/转发）一律人工闸，只读

## 三、ONES 字段 uuid → 语义（fields API，983 字段）

| uuid | 语义 | GraphQL 名 | 类型 |
|---|---|---|---|
| `Gvi8gt9w` | 项目状态 | `_Gvi8gt9w{value}` | 枚举对象 |
| `VEpH5GrQ` | 履约项异常/变更备注 | `_VEpH5GrQ{value}` | 枚举对象 |
| `Wx5cft6o` | 项目编号 | `_Wx5cft6o` | 标量文本 |
| `CuG2EPnC` | 最终客户名称 | `_CuG2EPnC` | 标量文本 |
| `RnWqUALs` | 客户名称 | `_RnWqUALs` | 标量文本 |
| `91zfR6N1` | 项目履约义务状态 | `_91zfR6N1` | 枚举对象 |
| `2jEz2XG9` | 项目经理 | `_2jEz2XG9` | 标量文本（⚠️ 实测全空，无值） |
| `ArYbG1Hf`/`6ehQSmch` | 授权开始/结束 | int | ⚠️ 实测全空 |
| `THZBUbgx`/`QP2aBu2T` | 实际服务/授权开始/结束 | int | ⚠️ 实测全空 |
| `DECCCa8Z` | 维保截止 | int | ⚠️ 实测全空 |
| `2yD1cAR4` | 项目验收日期 | int | ⚠️ 实测全空 |
| `FbfgaT74`/`J8NeU3jm`/`za9qTxRB` | 是否维保/已验收/验收状态 | `{value}` | ⚠️ 实测全空 |

> **结论**：授权/维保期限、项目经理在 ONES 自定义字段上**无落库值**（至少对中移金科两个项目）。
> 授权/维保只能从**【云端】license 任务 `descriptionText`** 提取（关键词「授权时间/授权期限 a-b」）；
> 项目经理需人工口径（`--pm`），否则标【缺失】。

## 四、ONES GraphQL 关键发现

1. 自定义字段命名 = `_` + 字段 uuid；字段名本身报 unknown field
2. 枚举型是对象须 `{value}`；文本型是标量直接取；标量误加 `{value}` 报 `unknown field "value"`，对象误不加报 `object field must have selections`
3. 项目 key 格式 `project-<uuid>`；**SSXM 编号在项目名里**（`【SSXM-…】…`）→ 查项目用 `projects(filter:{name_match:"SSXM-…"})`，任务名不含编号
4. `__type` 内省被禁；schema 缓存：`analysis_output/ones_raw/schema_types.json`
5. 直连 token 会过期（802 MissingToken）→ 必须在 Chrome 页面上下文执行同步 XHR
6. issueType：项目履约义务=`WEpkPvew`；客户信息/项目信息/合同信息/项目交付等按实查

## 五、端到端验证结果

| OA 单 | 流程 | 客户 | ONES 项目 | 履约义务 |
|---|---|---|---|---|
| 885576 | PoC | 绿城物业服务集团有限公司 | SSXM-2026-1112-3082 | 2 条 |
| 885673 | 提前实施 | 安吉加加信息技术有限公司 | SSXM-2026-1112-3083 | 9 条 |
| 885755 | 销售合同下单 | 亚玛芬体育用品贸易（上海）有限公司 | 未建项 | — |
| 886291 | PoC（2026-11-17） | 中移动金融科技有限公司 | 未建 2026-11-17 项目 | — |
| SSXM-2026-0611-1491 | 签约 | 中移动金科（签约：中广瑞波） | 验收完成 | 授权 2026-06-16~2027-06-16 |
| SSXM-2026-0603-1405 | 签约 | 中移动金科（签约：东信和平） | 验收完成 | 授权 2026-05-12~2027-05-12 |

## 六、脚本

`scripts/oa_workflow_ones.py`（只读）

```bash
# 签约项目块（按 SSXM 编号，输出 Rex 确认样式）
python3 scripts/oa_workflow_ones.py --code SSXM-2026-0611-1491 SSXM-2026-0603-1405 \
    --pm 邓旭兵 --final-customer 中移动金融科技有限公司

# OA 单（捕获→解析→ONES）
python3 scripts/oa_workflow_ones.py --capture 886291
python3 scripts/oa_workflow_ones.py 886291
```

## 七、待办两个口径的差异（2026-11-18 实证，解释 wf_778/752 消失之谜）

**现象**：`doingBaseInfo.treedata` / `doingCountInfo.treecount` 只出现部分流程，
而 `/api/ec/dev/table/datas` 全量列表里能看到更多 workflowid。

**根因（实证）**：两个口径取数不同源。

| 口径 | 端点 | 含义 | 2026-11-18 实测 |
|---|---|---|---|
| 树/计数 | `workflow/reqlist/doingBaseInfo` + `doingCountInfo` | **当前启用的流程节点**（左侧导航树） | `type_40 梆梆_项目实施管理` → `wf_840 / wf_757 / wf_923` |
| 列表 | `/api/ec/dev/table/datas`（全量分页，dataKey 当次捕获） | **全部待办单据**，含历史流程定义 | 286 条：840=272、**778=9、752=2**、757=2、923=1 |

**wf_778 / wf_752 是什么**：均为「销售合同验收文件归档流程」的**旧 workflowid 定义**
（单据创建人多为崔硕，日期 2023-01 ~ 2024-08）。该流程定义已被 `wf_840` 取代，
但**遗留单据仍挂在待办列表**，因此：
- 树节点里查不到（旧定义不在当前导航树）；
- 列表口径能查到（单据本身未销）。

**纪律（Always）：**
- Always 报「某流程有几条待办」时**注明口径**；两者数字对不上是正常，不是数据错。
- Never 用树节点缺失推断「某流程无待办」——旧定义流程的单据不进树。
- Always 全量分页用当次 POST 捕获的 `dataKey`，禁止硬编码旧值。
- 目标流程清单里 `wf_820/815/916` 当前既不在树、列表也为 0（820 的 886291 已由人工处理）。

## 八、脚本清单（权威源）

| 脚本 | 用途 | 处置 |
|---|---|---|
| `scripts/oa_workflow_ones.py` | OA 单 → ONES 桥（`--code` 签约块 / `--capture` / requestid） | ✅ 权威 |
| `scripts/oa_todo_dist.py` | 待办全量分布统计（双口径对比，`--save` 落盘） | ✅ 权威（2026-11-18 新增） |

**已吸收/无需固化**（原 `tmp/oa-pif/` 临时脚本，结论已进本文件，脚本不入库）：
- `refresh_now.py`（5 行）→ 薄包装 `refresh_oa_session()`，SKILL 已说明，无需重复；
- `capture_one.py`（34 行）→ 与 `oa_workflow_ones.py --capture` 等价，已被吸收；
- `todo_dist.py`（58 行）→ 由 `oa_todo_dist.py` 取代（新增双口径 + 树计数 + flag 修复）。
- `probe*.py` / `dump*.py` / `proj_*.py` / `fields_of.py` 等 → 一次性侦察，
  结论已固化在本文件第三/四节，脚本本身不入库（避免沉没成本资产化）。
