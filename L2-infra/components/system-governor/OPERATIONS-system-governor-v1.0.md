# OPERATIONS — 系统治理工作流（system-governor）v1.0

> 安装 / 启动 / 日常使用 / 故障排查。配套 `PRD / DESIGN-OUTLINE / DESIGN-DETAIL` 同 v1.0。

## 1. 安装

无需安装。纯 Python 标准库（subprocess / threading / json / hashlib），无第三方依赖、无网络/Token 依赖。

```bash
cd /Users/bangcle/.openclaw/workspace
# 自检：查看帮助
python3 L2-infra/components/system-governor/scripts/governor.py run --help
```

依赖的既有组件（均已落地）：
- `L2-infra/scripts/error_handler/scan_errors.py`
- `L2-infra/scripts/system_full_audit.py`
- `L2-infra/components/workspace-temp-cleanup/scripts/{tempcleanctl,archive}.py`
- `model-scheduling/logs/service_guardian_state.json`

## 2. 日常使用

### 2.1 只读盘点（最常用，零风险）

```bash
# 全部四 lane dry-run，零写操作
python3 L2-infra/components/system-governor/scripts/governor.py run

# 只盘点未完成建设任务
python3 L2-infra/components/system-governor/scripts/governor.py run --only D

# 程序消费
python3 ... governor.py run --json
```

### 2.2 真实处置

```bash
# L0/L1 写动作：归档移动 + trash 过期临时资产
python3 ... governor.py run --apply
```

安全保证：
- 默认 dry-run，不加 `--apply` 不产生任何写操作。
- L2（改配置/切 Provider/删数据）、L3（对外副作用/凭据/强推）**永不自动执行**，只在账本记 `needs-human` + 建议命令。
- 归档移动保留相对路径 + sha256 manifest，可回滚。

### 2.3 查看上次账本

```bash
python3 ... governor.py report
# 或直接读 memory/governor-latest.json
```

### 2.4 资产审计（v1.1，默认零写）

```bash
# 全盘资产审计（full_audit §12 六探针：P1 计数漂移/P2 断链/P3 空壳/P4 未提交/P5 残留/P6 重复）
python3 ... governor.py audit

# 限定探针（如只看断链与重复）
python3 ... governor.py audit --only P2,P6

# 结构化报告
python3 ... governor.py audit --json

# 执行 L1 可回滚处置（仅 git mv 归位；L2+ 即使 apply 也只记 needs-human）
python3 ... governor.py audit --apply
```

安全保证：
- 默认零写；L2+（改文档/改代码/提交/降级）永远 needs-human 停手。
- L1 仅 `git mv`（保留历史、可 `git revert`），执行前校验 dest 不存在防覆盖。
- 账本落 `memory/governor-audit-latest.json`（原子写）。

## 3. 产物位置

| 文件 | 说明 |
|---|---|
| `memory/governor-latest.json` | 最近一次 run 账本（gitignore） |
| `memory/governor-audit-latest.json` | 最近一次资产审计账本（v1.1，gitignore） |
| `.archive/` | 归档根目录（dot，gitignore） |
| `.archive/manifest.json` | 归档移动登记（源→目标、规则、sha256） |

## 4. 故障排查

| 现象 | 排查 |
|---|---|
| Lane A 报 `scan_latest_missing` | 先手动跑一次 `scan_errors.py` |
| Lane B 报 `full_audit_unavailable` | 单独跑 `system_full_audit.py --json`（可能超时） |
| Lane B 报 `guardian_state_missing` | `launchctl list \| grep guardian`，检查常驻服务 |
| audit 报 `invalid probe(s)` | `--only` 只接受 P1-P6 |
| audit 报超时 | 加 `--timeout` 提高预算（默认 300s） |
| 归档后想找回 | 查 `.archive/manifest.json` 的 src/dst，手动移回 |
| 某 lane 报 `lane_timeout` | `--only <lane>` 单独重跑，或排查底层脚本卡顿 |

## 5. 子进程执行注意（防静默）

命令耗时 >10s 时，在执行环境设 `yieldMs>=60000` 让其前台跑完拿输出；
若已被转后台，用 `process(action=log)` 拉对应 session 日志，不盲目重跑（见 AGENTS.md「子进程执行规范」）。
