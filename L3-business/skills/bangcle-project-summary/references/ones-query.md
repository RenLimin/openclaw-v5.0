# ONES 数据查询参考（实测有效）

> 团队/项目 UUID 随客户而变；以下为本工作区实测的方法与路径。

## 鉴权

- 登录态 token 存于浏览器 `localStorage['ct']`；用户在 `localStorage['user_id']`。
- 同源页面内 fetch 调内部 API，请求头加 `Ones-Auth-Token: <ct>`（cookie 亦可）。
- 若登录接口限流（801），用浏览器自动化从已登录页面 localStorage 取 token（见 ones-browser-export）。
- async fetch 在 osascript 注入时返回 Promise 取不到值 → 写入全局变量后轮询读取。

## GraphQL 端点

```
POST https://ones.bangcle.com/project/api/project/team/<team_uuid>/items/graphql
```

## 实测语法

- 客户模糊匹配：`tasks(filter: {name_match: "客户名"})`
- 编号批量：`tasks(filter: {number_in: [373500, ...]})`
- UUID 批量：`tasks(filter: {uuid_in: [...]})`
- 类型过滤：`issueType: {uuid_equal: "<issue_type_uuid>"}`
- 项目过滤：`project_in: [<project_uuid>]`
- 父任务下钻：`tasks(filter: {parent_uuid_in: [<task_uuid>]})` 或 `subTasks { number name status { name } }`

## Task 常用字段注意（对象类型必须带选择集）

- 标量：`number uuid name descriptionText createTime planStartDate planEndDate progress statusCategory attachmentCount discussionCount`
- 对象：`status { name category }`、`owner { name }`、`issueType { name }`、`project { uuid name }`、`parent { number name }`
- 列表对象：`products { uuid name }`、`attachments { uuid name mime size createTime ownerName }`
- `publishVersion` 是 **Task 对象列表**（不是标量），必须带 `{ ... }`
- `links` 是 `{ taskUUID linkDescType createTime }`，关联任务需按 UUID 二次拉取

## 评论

```graphql
{ commonComments(filter: {objectId_in: [<task_uuids>], objectType_equal: "task"})
  { objectId message createTime fromUser { name } messageType } }
```

## issueType 内省

- 履约义务类型 uuid 随环境而异，先查：`{ issueTypes { uuid name } }` 定位「项目履约义务」（实测示例 `WEpkPvew`）。

## 内省限制

- 可查 `{ __schema { queryType { fields { name } } } }` 与 `__schema { types { name fields { name } } }`
- `__type(name:...)` 被禁用，会报 `Malformed.GraphQL`。

## 时间戳

- Task 主字段（createTime 等）为**微秒**；评论 createTime 为**秒**。按 Asia/Shanghai 转换。
