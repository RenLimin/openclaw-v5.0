# IMPLEMENTATION-PLAN — Contract Ontology Bridge v1.0（P1/P2）

> 前置：OUTLINE `ac9faff`、DETAIL `f6ff800` 均获 Rex 评审通过（2026-11-04）。
> 范围：P1 只读桥 + P2 持久化/状态机接线。P3/P4 冻结。
> 日期：2026-11-04 · Jerry 🦞
>
> 📌 **关系指针（2026-11-06 追加）**：本计划属 11-04 只读/持久化桥旧路线；11-05 Palantir 动词桥（L4 `contract_review/ontology_bridge/`，`a1efeb4`）另立。两路线并存，关系见同目录 OUTLINE 顶部指针。

## Phase 拆分

| Phase | 交付物 | 依赖 | 估点 | 出口 |
|---|---|---|---|---|
| **P1.a** | `ontology/__init__.py`、`ontology/mapper.py`（字段+金额+状态映射纯函数） | DETAIL §2.1 | 1 | mapper 单测全绿 |
| **P1.b** | `services/oa/cube_provider.py`（CubeClient→OaProvider 只读适配） | P1.a | 1 | OaProvider 接口约束测试全绿 |
| **P1.t** | `tests/unit/test_mapper.py`、`test_cube_provider.py`、`tests/fixtures/card_golden.json` | P1.a/b | 1 | P1 测试真实执行通过 |
| **P2.a** | `repository/db.py` V2 增量迁移（contracts/approval_instances + Repository 方法） | — | 2 | 迁移幂等×3 |
| **P2.b** | `services/contract_service.py`（映射落库 + L3 状态机接线 + 原子审计） | P1.a/P2.a | 2 | 状态机全路径真实 SQLite |
| **P2.t** | `test_contract_service.py` + `tests/integration/test_bridge_e2e.py` | P2 全部 | 2 | 非法动作零落库 / 幂等×3 / 黄金比对 |
| **V** | 组件全量回归（既有 127 不回退）+ L2/L3 跨层抽查 + 7 步验收 | P1+P2 | 1 | VERIFICATION 报告 |

合计约 **10 点**。执行方式：隔离 subagent 分 P1、P2 两段串行（每段 < 50% ctx），主会话清空上下文做独立验收。

## 验收映射（DETAIL §6 → 测试）
| 验收项 | 锁定测试 |
|---|---|
| 字段/金额映射正确、缺失不抛 | test_mapper_*（含黄金 fixture 逐字段） |
| 状态无数据源恒 unknown | test_map_oa_status_unavailable / test_cube_provider_query_unknown |
| 写方法冻结 | test_push/register_callback_raise |
| 迁移幂等 | test_migration_idempotent_3x |
| 状态机全路径 | test_bridge_e2e::test_full_lifecycle |
| 非法动作原子零落库 | test_illegal_action_atomic_no_write |
| 审计 append-only | test_audit_append_only（接口级无 update/delete） |
| 既有不回退 | bangcle-contract 全量 127+ 全绿 |

## 提交策略
- 每个 Phase 独立 commit，`git add` 仅目标文件；排除并行会话的 `models.yaml`/`routing.yaml`。
- 提交信息前缀 `feat(contract-bridge):`；测试产物不入库。
- 全部完成 + 验收通过后统一 push（中途本地 commit）。

## 冻结项（不在本计划）
泛微 workflow 审批流映射、`push_result` 真实写回、回调订阅（P3/P4，待数据源 + Rex 单独拍板）。
