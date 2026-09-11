# 维护组件设计

> L2 基础设施层 · 系统维护组件
>
> **2026-09-11 创建**：Colima/Docker 健康检查 + 仓库维护脚本。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 系统维护 |
| 状态 | ✅ 已建设 (2026-08) |
| 验证 | smoke test + 手动验证 |

## 2. 设计约束

1. **macOS 优先**：Colima + launchd 方案仅适用于 macOS，其他平台需手动 `docker start`。
2. **自动修复优先**：Docker 不可用时自动尝试恢复，失败才退出码 1 通知人工。
3. **配置校验前置**：启动前先校验 launchd plist 内容，避免无效重启。
4. **渐进式修复**：launchd → 手动 colima start → 人工介入，三级递进。
5. **幂等安全**：重复执行不会产生副作用（已运行则直接返回成功）。

## 3. 架构

```
┌──────────────────────────────────────────────────────┐
│                    maintenance                        │
├──────────────────────────────────────────────────────┤
│          colima-docker-check.py                       │
│          Colima/Docker 健康巡检 + 自动修复             │
├──────────────────────────────────────────────────────┤
│          tests/                                       │
│          ├── conftest.py                              │
│          └── test_smoke.py                            │
└──────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 健康巡检 | `colima-docker-check.py` | Docker/Colima 状态检测 + 自动修复 |
| 测试 | `tests/test_smoke.py` | 组件目录结构和 Python 文件存在性验证 |

## 4. 核心模块详解

### 4.1 colima-docker-check.py — Colima/Docker 健康巡检

**检测流程**（四级递进）：

```
Level 1: docker info
  ├── 可用 → ✅ 退出 0
  └── 不可用 → Level 2

Level 2: colima status
  ├── 运行中 → Docker 异常，尝试 launchd 重启
  └── 未运行 → Level 3

Level 3: launchd 配置校验
  ├── 非 macOS / 无 launchd → ❌ 退出 1，提示手动 colima start
  ├── plist 不存在 → ❌ 退出 1
  ├── colima 路径不正确 → ❌ 退出 1
  └── 配置正确 → Level 4

Level 4: 启动 Colima
  ├── launchd unload/load → 等待 15s → docker info → ✅
  └── launchd 失败 → 手动 colima start → docker info → ✅/❌
```

**核心函数**：

| 函数 | 返回 | 说明 |
|---|---|---|
| `is_docker_available()` | bool | `docker info` 返回码 0 |
| `is_colima_running()` | bool | `colima status` 输出含 "colima is running" |
| `check_launchd_available()` | bool | macOS + launchctl 可用 |
| `check_launchd_colima()` | bool | plist 存在 + 路径正确 + PATH 配置正确 |
| `restart_colima_via_launchd()` | bool | unload/load + 15s 等待 + 验证 |

**launchd plist 校验要点**：
- 路径：`~/Library/LaunchAgents/com.colima.auto.plist`
- 必须包含 `/opt/homebrew/bin/colima`（ARM Mac 路径）
- `EnvironmentVariables` 中必须包含 `/opt/homebrew/bin`（limactl 查找路径）

**退出码**：
| 退出码 | 含义 |
|---|---|
| 0 | Docker 可用（正常或修复成功） |
| 1 | 修复失败，需人工介入 |

## 5. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| python3 | 运行时 | 纯标准库实现（subprocess / sys / os / shutil / pathlib） |
| docker | 外部工具 | `docker info` 健康探测 |
| colima | 外部工具 | `colima status` / `colima start` |
| launchctl | 外部工具 | macOS 服务管理（仅 macOS） |

## 6. 使用方式

```bash
# 手动运行
python3 L2-infra/components/maintenance/colima-docker-check.py

# 典型输出
=== 开始 Colima/Docker 健康检查 ===

❌ Docker daemon 不可用，开始排查...

❌ Colima 未运行
🔄 尝试通过 launchd 重启 colima...
⌛ 等待 Colima 启动（15秒）...
✅ 成功启动 Colima，Docker 现在可用了

=== 检查完成，修复成功 ===
```

## 7. 典型故障场景

| 场景 | 现象 | 修复路径 |
|---|---|---|
| Docker 已可用 | 直接退出 0 | 无需修复 |
| Colima 未运行 + launchd 配置正确 | launchd 重启成功 | Level 4 自动修复 |
| Colima 未运行 + launchd 配置异常 | 退出 1 | 需手动修复 plist |
| launchd 启动失败 | 降级到手动 `colima start` | Level 4 二级修复 |
| 非 macOS 平台 | 退出 1 | 手动 `docker start` / `colima start` |
| Docker 在运行但 colima status 异常 | Colima 运行但 Docker 不可用 | launchd 重启 |

## 8. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 集成到 cron 定时巡检 | 高 | 当前手动运行，可加入 cron 自动巡检 |
| 通知集成 | 中 | 修复失败时自动通知 Rex（wecom） |
| 多平台支持 | 低 | Linux/Windows 环境下需不同策略 |
| 资源监控 | 低 | 扩展检查 Colima 的 CPU/内存/磁盘使用 |
| 自动 plist 修复 | 低 | 检测到 plist 配置异常时自动重写 |

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08 | colima-docker-check.py 首版（四级递进检测 + 自动修复） |
| 2026-09-11 | 编写 DESIGN.md |
