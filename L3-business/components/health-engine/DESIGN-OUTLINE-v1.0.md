# health-engine — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
hlt001_score/    → 健康评分引擎
hlt002_vitals/   → 生命体征引擎
hlt003_exercise/ → 运动记录引擎
hlt004_nutrition/ → 营养摄入引擎
hlt005_sleep/    → 睡眠数据引擎
hlt006_stress/   → 压力评估引擎
```

## 2. 模块划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| hlt001_score | 健康评分 | 多维度数据 | 综合评分 |
| hlt002_vitals | 生命体征 | 身高/体重/血压 | BMI/血压分析 |
| hlt003_exercise | 运动消耗 | 运动类型/时长 | 卡路里消耗 |
| hlt004_nutrition | 营养分析 | 饮食记录 | 营养素统计 |
| hlt005_sleep | 睡眠评估 | 睡眠数据 | 睡眠质量评分 |
| hlt006_stress | 压力评估 | 压力指标 | 压力水平 |

## 3. 接口契约

- `ScoreEngine.calculate(data) → score`
- `VitalsEngine.analyze(height, weight, bp) → bmi/bp_level`
- `ExerciseEngine.calculate(type, duration) → calories`
- `NutritionEngine.analyze(food_log) → nutrients`
- `SleepEngine.evaluate(sleep_data) → quality_score`
- `StressEngine.assess(indicators) → stress_level`

## 4. 技术选型

- 纯函数式设计（零副作用）
- 无状态计算，数据由 L4 注入
- 医学标准对照表内置

## 5. 分层约束

- L3 纯逻辑层：不直接访问 DB
- 被 health-management 继承
