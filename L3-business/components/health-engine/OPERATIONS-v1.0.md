# health-engine — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+

### 1.2 安装步骤

```bash
cd L3-business/components/health-engine
# 纯逻辑层，无需额外依赖
```

### 1.3 启动命令

本组件为库模式，由 L4 层调用，无独立启动命令。

### 1.4 健康检查

```bash
python3 -c "from health_engine import *; print('OK')"
```

## 2. 操作指南

### 2.1 场景一：健康评分

```python
from health_engine.hlt001_score import ScoreEngine
engine = ScoreEngine()
score = engine.calculate({"age": 30, "weight": 70, "height": 175})
```

### 2.2 场景二：生命体征分析

```python
from health_engine.hlt002_vitals import VitalsEngine
engine = VitalsEngine()
bmi = engine.bmi(weight=70, height=175)
bp_level = engine.bp_analysis(systolic=120, diastolic=80)
```

## 3. 配置说明

无外部配置，纯计算引擎。

## 4. 故障排查

### 4.1 计算结果异常

- **症状**: 结果与预期不符
- **原因**: 输入数据格式错误
- **解决**: 检查输入数据类型和范围

## 5. FAQ

**Q1: 如何扩展新引擎？**
A: 在 `health-engine/` 下创建新目录 hlt00x_xxx，定义 Engine 类

**Q2: 支持实时数据吗？**
A: 当前为纯计算，数据由 L4 注入

## 6. 附录

### 6.1 接口清单

- `ScoreEngine`: calculate
- `VitalsEngine`: bmi / bp_analysis
- `ExerciseEngine`: calculate
- `NutritionEngine`: analyze
- `SleepEngine`: evaluate
- `StressEngine`: assess
