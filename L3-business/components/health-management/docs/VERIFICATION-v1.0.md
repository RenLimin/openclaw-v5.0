# VERIFICATION - health-management v1.0

> **版本**: v1.0  
> **组件**: health-management  
> **测试日期**: 2026-09-29  
> **测试环境**: Python 3.10+ / Pydantic v2 / 内存存储

---

## 1. 验收标准回顾

| 编号 | 验收项 | 对应测试模块 |
|---|---|---|
| AC-001 | 6 大领域模块均可独立完成 CRUD | test_profile, test_checkup, test_metrics, test_medication, test_risk_assessment, test_health_plan |
| AC-002 | 多租户隔离，跨租户数据不可见 | 各测试文件 + test_base_repository |
| AC-003 | 软删除机制 | test_base_repository + 各领域 delete 测试 |
| AC-004 | Pydantic 模型验证生效 | 各领域模型边界测试 |
| AC-005 | BaseRepository 统一接口复用 | test_base_repository |
| AC-010 | 领域驱动分层结构 | 代码审查 |
| AC-011 | 测试覆盖全部领域 | 7 个测试文件 |
| AC-012 | 数据库迁移脚本可执行 | migrations/001_initial_schema.sql |
| AC-013 | L4 适配性，无反向依赖 | import 检查 |

---

## 2. 测试用例

### 2.1 test_base_repository — 基础仓储测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-BASE-001 | create 后 get_by_id 可获取 | 返回创建的对象 | P0 |
| TC-BASE-002 | 创建时自动生成 id | id 非空，UUID hex 格式 | P0 |
| TC-BASE-003 | 创建时自动注入 tenant_id | tenant_id = 当前上下文中的值 | P0 |
| TC-BASE-004 | 创建时自动设置 created_at / updated_at | 时间非空，类型 datetime | P0 |
| TC-BASE-005 | create 重复 id 抛 ValueError | 异常抛出 | P0 |
| TC-BASE-006 | create 时 tenant_id 与上下文不一致抛 ValueError | 异常抛出 | P0 |
| TC-BASE-007 | get_by_id 不存在返回 None | 返回 None | P0 |
| TC-BASE-008 | list 返回当前租户所有未删除记录 | 数量正确，按 created_at 倒序 | P0 |
| TC-BASE-009 | list 分页（limit + offset）正确 | 返回指定范围 | P1 |
| TC-BASE-010 | filter 按字段等值过滤正确 | 结果匹配条件 | P0 |
| TC-BASE-011 | filter 空条件等价于 list | 结果一致 | P1 |
| TC-BASE-012 | update 更新指定字段 | 字段值变更，updated_at 刷新 | P0 |
| TC-BASE-013 | update 不能修改 id / tenant_id | 字段保持原值 | P0 |
| TC-BASE-014 | update 不存在记录抛 ValueError | 异常抛出 | P0 |
| TC-BASE-015 | delete 软删除，is_deleted 变为 True | 标记为已删除 | P0 |
| TC-BASE-016 | delete 后 get_by_id 返回 None | 不可见 | P0 |
| TC-BASE-017 | delete 后 list 不包含 | 列表过滤掉 | P0 |
| TC-BASE-018 | count 返回未删除记录数 | 统计正确 | P1 |
| TC-BASE-019 | 多租户隔离：租户 A 看不到租户 B 数据 | 完全隔离 | P0 |
| TC-BASE-020 | 未设置租户上下文操作抛 RuntimeError | 异常抛出 | P0 |

### 2.2 test_profile — 健康档案测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-PROF-001 | 创建健康档案必填字段 | 创建成功 | P0 |
| TC-PROF-002 | gender 仅允许枚举值 | 非法值抛 ValidationError | P0 |
| TC-PROF-003 | blood_type 枚举验证 | 非法值抛 ValidationError | P1 |
| TC-PROF-004 | height_cm 范围校验 (0, 300] | 越界抛 ValidationError | P0 |
| TC-PROF-005 | weight_kg 范围校验 (0, 500] | 越界抛 ValidationError | P0 |
| TC-PROF-006 | age 计算属性正确 | 实足年龄正确 | P0 |
| TC-PROF-007 | bmi 计算属性正确 | BMI = weight / height² | P0 |
| TC-PROF-008 | bmi 缺身高或体重返回 None | 返回 None | P1 |
| TC-PROF-009 | ideal_weight_kg 计算正确 | Broca 改良公式 | P1 |
| TC-PROF-010 | allergies / chronic_diseases 列表默认空 | 默认 list 非共享 | P1 |
| TC-PROF-011 | profile_id 未设置时为空字符串 | 默认值正确 | P1 |
| TC-PROF-012 | 健康档案 CRUD 完整流程 | create → get → update → delete | P0 |
| TC-PROF-013 | 按 name 过滤查询 | filter(name=xxx) 正确 | P1 |

### 2.3 test_checkup — 体检记录测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-CHK-001 | 创建体检记录（含 items） | 创建成功 | P0 |
| TC-CHK-002 | status 枚举验证 | 非法值抛 ValidationError | P0 |
| TC-CHK-003 | abnormal_items 返回异常项目 | 仅返回 is_abnormal=True 的 | P0 |
| TC-CHK-004 | abnormal_count 统计正确 | 数量正确 | P0 |
| TC-CHK-005 | total_items 统计正确 | 数量正确 | P1 |
| TC-CHK-006 | get_item 按编码查找 | 找到/找不到均正确 | P0 |
| TC-CHK-007 | add_item 新编码追加 | items 数量 +1 | P1 |
| TC-CHK-008 | add_item 同编码替换 | 数量不变，内容更新 | P1 |
| TC-CHK-009 | checkup_date 类型校验 | 必须是 date | P0 |
| TC-CHK-010 | follow_up_date 可选 | 可 None | P1 |
| TC-CHK-011 | 体检记录 CRUD 完整流程 | create → get → update → delete | P0 |

### 2.4 test_metrics — 生命体征测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-MET-001 | 创建指标记录 | 创建成功 | P0 |
| TC-MET-002 | metrics_type 枚举验证 | 24 种类型全部合法 | P0 |
| TC-MET-003 | unit 自动填充（heart_rate → bpm） | 单位正确 | P0 |
| TC-MET-004 | unit 手动指定优先 | 不覆盖已有值 | P1 |
| TC-MET-005 | source 枚举验证 | 7 种来源合法 | P1 |
| TC-MET-006 | measured_at 默认当前时间 | 自动填充 | P0 |
| TC-MET-007 | value 类型校验（float） | 数字类型正确 | P0 |
| TC-MET-008 | is_abnormal / abnormal_flag 标注 | 可手动标注异常 | P1 |
| TC-MET-009 | 按 profile_id + metrics_type 过滤 | filter 正确 | P0 |
| TC-MET-010 | 指标记录 CRUD 完整流程 | create → get → update → delete | P0 |
| TC-MET-011 | 全部 24 种指标类型 unit 正确 | 遍历验证 | P1 |

### 2.5 test_medication — 用药管理测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-MED-001 | 创建用药记录 | 创建成功 | P0 |
| TC-MED-002 | frequency 枚举验证（12 种） | 非法值抛错 | P0 |
| TC-MED-003 | status 枚举验证（5 种） | 非法值抛错 | P0 |
| TC-MED-004 | is_active_today：进行中 + 在周期内 → True | True | P0 |
| TC-MED-005 | is_active_today：状态非 ACTIVE → False | False | P0 |
| TC-MED-006 | is_active_today：未到开始日期 → False | False | P1 |
| TC-MED-007 | is_active_today：已过结束日期 → False | False | P1 |
| TC-MED-008 | days_remaining 计算正确 | 剩余天数正确 | P0 |
| TC-MED-009 | days_remaining 无 end_date 返回 None | 返回 None | P1 |
| TC-MED-010 | reminder_times 列表默认空 | 空列表 | P1 |
| TC-MED-011 | side_effects 列表默认空 | 空列表 | P1 |
| TC-MED-012 | 用药记录 CRUD 完整流程 | create → get → update → delete | P0 |
| TC-MED-013 | refill_count / max_refills 续方统计 | 整数类型正确 | P1 |

### 2.6 test_risk_assessment — 风险评估测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-RISK-001 | 创建风险评估（含 factors + recommendations） | 创建成功 | P0 |
| TC-RISK-002 | risk_level 枚举验证（5 级） | 非法值抛错 | P0 |
| TC-RISK-003 | risk_type 枚举验证（13 种） | 非法值抛错 | P0 |
| TC-RISK-004 | score_ratio 计算正确 | score / score_max | P0 |
| TC-RISK-005 | score_max ≤ 0 时 score_ratio = 0.0 | 除零保护 | P1 |
| TC-RISK-006 | top_risk_factors 返回权重最高的 N 个危险因素 | 按 weight 降序，排除保护性 | P0 |
| TC-RISK-007 | top_recommendations 返回优先级最高的 N 条 | 按 priority 升序 | P0 |
| TC-RISK-008 | factor_summary 统计正确 | total / risk_count / protective_count | P1 |
| TC-RISK-009 | RiskFactor is_positive 区分危险/保护 | 布尔值正确 | P1 |
| TC-RISK-010 | RiskRecommendation priority 1-5 | 优先级正确 | P1 |
| TC-RISK-011 | 风险评估 CRUD 完整流程 | create → get → update → delete | P0 |

### 2.7 test_health_plan — 健康计划测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-PLAN-001 | 创建健康计划（含 tasks + milestones） | 创建成功 | P0 |
| TC-PLAN-002 | plan_type 枚举验证（12 种） | 非法值抛错 | P0 |
| TC-PLAN-003 | status 枚举验证（6 种） | 非法值抛错 | P0 |
| TC-PLAN-004 | days_elapsed 计算正确 | 已过天数 | P0 |
| TC-PLAN-005 | days_elapsed 未开始返回 0 | 0 | P1 |
| TC-PLAN-006 | days_remaining 计算正确 | 剩余天数 | P0 |
| TC-PLAN-007 | days_remaining 无 end_date 返回 None | None | P1 |
| TC-PLAN-008 | overall_progress = 任务 progress 均值 | 平均值正确 | P0 |
| TC-PLAN-009 | overall_progress 无任务返回 0.0 | 0.0 | P1 |
| TC-PLAN-010 | completed_tasks_count 正确 | 统计 COMPLETED 数量 | P0 |
| TC-PLAN-011 | achieved_milestones_count 正确 | 统计 achieved 数量 | P1 |
| TC-PLAN-012 | get_task 按 task_id 查找 | 找到/找不到 | P0 |
| TC-PLAN-013 | add_task 自动生成 task_id | ID 非空 | P0 |
| TC-PLAN-014 | update_task_progress 修改进度 | progress 更新 | P0 |
| TC-PLAN-015 | update_task_progress 进度 ≥100 → 状态 COMPLETED | 状态 + completion_date 自动更新 | P0 |
| TC-PLAN-016 | update_task_progress 进度 0<x<100 → IN_PROGRESS | 状态更新 | P1 |
| TC-PLAN-017 | update_task_progress 进度限制在 [0, 100] | clamp 生效 | P1 |
| TC-PLAN-018 | update_task_progress 不存在的 task_id 返回 False | False | P1 |
| TC-PLAN-019 | TaskStatus 枚举验证（6 种） | 非法值抛错 | P1 |
| TC-PLAN-020 | 健康计划 CRUD 完整流程 | create → get → update → delete | P0 |

### 2.8 集成测试

| 用例 ID | 测试描述 | 预期结果 | 优先级 |
|---|---|---|---|
| TC-INT-001 | 多租户多领域数据完全隔离 | 租户间互不干扰 | P0 |
| TC-INT-002 | 同一 profile 下多领域数据关联 | profile_id 一致 | P0 |
| TC-INT-003 | 并发写入不丢失数据 | 线程安全 | P1 |
| TC-INT-004 | 软删除数据不参与 count | 统计准确 | P0 |
| TC-INT-005 | L4 import 路径正确（fin-l4 → health-management） | import 成功，无循环依赖 | P1 |

---

## 3. 黄金基准测试集

### 3.1 标准测试数据

| 数据集 | 内容 | 用途 |
|---|---|---|
| profile-standard | 1 份完整健康档案，含全部字段 | 基础 CRUD 验证 |
| metrics-30day | 30 天每日 5 项指标（血压/心率/血糖/体重/步数） | 时间序列查询验证 |
| checkup-annual | 1 份完整年度体检报告，含 50+ 项目、10 项异常 | 异常统计验证 |
| medication-3drugs | 3 种常用药（降压/降糖/降脂），不同频次 | 用药状态验证 |
| risk-comprehensive | 1 份综合风险评估，含 15 个风险因子 + 8 条建议 | 风险计算验证 |
| plan-weight-loss | 1 份 90 天减重计划，含 12 个任务 + 3 个里程碑 | 进度计算验证 |

### 3.2 基准验证点

| 验证项 | 预期值 | 偏差容限 |
|---|---|---|
| BMI 计算（身高 175cm，体重 70kg） | 22.86 | ±0.01 |
| 年龄计算（出生日期 1990-06-15，当前 2026-09-29） | 36 | 0 |
| 理想体重（男，175cm） | 67.5 kg | ±0.1 |
| 30 天指标记录数 | 150 条 | 0 |
| 体检异常项目数 | 10 | 0 |
| 减重计划整体进度（12 任务，进度各异） | 按均值计算 | ±0.1 |
| 多租户隔离 | 租户 A 查不到租户 B 数据 | 0 条泄漏 |

---

## 4. 测试结果统计

> 以下为模板，实际执行后填充数据。

### 4.1 汇总

| 指标 | 数值 |
|---|---|
| 测试用例总数 | TBD |
| 通过数 | TBD |
| 失败数 | TBD |
| 跳过数 | TBD |
| 通过率 | TBD |
| 执行总时长 | TBD |

### 4.2 分模块统计

| 模块 | 用例数 | 通过 | 失败 | 通过率 |
|---|---|---|---|---|
| base_repository | 20 | TBD | TBD | TBD |
| profile | 13 | TBD | TBD | TBD |
| checkup | 11 | TBD | TBD | TBD |
| metrics | 11 | TBD | TBD | TBD |
| medication | 13 | TBD | TBD | TBD |
| risk_assessment | 11 | TBD | TBD | TBD |
| health_plan | 20 | TBD | TBD | TBD |
| 集成测试 | 5 | TBD | TBD | TBD |
| **合计** | **104** | TBD | TBD | TBD |

### 4.3 黄金基准对比

| 验证项 | 预期值 | 实际值 | 偏差 | 通过？ |
|---|---|---|---|---|
| BMI 计算 | 22.86 | TBD | TBD | TBD |
| 年龄计算 | 36 | TBD | TBD | TBD |
| 30 天指标记录数 | 150 | TBD | TBD | TBD |
| 体检异常项目数 | 10 | TBD | TBD | TBD |
| 多租户隔离 | 0 条泄漏 | TBD | TBD | TBD |

### 4.4 缺陷记录

| 缺陷 ID | 模块 | 严重程度 | 描述 | 状态 |
|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD |

---

## 5. 验收结论

### 5.1 功能验收

- [ ] AC-001：6 大领域 CRUD 全部通过
- [ ] AC-002：多租户隔离验证通过
- [ ] AC-003：软删除机制验证通过
- [ ] AC-004：Pydantic 模型验证生效
- [ ] AC-005：BaseRepository 统一接口复用正确

### 5.2 非功能验收

- [ ] AC-010：领域驱动分层结构符合规范
- [ ] AC-011：测试覆盖全部 6 个领域 + base repo
- [ ] AC-012：数据库迁移脚本可执行
- [ ] AC-013：L4 适配性验证通过，无反向依赖

### 5.3 最终结论

□ 通过 □ 有条件通过 □ 不通过

**审核人**：__________  
**审核日期**：__________  
**备注**：
