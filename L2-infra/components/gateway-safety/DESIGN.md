# gateway-safety — 网关安全（安全重启 / 预检守卫 / 挂起补偿）组件设计

> 层级：L2 基础设施层 · 组件类：网关安全
> 状态：✅ 已建设（2026-10-27 建立，2026-11-04 增挂起补偿；2026-11-20 补写本设计）
> 关联规范：AGENTS.md §Gateway 重启安全铁律 ★★★、`hooks/compaction-guard/HOOK.md`、
> `docs/architecture/DESIGN-DETAIL-reliability-auto-recovery-v1.0.md` §P1-a
> 能力登记：`capability-registry/registry.yaml` id=`gateway-safety`
> 事故驱动：2026-10-27 compaction 180s 超时 + 扫描器重复计数 5 次并裸调 restart 自杀式重启

## 1. 定位

为 OpenClaw Gateway 的**主动重启**提供一道「先预检、再重启」的安全闸门，
避免在关键工作（in-flight 压缩）进行中重启导致工作中断 / 引擎 wedge，
并在闸门临时硬阻断时把这次「被安全推迟的重启」挂起为待补偿状态，
待闸门放行且故障仍在时**恰好补一次**重启，绝不连续重启。

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 网关安全（安全重启 + 预检守卫 + 挂起补偿） |
| 状态 | ✅ 已建设（2026-10-27） |
| 权威入口 | `scripts/safe_restart.sh`、`scripts/pre_restart_guard.py` |
| 状态文件 | `~/.openclaw/state/pending-recovery.json`（运行态，不入库） |
| 依赖状态源 | `~/.openclaw/state/compaction-state.json`（由 `compaction-guard` hook 维护） |
| 关联规范 | AGENTS.md §Gateway 重启安全铁律、`hooks/compaction-guard/HOOK.md`、error_handler DESIGN §4.5 |

**非目标**：不拦截 config-patch 触发的进程内自动重启（OpenClaw 无外部否决点）；
不修改系统睡眠设置；不重写 gateway 内置 thaw / health-monitor。

## 2. 设计约束（来自代码实证）

1. **硬阻断优先于可用性**：pre-restart guard 检测到新鲜 in-flight 压缩 → `rc=1` 硬阻断；
   `safe_restart.sh` **永不**用 `--force` 覆盖 `rc=1`（只有 `rc=2` 不确定才允许 `--force` 覆盖）。
2. **fail-closed**：guard 自身错误 / 无法读取压缩状态 → 非 `--strict` 时 `rc=2`（不确定），
   `--strict` 时按阻断处理（`rc=1`）；默认不放行「不确定」状态。
3. **stale 标记不无限阻断**：压缩 `running` 标记超过 `FRESH_WINDOW_SECONDS=360s`（6 分钟）
   视为 stale（崩溃 / 硬杀），不再阻断重启；与 hook 的 `FRESH_MS` 保持同步。
4. **补偿有界 + TTL 兜底**：同一 `evidence_hash` 只挂一条 pending；最多补偿 **1** 次
   （`MAX_COMPENSATIONS=1`）；`guard_rc != 0`（仍阻断或不确定）一律不补；
   pending 默认 `DEFAULT_TTL_MIN=30` 分钟，超 TTL 不再自动补，转人工。
5. **写状态原子化**：`recovery_pending.save()` 先写 `.tmp` 再 `os.replace`，避免半截文件。
6. **运行态与仓库态分离**：pending 状态在 `STATE_DIR = ~/.openclaw/state`
   （`PENDING_FILE = STATE_DIR/pending-recovery.json`，未读环境变量），不入库、不入 git；
   `feedback.jsonl` 才是入库资产（分属 delivery-quality）。

## 3. 架构

```
                       ┌──────────────────────────────────────────────┐
   agent / 脚本发起重启 │  scripts/safe_restart.sh                       │
   （error_handler /    │  1) 解析 --force / --strict / 透传参数         │
    channel_recovery /  │  2) 跑 pre_restart_guard.py                    │
    人工）              │  3) 按 guard rc 决策                          │
                       │     rc=0 → exec openclaw gateway restart       │
                       │     rc=1 → 硬阻断，exit 1（--force 无效）      │
                       │     rc=2 → 不确定，exit 2（--force 才继续）    │
                       └───────────────┬──────────────────────────────┘
                                       │ 调用
                                       ▼
                       ┌──────────────────────────────────────────────┐
                       │  scripts/pre_restart_guard.py                  │
                       │  · check_inflight_compaction()                 │
                       │     读 compaction-state.json → live / stale   │
                       │  · check_recent_compaction_failure()           │
                       │     tail -n 2000 gateway.log（仅告警，不阻断） │
                       │  输出 JSON + rc(0/1/2)                         │
                       └───────────────┬──────────────────────────────┘
                                       │ 读
                                       ▼
                       ┌──────────────────────────────────────────────┐
                       │  ~/.openclaw/state/compaction-state.json       │
                       │  由 hooks/compaction-guard/handler.js 维护：   │
                       │   session:compact:before → running[sessionKey] │
                       │   session:compact:after  → done                │
                       │   gateway:pre-restart    → 仅观察，无法 cancel │
                       └──────────────────────────────────────────────┘

   挂起补偿链（P1-a，2026-11-04）：
   error_handler/scan_errors.py
      auto_fix()
        ├─ resolve_pending_restart(fixes)   ← 每轮开头
        │    读 recovery_pending.load()
        │    can_compensate(rec, guard_rc)?
        │      ├─ guard 放行 + 进程已健康 → clear（无需重启）
        │      ├─ guard 放行 + 故障仍在 + 未超次/TTL → 补 1 次 guarded 重启
        │      │    成功 → mark_compensated() + clear()
        │      │    失败 → 保留，由 TTL 兜底
        │      ├─ guard 仍阻断 → 静默等待
        │      └─ 超 TTL → 转人工 + clear()
        └─ 进程不健康分支重启 rc=1 → recovery_pending.upsert(reason, evidence)
   recovery_pending.py（本组件）
      状态：~/.openclaw/state/pending-recovery.json
      接口：load / upsert / save / clear / touch_guard_rc / is_expired /
            can_compensate / mark_compensated / evidence_hash
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 预检守卫 | `scripts/pre_restart_guard.py` | 判定「此刻重启是否安全」，输出 JSON + rc(0/1/2) |
| 安全重启包装 | `scripts/safe_restart.sh` | 先跑 guard，通过才 `exec openclaw gateway restart` |
| 挂起补偿状态 | `recovery_pending.py` | 被推迟重启的 pending 记录：去抖 / TTL / 有界补偿 |
| 编排调用方 | `L2-infra/scripts/error_handler/scan_errors.py` | `resolve_pending_restart` + `auto_fix` 中 upsert |
| 状态生产者 | `hooks/compaction-guard/handler.js`（组件外，依赖） | 维护 in-flight 压缩标记 |
| 测试 | `tests/test_recovery_pending.py` | pending 状态 7 用例（临时文件，不触真实 state） |

### 3.2 关键常量

| 常量 | 值 | 位置 | 说明 |
|---|---|---|---|
| `FRESH_WINDOW_SECONDS` | 360 | `pre_restart_guard.py` | 与 hook `FRESH_MS=6*60*1000` 同步 |
| `FRESH_MS` | 360000 | `hooks/compaction-guard/handler.js` | 同一窗口的另一侧实现 |
| `DEFAULT_TTL_MIN` | 30 | `recovery_pending.py` | pending 记录存活期 |
| `MAX_COMPENSATIONS` | 1 | `recovery_pending.py` | 同一证据最多补 1 次 |

## 4. 接口与用法（真实可执行）

### 4.1 安全重启（所有 agent / 脚本主动重启的强制入口）

```bash
bash L2-infra/components/gateway-safety/scripts/safe_restart.sh
bash L2-infra/components/gateway-safety/scripts/safe_restart.sh --strict
bash L2-infra/components/gateway-safety/scripts/safe_restart.sh --force   # 仅覆盖 rc=2
```

- 退出码：`0` 重启已发起；`1` guard 硬阻断；`2` guard 不确定（未加 `--force`）。
- **红线**：禁止裸调 `openclaw gateway restart`（会绕过 guard，见 AGENTS.md §Gateway 重启安全铁律）。

### 4.2 单独跑预检（改 config 前手动确认）

```bash
python3 L2-infra/components/gateway-safety/scripts/pre_restart_guard.py
python3 L2-infra/components/gateway-safety/scripts/pre_restart_guard.py --strict
```

输出 JSON 字段：`safe` / `inflight_compaction` / `stale_compaction_markers` /
`recent_compaction_failure` / `reason`（或 `error`）。

### 4.3 挂起补偿状态（供 error_handler 编排调用）

```bash
# 用临时路径演练，避免触碰真实 ~/.openclaw/state
python3 - <<'PY'
import sys, tempfile, os
sys.path.insert(0, "L2-infra/components/gateway-safety")
import recovery_pending as rp
path = os.path.join(tempfile.mkdtemp(), "pending.json")
rec, created = rp.upsert("llm_timeout", "ev line A", path=path)   # 同证据去重
print(rec["evidence_hash"], created)
print(rp.can_compensate(rp.load(path), guard_rc=0))
rp.mark_compensated(path=path); rp.clear(path=path)
PY
```

| 接口 | 语义 |
|---|---|
| `load(path=None)` | 读 pending；无 / 损坏返回 `None` |
| `save(data, path=None)` | 原子写（`.tmp` + `os.replace`） |
| `clear(path=None)` | 删除；幂等 |
| `upsert(reason, evidence_text, *, path=None, ttl_min=30)` | 挂起一条；同 `evidence_hash` 已存在返回 `(rec, False)` |
| `touch_guard_rc(rc, *, path=None)` | 记录最近一次 guard rc |
| `is_expired(record, *, now=None)` | 是否超 TTL |
| `can_compensate(record, guard_rc, *, now=None)` | 全条件：guard=0 + 未超次 + 未超 TTL |
| `mark_compensated(*, path=None)` | `compensations += 1`、`attempts += 1`、记 `compensated_at` |
| `evidence_hash(reason, evidence_text)` | sha1 前 16 位，稳定去抖 |

### 4.4 运行测试

```bash
python3 -m pytest L2-infra/components/gateway-safety/tests/ -v      # 7 passed
```

编排侧另有 `L2-infra/scripts/error_handler/tests/test_pending_recovery.py`
（stub guard/restart/health，验证 block→放行恰好补 1 次 / 持续 block 不计数 / TTL 转人工 / 去重）。

### 4.5 前置检索（防重复建设）

```bash
python3 L2-infra/components/config/capability-registry/capability_registry.py --query 重启
```

## 5. 与 AGENTS.md 红线的关系（不得绕过）

AGENTS.md §Gateway 重启安全铁律 ★★★（2026-10-27）规定：

- 所有 agent / 脚本主动发起的重启**必须**走 `safe_restart.sh`（先跑 pre-restart guard）；
- ❌ 禁止裸调 `openclaw gateway restart`——会绕过 guard、可能打断进行中的压缩 / 关键工作；
- 判据 `compaction-state.json` 由 `compaction-guard` hook 维护，`running` 超 6 分钟视为 stale；
- config-patch 触发的内部自动重启**拦不住**（无外部否决点），对策：改 config 前手动跑 guard，
  能用热加载就不要硬重启。

**本设计对该红线的落实**：红线是「规则」，本组件是「可执行机制」——
`safe_restart.sh` 是红线的唯一强制入口，`pre_restart_guard.py` 是判据实现，
`recovery_pending.py` 是红线的补集（阻断时不丢弃恢复意图，避免「一刀切阻断 = 永不恢复」）。

> 注：本仓另有 `L2-infra/components/gateway-safety/scripts/safe_restart.sh` 的调用方
> —— `L2-infra/scripts/error_handler/scan_errors.py`（`guarded_restart`）、
> `L2-infra/components/observability/scripts/channel_recovery.py`（全量兜底）。
> 新增调用方应复用本组件，不得自行拼 `openclaw gateway restart`。

## 6. 业界对标

| 实践 | 来源 | 本组件对应 |
|---|---|---|
| **Kubernetes Pod Disruption Budget（自愿中断预算）**：只约束「自愿中断」（drain / 升级），并承认无法保证非自愿故障；预算只提供「有计划的可用性下限」 | <https://kubernetes.io/docs/tasks/run-application/configure-pdb> | 本组件是「重启」这一自愿中断的闸门：只拦 in-flight 关键工作，不承诺拦住所有不可用；6 分钟 stale 窗口避免无限阻断 |
| **Google SRE：重启服务器用于「wedge 且无进展」场景**，并强调级联失效下要先卸载负载再重启 | <https://sre.google/sre-book/addressing-cascading-failures> | 重启是「进程 wedge / 不健康」的修复手段；guard 先确认没有 in-flight 工作再重启，避免把可恢复工作一并打断 |
| **Graceful shutdown / 两阶段排空**：SIGTERM 后先停止接收新工作，再在有限时间内排空在途请求，未完成的重新入队 | <https://cloud.google.com/blog/topics/developers-practitioners/graceful-shutdowns-cloud-run-deep-dive>、<https://github.com/llm-d/llm-d-async/issues/227> | `compaction-guard` 维护「在途」真值，guard 在排空完成前不放行——等价于「排空窗口内拒绝自愿中断」 |
| **OWASP Gen AI Security Project / shift-left**：安全控制前置到最早环节，而非运行期补救 | <https://genai.owasp.org/llm-top-10> | 重启前的预检闸门即「前置控制」；`rc=2` 不确定时 fail-closed，不把不确定性当放行 |

## 7. 设计取舍

| 决策 | 备选 | 理由 |
|---|---|---|
| 用文件状态而非内存/DB | SQLite / 内存标记 | 跨进程可见（agent / cron / hook 分属不同进程）；crash 后可读；与 hook 已有 state 约定一致 |
| 挂起补偿最多 1 次 | 无限重试 / 多次补偿 | 避免「重启风暴」与级联失效；超限转人工 |
| `rc=1` 不可被 `--force` 覆盖 | 允许强制 | 硬阻断是安全底线；`--force` 只用于「不确定」 |
| guard 不能否决内部 config-patch 重启 | 试图拦截 | OpenClaw 无外部否决点；改为「改 config 前手动跑 guard + 优先热加载」的缓解 |
| 补偿状态不入 git | 入库 | 运行态数据，避免污染审计链；与 `feedback.jsonl` 的入库策略分离 |

## 8. 测试与验收

- `tests/test_recovery_pending.py`（7 用例，全绿）：
  缺失文件返回 `None`、upsert 创建与去重、clear 幂等、guard rc 门禁（1/2 不补、0 可补）、
  只补一次、TTL 过期阻断、损坏文件返回 `None`。
- `L2-infra/scripts/error_handler/tests/test_pending_recovery.py`（编排 6 用例）：
  临时 state 文件 + stub，不触真实 `~/.openclaw/state`。
- 实测：`python3 -m pytest L2-infra/components/gateway-safety/tests/ -q` → `7 passed`。

## 9. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 补 `pre_restart_guard.py` 独立单测（live/stale/告警分支） | 中 | 资产生命周期要求可执行验收 |
| `safe_restart.sh` 结构化 rc 输出（便于调用方解析） | 中 | 多调用方需要机器可读判据 |
| 与 `system-governor` / 审计打通（每次 guard 决策留痕） | 低 | Rex 拍板 |
| 覆盖更多在途工作类型（除压缩外的长任务标记） | 低 | 长任务打断事故再现 |

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-27 | 建立组件（`97b8f37`）：`pre_restart_guard.py` + `safe_restart.sh`；compaction timeout 180→300；扫描器重启改走 guard（此前裸调 restart 自杀式重启）；新增 `compaction-guard` hook 维护 in-flight 状态；AGENTS.md 增「Gateway 重启安全铁律」 |
| 2026-11-04 | 增挂起式安全重启补偿（`b3a6f63`，P1-a）：新增 `recovery_pending.py`（TTL 30min / 最多补 1 次 / evidence 去抖）；`scan_errors.resolve_pending_restart` 联动 |
| 2026-11-11 | `8d2bd3f` 修 `safe_restart.sh`：`set -u` 下空 `args` 数组导致 unbound variable（改 `${args[@]+"${args[@]}"}`） |
| 2026-11-20 | 补写根级 `DESIGN.md`：定位 / 设计约束 / 架构 / 接口 / 与 AGENTS.md 红线关系 / 业界对标 / 变更记录 |
