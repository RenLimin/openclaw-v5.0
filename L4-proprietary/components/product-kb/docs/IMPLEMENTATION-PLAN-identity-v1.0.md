# IMPLEMENTATION-PLAN — product-kb 权威身份层

| 项 | 值 |
|---|---|
| 文档 | IMPLEMENTATION-PLAN（identity 专项） |
| 版本 | v1.0 |
| 依据 | DESIGN-OUTLINE-identity-v1.0 + DESIGN-DETAIL-identity-v1.0（已提交） |
| 状态 | 待启动（P1 建表需等合同案例验证会话收口） |
| 原则 | 每 Phase：实现 → 真实命令自测 → VERIFICATION → 下一 Phase；不跳步 |

---

## 1. Phase 总览

| Phase | 交付 | 触碰文件 | 碰撞窗口 | 预计工时 |
|---|---|---|---|---|
| P1 | 身份表 + canonical_key 回填 + resolve/register/merge API | product_kb/db.py（加 DDL 方法）、新 `product_kb/identity.py`、新 `tests/test_identity.py`；**product_kb.db 加表，193 产品数据不动** | 可立即开工（加表不迁旧数据） | 3-4h |
| P2 | ContractMatcher 接入 resolve + needs_human_review 四态 | bangcle-contract `product_kb/contract.py` + 报告满足度映射 + 测试 | **验证会话收口后** | 2-3h |
| P3 | 导入幂等 + 身份管理 CLI | product_kb/io.py、product_kb/cli.py + 测试 | 验证会话收口后 | 2h |
| P4 | 审计/回滚 + 批量别名回填 | identity_audit（新表/复用）、回填脚本 + 文档 | 任意 | 2-3h |

> 总计约 9-12h，按 Phase 独立交付，不合并提交。

---

## 2. P1 详细任务（可立即开工，零碰撞）

| # | 任务 | 完成判据 |
|---|---|---|
| 1.1 | db.py 加 `init_identity_tables()`：建 product_identity/product_alias + kb_migration 登记 v12 | `CREATE TABLE IF NOT EXISTS`，重复执行幂等 |
| 1.2 | 新 identity.py：`canonical_key(name)` 规范化函数（NFKC/去标点/小写/保留版本号） | 193 条全量 0 冲突、0 空值 |
| 1.3 | identity.py：`ProductIdentityService`（register/add_alias/resolve/merge/list/get_by_product_id） | 单测全过，语义对齐 L2 IdentityService |
| 1.4 | backfill：为 193 产品逐一生成身份 + `internal` 别名（code、旧 id） | 193 身份 + 别名；重复键进冲突清单（人工裁定） |
| 1.5 | 单测：规范化、register 冲突、resolve CWA、merge 转移/去重/回滚、list | `python3 -m pytest tests/test_identity.py` 全绿 |

**P1 验收命令（真实执行）**：
```bash
python3 -m pytest L4-proprietary/components/product-kb/tests/test_identity.py -v
python3 - << 'PY'
# 断言：身份数=193、canonical_key 无空无重、resolve 未命中返回 None
PY
```

**回滚**：身份表独立，drop 两表即完全回滚，product/sku 无任何改动。

---

## 3. P2 详细任务（验证会话收口后）

| # | 任务 | 完成判据 |
|---|---|---|
| 2.1 | contract.py 注入 ProductIdentityService；match_item 先 resolve('contract_text') | 别名命中跳相似度阈值，直接取权威产品 |
| 2.2 | 新增第四态 needs_human_review（低相似度 <0.5） | OCR 误字不再硬判 unsatisfied |
| 2.3 | 报告 md/xlsx 满足度映射同步四态 | 报告正确显示"待人工确认" |
| 2.4 | 测试：别名命中、低相似度待确认、红线/停售逻辑不变 | 全绿；MVP 既有 20 测试零破坏 |

**E2E 黄金回归**：重跑 MVP 三个真实文件（docx/txt/scan.png），docx 仍满足、txt 仍不满足，scan 的"API安全平司"从 unsatisfied 变为 needs_human_review。

---

## 4. P3 详细任务

| # | 任务 | 完成判据 |
|---|---|---|
| 3.1 | io.py 导入前 resolve/查 canonical_key：命中更新、未命中新建+register+add_alias | 同一价格表连导 3 次幂等，无双记录 |
| 3.2 | cli.py 加 identity-backfill/alias-add/alias-list/merge/resolve/identity-conflicts | 每子命令真实跑通 |
| 3.3 | 测试：幂等导入 + CLI | 全绿 |

---

## 5. P4 详细任务

| # | 任务 | 完成判据 |
|---|---|---|
| 4.1 | merge 写 identity_audit（对齐 L2 P3 decision_record 语义） | 归并全留痕、可查、可回滚 |
| 4.2 | 批量别名回填：价格表原始名、文档文件名提取、2 条已有 aliases JSON 迁入 | 别名覆盖主要跨源写法 |
| 4.3 | 回滚工具：unmerge（恢复 status/merged_into/alias） | 归并可一键回滚 |

---

## 6. 协调与冻结协议（对齐并行两会话）

| 时点 | 动作 |
|---|---|
| 现在 | 仅 P1 可开工：加表 + 新文件，**不 update/delete 既有任何行** |
| 合同案例验证会话收口确认后 | 解锁 P2/P3（改 contract.py/io.py） |
| 每 Phase 开工前 | `git status` + product_kb.db 修改时间，确认无并行写入 |
| 提交 | 每 Phase 独立 commit；不含并行会话的未提交改动 |

---

## 7. 全局验收（最终，对齐 DETAIL §10）

1. 193 产品 canonical_key 全量、0 冲突、0 空值；
2. resolve CWA：别名命中取权威产品，未命中 None；
3. ContractMatcher 低相似度 → needs_human_review；
4. 价格表重复导入幂等；
5. 软归并 alias 转移、可审计、可回滚；
6. L2 114 / L3 42 / L4 20 测试零破坏，身份层新增用例全绿。

---

## 8. 变更历史
| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初稿（4 Phase / 9-12h，P1 零碰撞可立即开工） |
