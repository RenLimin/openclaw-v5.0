# L3 通用合同管理专家 — 开发计划（IMPLEMENTATION-PLAN）

| 项 | 值 |
|---|---|
| 文档 | IMPLEMENTATION-PLAN |
| 版本 | v1.0 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 依据 | PRD / OUTLINE / DETAIL / VERIFICATION v1.0 |
| 前置 | DETAIL 已 Rex 审核通过（2026-10-27） |

> 旧 core 742 行已验证实现可直接迁入，L3 以"迁移 + 契约对齐 + 补测试"为主，非从零开发。

---

## 1. Phase 拆分

| Phase | 内容 | 产出 | 准入/验收 | 工时(h) |
|---|---|---|---|---|
| L3-P1 | 骨架 + 旧 core 迁移 | `contract_management/{models,state_machine,risk_engine,amount_utils}.py` | 文件落位、import 通过 | 1.0 |
| L3-P2 | OA 抽象 + 公共导出 | `contract_management/oa/base.py`、`__init__.py` | DETAIL §6/§7 符号齐全 | 0.5 |
| L3-P3 | 测试建设 | `tests/` 6 文件（契约/纯净/状态/风险/金额/幂等） | VERIFICATION §2 | 2.0 |
| L3-P4 | 纯净性 + 契约校准 | AST 扫描、签名 inspect、规则 id 对齐 | AC-1/2/3 全过 | 1.0 |
| L3-P5 | 自测 + 黄金基准 | pytest 全绿、覆盖率达标 | VERIFICATION §7 门槛 | 1.0 |

合计：**5.5h**

---

## 2. 任务依赖

- P1 → P2（导出依赖模块齐备）→ P3（测试依赖实现）→ P4 → P5
- P3 用例可与 P1/P2 并行起草，但执行须在实现之后。

---

## 3. 风险与对策

| 风险 | 对策 |
|---|---|
| 迁移时代码夹带副作用 | test_purity AST 强卡；迁入前逐文件核对 import |
| 规则 id 漂移破坏可追溯 | 集合断言旧 core CHECK_RULES id |
| 签名与 DETAIL 不一致 | inspect.signature 契约测试锁定 |

---

## 4. 完成定义

VERIFICATION §7 全部门槛达成（pytest 全绿、纯净零告警、覆盖 ≥95%/90%、黄金基准匹配），方可进入 L4 联调。

---

## 5. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：5 Phase / 5.5h，迁移为主 |
