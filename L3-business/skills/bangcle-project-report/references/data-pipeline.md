# 数据管道参考：分页、触顶、合同字段、时间戳归一

> 本文件为 `bangcle-project-report` P1 取数脚本的参考文档。
> 既有实测参考：`L3-business/skills/bangcle-project-summary/references/ones-query.md`。

## 1. 鉴权

- 登录态 token 存于浏览器 `localStorage['ct']`（用户标识 `localStorage['user_id']`）。
- 同源页面内 `fetch` 调内部 API，请求头加 `Ones-Auth-Token: <ct>`（cookie 亦可）。
- **脚本不接触/不存储 token**：osascript 注入 JS → 页面内读取 → 请求头携带。
- 若登录接口限流（801），用浏览器自动化从已登录页面 localStorage 取 token（见 `ones-browser-export`）。
- async fetch 在 osascript 注入时返回 Promise 取不到值 → 写入全局变量 `window.__r` 后轮询读取。

## 2. GraphQL 端点

```
POST https://ones.bangcle.com/project/api/project/team/<team_uuid>/items/graphql
```

- 默认 `team_uuid = RZxvwUZ8`（可通过入参 `teamUUID` 覆盖）。
- 请求头：`Content-Type: application/json`、`Ones-Auth-Token: <ct>`。
- 请求体：`{"query": "<graphql>"}`。

### 关键：必须使用 `query { ... }` 包装器

实测：裸写 `tasks(filter:...)` 返回 `{"code":500,"errcode":"ServerError"}`。
必须写成 `query { tasks(filter:...) { ... } }` 才能正常返回。

### 项目枚举

```graphql
query { projects { uuid name _7KF6tXvk } }
```

### 逐项目任务

```graphql
query {
  tasks(filter:{project_in:["<pUUID>"]}) {
    number uuid name statusCategory createTime
    status { name category }
    owner { name }
    issueType { name }
    project { uuid name }
    products { uuid name }
    descriptionText
  }
}
```

## 3. 分页策略（实测行为）

> ⚠️ **实测发现**：ONES GraphQL 的 `tasks` 字段**忽略** `page` / `pageSize` 参数，
> 返回全部匹配任务。`page:1` 与 `page:2` 返回相同结果。

因此本脚本采用以下策略：

| 策略 | 说明 |
|---|---|
| 全量拉取 | 按 `project_in` 过滤，一次拉取该项目全部任务 |
| 条数校验 | 返回条数 `>= TASK_CAP`（5000）视为触顶截断 |
| 触顶标记 | `hitCap=true` → `completeness.globalTruncated=true` → 退出码 2 |
| 满页确认 | 若未来 API 支持分页，恢复 `page/pageSize` + 末页满页再拉一页确认 |

### 限流处理

- 限流错误码 `801`：指数退避（2s、4s、8s），最多重试 3 次。
- 3 次失败 → 停手，退出码 2。

### 安全阀

- 单项目任务数 `>= 5000` → 标记触顶，退出码 2。
- 防止无限循环：无（全量拉取模式无循环）。

## 4. 合同字段

- 项目合同金额字段：`Project._7KF6tXvk`，uuid `CAaTom7U`。
- 实时查询，不缓存；缺失时显式保留 `null` 并标记【缺失】。

## 5. 时间戳归一

| 字段来源 | 单位 | 处理 |
|---|---|---|
| Task 主字段（`createTime` 等） | **微秒** | 除以 1,000,000 转秒 |
| 评论 `createTime` | **秒** | 直接使用 |

- 统一按 `Asia/Shanghai`（UTC+8）转换为可读时间。
- 入参 `period.start` / `period.end` 为 `YYYY-MM-DD`，按 Asia/Shanghai 解释。

## 6. 错误处理

| 场景 | 行为 | 退出码 |
|---|---|---|
| 项目枚举失败 | stderr 报错，stdout 输出 `{"error": ...}` | 2 |
| 单项目任务拉取失败 | 同上 | 2 |
| 限流 801 重试 3 次仍失败 | 同上 | 2 |
| 触顶未确认（`hitCap`） | 正常输出数据，`completeness.globalTruncated=true` | 2 |
| 成功 | 输出完整 JSON | 0 |

## 7. 输出契约

```json
{
  "projects": [{"projectUUID": "...", "projectCode": "...", "projectName": "...", "contractNo": "...", "standardProduct": null, "status": "unknown"}],
  "tasks": [{"number": 0, "uuid": "...", "name": "...", "statusCategory": "...", "createTime": 0, "status": {"name": "...", "category": "..."}, "owner": {"name": "..."}, "issueType": {"name": "..."}, "project": {"uuid": "...", "name": "..."}, "products": [{"uuid": "...", "name": "..."}], "descriptionText": "..."}],
  "completeness": {
    "fetchedAt": "ISO8601",
    "perProject": {"<code>": {"fetched": 0, "total": 0, "hitCap": false}},
    "globalTruncated": false
  }
}
```

- 字段缺失：`null` 显式保留 + 标记【缺失】。
- 中间产物落 `analysis_output/ones_raw/`。
