# health-management — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+
- Pydantic: `pip install pydantic`

### 1.2 安装步骤

```bash
cd L3-business/components/health-management
pip install pydantic
```

### 1.3 启动命令

本组件为库模式，由 L4 层调用，无独立启动命令。

### 1.4 健康检查

```bash
python3 -c "from health_management import *; print('OK')"
```

## 2. 操作指南

### 2.1 场景一：创建健康档案

```python
from health_management.profile import HealthProfile, HealthProfileRepository
repo = HealthProfileRepository()
profile = repo.create(HealthProfile(name="张三", age=30))
```

### 2.2 场景二：添加体检记录

```python
from health_management.checkup import Checkup, CheckupRepository
repo = CheckupRepository()
checkup = repo.create(Checkup(profile_id=profile.id, results={...}))
```

### 2.3 场景三：跟踪指标

```python
from health_management.metrics import Metrics, MetricsRepository
repo = MetricsRepository()
metrics = repo.create(Metrics(profile_id=profile.id, systolic=120, diastolic=80))
```

## 3. 配置说明

### 3.1 配置文件

无外部配置，纯逻辑层。

### 3.2 默认值

- 存储: SQLite
- 多租户: tenant_id 隔离
- 删除: 软删除（is_deleted）

## 4. 故障排查

### 4.1 数据验证失败

- **症状**: 创建记录报错
- **原因**: 数据不符合 Pydantic 模型
- **解决**: 检查输入数据类型和范围

### 4.2 租户数据泄露

- **症状**: 看到其他租户数据
- **原因**: tenant_id 未正确隔离
- **解决**: 检查 Repository 层的 tenant_id 过滤

## 5. FAQ

**Q1: 如何扩展新领域？**
A: 在 `health-management/` 下创建新目录，定义 models.py + repository.py

**Q2: 支持多租户吗？**
A: 支持，所有模型携带 tenant_id

## 6. 附录

### 6.1 接口清单

- `BaseRepository`: get_by_id / create / update / delete
- `HealthProfileRepository`: 档案 CRUD
- `CheckupRepository`: 体检 CRUD
- `MetricsRepository`: 指标 CRUD
- `MedicationRepository`: 用药 CRUD
- `RiskAssessmentRepository`: 风险 CRUD
- `HealthPlanRepository`: 计划 CRUD

### 6.2 数据库表结构

6 个领域表: profile / checkup / metrics / medication / risk_assessment / health_plan
