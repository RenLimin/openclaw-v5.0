# L3 通用合同管理专家 — 验证方案（VERIFICATION）

| 项 | 值 |
|---|---|
| 文档 | VERIFICATION（测试方案，开发前冻结） |
| 版本 | v1.0 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 依据 | PRD-v1.0 + DESIGN-DETAIL-v1.0 |
| 状态 | 待审核 |

> 本文档是**准入测试方案**：开发完成的判定标准。测试一律针对 L3 纯函数公开 API，不 mock 业务、不触网/DB/文件。

---

## 1. 验收标准（Definition of Done）

| # | 标准 | 验证手段 |
|---|---|---|
| AC-1 | 公开 API 签名与 DETAIL §7 完全一致 | 契约测试 + `inspect.signature` |
| AC-2 | L3 零副作用：无 `os/sys/subprocess/socket/urllib/sqlite3` import | AST 静态扫描 |
| AC-3 | L3 不 import L4、不引用任何专有名词 | grep + AST |
| AC-4 | 状态机所有合法/非法流转正确 | 参数化用例 §3 |
| AC-5 | 分级表边界金额（10万/50万/200万）口径正确 | 黄金基准 §4 |
| AC-6 | 22 条规则 id 与旧实现一致，扫描判定口径正确 | 黄金基准 §5 |
| AC-7 | 金额大写全场景正确 | 黄金基准 §6 |
| AC-8 | 纯函数：同入参连跑 3 次结果一致，入参不被修改 | 幂等测试 |

---

## 2. 测试文件与运行方式

| 文件 | 内容 |
|---|---|
| `tests/test_contract_contract.py` | AC-1 API 签名 + 导出符号 |
| `tests/test_purity.py` | AC-2/AC-3 AST 静态纯净性 |
| `tests/test_state_machine.py` | AC-4/AC-5 状态机 + 分级 |
| `tests/test_risk_engine.py` | AC-6 风险规则与综合评级 |
| `tests/test_amount_utils.py` | AC-7 金额大写 |
| `tests/test_idempotency.py` | AC-8 幂等 + 不可变 |

```bash
# 纯 stdlib + pytest（无网络）
python3 -m pytest L3-business/components/contract-management/tests/ -q
# 纯净性独立审计
python3 -m tests.test_purity   # 或 pytest tests/test_purity.py
```

纯净性 AST 扫描判定：遍历 `contract_management/**/*.py` 的所有 `ast.Import/ast.ImportFrom`，命中黑名单模块即失败；`oa/base.py` 仅允许 `abc`、`typing`。

---

## 3. 状态机用例（AC-4）

| 用例 | 输入 (status, action) | 金额 | 期望 next |
|---|---|---|---|
| SM-01 | draft, submit | 50,000 | review1, role=销售经理 |
| SM-02 | draft, submit | 800,000 | review1, role=销售总监 |
| SM-03 | review1, approve（多级） | 800,000 | review2, role=法务审查员 |
| SM-04 | review2, approve | 800,000 | review3, role=财务经理 |
| SM-05 | review3, approve（末级） | 800,000 | approved, role=None |
| SM-06 | review2, reject | 800,000 | draft |
| SM-07 | approved, sign | 任意 | signed |
| SM-08 | signed, archive | 任意 | archived |
| SM-09 | review1, approve（单级末级） | 50,000 | approved |
| SM-10 | draft, approve（非法） | — | raises ValueError |
| SM-11 | approved, submit（非法） | — | raises ValueError |
| SM-12 | archived, 任意动作（终态） | — | raises ValueError |
| SM-13 | 任意, action="bogus" | — | raises ValueError |

另测 `can_transition` 与 `VALID_TRANSITIONS` 全连接一致性（遍历每条边双向核对）。

---

## 4. 分级黄金基准（AC-5）

| 金额 | level | roles 序列 |
|---|---|---|
| 0 | 1 | [销售经理] |
| 99,999.99 | 1 | [销售经理] |
| 100,000 | 2 | [销售经理, 法务审查员] |
| 499,999.99 | 2 | 同上 |
| 500,000 | 3 | [销售总监, 法务审查员, 财务经理] |
| 1,999,999.99 | 3 | 同上 |
| 2,000,000 | 4 | [VP/CEO, 法务总监, 财务总监] |
| 100,000,000 | 4 | 同上 |

注入自定义 `level_table` 用例：自定义表覆盖默认值，验证 DI 生效（不只是参数被接收）。

---

## 5. 风险引擎黄金基准（AC-6）

- 规则总数 = 22；`id` 集合与旧 core `CHECK_RULES` 完全一致（集合断言）。
- 构造**最小合规合同文本**（含全部命中关键词）→ 期望 22 pass、overall=low。
- 构造缺陷文本逐条反例：

| 反例 | 期望 |
|---|---|
| 删除签字盖章 | 1.5 → fail（high） |
| 违约金 50% | 6.2 → fail（high） |
| 违约金 20% | 6.2 → pass |
| 删除保密期限但留"保密" | 9.2 → warning |
| 仅缺"份"约定（low） | 13.1 → warning，不升级 overall |
| 3 条 warning | overall=medium（warning>2） |
| 任一 high fail | overall=high |

`to_dict()` 结构断言：键集合 + findings 已展开为原生 dict（无 dataclass 残留）。

---

## 6. 金额大写黄金基准（AC-7）

| 输入 | 期望输出 |
|---|---|
| 0 | 零元整 |
| 105 | 壹佰零伍元整 |
| 10000 | 壹万元整 |
| 12345.67 | 壹万贰仟叁佰肆拾伍元陆角柒分 |
| 100.05 | 壹佰元零伍分 |
| 200000000 | 贰亿元整 |
| -50 | 负伍拾元整 |

---

## 7. 准入门槛

- pytest 全绿（用例数以最终落地为准，目标 ≥ 50）
- test_purity 零告警
- 覆盖率：`contract_management/` 行覆盖 ≥ 95%，分支 ≥ 90%
- 黄金基准 100% 匹配

未满足任一项，不得进入"开发完成"，不允许提交实现代码合并。

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版测试方案：8 验收标准 + 状态机/分级/风险/金额黄金基准 |
