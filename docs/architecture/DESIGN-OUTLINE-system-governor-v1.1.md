# DESIGN-OUTLINE — 资产全盘审计固化为系统资产（system-governor v1.1）

- 状态：**待 Rex 评审**
- 日期：2026-11-11
- 作者：Jerry 🦞
- 层级：L2 基础设施（横切编排）
- 前置：`PRD-system-governor-v1.1.md` ✅（Rex 2026-11-11 通过，4 拍板点全部按推荐）
- 设计基线：`system-governor v1.0`（薄编排层已落地）、架构 §1.3 原生优先 / 复用优先

> **核心设计立场**：延续 v1.0「薄编排」哲学——**不重写任何既有检测/生成/编排逻辑**。
> 新增集中在三处：①full_audit §12 资产一致性探针集（纯只读）；②Lane B 编排接入；③`governor.py audit` 六环节审计工作流。

---

## 1. 总体架构

```
                        ┌─────────────────────────────┐
                        │   governor.py（统一入口）     │
                        │  run / report / audit       │
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
             │     + 新增 §12 探针:               │            │
             │     P1计数 P2断链 P3空壳           │            │
             │     P4未跟踪 P5硬编码 P6重复        │            │
             │            │                       │            │
             └────────────┴───────────┬───────────┴────────────┘
                                       ▼
                          ┌─────────────────────────┐
                          │ 聚合 / 去重 / 分级        │
                          │ ledger.py                │
                          │ → governor-latest.json   │
                          │ → governor-audit-latest  │
                          │    .json（audit 专用）   │
                          └─────────────────────────┘
```

### 1.1 数据流（run 模式，延续 v1.0）

1. 入口解析参数 → 并发跑 lane → 聚合去重分级 → `--apply` 才写 → 落账本。

### 1.2 数据流（audit 模式，新增）

1. `audit` 命令触发**六环节**：取证 → 定性 → 方案 → 拍板 → 执行 → 回归。
2. 取证环节复用 §12 探针输出 + git/目录/文档交叉核对（探针结果即证据源）。
3. 定性/方案环节按规则表分类并给出建议（纯计算，无写）。
4. 拍板环节：L2+ 项 status=needs-human 停手；L1 项进 dry-run 清单。
5. `--apply`：仅执行 L1 可回滚处置（git mv 归位/合并），每笔进账本。
6. 回归：重跑 §12 确认清零，写 `governor-audit-latest.json`。

---

## 2. 模块划分（增量）

### 2.1 full_audit §12（新增探针集，落在既有脚本内）

```
system_full_audit.py
└── audit_asset_consistency()      # §12 资产一致性检测（纯只读）
    ├── P1 计数漂移    → discover_completed_components vs 清单登记
    ├── P2 路径断链    → 文档引用组件路径存在性
    ├── P3 空壳组件    → 0 py 且声明已上线
    ├── P4 未跟踪/未提交 → git status
    ├── P5 硬编码根路径 → 引用已移除根路径扫描
    └── P6 重复资产    → 跨目录同 sha256
```

- 阈值常量 `ASSET_CONSISTENCY_THRESHOLDS` 集中定义（PRD §6.1 通过：P4 >10 untracked / >3 uncommitted 告警）。
- 复用 `discover_completed_components()`（41 项）与 `run()` 子进程封装。
- 纯只读：不写文件、不 git 变更、不删除。

### 2.2 Lane B 编排接入（增量修改 `lane_b_assets.py`）

- 增加对 full_audit §12 章节的聚合。
- §12 探针命中 → `Finding(lane="B", severity="warning", status="open", action="governor.py audit")`。
- policy 规则表加 `asset_consistency` 前缀 → CONFIRM（需人工确认处置，探针只读不自动改）。

### 2.3 `governor.py audit` 子命令（新增）

```
system-governor/
├── scripts/governor.py          # + audit 子命令（复用 argparse/ledger）
├── src/
│   ├── audit_flow.py            # 新增：六环节审计工作流编排
│   ├── audit_classify.py        # 新增：定性分类 + 处置建议规则表
│   ├── audit_exec.py            # 新增：L1 可回滚处置执行器（git mv 归位/合并）
│   ├── lanes/lane_b_assets.py   # 修改：接入 §12
│   ├── models.py                # 微增：AuditItem 数据结构
│   └── policy.py                # 微增：asset_consistency 前缀 → CONFIRM
└── tests/
    ├── test_audit_classify.py   # 新增
    ├── test_audit_exec.py       # 新增
    └── test_lane_b_assets.py    # 新增（§12 聚合）
```

### 2.4 数据结构（新增 `AuditItem`）

```python
@dataclass(frozen=True)
class AuditItem:
    id: str                # 稳定标识，如 "P3-health-engine"
    category: str          # 残留 | 重复 | 空壳 | 口径漂移 | 断链
    evidence: str          # 证据（file:line / 命令输出）
    suggestion: str        # 处置建议（归位/合并/降级/删除/补实现）
    tier: str              # L0-L3 分级
    status: str            # pending | approved | done | skipped | needs-human
    detail: dict           # 补充字段（路径对、计数、阈值等）
```

---

## 3. 契约

### 3.1 §12 探针输出（并入 full_audit 既有 check 格式）

```python
check("asset count drift", "⚠️", "发现 27 个 L2 组件 vs 清单登记 19")
check("doc path broken", "⚠️", "L3-business/components/cissp-learning/ 不存在（文档引用）")
check("skeleton component", "⚠️", "health-engine: 0 py 但声明✅已上线")
check("untracked assets", "⚠️", "12 个未跟踪文件 / 4 个未提交变更（阈值 10/3）")
check("hardcoded root path", "⚠️", "service_guardian.py:39 引用已移除根路径")
check("duplicate assets", "⚠️", "favicon.png: src/bdms 与 L4/bdms 同 sha256")
```

### 3.2 Lane B 聚合（延续 Finding 契约）

- `lane="B"`、`item="asset_consistency"`、`severity="warning"`、`status="open"`。
- `action="运行 governor.py audit 进入审计工作流"`。

### 3.3 audit 子命令 CLI

```bash
governor.py audit                # 六环节，默认零写（dry-run）
governor.py audit --json         # 结构化 AuditItem 列表 + 汇总
governor.py audit --apply        # 仅执行 L1（git mv 归位/合并），L2+ 仍 needs-human
governor.py audit --only P1,P3   # 只跑指定探针的取证（可选）
```

- 审计账本：`memory/governor-audit-latest.json`（复用 ledger 原子写）。

---

## 4. 关键技术决策

| 决策 | 选择 | 依据 |
|---|---|---|
| 探针实现位置 | full_audit §12（同一脚本内新增函数） | Lane B 已消费 full_audit --json，接入点集中 |
| 探针执行方式 | 复用 full_audit 既有 `run()` 子进程封装 | 无新依赖，沿用超时/隔离语义 |
| audit 工作流 | `governor.py audit` 子命令 + 独立 `audit_flow.py` | 复用 argparse/ledger/policy，不新建 CLI |
| 定性分类 | `audit_classify.py` 规则表（类别 → 建议 → tier） | 可测试、可扩展，判定逻辑集中 |
| L1 执行 | `audit_exec.py` 仅 git mv 类（保留历史/可回滚） | PRD §6.4：删除/降级永远 L2 人工 |
| 幂等 | AuditItem.id 稳定 + 账本去重 | 同一问题多轮审计不重复报告 |
| 安全 | audit 默认零写；L2+ 即使 --apply 也只记 needs-human | 延续 v1.0 红线 |

---

## 5. 与既有系统的边界

- **不改**：gen_asset_inventory 生成/发现逻辑、Lane A/C/D、reliability 行为、既有 11 节检测判定。
- **最小增量**：full_audit 新增 §12（不动 §1-§11）；policy 加一个前缀映射；models 加 AuditItem。
- **不新建**：独立组件/技能/CLI（复用 system-governor 全部既有设施）。
- **不自动执行**：L2+ 破坏性处置永远人工。

---

## 6. 影响面与分期

| Phase | 内容 | 依赖 | 估时 |
|---|---|---|---|
| P1 | full_audit §12 探针集（6 探针 + 阈值常量） | PRD 通过 | 1 人日 |
| P2 | Lane B 接入 §12 + policy 前缀 + models.AuditItem | P1 | 0.5 人日 |
| P3 | audit 子命令（audit_flow + classify + exec + 账本） | P2 | 1 人日 |
| P4 | 测试（test_audit_classify / test_audit_exec / test_lane_b）+ 回归 | P3 | 0.5 人日 |
| P5 | 技能入口更新 + OPERATIONS/VERIFICATION 文档 + 全量回归 | P4 | 0.5 人日 |
| 合计 | | | 约 3.5 人日 |

每 Phase 独立可交付、可回滚；P1 探针纯只读风险最低，P3 exec 全程 dry-run 先行。

---

## 7. 待 Rex 拍板

1. §12 探针集是否按 P1-P6 六项落地（不含 §11 已覆盖的登记漂移）？
2. audit 工作流六环节固化进 `governor.py audit`（复用编排/账本）是否接受？
3. AuditItem 数据结构（id/category/evidence/suggestion/tier/status/detail）是否满足决策留痕需求？
4. Phase 顺序是否按 P1→P5；P3 exec 是否默认 dry-run、`--apply` 才执行 L1？

> 通过后进入 **DESIGN-DETAIL**（接口签名 / 探针算法细节 / 分类规则表 / 测试黄金基准），DETAIL 复审通过再编码。
