# 交付质量反馈库 Schema（feedback.jsonl）

> 每行一条 JSON 对象（JSONL），git-tracked。记录 Rex 对交付结果的问题反馈与纠正，驱动定期优化。
> 归属：L2 基础设施 / delivery-quality · 契约：ADR-035 数据闭环层。

## 字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | `FB-YYYYMMDD-NN`，当日序号 |
| `ts` | string | ✅ | ISO8601 记录时间（Asia/Shanghai） |
| `reporter` | string | ✅ | 反馈人（默认 `gateway-owner`） |
| `source_session` | string | ✅ | 发起会话 key |
| `domain` | string | ✅ | 业务域：`project` / `contract` / `product` / `cross` / `other` |
| `target` | string | ⬜ | 被反馈对象（项目号/合同号/报告路径） |
| `dimension` | string | ✅ | 问题维度，见下方枚举 |
| `severity` | string | ✅ | `high` / `medium` / `low`（对结论正确性的影响） |
| `finding` | string | ✅ | Rex 反馈的问题（原话/要点） |
| `root_cause` | string | ⬜ | 初判根因（review 时可补） |
| `corrective_action` | string | ⬜ | 已采取的纠正 |
| `status` | string | ✅ | `open` / `corrected` / `promoted` / `wontfix` |
| `resolution` | string | ⬜ | 最终处置（升级到哪：KB/fixture/P2） |
| `tags` | array | ⬜ | 自由标签 |

## dimension 枚举（问题维度）

| 值 | 含义 |
|---|---|
| `data_completeness` | 应返回的字段/信息缺失（如编号截断、缺产品维度） |
| `data_fidelity` | 数据口径/取值错误（如类型误标、完成率口径错） |
| `calculation_logic` | 统计/计算规则错误（如未计结项） |
| `missing_risk_analysis` | 应有风险分析但缺失（如合同风险） |
| `missing_context` | 缺背景/关联信息（如对应产品/服务） |
| `best_practice_gap` | 不符业界最佳实践（要素不全） |
| `sourcing` | 数据源/溯源/降级标注问题 |
| `format_presentation` | 展示/格式问题 |
| `other` | 其他 |

## 生命周期

```
open（默认记录）
  ├─ corrected：当场已纠正（根因可能未系统解决）
  ├─ promoted：review 后升级为 KB 文档 / 黄金 fixture / P2 契约条款
  └─ wontfix：判定不处理（须在 resolution 说明理由）
```

## 去重与复发

- review 脚本按 `dimension + root_cause` 聚类；同一根因多次出现 = 复发，触发升级建议。
- 单条反馈可只 `corrected`，但复发 ≥2 次的维度应考虑 `promoted`（系统级防再发）。
