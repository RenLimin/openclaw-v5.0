# workspace-temp-cleanup — 操作手册 (OPERATIONS)

> INFRA-CLN-001 · v1.0 · 2026-10-29

## 1. 安装与启动
### 1.1 依赖
- macOS + `/usr/bin/trash`（系统自带）；Python 3（stdlib，无第三方包）
### 1.2 安装
组件随仓库分发，无需安装；cron 见 §3。
### 1.3 启动命令
```bash
cd ~/.openclaw/workspace/L2-infra/components/workspace-temp-cleanup
python3 scripts/tempcleanctl.py dry-run        # 预览（默认）
python3 scripts/tempcleanctl.py clean --yes    # 实删（进废纸篓）
python3 scripts/tempcleanctl.py list
python3 scripts/tempcleanctl.py verify
```
### 1.4 健康检查
`verify` exit 0 = trash 可用、登记合法、gitignore 已覆盖临时区。

## 2. 操作指南
### 2.1 AI 产生临时文件（写方）
1. 落在 `analysis_output/` / `scripts/tmp/` / `tmp/` / `scratch/`，或命名 `*-tmp`/`*.tmp`
2. 需自定义 TTL 时在仓库根 `.openclaw-temp.json` 的 entries 追加一项
3. 正式交付物不要放临时区，直接 commit
### 2.2 手动清理
先 `dry-run` 看清单 → 确认后 `clean --yes` → 文件进废纸篓可恢复
### 2.3 查看将被删什么
`dry-run`（有过期项 exit 2）；`list` 看全部临时资产 TTL 状态

## 3. 配置说明
### 3.1 路径
- 登记：仓库根 `.openclaw-temp.json`；临时区：见架构 §7.4.5
### 3.2 默认值
- TTL：intermediate 7 天 / ledger 30 天；entry.ttl_days 可覆盖
- cron：每日 03:30 isolated 执行 `clean --yes`

## 4. 故障排查
| 症状 | 原因 | 解决 |
|---|---|---|
| verify exit 3「trash missing」 | trash 不在 PATH | 恢复 /usr/bin/trash；组件绝不 fallback rm |
| clean 拒绝「invalid registry」 | JSON 写坏 | 修复 `.openclaw-temp.json`，verify 通过再 clean |
| 文件没被删 | 未标记 / 未超 TTL / 内含新文件 | 属预期；确需删请先登记或手动 trash |
| 路径越界报错 | entry 含 `../` | 改为 root 内相对路径 |

## 5. FAQ
- Q：删错能恢复吗？A：能，全部进系统废纸篓。
- Q：正式交付物会被删吗？A：不会，未标记/已 commit 的不在候选集。
