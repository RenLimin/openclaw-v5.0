# cissp-learning

**定位：** L3 业务层 — CISSP 认证学习管理系统，覆盖学习计划、知识点、题库、笔记。

## 功能列表

- 学习计划管理（状态机：草稿→进行中→暂停→完成→归档）
- 知识点管理（知识域/知识域条目）
- 题库与测验（答题、评分、正确率统计）
- 学习笔记（关联知识点）
- 学习进度跟踪
- 多租户隔离（tenant_id）
- 软删除（is_deleted）

## 目录结构

```
cissp-learning/
├── __init__.py
├── base/
│   ├── __init__.py
│   ├── base_model.py             # 统一数据模型基类
│   └── base_repository.py        # 通用仓储基类
├── models/
│   ├── __init__.py
│   ├── learning_plan.py          # 学习计划领域模型
│   ├── knowledge_point.py        # 知识点模型
│   ├── quiz.py                   # 题库/测验模型
│   ├── learning_progress.py      # 学习进度模型
│   └── note.py                   # 笔记模型
├── repositories/
│   ├── __init__.py
│   ├── learning_plan_repo.py
│   ├── knowledge_point_repo.py
│   ├── quiz_repo.py
│   ├── learning_progress_repo.py
│   └── note_repo.py
├── migrations/
│   └── 001_initial_schema.sql    # 初始建表脚本
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_base_repository.py
    ├── test_learning_plan.py
    ├── test_knowledge_point.py
    ├── test_quiz.py
    ├── test_note.py
    └── test_learning_progress.py
```

## 使用方式

```python
from repositories.learning_plan_repo import LearningPlanRepo
repo = LearningPlanRepo()
plan = repo.get_by_id("plan-001")
```

数据库通过 `migrations/001_initial_schema.sql` 初始化。

## 依赖

- Python 3.10+
- Pydantic（模型验证）
- SQLite / MySQL（通过 repository 层适配）
