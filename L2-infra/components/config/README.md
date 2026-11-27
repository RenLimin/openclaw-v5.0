# config

**定位：** L2 基础设施层 — 配置管理，固化"读→改→确认→快照"四步流程，防止配置漂移。

## 功能列表

- 配置审计（快照/hook/校验/凭据引用扫描）
- 脱敏快照入库（`config-snapshots/openclaw.json`）
- 配置 diff（当前 vs 上次快照）
- 四步安全变更流程：dry-run → apply → 读回确认 → 快照
- 模型 contextWindow 实测探测
- Git pre-commit hook 自动安装
- 凭据泄漏扫描（推送前检查）
- 静态资源清单生成

## 目录结构

```
config/
├── config.sh                  # 主入口脚本（审计/快照/diff/apply/scan）
├── config_safe_write.sh       # 安全写入封装
├── snapshot_config.py         # 快照入库脚本
├── gen_asset_inventory.py     # 静态资源清单生成
├── install-hooks.sh           # Git hooks 安装脚本
├── git-hooks/
│   └── pre-commit             # pre-commit hook
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
└── DESIGN.md
```

## 使用方式

```bash
./config.sh audit             # 全面审计
./config.sh snapshot          # 脱敏快照入库
./config.sh diff              # 当前 vs 上次快照
./config.sh apply <file>      # 四步安全变更
./config.sh probe <model> <n> # 实测模型 contextWindow
./config.sh scan              # 凭据泄漏扫描
./install-hooks.sh            # 安装 Git hooks
```

## 能力注册表（capability-registry）

`capability-registry/` 维护 `registry.yaml`（已建能力的唯一权威索引），引擎为 `capability_registry.py`。

### 查询与权威性仲裁

```bash
# 可发现性：关键词命中 + 权威入口
python3 L2-infra/components/config/capability-registry/capability_registry.py --query contract

# 只看权威入口（过滤 overlap/deprecated 次要条目）
python3 L2-infra/components/config/capability-registry/capability_registry.py --query project --strict
```

同一能力域（`domain`）命中 ≥2 条时，非 authoritative 条目自动降权排后，并标注
`[overlap→权威:<能力 id>]`，让后续会话一眼看到「该用哪个」。不传新参数时行为不变（向后兼容）。

### registry.yaml 字段

| 字段 | 取值 | 说明 |
|---|---|---|
| `domain` | 字符串（如 `contract`/`project`/`oa`） | 能力域；空=未声明，不参与重叠判定（P7 只统计声明了域的条目） |
| `authority` | `authoritative`（默认）/ `overlap` / `deprecated` | 权威性；缺省或非法值加载时归一化为 `authoritative` |

- 同域应只有一个 `authoritative` 入口；其余标 `overlap`。
- `supersedes` 指向的文件**已全部物理删除**的条目标 `deprecated`（`--strict` 会过滤掉）。

### 维护约定

- 新增能力/组件/skill → 先 `--query` 查重；确实新建 → 同日补 `registry.yaml` 条目并声明 domain/authority。
- 覆盖率门禁：`--coverage` 必须 100%（含并行会话在途新建目录造成的临时缺口需由对应会话补登记）。
- 自校验：`--validate` 校验 entry 路径存在性 + health 探针可调用性。

## 依赖

- `openclaw` CLI
- Python 3（snapshot_config.py / gen_asset_inventory.py）
- bash 4+
