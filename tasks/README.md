# tasks/ — 任务协议目录

> L2 会话隔离与共享组件（ADR-202609-024）的任务协议载体。
> 设计文档: `docs/architecture/components/session-isolation-sharing/DESIGN.md`

## 目录结构

| 目录 | 用途 |
|---|---|
| `_templates/` | 模板文件（TASK.yml 模板等） |
| `in-progress/` | 进行中的任务卡（`<task_id>/TASK.yml`） |
| `done/` | 已完成的任务卡 |
| `archive/` | 归档的任务卡（含事件日志） |

## 使用流程

1. **创建任务**: 复制 `_templates/TASK.yml` 到 `in-progress/<task_id>/`
2. **启动任务**: 会话读取 `TASK.yml` + `CONTEXT.md` 恢复现场
3. **更新进度**: 修改 `goals[].status` + `updated_at`
4. **记录事件**: 追加到 `in-progress/<task_id>/events.jsonl`
5. **完成任务**: 移到 `done/`，产出物记入 `artifacts`

## 隔离规则

- `tasks/` 目录**不在**会话生命周期清理范围（ADR-013 cleanup 需排除）
- 共享状态在 `state/` 目录（State Protocol），任务卡只放任务定义
