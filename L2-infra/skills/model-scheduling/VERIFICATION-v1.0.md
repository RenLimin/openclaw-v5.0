# model-scheduling — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/model-scheduling/`（SKILL.md，薄入口）
> 实际实现: `L2-infra/components/model-scheduling/`（代理/额度恢复/守护）+ `L2-infra/components/scheduler-guard/`（调度审计）

## 验收标准（Definition of Done）

1. Exhausted 额度恢复链路可用：`check_quota_and_restore.py --detail` 能真实探测目标模型可用性，恢复成功才放回 fallback chain，未恢复则保持 exhausted 并给出结论。
2. 恢复脚本**已被调度**（LaunchAgent 存在且 loaded），不得「脚本交付 ≠ 机制交付」。
3. proxy 额度状态机修复生效：exhausted 在 TTL 内 `unreachable`、超 TTL `unknown`；402 仅首次标记写 `last_checked`；`startup_probe` 仅在状态变化/首次标记刷新时间戳。
4. 调度资产审计可程序消费（`audit.py --json`），声明与实际调度一致性可判定。
5. SKILL.md 中的验证口径与实际一致。

## 测试范围

- 组件 pytest 全量（`L2-infra/components/model-scheduling/tests`）。
- `test_proxy_exhausted.py` 单文件回归（SKILL.md 点名的 13 项）。
- `check_quota_and_restore.py --detail` 真实探测。
- `scheduler-guard/audit.py --json` 调度一致性。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 全量回归 | `pytest tests -q`（组件目录） | 全绿 | ✅ 48 passed in 4.78s |
| TC02 | 额度状态机 | `pytest tests/test_proxy_exhausted.py -q` | 13 passed | ✅ 13 passed in 1.22s |
| TC03 | 真实额度探测 | `check_quota_and_restore.py --detail` | 给出恢复/未恢复结论 + exit=0 | ✅ 已恢复 0 / 仍耗尽 2 |
| TC04 | 调度一致性 | `scheduler-guard/audit.py --json` | 无未调度、无不一致 | ⚠️ unscheduled 0，inconsistent 1 |
| TC05 | proxy 存活 | health_check `--only model-scheduling` | 进程/健康/配置全 pass | ✅ 全 pass |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01
  cd L2-infra/components/model-scheduling && python3 -m pytest tests -q -p no:cacheprovider
  # → 48 passed in 4.78s
  #    分布: test_endpoint_probe 7 / test_fallback_resilience 22 / test_proxy_exhausted 13
  #          / test_smoke 2 / test_stream_timeout 4

  # TC02
  python3 -m pytest tests/test_proxy_exhausted.py -q -p no:cacheprovider
  # → 13 passed in 1.22s   （与 SKILL.md 声明「13 项回归测试」一致）

  # TC03（真实触网探测）
  python3 L2-infra/components/model-scheduling/scripts/check_quota_and_restore.py --detail
  # → 发现 2 个 exhausted: deepseek/deepseek-chat, deepseek/deepseek-reasoner
  #   ❌ 仍不可用: HTTP 402: Insufficient Balance (request_id: …)
  #   ⚠️ 所有目标模型仍不可用，保持 exhausted 状态
  #   已恢复: 0 / 仍耗尽: 2     exit=0

  # TC04
  python3 L2-infra/components/scheduler-guard/audit.py --json
  # → total 17 | scheduled 15 | unscheduled 0 | plist_not_loaded 1 | inconsistent 1
  #   ❌ session_cleanup.py: declared=scheduled, actual=plist_exists_not_loaded,
  #      loaded=False, consistent=False
  #   ➖ cron_retry.sh: manual_only / manual_only / consistent=True（合理豁免）

  # TC05
  python3 L2-infra/skills/system-health-check/scripts/health_check.py --only model-scheduling --json
  # → proxy-process / proxy-health / config-models.yaml / config-routing.yaml / config-providers.yaml 全 pass
  ```
- 结论: **通过（含 1 项调度漂移待修）**。额度恢复与状态机逻辑回归全绿（48 用例），真实探测行为符合「未恢复保持 exhausted」设计；恢复脚本与 proxy 均已调度 loaded。

## 遗留问题（如实记录）

1. **调度漂移（新发现）**：`scheduler-guard/audit.py` 实测 `scheduled 15 / plist_not_loaded 1 / inconsistent 1`，而 SKILL.md「验证方式」声明「总计 17 | 已调度 16 | 未调度 0 | 不一致 0」。差异条目为 `session_cleanup.py`（plist 存在但未 loaded）。→ **SKILL.md 口径已过期，需修正**；同时应 `launchctl load` 该 plist 或调整 manifest。
2. **真实环境额度未恢复**：deepseek 两个模型仍为 HTTP 402，属外部账户状态，非本 skill 缺陷；TC03 的验收点是「脚本正确判定并保持 exhausted」，该点通过。
3. **SKILL.md 与组件文档双份维护**：`VERIFICATION-v1.1.md` 在组件侧，skill 侧本文档需与其保持口径同步。
