# scheduler-guard — 调度资产守卫

> L2 基础设施层 · 定时/自动脚本的调度落地审计
>
> **2026-11-20**：补写根级设计文档，对齐真实代码（`audit.py` + `manifest.yaml` + `LaunchAgent/*.plist`）。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 调度守卫（launchd 调度落地审计） |
| 状态 | ✅ 已建设（2026-11-08 建系统性防线；2026-11-20 补设计文档） |
| 关联规范 | AGENTS.md §子进程执行规范 / §定时任务环境降级红线、`capability-registry/registry.yaml` 条目 `scheduler-guard` |
| 能力注册表 entry | `python3 L2-infra/components/scheduler-guard/audit.py` |

**一句话定位**：所有声称「自动 / 定时 / 恢复 / 巡检」的脚本必须登记在 `manifest.yaml`，
由 `audit.py` 定期核对是否**真的**被 launchd/cron 调度——防止「脚本写好了但从未被调度」这类静默失败。

**背景事故（2026-11-08）**：`check_quota_and_restore.py` 写好但从未被调度，只出现在 memory 文档里，
导致 deepseek 余额耗尽后永久卡死。全库扫描发现同类问题不止一处：**16 个「自动」脚本仅 1 个被调度**。

## 2. 设计约束

以下约束均来自代码/配置实证：

1. **单一权威清单**：`manifest.yaml` 是调度资产的唯一权威（`version: 1`，`updated: 2026-11-08T21:40:00+08:00`，17 条 entries）。审计不猜测、不扫描「看起来像自动」的脚本，只对账清单。
2. **双源交叉验证**：实际状态由两处独立证据合成——
   - `launchctl list`（job 是否**已加载**，含 pid / last_exit）；
   - `plutil -extract ProgramArguments`（plist **声明**了哪个脚本，兼容 `bash -c "exec ... script.py"` 包装形式）。
   二者缺一即判定为 `plist_exists_not_loaded`。
3. **四态判定 + 人工例外**：`scheduled` / `plist_exists_not_loaded` / `unscheduled` / `manual_only`。`manual_only` 用于「被其他调度覆盖」的包装脚本（如 `cron_retry.sh` 是 `check_and_retry.py --apply` 的包装），允许无 plist。
4. **默认只读，修复需人工**：`--fix` 只打印 plist 草稿，**不自动加载**；任何写动作（`launchctl load`）由人执行。
5. **审计自身必须被调度**：`ai.openclaw.scheduler-guard`（`StartInterval 21600` + `RunAtLoad`）每 6h 跑 `audit.py --json`，结果落 `logs/audit-latest.json`。守卫组件不能是「未调度的自动脚本」——自指约束。
6. **plist 可移植性约定**（全部 15 个 plist 一致）：`/bin/bash -c "source ~/.zshenv 2>/dev/null; exec /opt/homebrew/bin/python3 <绝对脚本路径>"`，显式 `WorkingDirectory` + `EnvironmentVariables.HOME`，stdout/stderr 同文件。规避 launchd 环境 PATH 与交互 shell 不一致（见 AGENTS.md 定时任务环境降级红线）。

## 3. 架构

```
┌────────────────────────────────────────────────────────────────┐
│  manifest.yaml（唯一权威，17 entries）                          │
│   script / plist / schedule / status / note                    │
└───────────────┬────────────────────────────────────────────────┘
                │ 读取
                ▼
┌────────────────────────────────────────────────────────────────┐
│  audit.py                                                      │
│                                                                │
│  load_manifest() ──────────────┐                                │
│                                │                                │
│  get_loaded_jobs()             │   launchctl list              │
│    → {label: {pid,last_exit}}  │                                │
│                                │                                │
│  get_plist_scripts()           │   plutil -extract             │
│    → {脚本名: plist路径}        │   ProgramArguments            │
│                                ▼                                │
│  audit()  逐条对账：declared_status vs actual_status            │
│    ├─ actual_plist 且 loaded       → scheduled                 │
│    ├─ actual_plist 未 loaded       → plist_exists_not_loaded   │
│    ├─ 声明 manual_only 且无 plist  → manual_only               │
│    └─ 其余                         → unscheduled               │
│    consistent = declared == actual 或 declared == manual_only  │
└───────────────┬────────────────────────────────────────────────┘
                │
       ┌────────┴─────────┬──────────────────┐
       ▼                  ▼                  ▼
  人类可读报告        --json 结构化      --fix 草稿（不加载）
       │                  │
       │                  ▼
       │        logs/audit-latest.json
       ▼
  stdout 摘要：total / scheduled / unscheduled /
             plist_not_loaded / inconsistent

──────────────────────────────────────────────────────────────────
  调度载体：~/Library/LaunchAgents/*.plist（15 个仓库内 plist）
  ├─ StartInterval（周期型）：error-scan 7200 / provider-health 3600 /
  │   scheduling-health 3600 / service-guardian 300 / gateway-watchdog 300 /
  │   auto-recovery 600 / session-recovery 600 / agent-observer 900 /
  │   colima-check 1800 / scheduler-guard 21600
  ├─ StartCalendarInterval（定点型）：backup 03:00 / session-cleanup 02:00 /
  │   system-audit 09:00 / daily-summary 23:50
  └─ KeepAlive + RunAtLoad（常驻型）：service-guardian-daemon
──────────────────────────────────────────────────────────────────
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 权威清单 | `manifest.yaml` | 登记所有「自动」脚本 → plist 映射与声明状态 |
| 审计器 | `audit.py` | 双源对账 + 四态判定 + 报告/JSON/草稿三输出 |
| 调度载体 | `LaunchAgent/*.plist` | 15 个 launchd job 定义（周期 / 定点 / 常驻三类） |
| 结果产物 | `logs/audit-latest.json` | 最近一次 `--json` 审计结果（每 6h 覆盖） |
| 运行日志 | `logs/scheduler-guard.log` | 审计 job 的 stdout/stderr |

### 3.2 实测状态（2026-11-20 核对）

- `~/Library/LaunchAgents/` 下 `ai.openclaw.*` 共 18 个 label；`launchctl list` 已加载 18 个。
- `audit-latest.json` 摘要：`total 17 / scheduled 15 / unscheduled 0 / plist_not_loaded 1 / inconsistent 1`。
- 仓库 `LaunchAgent/` 目录含 15 个 plist；manifest 另有 2 个 plist（`ai.openclaw.quota-restore`、`ai.openclaw.model-scheduling`）只落在 `~/Library/LaunchAgents`，未纳入本目录。

## 4. 接口与用法

```bash
cd /Users/bangcle/.openclaw/workspace/L2-infra/components/scheduler-guard

# 人类可读审计
python3 audit.py

# 结构化审计（供自动化处置，也是 6h 定时任务实际用法）
python3 audit.py --json

# 生成未调度项的 plist 草稿（只打印，不自动加载）
python3 audit.py --fix
```

**定时任务**：

| label | 周期 | 动作 |
|---|---|---|
| `ai.openclaw.scheduler-guard` | 每 6h（`StartInterval 21600`）+ `RunAtLoad` | `audit.py --json > logs/audit-latest.json 2>&1` |

**新增「自动」脚本检查清单**（README.md 定义）：
1. 写脚本 → 2. 立即登记 `manifest.yaml` → 3. 建 plist 到 `LaunchAgent/` → 4. `launchctl load` → 5. `python3 audit.py` 确认 `scheduled` → 6. **验证脚本真的执行了**（看日志/产出文件，不轻信 plist 加载成功）。

## 5. 业界对标

| 对标 | 借鉴点 | 参考 |
|---|---|---|
| Apple launchd / LaunchAgent 最佳实践 | 声明式 job 定义 + `launchctl` 状态查询 + 显式环境变量/绝对路径；job 状态与声明分离 | Apple Developer「Creating Launch Daemons and Agents」；`launchd.plist(5)`、`launchctl(1)` man page |
| Kubernetes reconcile loop / GitOps | 「期望态（manifest）vs 实际态（已加载 job）」持续对账，漂移即告警 | Kubernetes Controller 模式文档；Argo CD GitOps |
| Backstage Software Catalog | 以单一权威清单为 source of truth，drift 检测而非人工盘点 | backstage.io Software Catalog 文档 |
| Definition of Done（Scrum Guide） | 「自动」的完成定义必须是**可验证的调度落地**，而非脚本存在 | Scrum Guide「Definition of Done」 |

## 6. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-08 | 建立组件：`manifest.yaml` + `audit.py` + 15 个 LaunchAgent plist，补齐 16→17 个脚本的调度落地 |
| 2026-11-08 | 增加 `ai.openclaw.scheduler-guard` 自审计 job（每 6h） |
| 2026-11-20 | 补写根级 `DESIGN.md`，对齐真实代码与实测调度状态 |
