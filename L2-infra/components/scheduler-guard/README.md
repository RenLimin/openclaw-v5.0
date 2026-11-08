# scheduler-guard — 调度资产守卫

## 用途

**「脚本交付 ≠ 机制交付」的系统性防线。**

所有声称「自动/定时/恢复/巡检」的脚本必须登记在 `manifest.yaml`，
由 `audit.py` 定期核对是否真的被 launchd/cron 调度。
防止「脚本写好了但从未被调度」这类静默失败。

## 背景

2026-11-08 — `check_quota_and_restore.py` 写好但从未被调度，
只出现在 memory 文档里，导致 deepseek 余额耗尽后永久卡死。
全库扫描发现同类问题不止一处：**16 个"自动"脚本仅 1 个被调度**。

## 组件结构

```
scheduler-guard/
├── manifest.yaml       # 调度资产清单（唯一权威）
├── audit.py            # 审计脚本（核对 manifest vs 实际调度）
├── LaunchAgent/        # 补齐的 LaunchAgent plist
│   ├── ai.openclaw.scheduler-guard.plist          # 审计自身（每 6h）
│   ├── ai.openclaw.quota-restore.plist            # 额度恢复（每 6h）
│   ├── ai.openclaw.backup.plist                   # 综合备份（每天 03:00）
│   ├── ai.openclaw.error-scan.plist               # 错误扫描（每 2h）
│   ├── ai.openclaw.daily-summary.plist            # 每日摘要（每天 23:50）
│   ├── ai.openclaw.provider-health.plist          # Provider 健康（每小时）
│   ├── ai.openclaw.service-guardian.plist         # 服务守护 cron 版（每 5min）
│   ├── ai.openclaw.service-guardian-daemon.plist  # 服务守护常驻版（KeepAlive 3s）
│   ├── ai.openclaw.scheduling-health.plist        # 调度健康（每小时）
│   ├── ai.openclaw.session-recovery.plist         # 会话重试（每 10min）
│   ├── ai.openclaw.session-cleanup.plist          # 会话清理（每天 02:00）
│   ├── ai.openclaw.gateway-watchdog.plist          # 网关观测（每 5min）
│   ├── ai.openclaw.colima-check.plist             # Colima/Docker（每 30min）
│   ├── ai.openclaw.system-audit.plist             # 系统全量审计（每天 09:00）
│   ├── ai.openclaw.auto-recovery.plist            # 上下文压缩恢复（每 10min）
│   └── ai.openclaw.agent-observer.plist           # 可观测性埋点（每 15min）
└── logs/
    ├── audit-latest.json   # 最近一次审计结果
    └── scheduler-guard.log # 审计日志
```

## 用法

```bash
# 审计（人类可读）
python3 audit.py

# 审计（JSON，供自动化处置）
python3 audit.py --json

# 生成未调度项的 plist 草稿（不自动加载）
python3 audit.py --fix
```

## manifest.yaml 字段

| 字段 | 说明 |
|---|---|
| `script` | 脚本绝对路径 |
| `plist` | LaunchAgent plist 路径（未调度则 null） |
| `schedule` | 调度周期描述 |
| `status` | `scheduled` \| `unscheduled` \| `manual_only` |
| `note` | 备注 |

`manual_only`：脚本被其他调度覆盖（如 `cron_retry.sh` 是 `check_and_retry.py --apply` 的包装，后者已调度），无需重复调度。

## 新增「自动」脚本时的检查清单

1. 写脚本
2. **立即**在 `manifest.yaml` 登记
3. 创建对应 LaunchAgent plist 到 `LaunchAgent/`
4. `launchctl load` 加载
5. 跑 `python3 audit.py` 确认 `status=scheduled`
6. **验证脚本真的执行了**（看日志/产出文件，不轻信 plist 加载成功）

## 审计调度

`ai.openclaw.scheduler-guard` 每 6h 自动跑 `audit.py --json`，
结果写入 `logs/audit-latest.json`。
若 `unscheduled > 0` 或 `inconsistent > 0`，需人工 review。

## 维护

- 新增脚本 → 更新 `manifest.yaml` + 加 plist + 加载 + 审计
- 删除脚本 → 同步清理 `manifest.yaml` + plist
- 审计异常 → 检查 `logs/audit-latest.json` 的 `unscheduled`/`inconsistent` 项
