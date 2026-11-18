# OA 项目实施流程 → ONES 字段映射（技术链路验证 2026-11-13；v2 2026-11-18）

## 一、OA 三类流程（workflowid 已验证）

| 流程 | workflowid | 说明 |
|---|---|---|
| PoC需求申请流程 | 820 | POC 类待办 |
| 提前实施需求申请流程 | 815 | 提前实施类待办 |
| 销售合同下单流程（数据审核触发） | 916 | 签约项目类待办 |
| 销售合同验收文件归档流程 | 840 | 验收归档待办 |

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
