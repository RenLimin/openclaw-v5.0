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
    notes: "..."                 # 陷阱与红线
    supersedes: ["被本能力取代的旧脚本路径"]
allow: [{path, reason}]          # 合法一次性脚本白名单
```

### 3.2 三条链路

| 链路 | 实现 | 作用 |
|---|---|---|
| 可发现性 | `capability_registry.py --query/--list/--explain` | agent 动手前查 |
| 门禁 | `capability_registry.py --check --staged` ← pre-commit step 5 | 拦新建重复脚本，指出权威入口 |
| 渲染 | `gen_asset_inventory.py` §能力注册表 | 人看 / agent 读资产清单时可见 |

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
```

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

`L2-infra/components/config/tests/test_capability_registry.py`（12 用例）：
加载 / 精确查询 / 别名查询 / 全能力 entry 可执行性 / 三类重复脚本识别与建议准确性 / 白名单 / 非 py 忽略 / supersedes 登记。

## 8. 演进

| 方向 | 触发 |
|---|---|
| 能力依赖图（调用链） | 多能力串联编排需求 |
| 与 system-governor P6 打通（自动归位） | P6 成熟后 |
| entry 健康探测（入口存在性校验） | 入口漂移问题出现时 |

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-20 | 首版：registry.yaml（10 能力）+ 引擎 + 测试 + pre-commit 门禁 + 资产清单渲染 |
