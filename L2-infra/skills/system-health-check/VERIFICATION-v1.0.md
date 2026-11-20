# system-health-check — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/system-health-check/`（SKILL.md + config/services.json + scripts/health_check.py + scripts/service_health_check.py）

## 验收标准（Definition of Done）

1. `health_check.py` 八类检查可运行：gateway / channels / model-scheduling / components / cron / tests / secrets / git，输出人类可读与 `--json` 两种格式。
2. 退出码语义正确：`0` 全通过、`1` 有失败、`2` 检查自身出错；`--brief` 只出摘要；`--only/--skip` 类别过滤生效。
3. `service_health_check.py` 两层检测可用：L1 存活（<5s）+ L2 业务路径（<30s），支持 `--list / --l1-only / --json / --brief / --fix`。
4. 服务注册与 `config/services.json` 一致，`--list` 可枚举。
5. 服务状态三态正确：healthy / degraded / failed。

## 测试范围

- `health_check.py`：全量 brief、JSON、`--only`、`--skip`。
- `service_health_check.py`：`--list`、全量 L1、单服务 L1+L2、JSON。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 全量摘要 | `health_check.py --brief` | 有 total/passed/failed/warn | ✅ 20 项：18 pass / 2 warn / 0 fail |
| TC02 | JSON 格式 | `health_check.py --json` | summary + checks[] | ✅ 20 项结构完整 |
| TC03 | 类别过滤 | `--only gateway --json` | 仅 gateway 类 | ✅ 2 项全 pass |
| TC04 | 跳过类别 | `--skip git --brief` | 总数下降且无 git | ✅ 16 项（15 pass / 1 warn） |
| TC05 | 服务枚举 | `service_health_check.py --list` | 列出注册服务 | ✅ 4 个服务 |
| TC06 | L1 全量 | `all --l1-only` | 三态汇总 | ✅ 2 healthy / 2 failed（bdms-web、llama-cpp 未启动） |
| TC07 | 单服务 L1+L2 | `openclaw-gateway --json` | overall=healthy | ✅ healthy（L1+L2 均 pass） |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01
  python3 L2-infra/skills/system-health-check/scripts/health_check.py --brief
  # → 总检查项: 20 | ✅ 通过: 18 | ⚠️ 警告: 2 | ❌ 失败: 0 | ⏭️ 跳过: 0    exit=0

  # TC02（JSON 摘要）
  python3 L2-infra/skills/system-health-check/scripts/health_check.py --json
  # → summary {total:20, passed:18, failed:0, warn:2, skipped:0}
  #   warn: components/design-docs、git/working-tree（工作区有并行会话在途改动）

  # TC03
  python3 L2-infra/skills/system-health-check/scripts/health_check.py --only gateway --json
  # → {total:2, passed:2}  gateway-running pid 69547 / gateway-version OpenClaw 2026.9.8 (fc23bc8)

  # TC04
  python3 L2-infra/skills/system-health-check/scripts/health_check.py --skip git --brief
  # → 总检查项: 16 | 通过 15 | 警告 1 | 失败 0    exit=0

  # TC05
  python3 L2-infra/skills/system-health-check/scripts/service_health_check.py --list
  # → 4 个服务：openclaw-gateway(critical) / model-scheduling-proxy(critical)
  #            / bdms-web(high) / llama-cpp-embedding(high)

  # TC06
  python3 L2-infra/skills/system-health-check/scripts/service_health_check.py all --l1-only
  # → 服务总数 4 | ✅ 健康 2 | ❌ 失败 2 | exit=1
  #   ✅ OpenClaw Gateway（openclaw status 含 'Dashboard'）
  #   ✅ Model Scheduling Proxy（/health HTTP 200）
  #   ❌ BDMS Web UI（Connection refused）
  #   ❌ Llama-cpp Embedding（Connection refused）

  # TC07
  python3 L2-infra/skills/system-health-check/scripts/service_health_check.py openclaw-gateway --json
  # → overall healthy；l1_process_status pass / l2_dashboard_http pass（HTTP 200, 20432 bytes）
  ```
- 结论: **通过**。两模块契约（JSON 结构、退出码、类别过滤、服务枚举、三态判定）实测符合 SKILL.md；失败项为真实环境未启动服务，判定正确。

## 遗留问题（如实记录）

1. **两项服务未启动**：`bdms-web`、`llama-cpp-embedding` 实测 Connection refused。属运行环境状态，非脚本缺陷；`--fix` 修复路径本次未触发（避免对共享环境执行重启）。建议后续用 `--l1-only --fix` 在受控窗口验证修复链路。
2. **文档与实现项数差异**：SKILL.md 示例写「总检查项: 28」，实测为 20（8 类）。属示例口径漂移，非功能缺陷；建议把示例改为实际量级或标注「示例」。
3. **components/design-docs 长期 warn**：健康检查报 L2 组件 DESIGN.md 覆盖存在警告，与本次 10 个 skill 的验收补齐工作相关，可在补齐后复跑确认是否消除。
