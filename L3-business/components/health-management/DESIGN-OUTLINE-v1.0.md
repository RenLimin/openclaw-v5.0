# health-management — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
profile/           → 健康档案
checkup/           → 体检记录
metrics/           → 生命体征指标
medication/        → 用药管理
risk_assessment/   → 风险评估
health_plan/       → 健康计划
```

## 2. 模块划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| profile | 健康档案 | 个人信息 | 档案记录 |
| checkup | 体检记录 | 体检数据 | 体检历史 |
| metrics | 指标跟踪 | 生命体征 | 趋势数据 |
| medication | 用药管理 | 用药记录 | 用药安全 |
| risk_assessment | 风险评估 | 多维度数据 | 风险等级 |
| health_plan | 健康计划 | 个人数据 | 执行计划 |

## 3. 接口契约

- `BaseRepository.get_by_id(id)` / `create(obj)` / `update(id, obj)` / `delete(id)`
- `HealthProfile`: 个人信息 + 生活方式 + 家族病史
- `Checkup`: 体检记录 + 结果
- `Metrics`: 血压/心率/血糖等指标
- `Medication`: 药品名/剂量/频次
- `RiskAssessment`: 风险等级 + 评估依据
- `HealthPlan`: 计划内容 + 执行状态

## 4. 技术选型

- Pydantic 数据验证
- Repository 模式封装
- 多租户隔离（tenant_id）
- 软删除机制（is_deleted）

## 5. 分层约束

- L3 通用层：不绑定专有业务
- 被 L4 继承：health-engine 调用本组件
