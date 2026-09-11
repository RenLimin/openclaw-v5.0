# health-engine

**定位：** L3 业务层 — 健康引擎，管理健康数据（体征、运动、营养、睡眠、压力、评分）。

## 功能列表

- 当前为骨架阶段，目录结构已规划：
  - `hlt001_score` — 健康评分
  - `hlt002_vitals` — 生命体征
  - `hlt003_exercise` — 运动记录
  - `hlt004_nutrition` — 营养摄入
  - `hlt005_sleep` — 睡眠数据
  - `hlt006_stress` — 压力评估
- 预留 `health_engine/` 包目录
- 预留 `tests/` 目录

## 目录结构

```
health-engine/
├── health_engine/            # 预留包目录
│   ├── models/               # 领域模型（待开发）
│   └── repositories/         # 仓储层（待开发）
├── hlt001_score/             # 健康评分（待开发）
├── hlt002_vitals/            # 生命体征（待开发）
├── hlt003_exercise/          # 运动记录（待开发）
├── hlt004_nutrition/         # 营养摄入（待开发）
├── hlt005_sleep/             # 睡眠数据（待开发）
├── hlt006_stress/            # 压力评估（待开发）
└── tests/                    # 测试（待开发）
```

## 说明

骨架阶段，尚无实际代码。参照 `health-management` 组件的模型设计（Pydantic + Repository 模式）进行后续开发。

## 依赖

- 暂无（待开发）
