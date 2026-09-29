# DESIGN-DETAIL - health-management v1.0

> **版本**: v1.0  
> **层级**: L3 通用业务层  
> **组件**: health-management  
> **最后更新**: 2026-09-29

---

## 1. 接口契约

### 1.1 BaseRepository 接口

所有领域仓储继承自 `BaseRepository[T]`，提供统一的 CRUD 接口。

```python
class BaseRepository(Generic[T]):
    """内存版数据仓库基类，支持多租户隔离。"""

    # 类属性：子类必须覆盖
    model_cls: Type[T]

    # CRUD
    @classmethod
    def create(cls, **data: Any) -> T: ...
    @classmethod
    def get_by_id(cls, item_id: str) -> Optional[T]: ...
    @classmethod
    def list(cls, *, limit: int = 100, offset: int = 0) -> List[T]: ...
    @classmethod
    def filter(cls, *, limit: int = 100, offset: int = 0, **conditions: Any) -> List[T]: ...
    @classmethod
    def update(cls, item_id: str, **updates: Any) -> T: ...
    @classmethod
    def delete(cls, item_id: str) -> None: ...  # 软删除
    @classmethod
    def count(cls) -> int: ...
```

**关键行为**：

| 方法 | 租户过滤 | 软删除过滤 | 返回副本 | 线程安全 |
|---|---|---|---|---|
| `create` | 自动绑定当前 tenant | - | 原对象引用 | ✅ RLock |
| `get_by_id` | ✅ 仅当前租户 | ✅ 跳过 is_deleted | ✅ model_copy() | ✅ |
| `list` | ✅ | ✅ | ✅ | ✅ |
| `filter` | ✅ | ✅ | ✅ | ✅ |
| `update` | ✅ | ✅ 已删除抛 ValueError | ✅ | ✅ |
| `delete` | ✅ | 设 is_deleted=True | - | ✅ |
| `count` | ✅ | ✅ | int | ✅ |

### 1.2 租户上下文管理

```python
# 设置当前租户（返回 token 用于 reset）
def set_current_tenant(tenant_id: str) -> Any: ...

# 重置租户上下文
def reset_current_tenant(token: Any) -> None: ...

# 获取当前租户，未设置时抛 RuntimeError
def _current_tenant() -> str: ...
```

**使用模式**：
```python
token = set_current_tenant("tenant-001")
try:
    profile = ProfileRepo.create(name="张三", birth_date="1990-01-01")
    result = ProfileRepo.get_by_id(profile.id)
finally:
    reset_current_tenant(token)
```

### 1.3 领域 Repository 接口

各领域 repo 为薄封装，继承 BaseRepository 后指定 model_cls 即可：

```python
class ProfileRepo(BaseRepository[HealthProfile]):
    model_cls = HealthProfile

class CheckupRepo(BaseRepository[CheckupRecord]):
    model_cls = CheckupRecord

class MetricsRepo(BaseRepository[MetricsRecord]):
    model_cls = MetricsRecord

class MedicationRepo(BaseRepository[MedicationRecord]):
    model_cls = MedicationRecord

class RiskAssessmentRepo(BaseRepository[RiskAssessment]):
    model_cls = RiskAssessment

class HealthPlanRepo(BaseRepository[HealthPlan]):
    model_cls = HealthPlan
```

> **设计决策**：当前 v1.0 各领域 repo 仅继承 BaseRepository，无额外方法。领域特定的查询逻辑（如按 profile_id 过滤）通过 `filter(profile_id=xxx)` 实现。后续可按需扩展领域方法。

---

## 2. 数据模型

### 2.1 基类模型 — TenantModel

```python
class TenantModel(BaseModel):
    id: str                    # UUID hex，自动生成
    tenant_id: str             # 自动从当前租户上下文获取
    created_at: datetime       # 创建时间，UTC
    updated_at: datetime       # 更新时间，UTC
    is_deleted: bool = False   # 软删除标记
```

**约束**：
- `id`：创建时自动生成 UUID4 hex（32 字符）
- `tenant_id`：创建时自动从 `_current_tenant_var` 获取，不可手动指定不同值
- `created_at` / `updated_at`：UTC 时间，update 时自动刷新 updated_at
- `is_deleted`：软删除，`delete()` 方法将其设为 True

### 2.2 健康档案 — HealthProfile

```python
class HealthProfile(TenantModel):
    # 基本身份
    profile_id: str            # 业务编码，可与外部系统对齐
    name: str                  # 姓名
    gender: Gender             # MALE / FEMALE / OTHER
    birth_date: date           # 出生日期
    id_card_no: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    avatar_url: Optional[str]

    # 生理基础
    height_cm: Optional[float]  # (0, 300]
    weight_kg: Optional[float]  # (0, 500]
    blood_type: BloodType       # A / B / AB / O / UNKNOWN
    rh_factor: Optional[str]

    # 社会属性
    marital_status: MaritalStatus
    occupation: Optional[str]
    education: Optional[str]

    # 生活方式
    smoking_status: str        # never / former / current
    drinking_status: str       # never / occasional / regular / heavy
    exercise_hours_per_week: float
    sleep_hours_per_day: float
    dietary_preference: str    # normal / vegetarian / vegan / low_salt / low_sugar

    # 病史
    allergies: List[str]
    chronic_diseases: List[str]
    family_history: List[str]
    past_surgeries: List[str]

    # 状态
    is_active: bool = True
    tags: List[str]
    remark: str = ""
```

**计算属性**：
- `age: int` — 实足年龄
- `bmi: Optional[float]` — BMI = 体重(kg) / 身高(m)²
- `ideal_weight_kg: Optional[float]` — 理想体重（Broca 改良公式）

### 2.3 体检记录 — CheckupRecord

```python
class CheckupItem(BaseModel):
    item_code: str             # 项目编码
    item_name: str             # 项目名称
    category: str = ""         # 分类：血常规/生化/影像...
    result: Optional[str]      # 结果值（字符串，兼容文字描述）
    value: Optional[float]     # 数值结果（定量项目）
    unit: Optional[str]
    reference_range: Optional[str]
    is_abnormal: bool = False
    abnormal_flag: Optional[str]  # high / low / normal
    method: Optional[str]
    remark: str = ""

class CheckupRecord(TenantModel):
    profile_id: str
    checkup_date: date
    hospital: str = ""
    department: Optional[str]
    doctor: Optional[str]
    package_name: Optional[str]
    checkup_type: str = "annual"   # annual / 入职 / 复查 / 专项

    status: CheckupStatus          # scheduled / in_progress / completed / report_ready / cancelled
    report_url: Optional[str]
    overall_summary: str = ""
    doctor_advice: str = ""
    follow_up_required: bool = False
    follow_up_date: Optional[date]

    items: List[CheckupItem] = []
    tags: List[str] = []
    notes: str = ""
```

**计算属性 / 方法**：
- `abnormal_items: List[CheckupItem]` — 所有异常项目
- `abnormal_count: int` — 异常项目数量
- `total_items: int` — 项目总数
- `get_item(item_code) -> Optional[CheckupItem]`
- `add_item(item: CheckupItem)` — 同编码替换

### 2.4 生命体征 — MetricsRecord

```python
class MetricsType(str, Enum):
    # 生命体征
    HEART_RATE = "heart_rate"
    BLOOD_PRESSURE_SYSTOLIC = "bp_sys"
    BLOOD_PRESSURE_DIASTOLIC = "bp_dia"
    BLOOD_OXYGEN = "blood_oxygen"
    TEMPERATURE = "temperature"
    RESPIRATORY_RATE = "resp_rate"
    # 体重体脂
    WEIGHT = "weight"
    BODY_FAT = "body_fat"
    BMI = "bmi"
    MUSCLE_MASS = "muscle_mass"
    BONE_MASS = "bone_mass"
    WATER_RATIO = "water_ratio"
    # 血糖
    BLOOD_GLUCOSE_FASTING = "glucose_fasting"
    BLOOD_GLUCOSE_POSTPRANDIAL = "glucose_pp"
    BLOOD_GLUCOSE_RANDOM = "glucose_random"
    HBA1C = "hba1c"
    # 血脂
    TOTAL_CHOLESTEROL = "chol_total"
    TRIGLYCERIDE = "triglyceride"
    HDL = "hdl"
    LDL = "ldl"
    # 其他
    WAIST_CIRCUMFERENCE = "waist"
    HIP_CIRCUMFERENCE = "hip"
    STEPS = "steps"
    SLEEP_DURATION = "sleep_duration"

class MetricSource(str, Enum):
    MANUAL = "manual"
    WEARABLE = "wearable"
    SMART_SCALE = "smart_scale"
    BLOOD_PRESSURE_MONITOR = "bp_monitor"
    GLUCOMETER = "glucometer"
    LAB_TEST = "lab_test"
    OTHER = "other"

class MetricsRecord(TenantModel):
    profile_id: str
    metrics_type: MetricsType
    value: float
    unit: str = ""              # 未设置时按 metrics_type 自动填充
    measured_at: datetime
    source: MetricSource = MANUAL
    device_id: Optional[str]
    location: Optional[str]

    is_abnormal: bool = False
    abnormal_flag: Optional[str]   # high / low / normal

    note: str = ""
    tags: list[str] = []
```

**自动填充**：创建时若 `unit` 为空，自动根据 `metrics_type` 填充默认单位（如 `heart_rate → "bpm"`, `weight → "kg"`）。

### 2.5 用药管理 — MedicationRecord

```python
class MedicationFrequency(str, Enum):
    ONCE_DAILY = "qd"
    TWICE_DAILY = "bid"
    THREE_TIMES_DAILY = "tid"
    FOUR_TIMES_DAILY = "qid"
    EVERY_OTHER_DAY = "qod"
    WEEKLY = "qw"
    AS_NEEDED = "prn"
    BEFORE_MEAL = "ac"
    AFTER_MEAL = "pc"
    AT_BEDTIME = "hs"
    CUSTOM = "custom"

class MedicationStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"
    PAUSED = "paused"
    EXPIRED = "expired"

class MedicationRecord(TenantModel):
    profile_id: str

    # 药品信息
    drug_name: str
    brand_name: Optional[str]
    drug_category: Optional[str]
    dosage: str                    # 剂量，如 "10mg"
    strength: Optional[str]        # 规格，如 "10mg×30片"
    form: Optional[str]            # 剂型

    # 用法
    frequency: MedicationFrequency = ONCE_DAILY
    frequency_detail: Optional[str]
    route: str = "口服"
    quantity_per_dose: Optional[float]
    duration_days: Optional[int]

    # 周期
    start_date: date
    end_date: Optional[date]
    prescription_date: Optional[date]

    # 医生/处方
    prescriber: Optional[str]
    hospital: Optional[str]
    prescription_no: Optional[str]
    indication: Optional[str]

    # 状态
    status: MedicationStatus = ACTIVE
    refill_count: int = 0
    max_refills: Optional[int]

    # 提醒/备注
    reminder_enabled: bool = False
    reminder_times: List[str]      # ["08:00", "20:00"]
    side_effects: List[str]
    notes: str = ""
    tags: List[str] = []
```

**计算属性**：
- `is_active_today: bool` — 今天是否在用药期且状态为 ACTIVE
- `days_remaining: Optional[int]` — 剩余用药天数

### 2.6 风险评估 — RiskAssessment

```python
class RiskLevel(str, Enum):
    LOW = "low"
    MILD = "mild"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

class RiskType(str, Enum):
    CARDIOVASCULAR = "cardiovascular"
    DIABETES = "diabetes"
    HYPERTENSION = "hypertension"
    OBESITY = "obesity"
    STROKE = "stroke"
    CANCER_GENERAL = "cancer_general"
    RESPIRATORY = "respiratory"
    KIDNEY = "kidney"
    LIVER = "liver"
    MENTAL = "mental"
    OSTEOPOROSIS = "osteoporosis"
    METABOLIC_SYNDROME = "metabolic_syndrome"
    COMPREHENSIVE = "comprehensive"

class RiskFactor(BaseModel):
    name: str
    weight: float = 0.0
    value: Optional[str]
    is_positive: bool = False    # True=保护性, False=危险性
    description: str = ""
    evidence: Optional[str]

class RiskRecommendation(BaseModel):
    category: str                # 饮食/运动/用药/体检/生活方式
    priority: int = 3            # 1-5 (1最高)
    title: str
    description: str = ""
    target: Optional[str]
    timeline: Optional[str]
    references: List[str] = []

class RiskAssessment(TenantModel):
    profile_id: str
    risk_type: RiskType
    risk_level: RiskLevel

    score: float = 0.0
    score_max: float = 100.0
    risk_percentage: Optional[float]
    reference_group: Optional[str]

    algorithm: str = ""
    algorithm_version: str = "1.0"
    assessment_date: datetime

    risk_factors: List[RiskFactor] = []
    recommendations: List[RiskRecommendation] = []

    previous_assessment_id: Optional[str]
    change_from_previous: Optional[str]  # improved / worsened / stable

    summary: str = ""
    severity_note: str = ""
    next_review_date: Optional[datetime]

    tags: List[str] = []
    notes: str = ""
```

**计算属性 / 方法**：
- `score_ratio: float` — 得分率 0-1
- `top_risk_factors(n=5)` — 权重最高的前 N 个危险因素（排除保护性）
- `top_recommendations(n=3)` — 优先级最高的前 N 条建议
- `factor_summary() -> Dict[str, int]` — {total, risk_count, protective_count}

### 2.7 健康计划 — HealthPlan

```python
class PlanType(str, Enum):
    WEIGHT_LOSS = "weight_loss"
    BLOOD_PRESSURE_CONTROL = "bp_control"
    BLOOD_SUGAR_CONTROL = "bs_control"
    CHOLESTEROL_CONTROL = "lipid_control"
    FITNESS_IMPROVEMENT = "fitness"
    SLEEP_IMPROVEMENT = "sleep_improvement"
    STRESS_MANAGEMENT = "stress"
    POST_SURGERY_RECOVERY = "post_surgery"
    CHRONIC_DISEASE_MANAGEMENT = "chronic"
    PREVENTIVE_CARE = "preventive"
    CUSTOM = "custom"

class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    OVERDUE = "overdue"
    FAILED = "failed"

class PlanTask(BaseModel):
    task_id: str = ""
    title: str
    category: str = ""
    description: str = ""
    frequency: str = "daily"      # daily / weekly / monthly / one_time
    target_value: Optional[float]
    target_unit: Optional[str]
    priority: int = 3

    start_date: Optional[date]
    end_date: Optional[date]

    status: TaskStatus = PENDING
    progress: float = 0.0
    completion_date: Optional[date]

    related_risk_type: Optional[str]
    references: List[str] = []
    notes: str = ""

class PlanMilestone(BaseModel):
    milestone_id: str = ""
    title: str
    target_date: date
    description: str = ""
    achieved: bool = False
    achieved_date: Optional[date]
    evidence: str = ""

class HealthPlan(TenantModel):
    profile_id: str
    plan_name: str
    plan_type: PlanType = CUSTOM

    start_date: date
    end_date: Optional[date]
    duration_days: Optional[int]

    source_risk_assessment_id: Optional[str]
    source_checkup_id: Optional[str]
    created_by: str = "system"     # system / doctor / self / coach
    doctor_name: Optional[str]

    overall_goal: str = ""
    goals: List[str] = []

    status: PlanStatus = DRAFT

    tasks: List[PlanTask] = []
    milestones: List[PlanMilestone] = []

    baseline_metrics: dict = {}    # 基线指标
    target_metrics: dict = {}      # 目标指标
    current_metrics: dict = {}     # 当前指标

    tags: List[str] = []
    notes: str = ""
```

**计算属性 / 方法**：
- `days_elapsed: int` — 已过天数
- `days_remaining: Optional[int]` — 剩余天数
- `overall_progress: float` — 整体进度（任务完成度均值）
- `completed_tasks_count: int`
- `total_tasks_count: int`
- `achieved_milestones_count: int`
- `get_task(task_id) -> Optional[PlanTask]`
- `add_task(task: PlanTask)` — 自动生成 task_id
- `update_task_progress(task_id, progress) -> bool` — 自动更新状态

---

## 3. 技术方案

### 3.1 存储架构

**v1.0 实现**：内存字典存储

```python
_store: Dict[str, Dict[str, T]] = {}  # {tenant_id: {id: model}}
_lock = threading.RLock()
```

**设计理由**：
- L3 组件不绑定具体存储后端，内存版便于单元测试和快速验证
- Repository 模式封装，切换到 SQLAlchemy/MongoDB 只需替换 BaseRepository 实现
- 线程安全：`threading.RLock()` 保护所有读写操作

**未来扩展**：SQLite / MySQL 版只需实现新的 `BaseRepository` 子类，领域 repo 零改动。

### 3.2 多租户隔离机制

采用 **ContextVar + 自动注入** 模式：

1. **上下文传递**：使用 `contextvars.ContextVar` 存储当前租户 ID，协程安全
2. **自动注入**：创建模型时，`tenant_id` 默认值从 `_current_tenant()` 获取
3. **全链路过滤**：所有查询/更新/删除方法首行读取 `_current_tenant()`，仅操作当前租户数据
4. **安全校验**：`create()` 方法校验传入的 `tenant_id` 与上下文一致，不一致则抛 ValueError

**安全性边界**：
- 未设置租户上下文时，任何 CRUD 操作抛 `RuntimeError`
- 跨租户数据完全不可见（存储结构按 tenant_id 分桶）
- 无法通过 ID 猜测访问其他租户数据（ID 查先过租户桶）

### 3.3 软删除机制

- 所有实体含 `is_deleted: bool = False`
- `delete()` 方法不物理删除，仅调用 `update(is_deleted=True)`
- 所有查询方法（`get_by_id` / `list` / `filter` / `count`）自动过滤 `is_deleted=True` 的记录
- 数据保留在存储中，可审计、可恢复
- 物理删除需另行实现（v1.0 未提供，由 L4 层或运维脚本按需处理）

### 3.4 模型验证策略

全部基于 Pydantic v2：

| 验证类型 | 实现方式 | 示例 |
|---|---|---|
| 类型校验 | Pydantic 类型系统 | `float`, `date`, `Enum` |
| 范围校验 | `Field(gt=0, le=300)` | `height_cm: (0, 300]` |
| 枚举约束 | `str, Enum` | `Gender`, `BloodType` |
| 字段默认 | `default_factory` | `id`, `created_at` |
| 派生值填充 | `@model_validator` | 指标 unit 自动填充 |
| 默认值兜底 | `@field_validator` | profile_id 默认值 |
| 不可变字段 | update 中 pop | `id`, `tenant_id` 不可改 |

### 3.5 并发安全

- 全局 `threading.RLock()` 保护 `_store` 读写
- 所有读操作返回 `model_copy()`，避免外部修改影响存储
- 写操作在锁内完成（创建、更新、删除）
- ContextVar 天然协程安全，无需额外锁

### 3.6 数据库迁移

`migrations/001_initial_schema.sql` 提供关系型数据库建表脚本，包含：
- 6 张领域表（health_profiles, checkup_records, metrics_records, medication_records, risk_assessments, health_plans）
- 所有表均含 tenant_id + is_deleted + created_at + updated_at 标准字段
- 关键字段索引（tenant_id, profile_id, created_at）
- 按 SQLite 语法编写，MySQL/PostgreSQL 需适配

---

## 4. 错误处理

| 场景 | 异常类型 | 消息 |
|---|---|---|
| 未设置租户上下文 | `RuntimeError` | "No tenant context set. Call set_current_tenant(tenant_id) first." |
| 创建时 tenant_id 不一致 | `ValueError` | "tenant_id mismatch: data=..., context=..." |
| ID 已存在 | `ValueError` | "{ModelName} id={id} already exists" |
| 记录不存在或已删除 | `ValueError` | "{ModelName} id={id} not found" |

---

## 5. 设计约束与规范

### 5.1 领域独立性

- 各领域模块之间**互不 import**
- 无跨领域聚合（由 L4 层 service 编排）
- 每个领域包仅含 `models.py` + `repository.py` + `__init__.py`

### 5.2 L3 分层规则

- ✅ 允许：Pydantic 模型、数据验证、基础仓储、轻量计算属性
- ❌ 禁止：Web UI、权限控制、外部 API 调用、持久化实现细节
- ❌ 禁止：import 任何 L4 层代码

### 5.3 代码规范

- 模型继承 `TenantModel`
- Repository 继承 `BaseRepository[ModelT]`
- 类名：领域名 + Model/Repo（如 `HealthProfile`, `ProfileRepo`）
- 文件名：全小写下划线（`models.py`, `repository.py`）
