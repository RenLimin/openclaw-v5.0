# IMPLEMENTATION-PLAN — Bangcle 项目汇报材料生成技能 v1.0（待评审）

- 对应：PRD/OUTLINE/DETAIL/VERIFICATION/OPERATIONS v1.0
- 技能目录：`L3-business/skills/bangcle-project-report/`
- 原则：分 Phase、可独立验证；每 Phase 完成判据未达不进入下一 Phase。

---

## 1. Phase 总览

| Phase | 目标 | 主要交付 | 完成判据 |
|---|---|---|---|
| P1 | 取数与完整性 | fetch_project_tasks.py + references/data-pipeline.md | T1 PASS |
| P2 | 清洗/分类/汇总/明细 | normalize_and_classify.py、aggregate.py | T2/T3/T4 PASS |
| P3 | 目标闭环/在途/价值 | build_goal_matrix.py + 目标矩阵参考 + 模板 | T5 PASS |
| P4 | 溯源审计/受众适配/导出 | audit_provenance.py、render_report.py、脱敏参考 | T6/T7/T10 PASS |
| P5 | SKILL 装配 + E2E | SKILL.md + golden + 全链路 | T8/T9 + 黄金基准全复现 |

## 2. 任务拆解（WBS）

### P1 取数
- W11 薄封装浏览器注入 gql（复用 tmp/sdcbank/ones.py 模式）
- W12 项目枚举 + Project._7KF6tXvk 实时合同字段
- W13 逐项目分页取全 + 末页满页再拉 + completeness 结构
- W14 data-pipeline.md（分页/触顶/字段/时间戳）
- 判据：907 条原始可复现，hitCap 全 false。

### P2 清洗与汇总
- W21 时间戳三精度归一函数 + 表驱动测试
- W22 isWork 口径（剔除 6 类）+ inPeriod 卡周期
- W23 产品方向映射（含跨测评/加固上下文）
- W24 三维 Counter + reconciliation（done+wip=total）
- 判据：113/104/9 与三维账（66/17/19/7/4、44/34/19/10/3/2/1、76/5/32）。

### P3 目标闭环
- W31 合同台账合并（officialName/nameSource）
- W32 在途归并（进展+处理安排，不编日期）
- W33 GoalRealization 两类凭证 + 等级受控映射
- W34 internal/external 报告模板（7 章）
- 判据：9 方向等级齐全无悬空。

### P4 审计/适配/导出
- W41 audit_provenance（数字/名词/日期/标注区/脱敏/官方名）fail-closed
- W42 audience-redaction 词表 + 末步强制脱敏
- W43 render_report + python-docx 导出（标题7/明细113）
- 判据：PASS；插入无源项可被拦截。

### P5 装配与验收
- W51 SKILL.md（frontmatter/硬规则/S1-S8/验证/相关技能/契约引用）
- W52 golden 资产（计数 + 脱敏 IR 快照）
- W53 E2E 真人路径 + 幂等 3 连跑 + 边界/副作用扫描
- W54 README/资产清单（如组件有 frontmatter 清单机制）
- 判据：check_answer_contract + audit 双 exit 0；黄金 8 行复现。

## 3. 工时估算（粗）

| Phase | 估时 |
|---|---|
| P1 | 0.5–1 d |
| P2 | 1 d |
| P3 | 0.5–1 d |
| P4 | 1 d |
| P5 | 0.5 d |
| 合计 | 3.5–4.5 d |

> 取数依赖浏览器登录态与网络；P1 若遇限流顺延，不强推。

## 4. 依赖与风险应对

- 关键依赖：ONES 登录态、合同台账（BDMS）可访问、python-docx。
- 长任务：建设按 Phase 推进，脚本独立可重跑；如批量执行触发隔离规则，用一次性子会话处理纯实现。
- 风险：分页 schema 差异 → P1 先 `__schema` 内省确认再编码。

## 5. 交付与验收

- 每 Phase 跑对应 VERIFICATION 用例；P5 跑交付验收 7 步法。
- 通过后：技能落 L3 分层目录持久化，校验文件存在；`analysis_output` 产物不提交（gitignore）。
- 完成后更新任务卡为 complete，并在 daily 记录沉淀。
