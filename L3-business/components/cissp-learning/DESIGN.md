# cissp-learning

## 设计目标

为 CISSP 认证学习提供结构化管理能力，覆盖学习计划、知识点、题库、笔记、进度跟踪五大领域。解决学习内容碎片化、进度不可视、复习无规律的问题。

## 架构决策

- **领域驱动分层**：models/ 定义领域模型，repositories/ 负责数据访问，base/ 提供通用基类
- **多租户隔离**：所有模型携带 `tenant_id`，数据按租户隔离
- **软删除**：通过 `is_deleted` 标记实现，保留数据可恢复
- **Pydantic 模型验证**：统一使用 Pydantic 做数据校验，保证入库数据一致性
- **状态机管理学习计划**：学习计划使用显式状态机（草稿→进行中→暂停→完成→归档）

## 模块划分

```
cissp-learning/
├── base/                       # 基础设施层
│   ├── base_model.py           # 统一数据模型基类（tenant_id + CRUD）
│   └── base_repository.py      # 通用仓储基类
├── models/                     # 领域模型
│   ├── learning_plan.py        # 学习计划（状态机）
│   ├── knowledge_point.py      # 知识点（知识域/条目）
│   ├── quiz.py                 # 题库/测验
│   ├── learning_progress.py    # 学习进度
│   └── note.py                 # 笔记
├── repositories/               # 仓储层
│   ├── learning_plan_repo.py
│   ├── knowledge_point_repo.py
│   ├── quiz_repo.py
│   ├── learning_progress_repo.py
│   └── note_repo.py
├── migrations/
│   └── 001_initial_schema.sql  # 初始建表脚本
└── tests/                      # 单元测试（每个模型/仓储对应测试）
```

## 关键接口/数据结构

- `BaseModel`：所有模型的基类，提供 `tenant_id`、`created_at`、`updated_at`、`is_deleted`
- `BaseRepository`：通用仓储，提供 `get_by_id`、`create`、`update`、`delete`（软删除）
- `LearningPlan`：学习计划模型，含状态字段 `status`（draft/active/paused/completed/archived）
- `KnowledgePoint`：知识点模型，关联知识域和条目
- `Quiz`：题库模型，支持答题与评分
- `LearningProgress`：进度模型，跟踪学习完成度
- `Note`：笔记模型，关联知识点

## 依赖关系

- **依赖**：Python 3.10+、Pydantic、SQLite/MySQL
- **被依赖**：`cissp-trainer`（L4 层，复用学习规划与题库数据）

## 演进方向

1. **与 cissp-trainer 双向联动**：学习计划与智能出题引擎打通
2. **Anki 同步**：笔记和知识点导出为 Anki 卡片
3. **学习报告**：基于进度数据生成周/月报告
4. **多用户协作**：租户内多人共享学习计划
