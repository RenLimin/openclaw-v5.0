# DESIGN-DETAIL — 资产全盘审计固化为系统资产（system-governor v1.1）

- 状态：**待 Rex 评审**
- 日期：2026-11-12
- 作者：Jerry 🦞
- 层级：L2 基础设施（横切编排）
- 前置：`PRD-system-governor-v1.1.md` ✅（Rex 通过）、`DESIGN-OUTLINE-system-governor-v1.1.md` ✅（Rex 通过）
- 设计基线：`system-governor v1.0`（薄编排已落地）、架构 §1.3 原生优先 / 复用优先

> **实现状态变更指针（2026-11-12，Rex「继续」后推进）**：本 DETAIL 描述 v1.1 全部实现方案。正文按设计基线书写，不回改历史版本。

---

## 1. 目标与非目标（继承 PRD §2，不重复展开）

**核心**：延续 v1.0 薄编排。只新建三块（§12 探针集 + Lane B 接入 + audit 工作流），其余全部复用，不重写任何判定逻辑。

---

## 2. 接口契约

### 2.1 full_audit §12 探针输出（并入既有 check 格式）

```python
# system_full_audit.py 新增
ASSET_CONSISTENCY_THRESHOLDS = {
    "untracked_max": 10,      # P4 未跟踪文件告警阈值
    "uncommitted_max": 3,     # P4 未提交变更告警阈值
    "duplicate_min_bytes": 1024,  # P6 忽略 <1KB 的重复（如图标缓存）
}

def audit_asset_consistency() -> list[dict]:
    """12. 资产一致性检测（纯只读）。

    返回 check() 格式列表，与 §1-§11 同构，供 Lane B 聚合。
    """
    results = []
    # P1 计数漂移
    # P2 路径断链
    # P3 空壳组件
    # P4 未跟踪/未提交
    # P5 硬编码根路径
    # P6 重复资产
    return results
```

**探针算法**：

| 探针 | 算法 | 判定 |
|---|---|---|
| **P1 计数漂移** | `discover_completed_components()` 返回数 vs 资产清单文档 §4 登记数（解析 `01-asset-inventory.md` 表格行数） | 不等 → ⚠️，detail 含「发现 N / 登记 M」 |
| **P2 路径断链** | 从架构文档（`00-system-architecture.md` + `01-asset-inventory.md` + 各组件 README/DESIGN）正则提取 `L[1-4][-_a-zA-Z0-9/]*` 路径引用，逐个 `Path.exists()` | 任一缺失 → ⚠️，detail 列断链路径（最多 10 条） |
| **P3 空壳组件** | 遍历 `L2-infra/components/`、`L3-business/`、`L3-proprietary/`、`L4-proprietary/components/` 下组件目录：`py_count == 0` 且同目录文档/清单含「✅ 已上线」或「已实现」 | 命中 → ⚠️，detail 含组件名 + 证据文件 |
| **P4 未跟踪/未提交** | `git status --porcelain` 统计 `??` 行数与 `M`/`A`/`D` 行数 | 超阈值 → ⚠️，detail 含计数 + 前 5 条路径 |
| **P5 硬编码根路径** | 扫描 `L2-infra/`、`L3-*/`、`L4-*/` 下 `*.py`，正则匹配已移除根路径（`workspace/model-scheduling/`、`workspace/src/bdms/`、`workspace/recovered/`） | 命中 → ⚠️，detail 含 `file:line`（最多 10 条） |
| **P6 重复资产** | 对 `L2-infra/`、`L3-*/`、`L4-*/` 下文件按 sha256 分组，同 hash 且路径不同 → 候选；排除 `.git/`、`__pycache__/`、`node_modules/`、`.pytest_cache/`、生成物（`*.pyc`） | 命中 → ⚠️，detail 含路径对（最多 5 对） |

**安全**：六探针全部只读，不写文件、不 git 变更、不删除。P6 全量 sha256 可能耗时，设 60s timeout，超时降级为「仅比对同名文件」。

### 2.2 Lane B 接入（`src/lanes/lane_b_assets.py` 增量）

```python
SECTION_CONSISTENCY = "12. 资产一致性检测"

def _consistency_findings(audit: dict) -> list[Finding]:
    findings: list[Finding] = []
    sections = audit.get("sections") or {}
    for item in sections.get(SECTION_CONSISTENCY) or []:
        status = item.get("status", "")
        name = item.get("name", "")
        detail = item.get("detail", "")
        if status == "✅":
            findings.append(Finding(
                lane="B", item=name, severity="info", status="ok",
                evidence=f"{SECTION_CONSISTENCY}: {detail[:150]}",
            ))
        elif status == "⚠️":
            findings.append(Finding(
                lane="B", item=name, severity="warning", status="open",
                evidence=f"{SECTION_CONSISTENCY}: {detail[:150]}",
                action="运行 governor.py audit 进入资产审计工作流",
            ))
    return findings
```

- `_audit_findings()` 的章节元组从 `(SECTION_ASSETS, SECTION_PROVIDER)` 扩展为三元组（加 `SECTION_CONSISTENCY`）。
- 复用既有 `_audit_findings` 的 ✅/⚠️/❌ 三分支逻辑，不新增判定。

### 2.3 policy 增量（`src/policy.py`）

```python
_ITEM_TIER = {
    # ... 既有条目 ...
    # v1.1 新增：资产一致性探针（只读，但处置需人工确认）
    "asset_consistency": CONFIRM,
    "doc_path_broken": CONFIRM,
    "skeleton_component": CONFIRM,
    "untracked_assets": CONFIRM,
    "hardcoded_root_path": CONFIRM,
    "duplicate_assets": CONFIRM,
}
```

- 全部 `CONFIRM`：探针本身只读（无写动作），但处置建议（归位/合并/降级）需人工确认。
- 沿用 `DEFAULT_TIER = CONFIRM` 兜底，未知项默认停手。

### 2.4 AuditItem 数据结构（`src/models.py` 新增）

```python
@dataclass(frozen=True)
class AuditItem:
    id: str                # 稳定标识，如 "P3-health-engine"
    category: str          # 残留 | 重复 | 空壳 | 口径漂移 | 断链
    evidence: str          # 证据（file:line / 命令输出摘要）
    suggestion: str        # 处置建议（归位/合并/降级/删除/补实现）
    tier: str              # L0-L3 分级（audit_exec 用）
    status: str            # pending | approved | done | skipped | needs-human
    detail: dict           # 补充字段（路径对、计数、阈值等）
```

### 2.5 audit 子命令 CLI（`scripts/governor.py` 增量）

```bash
# 六环节，默认零写（dry-run）
python3 L2-infra/components/system-governor/scripts/governor.py audit

# 结构化输出
python3 ... governor.py audit --json

# 仅执行 L1 可回滚处置（git mv 归位/合并）；L2+ 仍 needs-human
python3 ... governor.py audit --apply

# 只跑指定探针取证（可选，默认全部）
python3 ... governor.py audit --only P1,P3
```

**参数契约**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `audit` | 子命令 | — | 与 `run`/`report` 平级 |
| `--apply` | flag | off | 开：执行 L1 写动作；关：全 dry-run |
| `--json` | flag | off | 开：stdout 输出 JSON 报告 |
| `--only P1,P2` | str | 全部 | 限定取证探针 |
| `--timeout` | int | 300 | 整体 wall-clock 预算秒 |

**退出码**：0=成功（含 dry-run）；1=执行异常；2=参数错误。

---

## 3. audit 工作流详细设计

### 3.1 六环节（`src/audit_flow.py`）

```
┌─ 1 取证 ─────────────────────────────────────────────┐
│ 调 full_audit §12（复用 _run_audit_json）→ 探针结果    │
│ + git status / 目录交叉核对（复用 audit 探针输出）      │
│ 产出：raw_findings[]                                   │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ 2 定性 ─────────────────────────────────────────────┐
│ audit_classify.classify(raw) → AuditItem[]            │
│ 规则：按探针 ID + 证据内容映射 category                │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ 3 方案 ─────────────────────────────────────────────┐
│ audit_classify.suggest(item) → suggestion + tier      │
│ 规则表（§3.2）                                        │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ 4 拍板 ─────────────────────────────────────────────┐
│ tier == L2/L3 → status=needs-human（停手，列命令）     │
│ tier == L1 → status=pending（进 dry-run 清单）         │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ 5 执行（仅 --apply）────────────────────────────────┐
│ audit_exec.run(items, apply)                          │
│ L1 且 apply → git mv 归位/合并（每笔进账本）           │
│ L2+ 即使 apply → 只记 needs-human，不执行              │
└───────────────────────┬───────────────────────────────┘
                        ▼
┌─ 6 回归 ─────────────────────────────────────────────┐
│ 重跑 §12 探针 → 确认命中项清零                          │
│ 写 memory/governor-audit-latest.json（复用 save_report）│
└───────────────────────────────────────────────────────┘
```

### 3.2 分类与建议规则表（`src/audit_classify.py`）

| 探针 | category | suggestion | tier |
|---|---|---|---|
| P1 计数漂移 | 口径漂移 | 运行 `gen_asset_inventory.py` 重新登记 | L1（文档生成器，可回滚） |
| P2 路径断链 | 断链 | 修正文档引用（`git mv` 或改文档） | L2（改文档需人工核对） |
| P3 空壳组件 | 空壳 | 降级为「📐 设计态」或补实现 | L2（改声明需人工拍板） |
| P4 未跟踪/未提交 | 口径漂移 | `git add` + commit（需人工确认范围） | L2（提交需人工确认） |
| P5 硬编码根路径 | 残留 | 改代码路径 + 迁移文件 + 重启 daemon | L2（改代码需人工确认） |
| P6 重复资产 | 重复 | `git mv` 归位到规范目录（保留一份） | L1（git mv 可回滚） |

**稳定 ID 规则**：`f"{probe_id}-{slug(evidence[:40])}"`，同 evidence 多轮审计 ID 不变（幂等）。

### 3.3 L1 执行器（`src/audit_exec.py`）

```python
def run(items: list[AuditItem], apply: bool) -> list[AuditItem]:
    """执行 L1 可回滚处置。L2+ 即使 apply 也只记 needs-human。"""
    executed = []
    for item in items:
        if item.tier in ("L2", "L3"):
            executed.append(replace(item, status="needs-human"))
            continue
        if not apply:
            executed.append(replace(item, status="pending"))
            continue
        # L1 且 apply：git mv 归位/合并
        ok = _git_mv(item.detail["src"], item.detail["dest"])
        executed.append(replace(item, status="done" if ok else "needs-human"))
    return executed
```

**安全边界**：
- 仅支持 `git mv`（保留历史、可 `git revert`）。
- 执行前校验 `src` 存在、`dest` 不存在（防覆盖）。
- 每笔操作记入账本 `actions[]`（时间、src→dest、结果）。
- 不支持 `rm`/`mv`（非 git 追踪文件）——这类归 L2 人工。

### 3.4 审计账本（复用 `ledger.py`）

```python
# 复用 save_report 的原子写（tmp + replace）
save_report(report, path="memory/governor-audit-latest.json")
```

账本 schema：

```json
{
  "timestamp": "ISO",
  "invoked": "cli",
  "apply": false,
  "items": [
    {
      "id": "P3-health-engine",
      "category": "空壳",
      "evidence": "L2-infra/components/health-engine/: 0 py，README 声明✅已上线",
      "suggestion": "降级为「📐 设计态」或补实现",
      "tier": "L2",
      "status": "needs-human",
      "detail": {"component": "health-engine", "py_count": 0}
    }
  ],
  "summary": {"total": 1, "pending": 0, "done": 0, "needs_human": 1, "skipped": 0}
}
```

---

## 4. 技能入口更新（`L2-infra/skills/system-governor/SKILL.md`）

增量补充：

```markdown
## 资产审计工作流（v1.1）

当需要全盘资产审计（残留/重复/空壳/口径漂移/断链）时：

1. 取证：`governor.py audit`（默认零写，跑 §12 六探针）
2. 看报告：`governor.py audit --json`（含 category/suggestion/tier）
3. L2+ 项：按 suggestion 列出的命令人工拍板
4. L1 项：确认 dry-run 清单后 `governor.py audit --apply`
5. 回归：重跑 `governor.py audit` 确认清零

安全：audit 默认零写；L2+ 即使 --apply 也不执行；账本落 memory/governor-audit-latest.json。
```

---

## 5. 测试黄金基准（`tests/`）

| 套件 | 用例 | 断言核心 |
|---|---|---|
| `test_asset_consistency.py` | 6 | 每个探针注入命中（临时空壳目录/断链路径/未跟踪文件/硬编码路径/重复文件）→ 命中；清理后 → 不命中 |
| `test_lane_b_assets.py` | 3 | §12 章节聚合为 Finding；✅→info/ok、⚠️→warning/open；无 §12 时不报错 |
| `test_audit_classify.py` | 5 | 六类探针 → 正确 category/tier；稳定 ID 幂等（同 evidence 两次 ID 相同） |
| `test_audit_exec.py` | 4 | L1+apply 执行 git mv；L2+apply 不执行只记 needs-human；无 apply 时零写；dest 已存在时拒绝 |
| `test_audit_flow.py` | 3 | 六环节串联；账本 schema 合法；回归后命中项清零 |

**验收门**：
1. `governor.py audit`（无 --apply）零写操作（git status 前后一致、无新文件）。
2. `--apply` 下 L1 执行、L2+ 不执行。
3. §12 六探针在注入用例下各自命中，清理后清零。
4. Lane B `run --only B --json` 的 findings 含 §12 结果。
5. 全量回归：既有 36 项检测 + system-governor 既有测试零破坏。
6. 真实执行，不虚构。

---

## 6. 影响面与文件清单

**新建**：
```
L2-infra/components/system-governor/src/audit_flow.py
L2-infra/components/system-governor/src/audit_classify.py
L2-infra/components/system-governor/src/audit_exec.py
L2-infra/components/system-governor/tests/test_asset_consistency.py
L2-infra/components/system-governor/tests/test_lane_b_assets.py
L2-infra/components/system-governor/tests/test_audit_classify.py
L2-infra/components/system-governor/tests/test_audit_exec.py
L2-infra/components/system-governor/tests/test_audit_flow.py
```

**最小增量修改**：
- `L2-infra/scripts/system_full_audit.py`：新增 §12 `audit_asset_consistency()` + 注册到 `sections`。
- `L2-infra/components/system-governor/src/lanes/lane_b_assets.py`：章节元组加 `SECTION_CONSISTENCY`。
- `L2-infra/components/system-governor/src/policy.py`：`_ITEM_TIER` 加 6 个前缀。
- `L2-infra/components/system-governor/src/models.py`：新增 `AuditItem`。
- `L2-infra/components/system-governor/scripts/governor.py`：新增 `audit` 子命令。
- `L2-infra/skills/system-governor/SKILL.md`：补资产审计工作流。

**不改**：gen_asset_inventory 生成/发现逻辑、Lane A/C/D、reliability 行为、既有 11 节检测判定、task_tracker、service_guardian。

---

## 7. 分期与验收（继承 OUTLINE §6）

P1 §12 探针 → P2 Lane B 接入 → P3 audit 子命令 → P4 测试 → P5 技能入口 + 文档 + 全量回归。每 Phase 独立可交付、可回滚。

---

## 8. 待 Rex 拍板（本 DETAIL 新增）

1. **P6 重复资产算法**：全量 sha256 分组（60s timeout，超时降级为同名比对）是否接受？还是仅比对同名文件（更快但漏检异源同内容）？
2. **L1 执行器边界**：仅支持 `git mv`（保留历史可回滚），不支持 `rm`/非 git 文件移动——这类归 L2 人工，是否接受？
3. **P2 路径断链提取**：从架构文档正则提取路径引用（覆盖 `00-system-architecture.md` + `01-asset-inventory.md` + 组件文档），是否接受这个范围？
4. **audit 账本位置**：`memory/governor-audit-latest.json`（复用 ledger 原子写）是否接受？

> 全部通过 → 按 P1 开始编码；每个 Phase 完成自测 + 汇报。
