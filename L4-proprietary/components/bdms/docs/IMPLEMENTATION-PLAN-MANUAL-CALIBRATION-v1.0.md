# IMPLEMENTATION-PLAN — BDMS 人工数据校准与填写 v1.0 开发计划

> 状态：**待 Rex 审核** | 作者：Jerry 🦞 | 日期：2026-10-28
> 依据：`PRD / OUTLINE / DETAILED / VERIFICATION / OPERATIONS` v1.0（均通过）
> 配套：总计划 `IMPLEMENTATION-PLAN-v2.1.md`；本计划仅覆盖「人工校准」增量。
> 本文通过后才进入编码（Phase 1）。

---

## 0. 版本定位

在已交付的 BDMS 交付月报模块上，旁路增量「人工数据校准与填写」能力。
不重写、不侵入核心算法，新增一张覆盖层 + 一个服务 + 一组 API + 前端对话框。

**交付边界**：v1.0 只做交付月报域（`dr_*`），不含批量粘贴、多级审批、其他模块。

---

## 1. 现有代码资产盘点

| 资产 | 文件 | 复用/改造方式 |
|---|---|---|
| 月报数据加载 | `modules/delivery_report/engine.py::load` | 加 raw/effective 选项，复用 |
| 校验规则 | `modules/delivery_report/validator.py` | 抽 `collect_suspicious_from_df`，规则不动 |
| 月报写出 | `modules/delivery_report/exporter.py` | 输入改 effective + 追加台账 Sheet |
| 服务编排 | `modules/delivery_report/service.py` | 新增校准编排；`revalidate` 走 effective |
| Web 路由 | `web/api.py` | 新增 7 个校准端点 |
| 前端报告页 | `web/templates/report.html`（内联 JS） | 校准对话框 + 数据浏览编辑 + 动态 Sheet |
| DB 助手 | `core/db.py` | init_db 注册新 schema；新增校准读写助手 |
| Schema | `core/schemas_v21.py` | 新增 `DR_CALIBRATION_SCHEMA` |
| 异步 job | `core/db.py` create_job + 现有轮询 | 大批量重校验复用 |
| 破坏性旧路径 | `validator.py:191` / `service.py:756,775` | 废弃/改走覆盖层 |

---

## 2. 开发原则

1. 先契约后实现：严格按 DETAILED 的 DDL/签名/API，不临时改字段。
2. 原始行零写入：任何提交前先跑 S-01（md5 不变）守门。
3. 单口径：所有对外数据经 `apply_overlays`，写完一步 grep 一次调用点。
4. 每 Phase 可独立验证：跑对应测试组，绿了才进下一 Phase。
5. 长任务隔离：编码量大的 Phase 用 subagent 分段，主会话只做评审与集成。
6. 真实测试：API/E2E 不用 TestClient 打网络写路径。

---

## 3. Phase 拆分

### Phase 1：数据模型 + DB 层（基础）
**目标**：两张表可建可读写，原始行零改动。

- [ ] `schemas_v21.py` 新增 `DR_CALIBRATION_SCHEMA`（dr_calibration + history + 部分唯一索引）
- [ ] `db.py::init_db` 注册 executescript
- [ ] `db.py` 新增校准读写助手（upsert/revoke/get_active_map/list/history）
- [ ] 启动验证旧库幂等建表
- [ ] 单元测试：建表、唯一索引 active 约束、revoked 可再校准

**退出标准**：U-01~U-05、S-01 思路就位；`pytest` 现有用例不回归。
**预估**：0.5 人日

### Phase 2：CalibrationService + 解析层（核心）
**目标**：覆盖层应用与值校验可用。

- [ ] 新建 `modules/delivery_report/calibration.py`
- [ ] 实现 `get_active_map / apply_overlays`（copy 语义、错位告警）
- [ ] 实现 `upsert / revoke`（事务 + history + 回填 corrected_value）
- [ ] 实现 `_validate_value`（日期/数值/文本/枚举，枚举取主数据 legend）
- [ ] 实现 `list_calibrations / overview / ledger_rows`
- [ ] 定义 `CalibrationError`（code：INVALID_TYPE/LOCKED/EMPTY_REASON/NOT_FOUND/BUSY）
- [ ] 单元测试 U-06~U-13

**退出标准**：单元全绿；apply_overlays 不改入参；非法值不落库。
**预估**：1 人日

### Phase 3：重校验闭环
**目标**：保存校准后自动增量重校验，问题状态正确流转。

- [ ] validator 抽 `collect_suspicious_from_df(month, sheets, only_sheets)`
- [ ] 原 `collect_suspicious` 改为调用新函数（规则单份）
- [ ] service 新增 `recalculate_after_calibration(month, affected)`
- [ ] issue 流转 confirmed/pending + 回填 operator/resolved_at
- [ ] 重算 review_status KPI
- [ ] `SYNC_LIMIT=200`：超限建 job 异步，分步进度
- [ ] 同月 job 进行中写操作返回 409
- [ ] 测试 A-01（重校验部分）、S-02/S-03、I-03

**退出标准**：校准→问题消失；撤销→问题回现；KPI 数值正确；大批量有进度。
**预估**：1 人日

### Phase 4：Web API
**目标**：7 个端点真实 HTTP 可用。

- [ ] POST `/calibrations/{month}`（提交/修改，含同步/异步返回）
- [ ] POST `/calibrations/{month}/revoke`
- [ ] GET `/calibrations/{month}`（sheet/row/status 过滤）
- [ ] GET `/calibrations/{month}/overview`
- [ ] GET `/sheets/{month}`（动态 Sheet）
- [ ] GET `/calibration-ledger/{month}`
- [ ] Pydantic 请求模型 + 统一错误响应（400/404/409）
- [ ] approved 月报锁定校验
- [ ] API 集成测试 A-01~A-12（真实 HTTP）

**退出标准**：14 条 API 测试全绿；错误码与 DETAILED 契约一致。
**预估**：0.75 人日

### Phase 5：前端（问题清单 + 数据浏览）
**目标**：人工可在界面完成校准全流程。

- [ ] 校准对话框组件（原值只读 + 动态控件 + 原因必填）
- [ ] 问题清单每行加「校准」按钮并接对话框
- [ ] 保存成功 toast + 刷新列表与 KPI
- [ ] 数据浏览 Sheet 下拉改动态接口（15 项）
- [ ] 数据浏览「进入编辑」+ 单元格发起校准
- [ ] 已校准单元格标记 + 悬停摘要 + 查看记录/撤销
- [ ] job_id 返回时的分步进度条
- [ ] E2E：E-01~E-06、E-09、E-10

**退出标准**：10 条 E2E 中界面相关全绿；空原因/锁定在 UI 层被拦截。
**预估**：1.25 人日

### Phase 6：导出增强
**目标**：导出含校准后值 + 台账 Sheet。

- [ ] exporter 数据源切到 effective
- [ ] 已校准单元格 openpyxl Comment 批注
- [ ] 追加「校准台账」Sheet（有校准才生成）
- [ ] 复用 `/export/{month}`，不新增路径
- [ ] 测试 A-13、E-07、黄金基准逐格比对、I-04

**退出标准**：导出值=黄金值；台账行数=active 数；无校准时无空 Sheet。
**预估**：0.5 人日

### Phase 7：旧路径收敛 + 调用点收口
**目标**：破坏性方法清零，单口径无绕过。

- [ ] 全仓 grep `apply_manual_fixes/apply_fixes`，确认外部调用
- [ ] 删除/废弃 `validator.apply_manual_fixes`
- [ ] `service.apply_fixes` 改走 CalibrationService 或移除
- [ ] grep 所有 `load_sheet_rows/engine.load`，确认对外读取都过解析层
- [ ] exporter/前端数据来源复核（C-03~C-06）
- [ ] 新增"原始行不可变"回归测试 S-01 全量
- [ ] regenerate 使校准失效逻辑（二次确认 + 批量 revoke 留痕）

**退出标准**：C-01~C-06 扫描报告 0 残留；S-01 全量通过。
**预估**：0.5 人日

### Phase 8：E2E 自测 + 7 步验收
**目标**：达到交付验收标准，交 Rex 人工验收。

- [ ] 跑全部 45 条测试（单元13/API14/E2E10/幂等4/安全4）
- [ ] 黄金基准 0 差异
- [ ] 幂等各 3 次稳定
- [ ] 调用点扫描归档
- [ ] 按交付验收 7 步法独立审计 + 出报告
- [ ] 修复发现的问题直至全绿
- [ ] 更新 OPERATIONS（如有实操差异）
- [ ] commit + push（获 Rex 授权后）

**退出标准**：7 步法全部通过；测试报告 + 对比报告 + 扫描报告齐备。
**预估**：0.75 人日

---

## 4. 依赖关系

```
P1 数据模型
  └─ P2 CalibrationService
        ├─ P3 重校验闭环
        │     └─ P4 Web API ── P5 前端
        │                       │
        └─ P6 导出增强 ──────────┤
                                  └─ P7 旧路径收敛 ── P8 验收
```
- P2 是核心，P3/P6 依赖它；P4 依赖 P3；P5 依赖 P4。
- P7 可与 P5/P6 部分并行，但必须在 P8 前完成。

---

## 5. 里程碑与工时

| 里程碑 | 内容 | 预估 | 累计 |
|---|---|---|---|
| M1 | P1+P2 数据与核心服务可用 | 1.5 d | 1.5 |
| M2 | P3+P4 重校验闭环 + API | 1.75 d | 3.25 |
| M3 | P5+P6 前端 + 导出 | 1.75 d | 5.0 |
| M4 | P7+P8 收敛 + 验收交付 | 1.25 d | **6.25 人日** |

> 工时为净开发估算，不含等待 Rex 审核与产品确认；各 Phase 退出需测试绿。

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 对外读取路径有遗漏，绕过解析层 | 高 | 每 Phase grep，P7 专项收口，C-03 守门 |
| 25k 问题全量重校验慢 | 中 | only_sheets 增量 + SYNC_LIMIT 异步 + 进度条 |
| 前端内联 JS 改造易回归 | 中 | 先冻结现有 E2E 基线，再增量改，逐条 E2E 验 |
| 枚举集合来源不一致 | 中 | 统一取主数据 legend，复用 validator 同源 |
| regenerate 行号漂移致校准错位 | 中 | 重生成即失效 + 二次确认 + history 留痕 |
| 旧方法被外部脚本依赖 | 低 | P7 全仓 grep + 灰度保留一版再删 |

---

## 7. 交付物清单

- 代码：`calibration.py`、db 助手、schema、7 API、前端对话框、exporter 台账。
- 测试：`test_calibration_unit.py` / `_api.py` / `_e2e.py` + 黄金 fixture。
- 报告：测试报告、黄金基准对比报告、调用点扫描报告、7 步法验收报告。
- 文档：本套 6 份设计文档（已完成 5 份）+ OPERATIONS。

---

## 8. 变更历史

- 2026-10-28 v1.0：Jerry 初稿。8 Phase、6.25 人日、4 里程碑、依赖图与风险缓解。
