# PRD — 资产全盘审计固化为系统资产（system-governor v1.1）

| 项 | 值 |
|---|---|
| 所属层级 | L2 基础设施（横切编排） |
| 版本 | v1.1（增量扩展 v1.0） |
| 日期 | 2026-11-11 |
| 作者 | Jerry 🦞 |
| 状态 | **待 Rex 评审** |
| 前置 | `system-governor v1.0`（已落地：编排器 + 四 Lane + L0-L3 闸门 + 账本）、`gen_asset_inventory.py`（资产清单生成器，已落地） |
| 关联 | `00-system-architecture.md` §4 资产清单、2026-11-11 四阶段资产审计整改（aee596e/3005ddf/979d91f/2363632） |

---

## 1. 背景与问题

2026-11-11 完成了一次**全盘资产审计**（四阶段整改：L1 命名对齐 / 残留归位 / 计数同步 / 空壳处置），沉淀了完整方法论。实测暴露两个结构性缺口：

1. **客观探针没有持续化**：审计中可机器化的检查（计数漂移、路径断链、空壳组件、未跟踪资产、硬编码根路径、重复资产）只在人工审计时发现，平时无人盯防 → 漂移会再次悄悄积累。
2. **决策工作流没有固化**：审计的「取证 → 定性 → 方案 → 拍板 → 执行 → 回归」六环节全靠会话记忆，换会话即丢失，且破坏性处置（合并/降级/删除）缺少可审计的决策留痕。

### 1.1 已确认的既有资产（复用，不重造）

| 能力 | 实现 | 状态 |
|---|---|---|
| 资产清单自动生成/漂移检测 | `gen_asset_inventory.py` + full_audit §11 | ✅ 已落地 |
| 统一编排 + 分级闸门 + 账本 | `system-governor` v1.0（四 Lane） | ✅ 已落地 |
| Lane B 资产健康 | `lane_b_assets.py` 聚合 full_audit §3/§4 + guardian | ✅ 已落地 |
| 36 项只读审计 | `system_full_audit.py`（11 节） | ✅ 已落地 |
| 组件发现 | `gen_asset_inventory.discover_completed_components()`（41 项） | ✅ 已落地 |
| 技能入口 | `L2-infra/skills/system-governor/SKILL.md` | ✅ 已落地 |

### 1.2 真正的缺口（本项目新建）

| 缺口 | 说明 |
|---|---|
| **探针集** | 6 类资产一致性探针（见 §3.1），持续盯防漂移，纯只读、cron 安全 |
| **Lane B 编排接入** | 新探针 findings 进入 governor 账本与分级闸门 |
| **audit 工作流命令** | 把六环节审计方法论固化为 `governor.py audit`，产出结构化决策留痕 |

---

## 2. 目标 / 非目标

### 目标

1. **探针持续化**：资产一致性漂移由 cron/巡检自动发现，不等人工季度审计。
2. **统一入口**：`governor.py run` 的 Lane B 自动包含资产一致性 findings；`governor.py audit` 一键跑完六环节审计流程。
3. **决策留痕**：每次审计产出结构化报告（JSON 账本），定性结论 + 处置建议 + 批准状态可追溯。
4. **安全边界延续**：探针只读；处置建议分级，L1 文件移动 dry-run+apply，L2+ 一律 needs-human 停手。

### 非目标（v1.1 不做）

- 不自动执行 L2/L3 破坏性处置（删除/降级/改名核心资产）——永远人工拍板。
- 不重写既有检测/生成器/编排逻辑，只增量扩展。
- 不新建独立技能/组件（复用 system-governor 技能入口与 Lane 架构）。
- 不做资产审计的「自动修复」闭环（探针发现 → 建议 → 人工批准 → 执行，不自动执行）。

---

## 3. 功能清单

### 3.1 新增 full_audit §12「资产一致性检测」（纯只读探针集）

| 探针 | 检测 | 判定 | 输出 |
|---|---|---|---|
| P1 组件计数漂移 | `discover_completed_components()` 发现数 vs 架构文档 §4 登记数 | 不一致 → ⚠️ | 发现 N / 登记 M |
| P2 文档路径断链 | 架构文档/资产清单引用的组件路径真实存在？ | 任一缺失 → ⚠️ | 断链路径清单 |
| P3 空壳组件 | 组件目录 0 py 且文档/清单声明「已上线/✅」 | 命中 → ⚠️ | 组件名 + 证据 |
| P4 未跟踪/未提交资产 | `git status` untracked 文件 + 未 commit 数 | 超阈值 → ⚠️ | 清单（前 N 条） |
| P5 硬编码根路径 | 脚本引用 workspace 根 `model-scheduling/`、`src/` 等已移除路径 | 命中 → ⚠️ | file:line |
| P6 重复资产 | 跨目录同 sha256 文件（排除 symlink/生成物） | 命中 → ⚠️ | 路径对 |

- 全部探针**只读**：不写文件、不 git 变更、不删除。
- 复用既有能力：P1/P3 调 `gen_asset_inventory`，P4 调 `git status`，P5/P6 为新增纯扫描。
- 阈值常量集中定义（`ASSET_CONSISTENCY_THRESHOLDS`），默认：P4 untracked > 10 或 uncommitted > 3 告警；其余探针命中即告警。

### 3.2 Lane B 编排接入

- `lane_b_assets.py` 增加对 §12 的聚合：探针命中 → `Finding(lane="B", severity="warning", status="open")`，action 指向 `governor.py audit`。
- 沿用现有分级策略：`asset_consistency` 前缀 → CONFIRM（需人工确认处置，探针本身只读）。

### 3.3 `governor.py audit` 子命令（审计工作流）

```bash
# 只读取证 + 定性 + 建议（默认，零写操作）
python3 .../governor.py audit

# 输出结构化审计报告 JSON（含处置建议与分级）
python3 .../governor.py audit --json

# 执行 L1 可回滚处置（如文件归位/合并；L2+ 一律 needs-human）
python3 .../governor.py audit --apply
```

六环节固化：

| 环节 | 动作 | 写操作 |
|---|---|---|
| 1 取证 | 跑 §12 探针 + git/目录/文档交叉核对 | 无 |
| 2 定性 | 按规则分类：残留 / 重复 / 空壳 / 口径漂移 | 无 |
| 3 方案 | 每项给出 归位 / 合并 / 降级 / 删除 / 补实现 建议 + 证据 | 无 |
| 4 拍板 | L2+ 项 → needs-human（停手，列命令请 Rex 批准） | 无 |
| 5 执行 | L1 项（文件移动类）→ dry-run 清单确认后 `--apply` | 有（可回滚） |
| 6 回归 | 重跑 §12 探针确认清零 + 写审计账本 | 账本落盘 |

- 审计报告落 `memory/governor-audit-latest.json`（复用 ledger 原子写）。
- 每个定性项含：`id / 类别 / 证据(file:line) / 建议 / tier(L0-L3) / status(pending/approved/done/skipped)`。

### 3.4 技能入口更新

- `L2-infra/skills/system-governor/SKILL.md` 增加：`audit` 子命令路由 + 资产一致性探针说明 + 六环节流程图。

---

## 4. 自动处置分级（安全红线，延续 v1.0）

| 级别 | 动作类型 | 默认行为 |
|---|---|---|
| L0 可逆自愈 | （本项目无新增，探针只读） | — |
| L1 可回滚文件操作 | 文件归位 / 重复合并（git mv 保留历史） | 默认 dry-run，`--apply` 执行 |
| L2 需确认 | 删除资产 / 降级声明 / 改名核心目录 | 一律停手列命令，Rex 批准 |
| L3 禁止自动 | 对外副作用 / 凭据 / 强推 | 永不执行 |

护栏：`audit` 默认零写；L2+ 即使 `--apply` 也只记 needs-human；L1 执行前必须 dry-run 清单；每笔 L1 操作进账本可回滚。

---

## 5. 验收标准

1. **探针真实**：用注入用例验证 6 探针各自命中（如临时建空壳目录 → P3 命中；临时断链路径 → P2 命中；测试后清理）。
2. **Lane B 接入**：`governor.py run --only B --json` 的 findings 含 §12 探针结果（无漂移时为 info/ok，有漂移时为 warning）。
3. **audit 工作流**：`governor.py audit --json` 产出结构化报告，六环节字段齐全；有 L2+ 项时 status=needs-human 且不执行。
4. **安全**：无 `--apply` 时零写操作（git status 前后一致、无新文件）；`--apply` 下 L2+ 项仍不执行。
5. **回归**：既有 36 项检测全部通过；system-governor 既有测试（policy/orchestrator/ledger）零破坏；gen_asset_inventory 漂移自检通过。
6. 所有结果真实执行，不虚构。

---

## 6. 待 Rex 拍板

1. **探针阈值**：P4 未跟踪 >10 或未提交 >3 才告警，是否接受？（默认保守，避免日常噪音）
2. **audit 形态**：`governor.py audit` 子命令（推荐，复用编排/账本）还是独立 CLI？
3. **§12 位置**：full_audit 新增第 12 节（推荐，保持 Lane B 消费点集中）还是并入 §11？
4. **L1 执行边界**：`--apply` 只允许「文件归位/重复合并」（git mv 可回滚），删除/降级永远 L2 需人工，是否接受？

> 全部通过 → 进入 OUTLINE/DETAIL 设计，每阶段评审后推进。
