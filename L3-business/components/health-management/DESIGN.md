# health-management

## 设计目标

为个人健康档案管理提供结构化管理能力，覆盖健康档案、体检、用药、指标、风险评估、健康计划六大领域。解决健康数据分散、长期跟踪困难、风险预警缺失的问题。

## 架构决策

- **领域驱动分层**：每个领域独立 models + repository，职责单一
- **Pydantic 模型验证**：统一使用 Pydantic 做数据校验
- **多租户隔离**：所有模型携带 `tenant_id`
- **软删除**：通过 `is_deleted` 标记实现
- **Repository 模式**：数据访问通过 repository 层封装，便于切换存储后端

## 模块划分

```
health-management/
├── repository/
│   └── base.py                 # 通用仓储基类
├── profile/                    # 健康档案
│   ├── models.py               # HealthProfile 模型
│   └── repository.py
├── checkup/                    # 体检记录
│   ├── models.py               # Checkup 模型
│   └── repository.py
├── metrics/                    # 生命体征指标
│   ├── models.py               # Metrics 模型
│   └── repository.py
├── medication/                 # 用药管理
│   ├── models.py               # Medication 模型
│   └── repository.py
├── risk_assessment/            # 风险评估
│   ├── models.py               # RiskAssessment 模型
│   └── repository.py
├── health_plan/                # 健康计划
│   ├── models.py               # HealthPlan 模型
│   └── repository.py
├── migrations/
│   └── 001_initial_schema.sql  # 初始建表脚本（6 个领域表）
└── tests/                      # 单元测试
```

## 关键接口/数据结构

- `BaseRepository`：通用仓储，`get_by_id` / `create` / `update` / `delete`
- `HealthProfile`：健康档案模型（基本信息、生活方式、家族病史、过敏史）
- `Checkup`：体检记录模型
- `Metrics`：生命体征指标模型（血压/心率/血糖等）
- `Medication`：用药模型（药品名、剂量、频次）
- `RiskAssessment`：风险评估模型
- `HealthPlan`：健康计划模型

## 依赖关系

- **依赖**：Python 3.10+、Pydantic、SQLite/MySQL
- **被依赖**：`health-engine`（参照本组件的模型设计进行计算层开发）

## 演进方向

1. **与 health-engine 打通**：health-engine 提供计算能力，本组件提供数据存储
2. **风险预警**：基于指标趋势自动触发风险提醒
3. **数据可视化**：指标趋势图、健康评分曲线
4. **多用户支持**：家庭成员共享健康档案
