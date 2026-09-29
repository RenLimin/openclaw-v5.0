# DESIGN-OUTLINE - health-management v1.0

> **版本**: v1.0  
> **层级**: L3 通用业务层  
> **组件**: health-management  
> **最后更新**: 2026-09-29

---

## 1. 架构定位

```
┌─────────────────────────────────────┐
│  L4 专有业务层                        │
│  (家庭健康 / 企业健康福利 / 移动App)   │
└────────────┬────────────────────────┘
             │ import (单向依赖)
             ▼
┌─────────────────────────────────────┐
│  L3 通用业务层 — health-management    │
│  健康档案 · 体检 · 指标 · 用药         │
│  风险评估 · 健康计划                   │
└────────────┬────────────────────────┘
             │ 依赖
             ▼
┌─────────────────────────────────────┐
│  L2 基础设施层                        │
│  持久化 · 模型验证 · 可观测性           │
└─────────────────────────────────────┘
```

**核心原则**：L3 只做数据模型 + 仓储 + 业务规则，不做 UI、不做权限、不做外部集成。

---

## 2. 总体架构

### 2.1 分层结构

```
health-management/
├── repository/              # 基础设施层 — 通用仓储基类
│   └── base.py
├── profile/                 # 领域 1 — 健康档案
│   ├── models.py
│   └── repository.py
├── checkup/                 # 领域 2 — 体检记录
│   ├── models.py
│   └── repository.py
├── metrics/                 # 领域 3 — 生命体征
│   ├── models.py
│   └── repository.py
├── medication/              # 领域 4 — 用药管理
│   ├── models.py
│   └── repository.py
├── risk_assessment/         # 领域 5 — 风险评估
│   ├── models.py
│   └── repository.py
├── health_plan/             # 领域 6 — 健康计划
│   ├── models.py
│   └── repository.py
├── migrations/              # 数据库迁移
│   └── 001_initial_schema.sql
└── tests/                   # 单元测试
```

### 2.2 架构风格

- **领域驱动设计 (DDD)**: 每个健康领域独立成包，高内聚低耦合
- **Repository 模式**: 数据访问统一封装，存储后端可替换
- **贫血模型**: Pydantic 模型仅承载数据，业务逻辑在 repository 或上层 service
- **配置驱动**: 不硬编码业务规则（如指标类型、风险等级），通过枚举/配置定义

---

## 3. 模块划分与职责

| 模块 | 职责 | 核心实体 | 依赖 |
|---|---|---|---|
| `repository/base` | 通用仓储基类，提供 CRUD 模板方法 + 软删除 + 租户过滤 | BaseRepository | 无（基础设施） |
| `profile` | 健康档案管理：个人基本信息、生活方式、家族病史、过敏史 | HealthProfile | base |
| `checkup` | 体检记录：体检报告结构化存储与查询 | Checkup, CheckupItem | base |
| `metrics` | 生命体征：血压/心率/血糖/体重等指标时间序列 | VitalMetric | base |
| `medication` | 用药管理：药品信息、剂量、频次、疗程 | Medication, MedicationDose | base |
| `risk_assessment` | 风险评估记录：评估输入、结果、风险等级、建议 | RiskAssessment | base |
| `health_plan` | 健康计划：目标、计划项、执行进度、完成率 | HealthPlan, PlanItem | base |
| `migrations` | 数据库 schema 初始化与版本化 | SQL 脚本 | 无 |

### 3.1 模块间依赖规则

```
base (零依赖)
  ↑ 继承
profile / checkup / metrics / medication / risk_assessment / health_plan
  (6 个领域模块相互独立，互不 import)
```

**规则**：
- 各领域模块之间**禁止直接 import**，保持独立性
- 所有领域 repo 继承 `BaseRepository`，复用 CRUD 逻辑
- 跨领域操作由 L4 层 service 编排，L3 层不做跨领域聚合

---

## 4. 核心数据流

### 4.1 CRUD 数据流

```
L4 Service
    │
    │ 1. 构造领域模型对象 (Pydantic 验证)
    ▼
DomainRepository
    │
    │ 2. 调用 base repo 通用方法（create/update/get/delete）
    ▼
BaseRepository
    │
    │ 3. 构造 SQL，注入 tenant_id + is_deleted 过滤
    ▼
SQLite / MySQL
```

### 4.2 查询数据流

```
L4 Service
    │  get_by_id(id, tenant_id)
    │  list(filters, tenant_id)
    ▼
DomainRepository
    │  补充领域特有查询条件
    ▼
BaseRepository
    │  执行查询，自动过滤 is_deleted
    ▼
返回 Pydantic 模型列表
```

---

## 5. 数据模型大纲

### 5.1 通用字段

所有实体均包含以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 主键，UUID 格式 |
| `tenant_id` | str | 租户 ID，数据隔离 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |
| `is_deleted` | bool | 软删除标记，默认 False |

### 5.2 领域实体概要

| 实体 | 关键字段 | 说明 |
|---|---|---|
| `HealthProfile` | name, gender, birth_date, height, weight, lifestyle, family_history, allergies | 健康档案主表 |
| `Checkup` | profile_id, checkup_date, hospital, overall_assessment, items(JSON) | 体检记录 |
| `VitalMetric` | profile_id, metric_type, value, unit, measured_at, source | 生命体征指标 |
| `Medication` | profile_id, drug_name, dosage, frequency, start_date, end_date, status | 用药记录 |
| `RiskAssessment` | profile_id, assessment_type, risk_level, score, factors, recommendations, assessed_at | 风险评估 |
| `HealthPlan` | profile_id, plan_name, goal, start_date, end_date, status, items(JSON) | 健康计划 |

---

## 6. 对外接口

### 6.1 Repository 统一接口

所有领域 repo 继承 BaseRepository，提供以下方法：

```python
class BaseRepository:
    def get_by_id(self, id: str, tenant_id: str) -> Optional[ModelT]
    def list(self, tenant_id: str, **filters) -> list[ModelT]
    def create(self, obj: ModelT, tenant_id: str) -> ModelT
    def update(self, id: str, data: dict, tenant_id: str) -> ModelT
    def delete(self, id: str, tenant_id: str) -> bool  # 软删除
    def count(self, tenant_id: str, **filters) -> int
```

### 6.2 领域扩展接口

各领域 repo 在基础 CRUD 之上扩展领域特有方法，例如：

- `MetricsRepo.list_by_type(profile_id, metric_type, start_date, end_date)` — 按类型+时间范围查指标
- `CheckupRepo.compare(checkup_id_1, checkup_id_2)` — 两次体检对比
- `HealthPlanRepo.get_progress(plan_id)` — 获取计划完成率
- `MedicationRepo.get_active(profile_id)` — 获取当前在用药物

---

## 7. 非功能设计

### 7.1 性能

- 关键字段（tenant_id, profile_id, created_at, is_deleted）建立索引
- 指标表按 metric_type + measured_at 建复合索引，支撑时间范围查询
- 大字段（items JSON、recommendations 文本）按需懒加载

### 7.2 可扩展性

- 新增领域：新建包 + models.py + repository.py + 继承 BaseRepository
- 更换存储：实现新的 BaseRepository 子类，领域 repo 无需改动
- 新增字段：Pydantic 模型 + SQL migration，向后兼容

### 7.3 安全

- tenant_id 强制过滤，防止跨租户数据泄露
- 软删除不物理删除，支持审计与恢复
- Pydantic 输入验证，防止非法数据

### 7.4 可测试性

- 纯 Python 实现，依赖少，单元测试易写
- SQLite 内存数据库可用于测试
- 7 个测试文件覆盖全部领域 + base repo

---

## 8. 依赖关系

### 8.1 上游依赖（L3 → L2）

| 依赖 | 用途 |
|---|---|
| Python 3.10+ | 运行时 |
| Pydantic | 数据模型验证 |
| sqlite3 (stdlib) | 默认存储 |
| L2 持久化组件 | 数据库连接与迁移（适配层） |

### 8.2 下游依赖方（L4 → L3）

| 调用方 | 用途 |
|---|---|
| fin-l4 (健康保险模块) | 健康数据 + 保险测算 |
| 未来 L4 健康应用 | 完整健康数据底座 |

---

## 9. 演进方向

1. **计算层分离**：将分析/计算逻辑抽到独立 health-engine（类似 finance-engine 模式）
2. **事件驱动**：领域事件（指标异常、计划到期），支持订阅通知
3. **数据导出/导入**：CSV/JSON 批量导入导出能力
4. **多 profile 关联**：支持家庭成员共享档案
5. **标准化接口**：发布为独立包，统一安装
