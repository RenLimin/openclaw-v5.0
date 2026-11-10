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
