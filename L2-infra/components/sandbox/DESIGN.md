# 沙箱隔离组件设计

> L2 基础设施层 · 沙箱隔离组件
>
> **2026-09-11 更新**：基于实际代码重写设计文档。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 沙箱隔离 |
| 状态 | ✅ 已实现 |
| ADR | ADR-013（沙箱隔离契约下沉到 L2） |
| 依赖 | L1-runtime 适配器（openclaw.adapter） |

## 2. 职责

沙箱隔离组件提供以下核心能力：

1. **沙箱生命周期管理**：创建、启动、停止、销毁沙箱实例
2. **权限策略检查**：白名单 + 黑名单 + 全局危险命令拦截
3. **文件挂载管理**：支持只读/读写挂载配置
4. **输出捕获**：获取沙箱内命令执行输出
5. **状态持久化**：沙箱状态落盘，支持重启恢复

## 3. 架构

```
┌─────────────────────────────────────────────────────┐
│                  cli.py (CLI 入口)                    │
├─────────────────────────────────────────────────────┤
│              SandboxIsolationService                  │  统一服务层
├──────────────────┬──────────────────────────────────┤
│  SandboxManager  │        SandboxPolicy             │  生命周期 / 权限
│  (生命周期管理)   │        (策略检查)                  │
├──────────────────┴──────────────────────────────────┤
│         L1-runtime / openclaw.adapter                │  底层执行适配
├─────────────────────────────────────────────────────┤
│         utils.py (通用工具函数)                        │  文件/时间/目录
└─────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| service | `service.py` | 统一服务门面，编排 Manager + Policy |
| manager | `scripts/sandbox.py` | 沙箱生命周期：创建/启动/停止/销毁/挂载 |
| policy | `scripts/policy.py` | 权限策略：白名单/黑名单/全局危险命令 |
| cli | `scripts/cli.py` | CLI 入口（10 个子命令） |
| utils | `scripts/utils/utils.py` | 通用工具：时间、文件读写、JSON、目录 |

### 3.2 数据模型

**Sandbox**（完整沙箱数据结构）：

```python
@dataclass
class Sandbox:
    sandbox_id: str        # sandbox-{timestamp}
    status: str            # created | running | exited | stopped | destroyed
    workdir: str           # 工作目录路径
    policy_name: str       # 关联的策略名称
    created_at: str        # ISO 8601 创建时间
    started_at: str        # 启动时间
    exited_at: str         # 退出时间
    command: List[str]     # 执行的命令
    exit_code: int         # 退出码
    mounts: List[Dict]     # 挂载配置列表
    env: Dict[str, str]    # 环境变量
```

**SandboxInfo**（轻量信息视图）：

```python
@dataclass
class SandboxInfo:
    sandbox_id: str
    status: str
    workdir: str
    created_at: str
    policy_name: str
```

## 4. 核心设计

### 4.1 沙箱生命周期

```
创建(created) → 启动(running) → 退出(exited)
                   ↓
               停止(stopped) → 销毁(destroyed)
```

- **创建**：生成 `sandbox-{timestamp}` ID，创建 workdir，写入 `state.json`
- **启动**：先经 Policy 检查命令权限，通过后通过 L1 适配器执行
- **停止**：调用适配器 kill_process，更新状态为 stopped
- **销毁**：停止运行中沙箱，删除整个目录，从内存移除

### 4.2 权限策略模型

策略检查三层防线：

| 层级 | 规则 | 说明 |
|---|---|---|
| 全局黑名单 | `DEFAULT_DANGEROUS_COMMANDS` | rm -rf /、fork bomb、mkfs 等 9 种危险模式 |
| 命令白名单 | `allowed_commands` | 策略文件中定义，命令必须在白名单中 |
| 路径黑白名单 | `allowed_paths` / `blocked_paths` | 路径参数通配符匹配，黑名单优先 |

策略文件存储在 `config/sandbox-policies/{name}.json`，格式：

```json
{
  "allowed_commands": ["python", "pip", "npm"],
  "allowed_paths": ["/workspace/*", "/tmp/*"],
  "blocked_paths": ["/etc/*", "/sys/*"]
}
```

### 4.3 状态持久化

沙箱状态存储在 `sandboxes/{sandbox_id}/state.json`，每次状态变更后立即落盘。启动时从磁盘加载已有沙箱到内存索引。

### 4.4 L1 适配器依赖

通过动态 import 加载 `L1-runtime/adapters/openclaw/openclaw.adapter`，调用以下接口：

| 适配器方法 | 用途 |
|---|---|
| `exec_background(command, cwd, env)` | 后台执行命令 |
| `kill_process(sandbox_id)` | 终止进程 |
| `get_output(sandbox_id, offset, limit)` | 获取输出 |
| `wait(sandbox_id, timeout)` | 等待完成 |

## 5. CLI 接口

```bash
# 沙箱生命周期
python3 scripts/cli.py create   --policy <name> [--workdir <path>]
python3 scripts/cli.py start    --id <sandbox_id> <command>...
python3 scripts/cli.py stop     --id <sandbox_id>
python3 scripts/cli.py destroy  --id <sandbox_id>

# 查询
python3 scripts/cli.py list
python3 scripts/cli.py info     --id <sandbox_id>
python3 scripts/cli.py output   --id <sandbox_id> [--offset N] [--limit N]
python3 scripts/cli.py wait     --id <sandbox_id> [--timeout N]

# 策略管理
python3 scripts/cli.py policy-create --name <name> \
    --allowed-commands <cmd1> <cmd2>... \
    [--allowed-paths <p1> <p2>...] \
    [--blocked-paths <p1> <p2>...]
python3 scripts/cli.py policy-list
```

## 6. Python API

```python
from service import SandboxIsolationService

svc = SandboxIsolationService()

# 创建沙箱
ok, msg, sandbox_id = svc.create_sandbox(
    policy_name="dev",
    workdir="/tmp/work",
    mounts=[{"source": "/data", "target": "/mnt/data", "readonly": True}],
    env={"DEBUG": "1"},
)

# 启动命令
ok, msg = svc.start_sandbox(sandbox_id, ["python", "main.py"])

# 等待完成
exit_code, output = svc.wait_sandbox(sandbox_id, timeout_seconds=60)

# 获取输出
output, err = svc.get_output(sandbox_id, offset=0, limit=100)

# 销毁
ok, msg = svc.destroy_sandbox(sandbox_id)
```

## 7. 存储结构

```
sandboxes/
└── sandbox-{timestamp}/
    ├── state.json          # 沙箱状态（Sandbox 数据序列化）
    └── workdir/            # 工作目录（创建时生成）

config/
└── sandbox-policies/
    ├── default.json        # 默认策略
    └── {name}.json         # 自定义策略
```

## 8. 依赖

| 依赖 | 来源 | 说明 |
|---|---|---|
| L1-runtime/openclaw.adapter | 内部 L1 层 | 底层命令执行、进程管理 |
| utils.utils | 本组件内 | 文件/时间/JSON 工具 |

外部依赖仅 Python 标准库（`os`, `json`, `time`, `re`, `shutil`, `tempfile`, `dataclasses`）。

## 9. 测试

```bash
python3 -m pytest L2-infra/components/sandbox/tests/ -v
```

当前覆盖：
- **Smoke test**（2 个）：目录结构验证、Python 文件存在性

## 10. 设计约束

1. **依赖倒置**：通过 L1 适配器抽象解耦具体运行时，不直接调用 Docker/API
2. **白名单优先**：命令和路径必须显式授权，默认拒绝
3. **危险命令硬编码**：全局黑名单不可被策略覆盖
4. **状态同步**：内存状态与磁盘 `state.json` 保持一致
5. **通配符匹配**：路径支持 `*` 通配符（转换为正则 `.*`）

## 11. 已知限制

- 实际挂载操作由底层适配器实现，Manager 只记录挂载配置
- `check_command` 中策略名称获取为简化实现（从命令首参数推断），生产使用建议从沙箱对象获取
- 当前无并发安全锁，多线程同时操作同一沙箱可能竞态
- 测试覆盖较薄（仅 smoke test），缺少策略检查、生命周期等核心逻辑单测

## 12. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-11 | 基于实际代码重写设计文档 |
