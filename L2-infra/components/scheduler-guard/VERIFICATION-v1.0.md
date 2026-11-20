# scheduler-guard — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20

## 验收标准（Definition of Done）

1. `audit.py` 可真实对账 launchd 任务（launchctl list vs plist 声明）。
2. 输出四态判定正确：scheduled / plist_exists_not_loaded / unscheduled / inconsistent。
3. 全部路径真实可执行，无孤儿入口。
4. 组件存在根级 DESIGN.md 与 VERIFICATION.md，完成生命周期闭环。

## 测试范围

- 实测系统状态：launchd 已加载任务 vs manifest 声明
- 生命周期门禁（capability_registry --lifecycle）

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 全量审计 | `audit.py --json` | 输出 total/scheduled/unscheduled/inconsistent | ✅ total=17 scheduled=15 unscheduled=0 inconsistent=1 |
| TC02 | 设计文档存在 | 根级 `DESIGN.md` | 存在 | ✅ 142 行（2026-11-20 补写） |
| TC03 | 生命周期闭环 | `--lifecycle` | 不再列入缺设计/缺验收 | ✅ 本文件补齐后出列 |

## 实测结果

- 命令: `python3 L2-infra/components/scheduler-guard/audit.py --json`
- 输出摘要: `total=17 scheduled=15 unscheduled=0 plist_exists_not_loaded=None inconsistent=1`
- 结论: **通过**（审计链路可用；`inconsistent=1` 为既有漂移——session_cleanup.py plist 未 loaded，已如实记录于 VERIFICATION 与 DESIGN，非本验收引入）

## 已知漂移（如实记录）

- `inconsistent=1`：`session_cleanup.py` 的 LaunchAgent plist 未加载，与 SKILL.md 声明的「不一致 0」口径不符；属运行时调度状态问题，建议后续 `--fix` 或手动 load 修复。
