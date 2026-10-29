# workspace-temp-cleanup — 概要设计 (DESIGN-OUTLINE)

> 组件：workspace-temp-cleanup (L2) · 编码：INFRA-CLN-001
> 版本：v1.0 · 日期：2026-10-29 · 状态：📐 待审核
> 关联：架构文档 v5.7 §7.4.5 · PRD-v1.0

## 1. 定位

L2 基础设施层运维治理组件：**只删"已标记"的临时资产，未标记一律不碰**。与 会话生命周期管理（清会话）、配置管理（治理封装）同级，不重新实现运行时能力。

## 2. 架构设计

### 2.1 整体架构

```
                 ┌─────────────────────────────┐
  写方(AI/脚本)  │   .openclaw-temp.json 登记    │  ← 唯一写入口（组件只读）
                 └──────────────┬──────────────┘
                                │ 解析
                 ┌──────────────▼──────────────┐
                 │  workspace-temp-cleanup      │
                 │  ┌───────────────────────┐  │
                 │  │ F1 临时区识别器        │  │  目录约定 + 登记清单 → 候选集
                 │  ├───────────────────────┤  │
                 │  │ F3 过期判定器          │  │  created+ttl_days vs 今天
                 │  ├───────────────────────┤  │
                 │  │ F4 dry-run 报告        │  │  默认：报告不删
                 │  ├───────────────────────┤  │
                 │  │ F5 trash 执行器        │  │  --yes + /usr/bin/trash
                 │  └───────────────────────┘  │
                 └──────────────┬──────────────┘
                                │ 实删动作
                 ┌──────────────▼──────────────┐
                 │  cron isolated（每日02:00）  │  → announce WeCom
                 └─────────────────────────────┘
```

### 2.2 模块划分

| 模块 | 职责 | 关键实现 |
|---|---|---|
| 识别器 (scanner) | 收集候选路径：登记清单 entries + 目录命名约定匹配 | 递归 `glob`，跳过 `.git`；符号链接不跟随 |
| 判定器 (judger) | 每个候选算过期：`age = today - max(mtime, created)`，`expired = age > ttl_days` | kind 默认 TTL：`intermediate=7` / `ledger=30`；entry 可覆盖 |
| 报告器 (reporter) | dry-run：表格输出 路径/大小/过期天数/动作 | 默认模式；stdout + 可选 jsonl |
| 执行器 (executor) | `--yes` 实删；`/usr/bin/trash`；收集删除清单 | 前置自检 trash 存在，缺则 abort |
| 通知器 (notifier) | 实删后 announce WeCom | 复用 observability 通知口径；无实删则静默 |
| CLI 入口 | `tempcleanctl`（§7.4.4 命名） | `dry-run` / `clean` / `list` / `verify` 子命令 |

### 2.3 接口契约

| 接口 | 输入 | 输出 |
|---|---|---|
| `tempcleanctl dry-run` | 无（读登记+约定） | 报告表 + exit 0；有候选过期 exit 2（可 grep） |
| `tempcleanctl clean` | `--yes`（必须显式） | 实删清单 + trash 结果；无 --yes 拒绝 |
| `tempcleanctl list` | 可选 `--json` | 全部临时资产及其 TTL/过期状态 |
| `tempcleanctl verify` | 无 | 自检：trash 可用性、登记 JSON 合法性、gitignore 覆盖 |

### 2.4 数据流

```
读 .openclaw-temp.json + 扫目录约定
  → 候选集（path/kind/ttl/created/mtime/size）
  → 判定过期集
  → dry-run 报告（默认） | clean --yes → trash → 通知
```

### 2.5 依赖关系

- 依赖：`/usr/bin/trash`（macOS）、Python 3 stdlib（argparse/json/glob/pathlib）
- 被依赖：无（独立 CLI + cron）
- 复用：不依赖 L1 抽象（纯运维脚本，与 session_cleanup 同级）

## 3. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 删除方式 | 只 trash，禁 rm | 可恢复，符合 AGENTS.md Red Lines |
| 默认行为 | dry-run | 防误删；实删需显式 --yes |
| 登记唯一写入口 | AI 写方登记 | 写方最清楚 TTL；组件只读防竞态 |
| cron 模式 | isolated | 与现有清理任务一致，不污染主会话 |
| 安全兜底 | 未标记不删 | 即使 TTL 过期、目录很旧，未登记/未命名约定也不删 |

## 4. 待确认点（送审）

1. cron 时间：每日 02:00 与会话清理（session_cleanup）同一窗口，还是错峰（如 03:30）？
2. 通知口径：实删动作 announce WeCom 是否必要？（默认 yes，沿用巡检口径）
3. TTL 默认值：中间数据 7 天 / 台账 30 天 —— 是否调整？
4. 是否需要 `verify` 子命令纳入 cron 定期自检？（建议每 30 分钟随错误扫描附带）
