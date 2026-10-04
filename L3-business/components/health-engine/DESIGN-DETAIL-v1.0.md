# 健康引擎 — 详细设计

> 组件：health-engine (L3)
> 版本：v1.0
> 日期：2026-09-03

## 1. 概述

健康引擎的详细设计，包含 6 大健康评分引擎：评分、生命体征、运动、营养、睡眠、压力。

## 2. 接口契约

### 2.1 评分引擎

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| calculate_score | POST | health_data | score |
| get_trends | GET | user_id, period | trends |
| compare_benchmark | POST | user_data | comparison |

### 2.2 生命体征引擎

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| record_vitals | POST | vitals_data | result |
| analyze_trends | GET | user_id, metric | analysis |
| detect_anomalies | GET | user_id | anomalies |

## 3. 数据模型

### 3.1 健康数据模型

```python
@dataclass
class HealthRecord:
    id: str
    user_id: str
    timestamp: datetime
    vitals: Dict[str, float]
    exercise: ExerciseData
    nutrition: NutritionData
    sleep: SleepData
    stress: StressData
```

### 3.2 评分模型

```python
@dataclass
class HealthScore:
    user_id: str
    date: date
    overall: float
    vitals_score: float
    exercise_score: float
    nutrition_score: float
    sleep_score: float
    stress_score: float
```

## 4. 技术方案

### 4.1 6 大评分引擎

1. **评分引擎**：综合健康评分计算
2. **生命体征引擎**：血压、心率、体温等监测
3. **运动引擎**：运动量、强度、频率分析
4. **营养引擎**：饮食结构、营养素摄入分析
5. **睡眠引擎**：睡眠质量、时长、周期分析
6. **压力引擎**：压力水平、应对能力评估

### 4.2 评分算法

加权综合评分：
- 生命体征：25%
- 运动：20%
- 营养：20%
- 睡眠：20%
- 压力：15%

## 5. 依赖关系

- L2 持久化适配 (SQLite)
- L2 知识库 (健康知识)

## 6. 测试方案

- 单元测试：各引擎评分算法
- 集成测试：综合评分计算
- E2E 测试：完整健康评估流程
