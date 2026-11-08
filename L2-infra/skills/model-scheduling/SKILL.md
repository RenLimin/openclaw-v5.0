# Model Scheduling — 模型调度与额度恢复技能

> L2 基础设施层技能。管理 model-scheduling 代理、exhausted 额度恢复、调度资产审计。
>
> **触发场景**：模型路由异常、deepseek/longCat 额度耗尽、proxy 卡死、调度资产审计、
> quota-restore 恢复验证、scheduler-guard 防线核查。

## 模块组成

| 模块 | 脚本/组件 | 定位 |
|---|---|---|
| 路由代理 | `scripts/proxy.py` | 接收请求，按任务类型路由到最优 provider |
| 额度恢复 | `scripts/check_quota_and_restore.py` | 检测 exhausted 模型，额度恢复后放回 fallback chain |
| 调度审计 | `L2-infra/components/scheduler-guard/audit.py` | 核对 manifest 与 launchctl 实际调度一致性 |

---

## 一、Exhausted 额度恢复（2026-11-08 修复）

### 问题背景

deepseek 余额耗尽后，系统反复撞 402、永久卡死。根因 3 处：

1. **恢复脚本从未被调度**：`check_quota_and_restore.py` 写好但无 cron/LaunchAgent 引用
2. **TTL 自愈逻辑洞**：402 每次都刷新 `last_checked` → 1h TTL 永远归零
3. **探活无条件覆盖时间戳**：每次 proxy 重启都重置 TTL 时钟

### 修复内容（proxy.py 3 处）

| 位置 | 修复 |
|---|---|
| `_get_provider_health` | exhausted 在 TTL 内返回 `unreachable`（跳过路由），超 1h 返回 `unknown`（重新试探） |
| 402 标记逻辑 | 仅**首次**标记 exhausted 时写 `last_checked`，后续 402 不刷新 |
| `startup_probe` | 仅在**状态变化**或**首次标记**时刷新 `last_checked` |

### 调度落地

```bash
# LaunchAgent: 每 6h 执行恢复脚本
launchctl list ai.openclaw.quota-restore
# 预期: LastExitStatus = 0

# 手动验证（强制输出）
python3 L2-infra/components/model-scheduling/scripts/check_quota_and_restore.py --detail
```

### 验证方式

```bash
# 13 项回归测试（不触网）
cd L2-infra/components/model-scheduling && python3 -m pytest tests/test_proxy_exhausted.py -v
# 预期: 13 passed

# 全量测试
python3 -m pytest tests/ -q
# 预期: 22 passed
```

---

## 二、调度资产审计（scheduler-guard）

### 用途

防止「脚本交付 ≠ 机制交付」——所有声称自动/定时/恢复的脚本必须有调度引用。

```bash
# 审计（JSON 输出）
python3 L2-infra/components/scheduler-guard/audit.py --json

# 预期: 总计 17 | 已调度 16 | 未调度 0 | 不一致 0
# cron_retry.sh 为 manual_only（由 session-recovery 调度覆盖）
```

### manifest 权威清单

`L2-infra/components/scheduler-guard/manifest.yaml` 是 17 个自动脚本的唯一权威清单，
新增脚本必须在此登记并配置 LaunchAgent。

---

## 三、故障排查

| 现象 | 排查命令 |
|---|---|
| 模型全部不可用 | `python3 scripts/health_check.py` |
| deepseek 402 卡死 | `python3 scripts/check_quota_and_restore.py --detail` |
| 调度未生效 | `python3 L2-infra/components/scheduler-guard/audit.py` |
| proxy 未启动 | `launchctl list ai.openclaw.model-scheduling` |

---

## 相关文档

- `L2-infra/components/model-scheduling/CHANGELOG.md` — 修复历史
- `L2-infra/components/model-scheduling/VERIFICATION-v1.1.md` — 测试方案
- `L2-infra/components/scheduler-guard/README.md` — 审计规范
