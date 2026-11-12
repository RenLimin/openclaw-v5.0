# VERIFICATION — 系统治理工作流（system-governor）v1.0

> 验收门与测试结果。配套设计文档同 v1.0。

## 1. 测试套件

| 套件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_governor_p1.py` | 12 | policy L0-L3 分级 / ledger 去重落盘 / orchestrator 异常超时隔离 / Lane D 只读 |
| `workspace-temp-cleanup/scripts/test_archive.py` | 8 | R1-R4 规则命中 / dry-run 零移动 / apply 移动+manifest / 幂等 |

## 2. 验收门（对应 PRD §5）

- [x] `governor.py run`（无 --apply）零写操作（临时 fixture + 真实 dry-run 双重验证）
- [x] `--apply` 下 L0/L1 执行、L2/L3 永不自动（model request errors 归 needs-human 未被处置）
- [x] Lane D 枚举真实未完成任务（current / 67 归档未完成 / 逐标题任务组 / doc_gap）
- [x] 账本去重且与 summary 一致（192 条目，零重复证据）
- [x] 归档规则排除目录永不命中（data/memory/output/数据库）
- [x] 纯 Python 标准库，无 Token/网络依赖
- [x] 跨组件既有测试零破坏（temp-cleanup 21 + error_handler 43 + governor 12 = 76 passed）

## 3. 关键设计修复记录（实现中发现并修复）

| # | 问题 | 修复 |
|---|---|---|
| 1 | policy 的 `archive` 前缀把 Lane D 只读项误判为 FILE | policy 按 lane 隔离，Lane D 恒 CONFIRM |
| 2 | 归组逻辑标题+checkbox 双追加 → 124 组重复 | 用 `added` set 保证标题只入队一次（316→192） |
| 3 | save_report 序列化原始 findings，与去重 summary 不一致 | build_report 去重后按 lane 重建 |
| 4 | Lane B 编辑误删 `audit = _run_audit_json()` | 补回赋值 |

## 4. 真实数据基线（2026-11-10 18:12，apply=True）

- total 204 unique：auto-fixed 2 / needs-human 1 / open 192（其中 Lane D 192，81 验收门 warning）
- 归档：workspace 干净，无命中（`.archive/` 空）
- Lane B needs-human：model request errors 近1h 7 条（配额余波，未自动处置）

---

# VERIFICATION — 资产审计工作流 v1.1（2026-11-12）

> v1.1 增量验收：§12 探针集 + Lane B 接入 + audit 六环节。配套 `DESIGN-DETAIL-system-governor-v1.1.md`。

## 1. 测试套件（新增 34 项）

| 套件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_asset_consistency.py` | 12 | 六探针命中/清零/误报防护（P3 只认完成态文档、P5 排除自指、P6 忽略备份/夹具/小文件） |
| `tests/test_lane_b_assets.py` | 3 | §12 聚合为 Finding；✅→info/ok、⚠️→warning/open 指向 audit；无 §12 不报错 |
| `tests/test_audit_classify.py` | 11 | 六类探针→正确 category/tier；稳定 ID 幂等且唯一；only 过滤；L1/L2 拍板状态 |
| `tests/test_audit_exec.py` | 4 | L1+apply 执行 git mv；L2+apply 永不执行；无 apply 零写；dest 已存在拒绝覆盖 |
| `tests/test_audit_flow.py` | 4 | 六环节串联；账本 schema 合法；dry-run 零写；L1 执行 L2 停手；回归计数 |

## 2. 验收门（对应 DETAIL §5）

- [x] `governor.py audit`（无 --apply）零写操作（git status 前后一致，13→13）
- [x] `--apply` 下 L1 执行、L2+ 不执行（L1 git mv 实测 + L2 needs-human 实测）
- [x] §12 六探针在注入用例下各自命中，清理后清零
- [x] Lane B `run` findings 含 §12 结果（warning 项 action 指向 `governor.py audit`）
- [x] 全量回归：既有 12 项 + 新增 34 项 = 46 passed 零破坏
- [x] 真实执行，不虚构

## 3. 真实数据基线（2026-11-12 13:2x，dry-run）

- total 8 items：needs-human 3（P2×2 断链 + P4 未提交）+ pending 5（P6 重复×5）
- P1 计数漂移：发现 41 / 登记 41 一致（口径修正：只统计组件路径行）
- P2 检出 2 条真实断链：`mcp-server`、`session-orchestrator`（00-system-architecture.md）
- P6 检出 17 组重复候选（排除备份/测试夹具/小文件后）
- 回归：3 warning 残留（P2×2 + P4），待人工处置

## 4. 关键实现修复记录

| # | 问题 | 修复 |
|---|---|---|
| 1 | P1 计数把 BDMS 重建表误算（48 vs 41） | 只统计含组件路径行的行数 |
| 2 | P2 正则漏带尾斜杠引用（66 条） | 允许可选尾斜杠，检出 2 条真实断链 |
| 3 | P3 把 PRD/DESIGN 的「已实现」当完成声明 | 只认 README/STATUS/OPERATIONS/VERIFICATION 的 ✅ 标记 |
| 4 | P5 审计脚本自身常量自指误报 | 排除 system_full_audit.py 自身 |
| 5 | P6 备份目录/测试夹具误报 | 排除 archive/backups/tests 目录 |
| 6 | AuditItem ID 同 evidence 撞车（P2 两条断链同 ID） | 稳定 ID 改用单项业务键（path/component/file:line/paths） |
