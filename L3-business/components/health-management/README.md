# health-management

**定位：** L3 业务层 — 个人健康档案管理，覆盖健康档案、体检、用药、指标、风险评估、健康计划。

## 功能列表

- 个人健康档案（基本信息、生活方式、家族病史、过敏史）
- 体检记录管理（checkup）
- 生命体征指标追踪（metrics）
- 用药管理（medication）
- 健康风险评估（risk_assessment）
- 健康计划制定与跟踪（health_plan）
- 多租户隔离（tenant_id）
- 软删除（is_deleted）

## 目录结构

```
health-management/
├── __init__.py
├── repository/
│   ├── __init__.py
│   └── base.py                       # 通用仓储基类
├── profile/
│   ├── __init__.py
│   ├── models.py                     # HealthProfile 模型
│   └── repository.py
├── checkup/
│   ├── __init__.py
│   ├── models.py                     # 体检记录模型
│   └── repository.py
├── metrics/
│   ├── __init__.py
│   ├── models.py                     # 生命体征指标模型
│   └── repository.py
├── medication/
│   ├── __init__.py
│   ├── models.py                     # 用药模型
│   └── repository.py
├── risk_assessment/
│   ├── __init__.py
│   ├── models.py                     # 风险评估模型
│   └── repository.py
├── health_plan/
│   ├── __init__.py
│   ├── models.py                     # 健康计划模型
│   └── repository.py
├── migrations/
│   └── 001_initial_schema.sql        # 初始建表脚本（6 个领域表）
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_base_repository.py
    ├── test_profile.py
    ├── test_checkup.py
    ├── test_metrics.py
    ├── test_medication.py
    ├── test_risk_assessment.py
    └── test_health_plan.py
```

## 使用方式

```python
from profile.repository import ProfileRepo
repo = ProfileRepo()
profile = repo.get_by_id("profile-001")
```

数据库通过 `migrations/001_initial_schema.sql` 初始化。

## 依赖

- Python 3.10+
- Pydantic（模型验证）
- SQLite / MySQL（通过 repository 层适配）
