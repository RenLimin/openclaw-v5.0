# gateway-safety — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20

## 验收标准（Definition of Done）

1. 安全重启必须经过 pre-restart guard 预检，硬阻断不可被 `--force` 静默绕过。
2. 挂起补偿（recovery_pending）有界：`MAX_COMPENSATIONS=1` + TTL 30min。
3. 全部路径真实可执行，无孤儿入口。
4. 组件存在根级 DESIGN.md 与 VERIFICATION.md，完成生命周期闭环。

## 测试范围

- 组件自动化测试（tests/）
- 生命周期门禁（capability_registry --lifecycle）

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 组件测试套件 | `pytest L2-infra/components/gateway-safety/tests -q` | 全绿 | ✅ **7 passed in 0.01s** |
| TC02 | 设计文档存在 | 根级 `DESIGN.md` | 存在 | ✅ 246 行（2026-11-20 补写） |
| TC03 | 生命周期闭环 | `--lifecycle` | 不再列入缺设计/缺验收 | ✅ 本文件补齐后出列 |

## 实测结果

- 命令: `python3 -m pytest L2-infra/components/gateway-safety/tests -q -p no:cacheprovider`
- 输出摘要: `7 passed in 0.01s`
- 结论: **通过**（自动化测试全绿；safe_restart.sh / pre_restart_guard.py / recovery_pending.py 契约与 AGENTS.md 红线一致）
