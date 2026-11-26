# capability-registry — 能力注册表组件设计 (DESIGN v1.0)

> 日期: 2026-11-20 · 层: L2 基础设施 · 归属: `L2-infra/components/config/capability-registry/`

## 1. 定位

**让任何会话在动手前能一键确认「这个能力是否已建成、权威入口在哪」**，从机制上消除重复建设。

单一权威索引：`registry.yaml`（人工维护，含 entry / notes / supersedes）。
派生视图：`docs/architecture/01-asset-inventory.md` §能力注册表（`gen_asset_inventory.py` 渲染）。

## 2. 问题背景（实证）

| 现象 | 根因 |
|---|---|
| OA/ONES 浏览器自动化反复重造脚本 | `bdms/scripts/` 下 15+ 个 ONES/OA 导出同族变体（`export_ones_202609` / `reexport_ones_all_*` / `diag_*`）；`tmp/` 下 19 个一次性脚本 |
| agent 误判「能力缺失」 | 旧资产清单**只有组件级粒度、无脚本级条目** → 查不到能力 |
| 无前置门禁 | 重复检测只有事后审计（system-governor P6），不拦新建 |

## 3. 设计

### 3.1 数据模型（registry.yaml）

```yaml
version: 1
updated: 2026-11-20
high_risk_dirs: [重复家族高发的目录]
duplicate_family_patterns: [文件名家族正则]
capabilities:
  - id: ones-export              # 稳定标识，不删只迁移
    name: ONES 项目数据导出
    layer: L4
    interfaces: [ones, export, browser]   # 查询关键词
    entry: ["..."]               # 可直接调用的路径/命令（禁止「见文档」）
    health: ["..."]              # 可选：可调用性探针（离线/只读/无副作用）
    notes: "..."                 # 陷阱与红线
    supersedes: ["被本能力取代的旧脚本路径"]
allow: [{path, reason}]          # 合法一次性脚本白名单
```

> `health:` 是 2026-11-23 新增字段（见 §3.4）。只有「能力可用」可被机器证明时才会用到，
> 属于**可选**：没有探针的能力只需保证 entry 可调用并在 notes 写明运行态前提。
```

### 3.2 五条防线（业界对标）

| 防线 | 命令 | 业界对标 | 作用 |
|---|---|---|---|
| 可发现性 | `--query/--list/--explain` | Backstage Software Catalog（统一资产索引，防重复） | agent 动手前查 |
| 覆盖率 | `--coverage` ← pre-commit step 6 | Backstage catalog completeness（无孤儿） | 未登记资产即阻断 |
| 自校验 | `--validate` ← pre-commit step 7 | Archgate fitness function / catalog validation | 孤儿 entry 即阻断 |
| 可调用性 | `--validate`（执行 `health:` 探针）← pre-commit step 7 | Archgate fitness function / chaos engineering 前置检查 | entry 存在但能力不可用即阻断 |
| 生命周期 | `--lifecycle --new-only --require-design` ← pre-commit step 8 | DoD / ADR Guard / OWASP shift-left | 新增资产无设计文档即阻断 |
| 门禁 | `--check --staged` ← pre-commit step 5 | OWASP shift-left（最早门禁） | 拦新建重复脚本，指出权威入口 |
| 渲染 | `gen_asset_inventory.py` §能力注册表 | TechDocs docs-like-code | 人看 / agent 读资产清单时可见 |

> 核心逻辑与解决「重复建设」同源：**可发现 + 前置门禁**，而非依赖 agent 自觉。

### 3.3 判定规则

1. 文件名命中 `duplicate_family_patterns` → 嫌疑
2. 用「剥前缀/日期/尾缀」的词干 + 关键词回退匹配能力 → 取最高分能力的权威入口
3. 命中 `allow` → 放行（显式登记 + 理由）
4. 输出：❌ 文件 + 原因 + **改用: <能力 id: 入口>**

## 4. 接口

```bash
python3 L2-infra/components/config/capability-registry/capability_registry.py --query oa
python3 L2-infra/components/config/capability-registry/capability_registry.py --list
python3 L2-infra/components/config/capability-registry/capability_registry.py --explain ones-export
python3 L2-infra/components/config/capability-registry/capability_registry.py --check --staged
python3 L2-infra/components/config/capability-registry/capability_registry.py --check --all
python3 L2-infra/components/config/capability-registry/capability_registry.py --coverage
python3 L2-infra/components/config/capability-registry/capability_registry.py --validate
python3 L2-infra/components/config/capability-registry/capability_registry.py --validate --skip-health   # 仅验路径
python3 L2-infra/components/config/capability-registry/capability_registry.py --lifecycle --new-only --require-design
```

### 3.4 可调用性探针（`health:`）—— 为什么 entry 存在还不够

**实证缺口（2026-11-23）**：`browser-automation` 条目路径真实、覆盖率 100%，
但**全仓无启动器** → `ones_available()` 恒 `False` → 每轮会话重复摸索启动命令。
即「已登记 ≠ 被触发即可用」。

`--validate` 因此在路径校验之后**顺带执行 `health:` 探针**：

| 约束 | 理由 |
|---|---|
| 只执行显式登记的探针 | 不自动探测，避免把慢/有副作用的命令带入提交门禁 |
| 必须离线、只读、无副作用 | 提交时不应启动服务/写文件/联网 |
| 单条超时（默认 60s，`REGISTRY_HEALTH_TIMEOUT` 可覆盖） | 防止门禁挂死 |
| 超时 / 无法执行 / 非零退出 → **fail-closed** | 不得静默放行 |
| `--skip-health` 逃生阀 | 应急绕过（需在 PR 说明） |

探针语义由资产自己定义，必须**状态无关**（例：`ensure_chrome.py status --probe` 只验
前置齐备，不要求实例处于开或关；否则用户合法使用实例时会被误判阻断提交）。

**与 `--expect` 的区别**：`--expect` 断言运行态（测试/运维），`--probe` 断言可调用性（门禁）。

### 3.5 新增资产默认强制（而非可选）

**问题**：`health:` 若只是可选字段，新增资产不写探针照样能过门禁，等于仍靠自觉。

**解**：pre-commit step 8 以 `--require-health` 强制：

| 规则 | 说明 |
|---|---|
| 新增资产（HEAD 中不存在）必须有 `health:` 探针 | 否则阻断提交 |
| 确无稳定可执行入口 → 写 `health_exempt: "理由"` | 可审计，不得留空绕过 |
| 应急跳过：`--lifecycle --require-health --skip-health-requirement` | 显式传参，需在 PR 说明 |

**为何不追溯存量资产**：与 `--lifecycle --new-only` 一致——只对新资产强制，
存量资产的探针登记逐次补齐（避免一次性阻断并行会话）。

存量资产的探针仍以 `--validate`（全量执行所有已登记 `health:`）为准，两者互补：
`--require-health` 管「新增必须有」，`--validate` 管「已登记的必须真的能跑」。

### 3.6 资产枚举口径单一事实源（`enumerate_assets`）

**事故（2026-11-25/26）**：`health_check.py` 自造 L2 组件枚举、`system_full_audit.py §3`
裸 `iterdir()` 数 L4 组件、`_discover_assets()` 又一套 `.`/`__` 前缀规则——**三套口径**。
后果：`.deprecated` 被算成组件（旧审计数 12 个 L4，实际 10 个）、设计文档误报缺失，
监控长期说谎而无人察觉。

**解**：唯一公共 API `enumerate_assets(kind=None, root=None)`（返回 `[(layer, kind, Path)]`），
所有「盘点有哪些资产」的场景强制走它：

| 调用方 | 用法 | 不可用时的行为 |
|---|---|---|
| `_discover_assets()` | 转形状（目录名列表） | —（内部实现即调它） |
| `health_check.check_components()` | `_iter_asset_dirs()` + `_asset_docs()` | **显式 skip**，不降级 |
| `system_full_audit §3` | `enumerate_assets("components", root=WORKSPACE)` | 降级并标注「iterdir(降级)」 |
| `--coverage` / `--lifecycle` | `_discover_assets()` | — |

排除规则集中为 `ASSET_EXCLUDED_NAMES = {.git, node_modules, __pycache__, .pytest_cache,
.mypy_cache, .deprecated, dist}`，由 `is_real_asset_dir()` 统一判定。
> 历史缺陷：常量定义了却无人引用（`_iter_asset_dirs` 只查 `.`/`__` 前缀），
> 导致 `node_modules` 混入——已由回归测试锁定（防再次分叉）。

### 3.7 范围豁免（`scope_exemptions`）

**问题**：`L1_runtime/components/{agent-registry,context-bus,error-handler,telemetry}`
在磁盘存在且有 DESIGN/VERIFICATION，但从未登记进 registry，长期被后续会话当作「未登记缺口」重复排查。

**定位**：不是漏登记，而是层级契约（ADR-202608-001）——L1 = OpenClaw 基座 + 运行时适配层，
不可修改、无对外可调用能力，故不产生 capability 条目。

**解**：`registry.yaml` 显式声明 `scope_exemptions`（path + reason），并在 `--coverage` /
`--lifecycle` 输出中**显性列出**，使边界可见而非隐缺口。豁免路径必须真实存在且写明理由
（回归测试强制），不得留空绕过。

## 5. 依赖

| 依赖 | 说明 |
|---|---|
| PyYAML | registry.yaml 解析（缺失时显式报错，不静默） |
| git | `--check --staged` 取暂存区列表 |
| pre-commit hook | 已装（`install-hooks.sh`，step 5） |

## 6. 设计约束

- **entry 必须可直接执行**（测试强制：含「见文档」即失败）
- 能力 id 稳定，迁移只改 entry，不删 id（保留审计链）
- 门禁只拦**新增**（`--staged` / 工作树 diff），历史脚本由 system-governor P6 扫归位
- 判定失败不静默：无能力命中 → 输出提示；注册表缺失/解析失败 → 显式报错

## 7. 测试

`L2-infra/components/config/tests/test_capability_registry.py`（33 用例）：
加载 / 精确查询 / 别名查询 / 全能力 entry 可执行性 / 三类重复脚本识别与建议准确性 /
白名单 / 非 py 忽略 / supersedes 登记 / 覆盖率 100% / 无重复 id /
`--validate` 孤儿检测（构造坏路径 + 不可执行指针）/ `--lifecycle` 新增资产判定与阻断 /
`_asset_docs` 递归（docs/ 子目录文档可被识别，防根级误报）/
**`enumerate_assets` 口径锁**（噪声目录排除、kind/layer 过滤、默认 root、豁免清单真实性与显性输出）。

## 8. 演进

| 方向 | 触发 |
|---|---|
| 能力依赖图（调用链） | 多能力串联编排需求 |
| 与 system-governor P6 打通（自动归位） | P6 成熟后 |
| ~~验收文档补齐~~ ✅ 2026-11-20 完成（71/71） | 已闭环 |

> entry 健康探测已实现（`--validate`，2026-11-20）。
> 文档递归识别已实现（`_asset_docs` 扫 docs/ 子目录，2026-11-20）。

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-20 | 首版：registry.yaml（10 能力）+ 引擎 + 测试 + pre-commit 门禁 + 资产清单渲染 |
| 2026-11-20 | 全量覆盖：81 条目（45 组件 + 26 skill + 10 能力族）；新增 `--coverage` 覆盖率硬指标 + pre-commit step 6 |
| 2026-11-20 | 工程化补齐：14 个孤儿 entry 修正（99 条路径全部真实）；新增 `--validate`（fitness function）+ `--lifecycle`（DoD/ADR Guard 闭环门禁）+ pre-commit step 7/8 |
| 2026-11-20 | 全量闭环：71 个资产设计/验收文档 71/71（补 5 DESIGN + 29 VERIFICATION）；`_asset_docs` 递归识别 docs/ 子目录，消除根级误报 |
| 2026-11-23 | 可调用性探针门禁：registry 新增可选 `health:` 字段；`--validate` 执行探针（超时/非零退出 fail-closed，`--skip-health` 逃生阀）；已登记 3 条（browser-automation / config / skill-system-health-check）。动因：entry 路径存在 ≠ 能力可用（browser-automation 无启动器的实证缺口） |
| 2026-11-23 | 探针改为**新增资产默认强制**：新增字段 `health_exempt`（显式豁免理由）；`--lifecycle --require-health` 阻断无探针/无豁免的新资产；pre-commit step 8 同步启用。可选 → 默认强制，消除「靠自觉」缺口 |
| 2026-11-26 | **资产枚举口径收敛**：新增公共 API `enumerate_assets(kind, root)` + `is_real_asset_dir()` + `ASSET_EXCLUDED_NAMES`；`health_check` / `system_full_audit §3` / `_discover_assets` 全部改为调用它，删除各自 iterdir 口径；修复 `ASSET_EXCLUDED_NAMES` 定义未被引用的缺陷（`node_modules` 混入）。新增 `scope_exemptions`（4 条 L1 豁免，ADR-202608-001）并在 `--coverage`/`--lifecycle` 显性列出 |
