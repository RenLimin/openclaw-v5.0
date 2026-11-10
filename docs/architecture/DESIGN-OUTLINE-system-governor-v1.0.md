# DESIGN-OUTLINE — 系统治理工作流（system-governor）v1.0

- 状态：**待 Rex 评审**
- 日期：2026-11-10
- 作者：Jerry 🦞
- 层级：L2 基础设施（横切编排）
- 前置：`PRD-system-governor-v1.0.md`
- 设计基线：`reliability-auto-recovery-v1.0`（故障自愈已落地）、架构 §1.3 原生优先 / 复用优先

> **核心设计立场**：system-governor 是**薄编排层（thin orchestrator）**，不重写检测与自愈。
> 新增代码集中在三处：①编排器与统一账本；②`tempcleanctl archive`；③任务盘点扫描器。

---

## 1. 总体架构

```
                        ┌─────────────────────────────┐
                        │   governor.py（统一入口）     │
                        │  run / report               │
                        │  --only / --apply / --json   │
                        └──────────────┬──────────────┘
                                       │ 并发派发(ThreadPool)
              ┌────────────┬───────────┴───────────┬────────────┐
              ▼            ▼                       ▼            ▼
        ┌──────────┐ ┌──────────┐            ┌──────────┐ ┌──────────┐
        │ Lane A   │ │ Lane B   │            │ Lane C   │ │ Lane D   │
        │ 问题自愈 │ │ 资产修复 │            │ 文件治理 │ │ 任务盘点 │
        └────┬─────┘ └────┬─────┘            └────┬─────┘ └────┬─────┘
             │            │                       │            │
   调用既有(不改):        │              新增+复用:             新增:
   scan_errors.py  system_full_audit      tempcleanctl      task_inventory
   recovery_pending  (§3/§4 只读)        .clean / .archive  _scanner.py
   stall_detect     endpoint_probe       archive_rule.py
   endpoint_probe   service_guardian
             │            │                       │            │
             └────────────┴───────────┬───────────┴────────────┘
                                       ▼
                          ┌─────────────────────────┐
                          │ 聚合 / 去重 / 分级        │
                          │ governance_ledger.py     │
                          │ → governor-latest.json   │
                          └─────────────────────────┘
```

### 1.1 数据流

1. 入口解析参数（lane 选择、apply 标志、输出格式）。
2. 四条 lane **并发**执行（无相互依赖），各自返回标准化 Finding 列表。
3. 聚合器统一去重（同 evidence 合并）、分级、按 §安全红线 决定 auto-fixed / needs-human。
4. `--apply` 才执行 L0/L1 写动作；否则全部为计划态（dry-run）。
5. 写统一账本 `memory/governor-latest.json`，并在终端打印人读摘要。

---

## 2. 模块划分

新建组件目录：`L2-infra/components/system-governor/`

```
system-governor/
├── SKILL.md                          # 可选：声明触发条件（PRD 拍板点1）
├── scripts/
│   └── governor.py                   # 统一入口 CLI
├── src/
│   ├── models.py                     # Finding / LaneResult / Ledger 数据结构
│   ├── orchestrator.py               # 并发调度 + 生命周期
│   ├── ledger.py                     # 聚合/去重/分级/落盘
│   ├── policy.py                     # L0-L3 处置分级 + apply 闸门
│   └── lanes/
│       ├── lane_a_issues.py          # 适配器：调 scan_errors + reliability
│       ├── lane_b_assets.py          # 适配器：调 full_audit §3/4 + probe + guardian
│       ├── lane_c_files.py           # 适配器：调 tempcleanctl
│       └── lane_d_tasks.py           # 适配器：调任务盘点扫描器
└── tests/
    ├── test_orchestrator.py
    ├── test_ledger.py
    ├── test_policy.py
    └── test_lane_d_inventory.py
```

### 2.1 外部新增（落在既有组件内）

| 文件 | 所属组件 | 说明 |
|---|---|---|
| `workspace-temp-cleanup/.../archive.py` + `tempcleanctl` 增 `archive` 子命令 | workspace-temp-cleanup | 归档能力（与 clean 分离） |
| `workspace-temp-cleanup/.../archive_rules.py` | 同上 | 归档规则（按架构/账龄/类型路由） |
| `session-recovery/scripts/task_inventory_scanner.py` | session-recovery | 任务盘点扫描器（多源聚合） |

> 归档与盘点逻辑放在**所属能力的既有组件**，governor 只调用，保持单一职责、可独立复用。

---

## 3. 各 Lane 适配契约

所有 lane 返回统一结构（`models.py`）：

```python
@dataclass
class Finding:
    lane: str            # "A".."D"
    item: str            # 检查项名
    severity: str        # critical | warning | info
    status: str          # open | auto-fixed | needs-human | planned
    evidence: str        # 证据/来源（可含命令、文件:行）
    action: str | None   # 已执行或建议的动作
    idempotency_key: str # 去重键（evidence hash）

@dataclass
class LaneResult:
    lane: str
    findings: list[Finding]
    stats: dict          # 计数/耗时
```

### 3.1 Lane A — 问题自愈

- 以子进程调用 `scan_errors.py --json`（需确认其支持 JSON 输出；若无，加 `--json` 为**最小增量**，不改判定逻辑）。
- 读取其 `fixes` / pending / stall 结果，映射为 Finding；自动动作结果由 reliability 模块自身回执决定，governor 不重复执行。

### 3.2 Lane B — 资产健康

- 调 `system_full_audit.py --json`，只取第 3、4 域（自研资产 / 模型 Provider）。
- 调 `endpoint_probe.py` 汇总端点；服务存活读 `service_guardian` 状态。
- 服务 down → 由 guardian 自愈（既有）；配置/key → needs-human（建议 `doctor --fix`）。

### 3.3 Lane C — 文件治理

- `tempcleanctl list`（发现）+ `archive --dry-run`（归档计划）+ `clean`（trash）。
- dry-run：只生成 planned 清单；`--apply`：执行 clean / archive。
- 归档规则（archive_rules）：按文件类型 + 账龄 + 架构归属，路由到归档区，登记 manifest。

### 3.4 Lane D — 任务盘点（全新扫描器）

多源聚合，输出未完成建设任务表：

| 数据源 | 提取 |
|---|---|
| `task_tracker` | current-task（active）+ 归档目录中未完成/失败记录 |
| `**/IMPLEMENTATION-PLAN-*.md` | 未勾选的 Phase / 任务项 |
| `**/VERIFICATION-*.md` | 验收门未勾选项 |
| 会话状态 | running 且绑定任务、长期 stalled 的会话 |
| 文档命名约定 | OUTLINE/DETAIL 存在但缺后续 PLAN/VERIFICATION 的断链 |

每条任务：名称、来源位置、阶段、状态（in-progress / stalled / doc-gap）、下一步建议。
纯只读。

---

## 4. 关键技术决策

| 决策 | 选择 | 依据 |
|---|---|---|
| 编排并发 | `concurrent.futures.ThreadPoolExecutor`（stdlib） | lane 多为子进程/IO 密集；沿用 reliability P1-d 模式，无新依赖 |
| 子进程调用 | 统一 `run_cmd`（严格 timeout + 隔离），不走 shell 拼接 | 复用 scan_errors 的 run_cmd 语义，防注入/拖死 |
| 跨 lane 去重 | `idempotency_key` = 规范化 evidence hash | 同一问题可能被 A、B 同时报 |
| 写操作闸门 | `policy.py` 集中判定，任何 lane 不得直接写 | 安全红线单点可控 |
| 可移植性 | 编排/策略与具体路径通过 config 注入，不绑定 OpenClaw 运行时 | 架构 §1.3 / ADR-012 |
| 幂等 | 归档 manifest + ledger 记录；同 evidence 有界动作 | 防风暴，沿用 recovery_pending TTL/次数常量 |

---

## 5. 与既有系统的边界

- **不改** reliability-auto-recovery 的 P1-a/b/c/d 行为与常量。
- **不改** scan_errors / full_audit 的检测判定；最多**增量**加 `--json` 输出（若缺）。
- 归档与盘点是**新增能力**，不影响现有 tempcleanctl clean 与 task_tracker 既有命令。
- 调度（是否加 cron）由 PRD 拍板点 2 决定，默认 v1.0 仅手动。

---

## 6. 影响面与分期（建议）

| Phase | 内容 | 依赖 | 估时 |
|---|---|---|---|
| P1 | models + policy + ledger + orchestrator 骨架（空 lane 跑通） | PRD 通过 | 0.5 人日 |
| P2 | Lane A / B 适配器（纯复用，最快见效） | P1 | 1 人日 |
| P3 | Lane D 任务盘点扫描器（只读，独立） | P1 | 1 人日 |
| P4 | tempcleanctl archive + 规则 + Lane C | P1 | 1.5 人日 |
| P5 | 全链路联调 + 统一报告 + 测试 + OPERATIONS/VERIFICATION | P2-P4 | 1 人日 |
| 合计 | | | 约 5 人日 |

每 Phase 独立可交付、可回滚；P4（文件移动）风险最高，全程 dry-run 先行。

---

## 7. 待 Rex 拍板（对应 PRD §6）

1. 组件目录与 CLI 形态是否按本 OUTLINE（`components/system-governor/` + `governor.py`）。
2. 是否需要 `SKILL.md` 让 agent 自动触发，还是仅手动 CLI。
3. Lane C 归档区位置与规则口径（workspace 内 `archive/` vs 外部目录）。
4. Phase 顺序是否按 P1→P5；是否同意 P4 默认 dry-run、`--apply` 才移动。

> 通过后进入 **DESIGN-DETAIL**（接口签名 / Finding schema / 归档规则 / 任务盘点多源解析 / 测试黄金基准），DETAIL 复审通过再编码。
