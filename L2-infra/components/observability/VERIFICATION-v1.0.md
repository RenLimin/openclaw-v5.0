# observability — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- 日志收集
- 指标追踪
- 健康监控

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 日志收集 | 应用日志 | 结构化日志 |
| TC02 | 指标追踪 | 运行时指标 | 指标数据 |
| TC03 | 健康监控 | 组件状态 | 健康报告 |

## 实测结果

- agent_observer: ✅
- logging: ✅
- tracing: ✅

---

# Channel 主动恢复（v1.0 · 2026-11-17）

## 测试方案

| 层 | 内容 | 命令 |
|---|---|---|
| 单元 | 环境注入 / 事件解析 / 四态判定 / 节流 / 端口解析 | `pytest tests/test_channel_recovery.py` |
| 黄金回放 | 真实 gateway.log 回放 2026-11-17 故障窗口（7 检查点） | `pytest tests/test_golden_replay.py` |
| 冒烟 | 组件结构 | `pytest tests/` |
| 人工 | `--check` 在线只读；观察一个 5min tick | 见 OPERATIONS |

## 实测结果（2026-11-17）

| 项 | 结果 |
|---|---|
| `pytest tests/` | ✅ 39 passed |
| 黄金回放 7 检查点 | ✅ 全部吻合 |
| launchd 裸环境（`env -i`）执行 watchdog | ✅ rc=0，判定 up |
| `channels.stop`→`channels.start` 受控实测 | ✅ 3s 内 `Authentication successful` |
| `--check` 在线判定 | ✅ up |

**黄金基线（回归用）**：08:11:31 断连 → 09:15:09 恢复。期望：
08:15 `down-unstable`、08:25/09:10 `down`、09:20 起 `up`、10:29 秒断已自愈 `up`。
