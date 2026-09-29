# OPERATIONS - health-management v1.0

> **版本**: v1.0  
> **组件**: health-management  
> **层级**: L3 通用业务层  
> **最后更新**: 2026-09-29

---

## 1. 安装与初始化

### 1.1 环境要求

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 需要 match statement / 新 typing 语法 |
| Pydantic | 2.0+ | 数据模型验证 |
| SQLite | 3.30+ | 关系型存储（可选，v1.0 默认内存版） |

### 1.2 安装步骤

本组件为 L3 纯 Python 库，无需独立安装，由 L4 层通过 import 引入。

```bash
# 确认 Python 版本
python3 --version  # 需 >= 3.10

# 安装依赖
pip install pydantic>=2.0

# 克隆或确认组件位置
ls L3-business/components/health-management/
```

### 1.3 L4 层接入

在 L4 业务层中通过 sys.path 注入后 import：

```python
import sys
import os

# 将 L3 组件加入 Python 路径
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '../../L3-business/components/health-management'
)))

# 导入需要的模块
from profile.models import HealthProfile
from profile.repository import ProfileRepo
from repository.base import set_current_tenant, reset_current_tenant
```

> **注意**：确保单向依赖（L4 → L3），L3 代码中不 import 任何 L4 模块。

### 1.4 数据库初始化（关系型存储时）

使用内存版存储时**无需初始化**。若切换到关系型数据库：

```bash
# 执行迁移脚本
sqlite3 health.db < L3-business/components/health-management/migrations/001_initial_schema.sql

# 验证表结构
sqlite3 health.db ".tables"
# 预期输出: health_profiles checkup_records metrics_records
#           medication_records risk_assessments health_plans
```

---

## 2. 快速上手

### 2.1 基本使用流程

```python
from repository.base import set_current_tenant, reset_current_tenant
from profile.models import HealthProfile, Gender
from profile.repository import ProfileRepo
from metrics.models import MetricsRecord, MetricsType
from metrics.repository import MetricsRepo

# 1. 设置租户上下文
token = set_current_tenant("tenant-001")
try:
    # 2. 创建健康档案
    profile = ProfileRepo.create(
        name="张三",
        gender=Gender.MALE,
        birth_date="1990-06-15",
        height_cm=175.0,
        weight_kg=70.0,
    )
    print(f"创建档案: {profile.id}, BMI: {profile.bmi}")

    # 3. 记录指标
    metric = MetricsRepo.create(
        profile_id=profile.id,
        metrics_type=MetricsType.BLOOD_PRESSURE_SYSTOLIC,
        value=128.0,
    )
    print(f"记录指标: {metric.metrics_type} = {metric.value} {metric.unit}")

    # 4. 查询档案
    found = ProfileRepo.get_by_id(profile.id)
    print(f"查询到: {found.name}, 年龄: {found.age}")

finally:
    reset_current_tenant(token)
```

### 2.2 典型场景示例

#### 场景 1：创建完整健康档案

```python
from profile.models import HealthProfile, Gender, BloodType, MaritalStatus
from profile.repository import ProfileRepo

profile = ProfileRepo.create(
    name="李四",
    gender=Gender.FEMALE,
    birth_date="1988-03-22",
    height_cm=165.0,
    weight_kg=58.0,
    blood_type=BloodType.A,
    marital_status=MaritalStatus.MARRIED,
    smoking_status="never",
    drinking_status="occasional",
    exercise_hours_per_week=3.5,
    sleep_hours_per_day=7.5,
    dietary_preference="normal",
    allergies=["青霉素", "海鲜"],
    chronic_diseases=["偏头痛"],
    family_history=["高血压（母亲）", "糖尿病（父亲）"],
)
```

#### 场景 2：录入体检报告并统计异常

```python
from checkup.models import CheckupRecord, CheckupItem, CheckupStatus
from checkup.repository import CheckupRepo
from datetime import date

checkup = CheckupRepo.create(
    profile_id=profile.id,
    checkup_date=date.today(),
    hospital="北京协和医院",
    checkup_type="annual",
    status=CheckupStatus.REPORT_READY,
    overall_summary="总体良好，血压略高，建议复查",
    items=[
        CheckupItem(item_code="BP_SYS", item_name="收缩压", value=142, unit="mmHg",
                     reference_range="90-140", is_abnormal=True, abnormal_flag="high"),
        CheckupItem(item_code="BP_DIA", item_name="舒张压", value=88, unit="mmHg",
                     reference_range="60-90", is_abnormal=False),
        CheckupItem(item_code="GLU_F", item_name="空腹血糖", value=5.6, unit="mmol/L",
                     reference_range="3.9-6.1", is_abnormal=False),
        # ... 更多项目
    ]
)

print(f"异常项目数: {checkup.abnormal_count} / {checkup.total_items}")
for item in checkup.abnormal_items:
    print(f"  ⚠️ {item.item_name}: {item.value} {item.unit} (参考: {item.reference_range})")
```

#### 场景 3：记录 30 天血压并查询趋势

```python
from metrics.models import MetricsRecord, MetricsType, MetricSource
from metrics.repository import MetricsRepo
from datetime import datetime, timedelta

# 批量录入 30 天血压
for i in range(30):
    d = datetime.utcnow() - timedelta(days=29 - i)
    MetricsRepo.create(
        profile_id=profile.id,
        metrics_type=MetricsType.BLOOD_PRESSURE_SYSTOLIC,
        value=120 + i * 0.5,  # 模拟逐渐升高
        measured_at=d,
        source=MetricSource.BLOOD_PRESSURE_MONITOR,
    )

# 查询最近 7 天收缩压
records = MetricsRepo.filter(
    profile_id=profile.id,
    metrics_type=MetricsType.BLOOD_PRESSURE_SYSTOLIC,
    limit=7,
)
for r in records:
    print(f"{r.measured_at.date()}: {r.value} {r.unit}")
```

#### 场景 4：用药管理

```python
from medication.models import MedicationRecord, MedicationFrequency, MedicationStatus
from medication.repository import MedicationRepo

med = MedicationRepo.create(
    profile_id=profile.id,
    drug_name="苯磺酸氨氯地平片",
    brand_name="络活喜",
    drug_category="降压药",
    dosage="5mg",
    strength="5mg×7片",
    form="片剂",
    frequency=MedicationFrequency.ONCE_DAILY,
    route="口服",
    start_date=date.today(),
    duration_days=30,
    reminder_enabled=True,
    reminder_times=["08:00"],
)

print(f"今日是否用药: {med.is_active_today}")
print(f"剩余天数: {med.days_remaining}")
```

#### 场景 5：健康计划与进度跟踪

```python
from health_plan.models import (
    HealthPlan, PlanType, PlanStatus, PlanTask, TaskStatus,
    PlanMilestone,
)
from health_plan.repository import HealthPlanRepo
from datetime import date, timedelta

plan = HealthPlanRepo.create(
    profile_id=profile.id,
    plan_name="30天减重计划",
    plan_type=PlanType.WEIGHT_LOSS,
    start_date=date.today(),
    end_date=date.today() + timedelta(days=30),
    overall_goal="减重 3kg",
    goals=["每周运动 5 次", "控制饮食热量", "每日步行 8000 步"],
    status=PlanStatus.ACTIVE,
    baseline_metrics={"weight": 70.0, "bmi": 22.86},
    target_metrics={"weight": 67.0, "bmi": 22.0},
    tasks=[
        PlanTask(title="每日步行 8000 步", category="运动", frequency="daily", priority=2),
        PlanTask(title="每周 3 次力量训练", category="运动", frequency="weekly", priority=3),
        PlanTask(title="控制每日热量摄入", category="饮食", frequency="daily", priority=2),
    ],
    milestones=[
        PlanMilestone(title="第一周适应期", target_date=date.today() + timedelta(days=7)),
        PlanMilestone(title="减重 1.5kg", target_date=date.today() + timedelta(days=15)),
        PlanMilestone(title="目标达成", target_date=date.today() + timedelta(days=30)),
    ]
)

# 更新任务进度
plan = HealthPlanRepo.get_by_id(plan.id)
plan.update_task_progress(plan.tasks[0].task_id, 100.0)
plan.update_task_progress(plan.tasks[1].task_id, 50.0)

print(f"整体进度: {plan.overall_progress}%")
print(f"完成任务: {plan.completed_tasks_count} / {plan.total_tasks_count}")
```

---

## 3. 配置指南

### 3.1 租户上下文配置

```python
from repository.base import set_current_tenant, reset_current_tenant

# 方式 1：手动管理（推荐）
token = set_current_tenant("my-tenant-id")
try:
    # ... 业务操作 ...
finally:
    reset_current_tenant(token)

# 方式 2：上下文管理器封装
from contextlib import contextmanager

@contextmanager
def tenant_context(tenant_id: str):
    token = set_current_tenant(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant(token)

with tenant_context("tenant-001"):
    ProfileRepo.create(name="王五", gender="male", birth_date="1990-01-01")
```

### 3.2 指标类型扩展

新增指标类型时，在 `MetricsType` 枚举中添加，并在 `MetricsRecord._fill_default_unit` 中补充默认单位映射。

### 3.3 存储后端切换

v1.0 为内存版。切换到关系型数据库：

1. 实现 `BaseRepository` 的 SQLAlchemy 版本
2. 各领域 repo 继承新的基类
3. 领域 models 保持不变（Pydantic ↔ ORM 模型做映射）

---

## 4. 测试运行

```bash
# 进入组件目录
cd L3-business/components/health-management

# 运行全部测试
python -m pytest tests/ -v

# 运行指定模块
python -m pytest tests/test_profile.py -v
python -m pytest tests/test_metrics.py -v

# 运行并生成覆盖率报告
python -m pytest tests/ --cov=. --cov-report=term-missing

# 运行特定测试用例
python -m pytest tests/test_health_plan.py::test_update_task_progress -v
```

---

## 5. 故障排查

### 5.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|---|---|---|
| `RuntimeError: No tenant context set` | 未调用 `set_current_tenant()` | CRUD 前先设置租户上下文 |
| `ValueError: tenant_id mismatch` | 显式传入的 tenant_id 与上下文不一致 | 不要手动传 tenant_id，让系统自动注入 |
| `ValueError: xxx id=yyy already exists` | 手动指定了已存在的 id | 不手动传 id，让系统自动生成 UUID |
| `ValueError: xxx id=yyy not found` | ID 不存在或已被软删除 | 检查 ID 拼写，确认记录未被删除 |
| `ValidationError` | 字段值不符合 Pydantic 校验规则 | 检查字段类型、范围、枚举值 |
| ImportError: No module named 'repository' | Python 路径未正确配置 | 确认 sys.path 包含 health-management 目录 |
| 测试间数据串扰 | 测试未清理 store | 在 conftest 中每个测试前调用 `_reset_store()` |

### 5.2 调试技巧

```python
# 1. 查看当前租户
from repository.base import _current_tenant_var
print(f"当前租户: {_current_tenant_var.get()}")

# 2. 查看存储中的数据量（调试用）
from profile.repository import ProfileRepo
print(f"档案总数: {ProfileRepo.count()}")

# 3. 完整查看 store 结构（仅限调试）
from repository.base import BaseRepository
print(BaseRepository._store.keys())  # 所有 tenant_id
```

### 5.3 性能问题排查

| 现象 | 可能原因 | 排查方法 |
|---|---|---|
| list 大量数据慢 | 全量排序 + 分页在 Python 层做 | 考虑切换到数据库版，用 SQL 排序 |
| filter 慢 | 每次遍历全量数据 | 对高频过滤字段建索引（切换 DB 版） |
| 并发性能差 | 全局 RLock 串行化 | 按 tenant_id 细粒度锁（按需优化） |

---

## 6. 升级与迁移

### 6.1 版本升级

本组件遵循语义化版本（SemVer）：
- **PATCH** (x.y.Z)：bug 修复，向后兼容
- **MINOR** (x.Y.z)：新增功能，向后兼容
- **MAJOR** (X.y.z)：不兼容变更

### 6.2 数据迁移

- **v1.0 内存版 → 关系型版**：编写导出脚本，将内存数据序列化为 JSON 后导入数据库
- **新增字段**：Pydantic 模型提供默认值，保证向后兼容
- **新增领域模块**：新增包 + models + repository + 迁移脚本，不影响已有模块

---

## 7. 架构边界

### 7.1 本组件负责

- ✅ 健康数据模型定义与验证
- ✅ 健康数据 CRUD 操作
- ✅ 多租户数据隔离
- ✅ 软删除
- ✅ 领域内轻量计算属性（BMI、年龄、进度等）

### 7.2 本组件不负责

- ❌ Web UI / REST API
- ❌ 用户认证与权限控制
- ❌ 复杂健康分析与计算（交由 health-engine）
- ❌ 外部设备数据同步
- ❌ 消息通知
- ❌ 数据持久化实现细节（由存储层负责）

---

## 8. FAQ

**Q: 为什么用内存存储？生产环境能用吗？**  
A: v1.0 内存版用于快速验证和单元测试。生产环境应实现数据库版 BaseRepository，接口保持一致。

**Q: 指标类型能自定义吗？**  
A: 可以，在 `MetricsType` 枚举中添加新值，并补充默认单位映射即可。

**Q: 跨领域查询怎么做？比如"查询某个用户所有异常指标和体检异常"？**  
A: 在 L4 层 service 中分别调用各领域 repo，然后聚合结果。L3 层不做跨领域 join，保持领域独立性。

**Q: 软删除的数据怎么恢复？**  
A: v1.0 未提供官方恢复 API。可直接操作存储层将 `is_deleted` 设回 False，或在 repository 子类中扩展 `restore()` 方法。

**Q: 支持 MySQL / PostgreSQL 吗？**  
A: 模型设计兼容关系型数据库，迁移脚本按 SQLite 编写。切换到 MySQL/PostgreSQL 需调整 SQL 语法和数据类型。
