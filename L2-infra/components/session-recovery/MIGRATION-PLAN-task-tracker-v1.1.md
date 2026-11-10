# task_tracker 分文件化 — 数据迁移方案 (MIGRATION-PLAN v1.1)

> 版本：v1.1 · 日期：2026-11-10 · 状态：⏳ 待 Rex 确认
> 原则：**不替任何业务会话伪造/还原/清理状态**；历史数据只登记、不自动改写；本次事故污染现场冻结留证，处置方式由 Rex 拍板。

## 1. 现状盘点（2026-11-10 21:00 实测）

| 数据源 | 现状 | 处置 |
|---|---|---|
| `memory/current-task.md` | **存在且被污染**：task_id=`task-20261110-task-tracker-concurrency`（本会话）、session_key=本会话，但 phase/step/progress 是另一会话（21:00:36 update，Phase1取数解析/step6）写入的内容 | 冻结留证（§2），不自动迁移 |
| `memory/task-history/` | 约 200+ 归档；同一 task_id 多条记录：`task-20261106-ccb-report`×4、`task-20260920-bdms-v21-mvp`×4、`task-20261031-bdms-acceptance`×3 等 | 只登记清单（§4），不自动清洗 |
| `memory/tasks/active/` | v1.1 新目录，当前不存在 | 由实现创建 |

## 2. 本次事故污染现场处置（待拍板）

### 2.1 冻结留证（建议立即执行，无副作用）

```
memory/evidence/20261110-task-tracker-pollution/
├── current-task.md.bak          # 污染现场完整原文（含 frontmatter + 进度）
├── analysis.json                # 解析后的双会话成分拆分（我的 task_id/session_key + 对方 phase/step/progress）
└── README.md                    # 时间线 + 证据链（含 21:00 活体复现记录）
```

冻结动作 = 只读复制 + 记录，**不改动原文件、不删除、不还原**。

### 2.2 原文件处置选项（Rex 三选一）

| 选项 | 动作 | 后果 | Jerry 建议 |
|---|---|---|---|
| A | 冻结后删除 current-task.md | 干净；本任务实现阶段重新 start 登记真实状态 | ⭐ 建议：符合「不还原业务状态」红线，污染不留痕 |
| B | 冻结后重建为本会话真实状态（phase=设计变更文档, step=0） | 相当于修复本次误覆盖 | 需要 Rex 确认该文件确属本会话且无其他会话依赖 |
| C | 保持原样不动 | 污染持续存在，check_and_retry/lane_d 读到的仍是假状态 | 不推荐 |

> 任何选项都不影响**另一会话**自身状态：它已不在 current-task.md 中（它的任务本应属于它自己的分文件），v1.1 上线后它会走自己的文件。

## 3. legacy current-task.md 迁移（v1.1 migrate 子命令）

适用：未来任何时刻 current-task.md 中**无污染嫌疑**的有效记录（含历史遗留，如故障恢复后主会话留下的任务）。

| 步骤 | 命令 | 行为 |
|---|---|---|
| 1 | `task_tracker.py migrate --dry-run` | 只读解析，输出将迁移的记录（task_id/name/session_key 来源/目标文件名），**零写入** |
| 2 | `task_tracker.py migrate --apply` | 写入 `tasks/active/<safe>__<hash8>.md`；`session_key` 取值优先级：`--session-key` > env `TASK_TRACKER_SESSION_KEY` > frontmatter 既有值 > `unknown-legacy` 占位（并在进度条记录「⚠️ legacy 迁移：无 session_key」） |
| 3 | 人工确认 | 原 current-task.md 默认**保留**（`--remove-original` 才删除），删除前 diff 确认 |

验收：dry-run 后文件数不变；apply 后分文件内容与原记录逐字段一致（时间戳、进度条目、failure_count）。

## 4. task-history 历史污染登记（只登记，不清洗）

执行 `migrate` 不影响归档；另提供只读盘点命令 `history-check`（新增，可选）：

```
task_tracker.py history-check --dup-by task_id
→ 输出同一 task_id 出现多次的清单：文件名 / archived_at / archive_reason / result 摘要
```

- 用途：让 Rex 看到哪些归档是并发污染的产物，人工决定是否补标 `archive_reason: polluted`（**v1.1 不自动补标**）。
- 已知重复（2026-11-10 实测）：ccb-report×4、bdms-v21-mvp×4、bdms-acceptance×3、system-governor×2、ccb-comprehensive×2、revenue-forecast×2 等。

## 5. 执行顺序（评审通过后）

1. 冻结留证（§2.1，立即做）
2. 按 Rex 选择处理原文件（§2.2）
3. 实现 v1.1（分文件 + 校验 + 锁 + current --all + migrate + history-check）
4. `migrate --dry-run` 预检 → `--apply` 迁移无污染遗留记录
5. 下游适配（check_and_retry / lane_d / scan_errors）+ 全量测试
6. 文档同步（LONG-TASK-SPEC / DESIGN.md / README / OPERATIONS / AGENTS.md 红线更新）

## 6. 验收

- 污染现场按 Rex 选定选项处置完毕，证据链完整（README 可审计）。
- migrate dry-run/apply 行为与 §3 一致；原文件默认保留。
- `history-check` 输出重复归档清单，全部为登记态，无自动改写。
