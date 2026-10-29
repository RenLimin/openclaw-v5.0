# workspace-temp-cleanup — 详细设计 (DESIGN-DETAIL)

> 组件：workspace-temp-cleanup (L2) · 编码：INFRA-CLN-001
> 模块：clean-engine · 版本：v1.0 · 日期：2026-10-29
> 前置：PRD / DESIGN-OUTLINE v1.0 已通过（决策：cron 03:30 · 实删 announce · TTL 7/30 · verify 随扫描）

## 1. 数据模型

### 1.1 `.openclaw-temp.json` Schema

```json
{
  "version": 1,
  "entries": [
    {
      "path": "analysis_output/",
      "kind": "ledger",
      "ttl_days": 30,
      "created": "2026-10-29",
      "source_task": "task-...",
      "note": "optional"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 缺省 | 说明 |
|---|---|---|---|---|
| path | string | ✅ | — | 相对 workspace 根；目录以 `/` 结尾 |
| kind | enum | ❌ | `intermediate` | `intermediate`(7d) / `ledger`(30d) |
| ttl_days | int | ❌ | kind 默认 | 覆盖默认 TTL |
| created | date(YYYY-MM-DD) | ❌ | 取 path mtime | 登记日期 |
| source_task | string | ❌ | — | 溯源任务 |
| note | string | ❌ | — | |

非法 JSON / 缺 version → `verify` 报错，clean 拒绝执行（fail-closed）。

### 1.2 内部候选记录 (Candidate)

```python
@dataclass
class Candidate:
    path: Path            # 绝对路径
    kind: str
    ttl_days: int
    created: date         # 登记日期
    mtime: date           # 文件系统最近修改
    size_bytes: int
    source: str           # "registry" | "convention"
    expired: bool
    age_days: int
```

## 2. 核心算法

### 2.1 候选收集

```
registry: 解析 .openclaw-temp.json → 每个 entry
convention: glob 匹配（相对 workspace 根，跳过 .git/ node_modules/，不跟随 symlink）
    tmp/ scratch/ analysis_output/ scripts/tmp/
    **/*-tmp/  **/*.tmp
去重：同一路径 registry 优先（带显式 TTL），convention 不覆盖
```

### 2.2 过期判定

```python
effective_origin = max(created, mtime)      # mtime 比 created 新则以 mtime 为准，保护近期写入
age_days = (today - effective_origin).days
expired = age_days > ttl_days              # 严格大于：TTL 当天不删，次日删
```

目录：以目录内**最新 mtime**（递归，取 max）作为目录 mtime。

### 2.3 大小计算

目录递归求和（跳过 symlink）；> 阈值时报告用 KB/MB 格式化。

## 3. CLI 契约

命令：`tempcleanctl`（入口 `scripts/tempcleanctl.py`，Python 3 stdlib）

### 3.1 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功，无过期项 / 删除成功 |
| 2 | dry-run/list 发现过期项（供 shell 管道判定） |
| 3 | verify 失败（trash 缺失 / 登记非法 / gitignore 缺覆盖） |
| 1 | 其他错误 |

### 3.2 子命令

| 子命令 | 参数 | 行为 |
|---|---|---|
| `dry-run` | `--json` | 报告全部候选，标注 expired；默认模式；有过期 exit 2 |
| `clean` | `--yes` | 无 --yes 拒绝（exit 1 + 提示）；有则 trash 过期项，输出删除清单 |
| `list` | `--json` | 列全部临时资产 TTL/状态，不判删除语义 |
| `verify` | — | trash 存在性 + 登记 JSON 合法 + gitignore 覆盖；失败 exit 3 |

### 3.3 全局参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--root` | 脚本推导的 workspace 根（.git 所在） | 指定 workspace |
| `--registry` | `<root>/.openclaw-temp.json` | 登记文件路径 |

## 4. 删除执行

```
前置：verify trash 可用（shutil.which("trash") 或 /usr/bin/trash）
逐候选：trash <path>
  - 记录成功/失败；单项失败不中断，最终汇总
  - 实删清单写 stdout（cron 捕获）；有任意成功删除 → 通知
绝无 rm / shutil.rmtree / os.remove（代码与测试双重禁止）
```

## 5. 安全约束（fail-closed）

- 未在 registry 且不匹配 convention → 永不出现在候选集
- trash 不可用 → abort，**禁止 fallback 任何永久删除**
- registry 非法 → clean abort
- 候选路径必须在 `--root` 之内（防 `../` 越界）
- symlink 不跟随、不删除其目标

## 6. cron 集成

- 时间：每日 **03:30**（与会话清理 02:00 错峰）
- 模式：`isolated`；命令 `tempcleanctl clean --yes`
- 实删成功 → announce WeCom（删除清单摘要）；无删除 → 静默
- `verify` 随错误扫描（每 30m）附带，失败计入扫描报告

## 7. 目录结构

```
L2-infra/components/workspace-temp-cleanup/
  PRD-v1.0.md
  DESIGN-OUTLINE-v1.0.md
  DESIGN-DETAIL-CLEAN-ENGINE-v1.0.md
  VERIFICATION-v1.0.md
  OPERATIONS-v1.0.md
  IMPLEMENTATION-PLAN-v1.0.md
  scripts/tempcleanctl.py
  tests/test_clean_engine.py
```
