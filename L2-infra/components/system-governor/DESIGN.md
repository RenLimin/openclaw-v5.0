# system-governor — 系统治理工作流

> L2 基础设施层 · 四 lane 治理编排 + 资产审计（P1–P6）
>
> **2026-11-20**：补写根级设计文档，对齐真实代码（`scripts/governor.py` + `src/` + `tests/`）。
> 配套：`DESIGN-DETAIL-system-governor-v1.0.md` / `DESIGN-DETAIL-system-governor-v1.1.md`、
> `OPERATIONS-system-governor-v1.0.md`、`VERIFICATION-system-governor-v1.0.md`。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 系统治理（编排 + 策略 + 账本 + 资产审计） |
| 状态 | ✅ 已建设（v1.0 2026-11-10；v1.1 2026-11-12 接入资产审计） |
| 关联规范 | AGENTS.md §资产生命周期闭环铁律、§子进程执行规范；`capability-registry/registry.yaml` 条目 `system-governor` / `skill-system-governor` |
| 能力注册表 entry | `python3 L2-infra/components/system-governor/scripts/governor.py audit`（及 `--apply`） |

**一句话定位**：把「系统里的问题」拆成四条互不依赖的 lane 并发盘点，
按 L0–L3 分级策略决定「自愈 / 可回滚执行 / 需人工 / 禁止自动」，
全部落统一账本；v1.1 追加资产一致性六探针（P1–P6）审计工作流。

## 2. 设计约束

以下约束均来自代码/配置实证：

1. **默认 dry-run**：`run` 与 `audit` 不加 `--apply` 时零写操作（`policy.will_write()` = `apply and tier in (AUTO, FILE)`）。审计实现里以临时 fixture + 真实 dry-run 双重验证过。
2. **L2/L3 永不自动**：`tier_for()` 未知项默认 `CONFIRM`（宁可停手）；`FORBIDDEN` 只记 `open`；L2/L3 即使 `--apply` 也只记 `needs-human`。Lane D 恒 `CONFIRM`（纯只读盘点，且与 Lane C 的 `archive` 前缀撞名，故按 lane 优先隔离）。
3. **幂等键 + 原子落盘**：`make_key = sha1(lane|item|normalize_evidence)[:16]`，跨 lane 同键只保留 severity 最高者；`save_report` / `_save_ledger` 用 `tmp + replace` 原子替换。
4. **单 lane 故障隔离**：`orchestrator.run_lane_with_budget` 用 daemon 线程 + `join(timeout=120)`，超时只产出一条 `lane_timeout` warning，不阻塞其余 lane；异常转 `lane_error`。
5. **纯标准库、无 Token/网络依赖**：`subprocess / threading / json / hashlib / sqlite3`，无第三方包；子进程用绝对脚本路径（`FULL_AUDIT`、`TEMPCLEANCTL`、`ARCHIVE` 均为绝对路径常量）。
6. **写动作只做可回滚操作**：Lane C `--apply` 走 `archive.py`（归档移动 + `.archive/manifest.json` 登记，含 sha256，可回滚）与 `tempcleanctl clean`（trash）；`audit_exec` 仅 `git mv`，且执行前校验 `src` 存在、`dest` 不存在（拒绝覆盖）。
7. **审计六环节闭环**：取证 → 定性 → 方案 → 拍板 → 执行 → 回归；回归阶段重跑 §12 探针并把仍告警项记入 `regression`，避免「自己报零告警」的自证偏差。

## 3. 架构

```
                    ┌─────────────────────────────────────┐
                    │  scripts/governor.py（统一 CLI 入口）│
                    │  run | report | audit               │
                    └──────────────┬──────────────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
┌───────────────────┐   ┌────────────────────┐   ┌──────────────────────────┐
│ src/orchestrator  │   │ src/ledger         │   │ src/audit_flow（v1.1）    │
│ ThreadPoolExecutor│   │ dedupe + summary   │   │ 六环节                    │
│ + 120s lane 预算  │   │ + 原子落盘         │   │ 取证→定性→方案→拍板→执行→回归│
└─────────┬─────────┘   └─────────┬──────────┘   └────────────┬─────────────┘
          │ 4 lane 并发            │                           │
          ▼                        ▼                           ▼
┌──────────────────────────────────────────────┐   ┌──────────────────────────┐
│ src/lanes/（适配器，只读聚合既有组件）         │   │ src/audit_classify       │
│  A 已知问题自愈  ← memory/error-scan-latest  │   │  §12 探针 → AuditItem    │
│  B 资产健康      ← full_audit §3/§4/§12 +    │   │  （category/suggestion/  │
│                  ← guardian_state.json        │   │   tier / 稳定 ID）       │
│  C 文件治理      ← tempcleanctl / archive     │   ├──────────────────────────┤
│  D 建设任务盘点  ← tasks.db / task-history /  │   │ src/audit_exec           │
│                  ← 文档未勾选项 / doc_gap      │   │  仅 git mv（L1+apply）    │
└──────────────────────────────────────────────┘   └──────────────────────────┘
          │
          ▼
  src/models.py（Finding / LaneResult / GovernanceReport / AuditItem）
  src/policy.py（L0 auto / L1 file / L2 confirm / L3 forbidden）
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| CLI 入口 | `scripts/governor.py` | `run` / `report` / `audit` 三个子命令；`--only` / `--apply` / `--json` / `--timeout` / `--ledger` |
| 编排器 | `src/orchestrator.py` | 并发调度 lane，单 lane 异常/超时隔离（`LANE_BUDGET_SEC = 120`） |
| 数据模型 | `src/models.py` | `Finding` / `LaneResult` / `GovernanceReport` / `AuditItem` + 状态常量 |
| 策略 | `src/policy.py` | L0–L3 分级规则表 + 显式 `tier=` 覆盖 + `will_write` / `resolve_status` |
| 账本 | `src/ledger.py` | 跨 lane 去重、summary 口径统一、原子落盘 |
| Lane A | `src/lanes/lane_a_issues.py` | 读 `error-scan-latest.json` 映射为 Finding（写动作委托 `scan_errors.py`，不重复执行） |
| Lane B | `src/lanes/lane_b_assets.py` | 聚合 `full_audit --json` §3/§4/§12 + `service_guardian_state.json` |
| Lane C | `src/lanes/lane_c_files.py` | dry-run 出 planned 清单；`--apply` 先 archive 再 trash |
| Lane D | `src/lanes/lane_d_tasks.py` | 只读：tasks.db active 任务 / 归档未完成 / 文档未勾选项按标题归组 / OUTLINE 缺 DETAIL |
| 审计流程 | `src/audit_flow.py` | 六环节串联 + 回归重跑 §12 + 原子落 `memory/governor-audit-latest.json` |
| 审计定性 | `src/audit_classify.py` | 六探针解析器（P1–P6）+ 规则表 + 稳定 ID |
| 审计执行 | `src/audit_exec.py` | 仅 L1 + apply 执行 `git mv`，dest 存在即拒绝覆盖 |

### 3.2 四条 lane 语义

| Lane | 名称 | 数据来源 | 写动作 |
|---|---|---|---|
| A | 已知问题自愈 | `memory/error-scan-latest.json` | 无（委托 `scan_errors.py` / reliability 模块） |
| B | 资产健康 | `system_full_audit.py --json` §3/§4/§12、`service_guardian_state.json` | 无（服务拉起由 guardian 常驻完成） |
| C | 文件治理 | `tempcleanctl.py dry-run --json`、`archive.py --json` | `--apply`：归档移动 + trash 过期项 |
| D | 建设任务盘点 | `memory/tasks.db`、`memory/task-history/*.md`、L2–L4 文档未勾选项、`docs/architecture` | 无（恒 CONFIRM，只读） |

### 3.3 资产审计六探针（v1.1）

| 探针 | 类别 | 处置建议 | tier |
|---|---|---|---|
| P1 计数漂移 | 口径漂移 | 运行 `gen_asset_inventory.py` 重新登记 | L1 |
| P2 路径断链 | 断链 | 修正文档引用（改文档或补齐路径） | L2 |
| P3 空壳组件 | 空壳 | 降级为「📐 设计态」或补实现 | L2 |
| P4 未跟踪/未提交 | 口径漂移 | 人工确认范围后 git add + commit | L2 |
| P5 硬编码根路径 | 残留 | 改代码路径 + 迁移文件 + 重启 daemon | L2 |
| P6 重复资产 | 重复 | `git mv` 归位到规范目录 | L1 |

## 4. 接口与用法

```bash
cd /Users/bangcle/.openclaw/workspace

# ── run：四 lane 治理（默认 dry-run，零写）──
python3 L2-infra/components/system-governor/scripts/governor.py run
python3 L2-infra/components/system-governor/scripts/governor.py run --only D
python3 L2-infra/components/system-governor/scripts/governor.py run --json
# --apply：执行 L0/L1 写动作（归档移动 + trash 过期临时资产）
python3 L2-infra/components/system-governor/scripts/governor.py run --apply

# ── report：读取最近一次 run 账本 ──
python3 L2-infra/components/system-governor/scripts/governor.py report
# 或直接读 memory/governor-latest.json

# ── audit：资产审计六环节（默认零写）──
python3 L2-infra/components/system-governor/scripts/governor.py audit
python3 L2-infra/components/system-governor/scripts/governor.py audit --only P2,P6
python3 L2-infra/components/system-governor/scripts/governor.py audit --json
python3 L2-infra/components/system-governor/scripts/governor.py audit --apply
python3 L2-infra/components/system-governor/scripts/governor.py audit --timeout 600
```

**产物位置**：

| 文件 | 说明 |
|---|---|
| `memory/governor-latest.json` | 最近一次 run 账本（gitignore） |
| `memory/governor-audit-latest.json` | 最近一次资产审计账本（v1.1，gitignore） |
| `.archive/` | 归档根目录（dot，gitignore） |
| `.archive/manifest.json` | 归档移动登记（源→目标、规则、sha256） |

**测试**：

```bash
python3 -m pytest L2-infra/components/system-governor/tests/ -v
```

套件：`test_governor_p1.py`（12，policy/ledger/orchestrator/Lane D）、
`test_asset_consistency.py`（12，P1–P6 六探针命中/清零/误报防护）、
`test_lane_b_assets.py`（3）、`test_audit_classify.py`（11）、
`test_audit_exec.py`（4）、`test_audit_flow.py`（4）——合计 46 passed（2026-11-12 基线）。

## 5. 业界对标

| 对标 | 借鉴点 | 参考 |
|---|---|---|
| Kubernetes Controller / reconcile loop | 期望态 vs 实际态对账、单控制器故障隔离、幂等执行 | Kubernetes 官方文档 Controller 模式；`k8s.io/controller-runtime` |
| Backstage Software Catalog | 资产清单一致性探针（计数漂移 / 断链 / 空壳 / 未提交 / 重复）映射为 catalog drift 检测 | backstage.io Software Catalog 文档 |
| OWASP 安全左移（shift-left） | L2/L3 永不自动、默认 dry-run、只执行可回滚操作 | OWASP「Shift Left Testing」；OWASP Top 10 治理实践 |
| Definition of Done（Scrum Guide） | 每个 finding 必须给出可验证的完成定义（done / needs-human / planned），而非「已记录」 | Scrum Guide「Definition of Done」 |

## 6. 与其他组件的关系

```
system-governor（本组件）
  ├─ 依赖 ─── L2-infra/scripts/error_handler/scan_errors.py（Lane A 数据来源）
  ├─ 依赖 ─── L2-infra/scripts/system_full_audit.py（Lane B + audit §12 取证）
  ├─ 依赖 ─── L2-infra/components/workspace-temp-cleanup/scripts/{tempcleanctl,archive}.py（Lane C 执行）
  ├─ 依赖 ─── L2-infra/components/model-scheduling/logs/service_guardian_state.json（Lane B）
  ├─ 依赖 ─── memory/tasks.db / memory/task-history/（Lane D）
  ├─ 被调用 ─ AGENTS.md §资产生命周期闭环铁律（验收/登记）
  └─ 同族 ─── skill-system-governor（L2-infra/skills/system-governor/SKILL.md）
```

## 7. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-10 | v1.0：四 lane 编排 + L0–L3 policy + 统一账本 + Lane D 只读盘点 |
| 2026-11-12 | v1.1：接入 `audit` 子命令（六环节）+ §12 六探针 + Lane B 聚合 + 稳定 ID / 去重修复 |
| 2026-11-13 | `memory/governor-latest.json` 最近一次 run 账本 |
| 2026-11-20 | 补写根级 `DESIGN.md`，对齐真实代码与验收基线 |
