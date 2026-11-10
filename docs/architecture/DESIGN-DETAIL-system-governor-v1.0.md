# DESIGN-DETAIL — 系统治理工作流（system-governor）v1.0

- 状态：**待 Rex 评审**
- 日期：2026-11-10
- 作者：Jerry 🦞
- 层级：L2 基础设施（横切编排）
- 前置：`PRD-system-governor-v1.0.md` ✅（Rex 通过）、`DESIGN-OUTLINE-system-governor-v1.0.md` ✅（Rex 通过）
- 设计基线：`reliability-auto-recovery-v1.0`、架构 §1.3 原生优先 / 复用优先
- 业界参照：调研结论「自建薄 runner + 复用成熟组件；Temporal 留作升级路径，不提前引入」（research-03）、「显式状态机 + 人在环闸门 + Schema-First 契约」（research-01）

> **实现状态变更指针（2026-11-10，Rex「通过，继续」后推进）**：本 DETAIL 描述 v1.0 全部实现方案。正文按设计基线书写，不回改历史版本。

---

## 1. 目标与非目标（继承 PRD §2，不重复展开）

**核心**：薄编排层。只新建三块（编排器 + Lane C 归档 + Lane D 盘点），其余全部复用既有检测/自愈能力，不重写任何判定逻辑。

---

## 2. 接口契约

### 2.1 CLI 入口（`scripts/governor.py`）

```bash
# 全量四条 lane，dry-run（默认，零写操作）
python3 L2-infra/components/system-governor/scripts/governor.py run

# 指定 lane + 真实执行（L0 自动，L1 文件操作）
python3 ... governor.py run --only A,C --apply

# 只读盘点任务（Lane D 单独用）
python3 ... governor.py run --only D

# 输出 JSON（供程序/报告消费）
python3 ... governor.py run --json

# 最近一次运行报告
python3 ... governor.py report
```

**参数契约**（argparse，全部可选）：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `run` / `report` | 子命令 | 必选其一 | |
| `--only A,B,C,D` | str | `A,B,C,D` | lane 选择，逗号分隔 |
| `--apply` | flag | off | 开：执行 L0/L1 写动作；关：全 dry-run |
| `--json` | flag | off | 开：stdout 输出 JSON 账本 |
| `--timeout` | int | 600 | 整体 wall-clock 预算秒 |

**退出码**：0=成功（含 dry-run）；1=lane 执行异常（非检测项失败）；2=参数错误。

### 2.2 核心数据结构（`src/models.py`）

```python
@dataclass(frozen=True)
class Finding:
    lane: str                 # "A"|"B"|"C"|"D"
    item: str                 # 检查项名，如 "scan_cron_errors"
    severity: str             # "critical"|"warning"|"info"
    status: str               # "open"|"auto-fixed"|"needs-human"|"planned"|"ok"
    evidence: str             # 证据/来源，可含 file:line、命令输出摘要
    action: str | None        # 已执行或建议动作；None=无动作
    idempotency_key: str      # 规范化 evidence hash，跨 lane 去重

@dataclass
class LaneResult:
    lane: str
    findings: list[Finding]
    stats: dict               # {"scanned": int, "errors": int, "warnings": int, "elapsed_s": float}

@dataclass
class GovernanceReport:
    timestamp: str            # ISO
    invoked: str              # 触发方式：cli|automation
    apply: bool               # 是否 --apply
    lanes: dict[str, LaneResult]
    summary: dict             # {"auto_fixed": int, "needs_human": int, "planned": int, "ok": int}
    ledger_path: str          # 账本落盘路径
```

### 2.3 处置分级策略（`src/policy.py`）

```python
# 返回该 finding 应执行的动作档位
def classify(finding: Finding, apply: bool) -> str:
    # "auto"      → L0 可逆自愈（--apply 下执行）
    # "file"      → L1 文件操作（--apply 下执行，dry-run 记 planned）
    # "confirm"   → L2 需人工（永不自动，记录 needs-human）
    # "forbidden" → L3 禁止自动（记录，不动作）
    ...
```

**分级表**（对应 PRD §4）：

| 档位 | 动作类型 | --apply 行为 | 默认行为 |
|---|---|---|---|
| L0 `auto` | 重试、guarded 重启、配额恢复、服务拉起 | 执行 | 记录 planned |
| L1 `file` | trash 删除、归档移动 | 执行（先 dry-run 清单） | 记录 planned |
| L2 `confirm` | 改配置、切路由、删数据 | **不执行**，needs-human + 建议命令 | 同左 |
| L3 `forbidden` | 对外副作用、凭据、强推 | 永不执行 | 同左 |

---

## 3. 各 Lane 详细设计

### 3.1 Lane A — 问题自愈（适配器 `lanes/lane_a_issues.py`）

**复用**：`scan_errors.py`（已有 `--detail`；**需最小增量加 `--json`** 输出现有 `result` dict）、`recovery_pending.py`、`stall_detect.py`、`endpoint_probe.py`、`auto_fix()`。

**流程**：
1. 子进程调 `scan_errors.py --json`（严格 timeout 60s，隔离异常）。
2. 解析 `result.errors[]` + `result.fixes[]`：
   - `fixes` 中 `status=ok` → Finding status=`auto-fixed`；
   - `fixes` 中需人工（如切 fallback 建议、`doctor --fix`）→ `needs-human`；
   - `errors` 无对应 fix → `open` + action=建议命令。
3. `--apply` 下：不重复执行 reliability 已自动做的动作（guarded 重启等由 scan_errors 自身 auto_fix 完成），governor 只**聚合回执**——即 Lane A 的写动作全部委托既有模块，governor 不做额外写。

**幂等**：reliability 既有 evidence 去抖 + TTL 常量沿用；governor 侧只按 `idempotency_key` 聚合。

### 3.2 Lane B — 资产健康（`lanes/lane_b_assets.py`）

**复用**：`system_full_audit.py --json`（已支持）、`endpoint_probe.py`、`service_guardian` 状态文件（`model-scheduling/logs/service_guardian_state.json`）。

**流程**：
1. 子进程 `system_full_audit.py --json`，提取第 3 域（自研资产）+ 第 4 域（模型/Provider）。
2. `endpoint_probe.py` 汇总端点可达性（严格超时）。
3. 服务 down → Finding status=`open`，action=`service_guardian 自愈（常驻已自动）`，severity=critical；
   配置/key 失效 → `needs-human`，action=`openclaw doctor --fix`。
4. `--apply`：服务拉起由 guardian 常驻自动完成，governor 不重复拉起；仅记录回执。

### 3.3 Lane C — 文件治理（`lanes/lane_c_files.py` + 新增归档能力）

**复用**：`tempcleanctl.py`（list / clean / verify）。

**新增**（落在 workspace-temp-cleanup 组件内，governor 只调用）：
- `archive.py`：归档核心。参数 `--root`、`--dest`（默认 workspace 内 `.archive/`）、`--rules`、`--dry-run`。
- `archive_rules.py`：规则引擎。

**归档规则 v1.0（`archive_rules.py`，按架构/账龄/类型）**：

| 规则 | 匹配 | 动作 |
|---|---|---|
| R1 大体积产物 | `*.xlsx`/`*.pptx` 且 > 50MB、不在 `output/` 当前周期 | 移 `.archive/` |
| R2 过期中间件 | `tmp/`、`*.tmp`/`*.bak` 且 mtime > 30 天 | 移 `.archive/`（可配置改 trash） |
| R3 历史备份 | `*.backup`/`*.bak.v*` 且 mtime > 90 天 | 移 `.archive/backup/` |
| R4 明确排除 | `data/`、`data/bdms.db`、`memory/`、`.git/`、registry 内未过期项 | **永不归档** |

**流程**：
1. `tempcleanctl list`（registry + 命名约定）→ planned 清单。
2. `archive --dry-run`（规则匹配，输出将移动文件 + 目标路径）。
3. `--apply`：先 `archive`（移动 + manifest 登记），再 `tempcleanctl clean`（trash）。
4. 归档 manifest：`.archive/manifest.json`（时间、源路径→目标、规则 ID、大小、sha256）。

**安全**：移动前校验目标不在源路径内（防自移动）；同路径幂等（已存在目标 → 追加时间戳后缀）；先 dry-run 后 apply。

### 3.4 Lane D — 建设任务盘点（新增 `session-recovery/scripts/task_inventory_scanner.py`）

**只读，多源聚合**：

| 数据源 | 提取 | 输出字段 |
|---|---|---|
| `task_tracker` current-task | active 任务 | id / name / phase / step / failure_count |
| `memory/task-history/*.md` | 归档任务中 `archive_reason != completed` 或失败计数>0 | id / reason / result |
| `**/IMPLEMENTATION-PLAN-*.md` | 未勾选 `- [ ]` 的 Phase/任务 | 路径 / 项 / 阶段 |
| `**/VERIFICATION-*.md` | 未勾选 `- [x]` 的验收门 | 路径 / 门 / 状态 |
| 活跃会话（sessions） | running + 绑定任务 / 长期 stalled | session_key / task / 状态 |

**输出 schema**：

```json
{
  "incomplete_tasks": [
    {
      "name": "system-governor P3",
      "source": "IMPLEMENTATION-PLAN-...md:42",
      "phase": "P3",
      "status": "in-progress",
      "next_action": "按 DESIGN-DETAIL 实现 Lane D"
    }
  ],
  "doc_gaps": [ {"path": "...", "gap": "有 OUTLINE 无 PLAN"} ],
  "summary": {"total": 0, "in_progress": 0, "stalled": 0, "doc_gaps": 0}
}
```

**边界**：不改任何任务文件；纯读取 + 聚合。

---

## 4. 编排器（`src/orchestrator.py`）

- `concurrent.futures.ThreadPoolExecutor(max_workers=4)` 并发跑四 lane（无相互依赖）。
- 每 lane 独立 `run_cmd` 严格 timeout（默认 lane 级 120s，总预算 600s）。
- 任一路失败不影响其余路（沿用 reliability P1-d 隔离模式）；失败 lane 记 `lane_error` Finding。
- 聚合 → 去重（`idempotency_key`）→ `policy.classify` → 落账本 `memory/governor-latest.json`。

---

## 5. 数据与配置

| 文件 | 路径 | 说明 |
|---|---|---|
| 账本 | `memory/governor-latest.json` | 最近一次 run 全量结果（不入 git 可选） |
| 归档目录 | `<workspace>/.archive/` | 默认；`--dest` 可覆盖（gitignore） |
| 归档 manifest | `.archive/manifest.json` | 移动登记 |
| 归档规则 | `workspace-temp-cleanup/archive_rules.py` | 代码内规则表（v1.0） |
| governor 配置 | `system-governor/config.yaml` | lane 启用、超时、路径覆盖（可选，v1.0 可用默认） |

> 归档目录用 **dot 目录 `.archive/`**（避免混入正式目录，且不干扰 repo_health 的 untracked 统计），加入 `.gitignore`。

---

## 6. 测试黄金基准（`tests/`）

| 套件 | 用例 | 断言核心 |
|---|---|---|
| `test_policy.py` | 4 | L0-L3 分类正确；`apply=False` 时无一写动作 |
| `test_orchestrator.py` | 3 | 四 lane 并发跑通；单 lane 失败隔离；总时长有界 |
| `test_ledger.py` | 3 | 去重合并；账本 schema 合法；幂等（同 evidence 两轮不重复） |
| `test_lane_d_inventory.py` | 4 | 枚举 current + history + PLAN 未勾 + VERIFICATION 未勾 + doc_gap；无任务时返回空 |
| `test_archive.py` | 5 | R1-R4 规则命中；dry-run 零移动；apply 移动+manifest；幂等（重跑不重复移动）；排除目录不动 |

**验收门**：
1. `governor.py run`（无 --apply）零写操作（用临时 workspace fixture 断言）。
2. `--apply` 下 L0 自动、L1 文件操作执行、L2/L3 永不执行。
3. Lane D 能枚举出当前真实未完成任务（含 task_history 中 `interrupted-by-new` 等）。
4. 全量回归：error_handler / gateway-safety / session-recovery / model-scheduling / workspace-temp-cleanup 既有测试零破坏。
5. 真实执行，不虚构。

---

## 7. 影响面与文件清单

**新建**：
```
L2-infra/components/system-governor/
├── scripts/governor.py            # CLI 入口
├── src/{models,orchestrator,ledger,policy}.py
├── src/lanes/{lane_a_issues,lane_b_assets,lane_c_files,lane_d_tasks}.py
├── config.yaml（可选默认）
└── tests/{test_policy,test_orchestrator,test_ledger,test_lane_d_inventory,test_archive}.py

L2-infra/components/workspace-temp-cleanup/scripts/archive.py      # 新增
L2-infra/components/workspace-temp-cleanup/scripts/archive_rules.py # 新增
L2-infra/components/session-recovery/scripts/task_inventory_scanner.py # 新增
```

**最小增量修改**：
- `scan_errors.py`：加 `--json`（输出既有 result dict，不改判定）。
- `tempcleanctl.py`：加 `archive` 子命令（调用 archive.py）。
- `.gitignore`：加 `.archive/`。

**不改**：reliability P1-a/b/c/d 行为、scan_errors/full_audit 判定、task_tracker 既有命令、service_guardian。

---

## 8. 分期与验收（继承 OUTLINE §6）

P1 骨架 → P2 Lane A/B → P3 Lane D → P4 归档 + Lane C → P5 联调 + 文档 + 全量回归。每 Phase 独立可交付、可回滚。

---

## 9. 待 Rex 拍板（本 DETAIL 新增）

1. **归档目录**：默认 `<workspace>/.archive/`（dot + gitignore）是否接受？还是指定外部目录？
2. **Lane A/B 写动作全部委托既有模块**（governor 只聚合回执、不重复执行）是否接受？
3. **scan_errors 加 `--json`** 这一最小增量是否接受（不动判定逻辑）？
4. Phase 顺序 P1→P5 是否按计划推进，P4 归档默认 dry-run？

> 全部通过 → 按 P1 开始编码；每个 Phase 完成自测 + 汇报。
