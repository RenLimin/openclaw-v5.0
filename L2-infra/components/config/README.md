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

## 依赖

- `openclaw` CLI
- Python 3（snapshot_config.py / gen_asset_inventory.py）
- bash 4+
