# health-engine

## 设计目标

为健康管理提供纯函数式计算引擎，覆盖健康评分、生命体征、运动记录、营养摄入、睡眠数据、压力评估六大领域。作为 L3 通用层，为 health-management 等组件提供计算能力。

## 架构决策

- **骨架阶段**：当前仅规划目录结构，尚无实际代码实现
- **参照 health-management 设计**：模型层采用 Pydantic + Repository 模式，本组件聚焦计算逻辑
- **纯函数式**：参照 finance-engine 的设计理念，计算引擎不持有数据、不访问 DB
- **模块化**：每个 hlt00x 模块独立封装，可单独演进

## 模块划分

```
health-engine/
├── health_engine/              # 预留包目录
│   ├── models/                 # 领域模型（待开发）
│   └── repositories/           # 仓储层（待开发）
├── hlt001_score/               # 健康评分（待开发）
├── hlt002_vitals/              # 生命体征（待开发）
├── hlt003_exercise/            # 运动记录（待开发）
├── hlt004_nutrition/           # 营养摄入（待开发）
├── hlt005_sleep/               # 睡眠数据（待开发）
├── hlt006_stress/              # 压力评估（待开发）
└── tests/                      # 测试（待开发）
```

## 关键接口/数据结构

（待设计，预留方向）
- `ScoreEngine`：健康评分计算
- `VitalsEngine`：生命体征分析（BMI/血压/心率）
- `ExerciseEngine`：运动消耗计算
- `NutritionEngine`：营养摄入分析
- `SleepEngine`：睡眠质量评估
- `StressEngine`：压力水平评估

## 依赖关系

- **依赖**：暂无（待开发）
- **被依赖**：暂无（待开发后，health-management 将调用本组件计算能力）

## 演进方向

1. **短期**：完成 hlt001_score 和 hlt002_vitals 的基础实现
2. **中期**：补齐六大模块的计算逻辑
3. **长期**：与 health-management 数据打通，形成"数据层 + 计算层"分离架构
