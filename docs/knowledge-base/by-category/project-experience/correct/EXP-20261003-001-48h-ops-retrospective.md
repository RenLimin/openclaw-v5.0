---
id: EXP-20261003-001
title: 48小时运维复盘 — 僵尸任务/Cron污染/DB损坏/凭据丢失
date: 2026-10-04
tags: [troubleshooting, cron, subagent, database, gateway, backup]
layers: [L1, L2]
stage: manage
status: active
---

# 48小时系统运维全复盘 — 僵尸任务、Cron污染、DB损坏与凭据丢失

> 2026-10-03 ~ 2026-10-04 期间发生的 6 类典型问题及其根治方法。每条均来自实测踩坑，非理论推导。

---

## 问题 1：僵尸 subagent settle 死循环 ★★★

### 现象
UI 每 6 分钟弹出 "subagent completion owner changed before settlement"，累计 2390+ 次。

### 根因
`subagent_runs` 表中 9-19 创建的 `f2926a63`（bdms-dr-rev 任务），子代理早已失败结束，但 `requesterSettleWake.status = "dispatching"` 持续重试通知主会话。

### 为什么重启无效
状态持久化在 sqlite 里，重启后从 DB 恢复又继续重试。

### 为什么直接删 DB 没用
Gateway 内存有缓存，会写回 DB。

### 正确方法
```
停 Gateway → 删 subagent_runs 记录 → 启 Gateway
```
用 nohup 后台脚本执行（避免当前会话随 Gateway 一起挂）。

### 验证
删除后 5 分钟 0 错误，DB 记录数 0。

---

## 问题 2：Cron job 跑 main session 污染 UI ★★

### 现象
水位预警 cron 每 30 分钟跑一次，失败后在 main session UI 留可见错误消息。

### 根因
`sessionTarget: "current"` → 跑在 main session。

### 修复
所有 cron job 必须 `sessionTarget: "isolated"`：
- 水位预警 `2894d5e2`
- 错误扫描 `20c21c0c`
- 会话生命周期清理 `8f1df502`

### 教训
**任何 cron job 不得使用 `sessionTarget: "current"`**，失败消息会污染用户会话。

---

## 问题 3：WeCom target 格式错误 ★★

### 现象
`errcode 93006: invalid chatid`，所有 cron 告警无法投递。

### 根因
target 写成 `user:1313` 或 `wecom:user:1313`。

### 正确格式
- ❌ `wecom:user:1313` / `user:1313`
- ✅ `1313`（直接写 userId，无前缀）

来源：`memory/2026-09-08.md`。

---

## 问题 4：DB 直接编辑被 Gateway 写回 ★★

### 现象
Gateway 运行中直接 `sqlite3` 删除 `subagent_runs` 记录，Gateway 内存缓存写回 DB，记录又回来了。

### 根因
Gateway 对 `subagent_runs` 表有内存缓存，WAL 模式并发写无法绕过。

### 正确方法
必须停 Gateway 后再编辑 DB。对 `task_runs` 和 `delivery_queue_entries` 表，WAL 模式并发写可以生效（实测成功），但 `subagent_runs` 不行。

### 教训
**不同表的缓存策略不同**：
- `subagent_runs`：有内存缓存，必须停 Gateway
- `task_runs` / `delivery_queue_entries`：WAL 并发写可生效

---

## 问题 5：DB 重制后凭据全丢失 ★★★

### 现象
DB 文件损坏重建后，`secret_store_entries` 表空了，4 个凭据全部 degraded：
- CODING_PLAN_API_KEY
- DEEPSEEK_API_KEY
- LONGCAT_API_KEY
- TAVILY_API_KEY

### 根因
凭据存在 SQLite 里，不在文件系统。DB 重制 = 凭据全丢。

### 恢复方法
1. 从备份 DB 导出：`SELECT name, value FROM secret_store_entries`
2. 写入 `.env` 文件
3. `openclaw secrets store import --from /tmp/restore_secrets.env --yes`
4. `openclaw secrets reload`

### 教训
**凭据备份必须独立于 DB 备份**。建议：
- 定期 `openclaw secrets store list` 确认凭据完整
- 凭据原始值保存在安全位置（如密码管理器），不依赖 DB 恢复

---

## 问题 6：AGENTS.md 超限被截断 ★

### 现象
workspace bootstrap 报 "AGENTS.md is 18004 chars (limit 15000); truncating"。

### 根因
AGENTS.md 累积到 24679 字符，超过 15000 限制。

### 修复
精简到 11175 字符：删除冗余说明、合并重复规则、移除过时的示例代码。

### 教训
**AGENTS.md 需要定期瘦身**。规则：每新增一条规则，检查总量是否接近 15000。

---

## 时间线

| 时间 | 事件 |
|---|---|
| 10-02 21:14 | fin-l4 测试修复、cron 超时修复、git 工作树清理 |
| 10-03 10:39 | Rex 报告 UI 报错刷屏 |
| 10-03 10:39-11:10 | 排查发现水位预警 cron 跑 main session + 僵尸 subagent |
| 10-03 11:10-13:05 | 修复 3 个 cron（改 isolated + 超时 + fallback） |
| 10-03 13:05-20:50 | 尝试清理僵尸 subagent（多次被 Gateway 重启打断） |
| 10-03 20:50-21:00 | 用 nohup 后台脚本成功清理僵尸 subagent |
| 10-03 21:16-21:43 | 清理 6 个 warning（lost tasks + delivery_failed + dead letter） |
| 10-03 22:11-22:31 | 系统全量检测（6 组件 1201 tests 全绿） |
| 10-03 22:34 | DB 清理脚本执行（停 Gateway 后记录被写回） |
| 10-04 16:51 | Rex 报告 Gateway 无法启动（实际正常，但 WeCom 渠道崩溃） |
| 10-04 17:27 | 升级微信插件 v2.4.6→v2.4.9 |
| 10-04 17:27-17:44 | 恢复 4 个凭据 + AGENTS.md 瘦身 |

---

## 核心教训汇总

1. **cron job 必须 isolated** — 永远不要 sessionTarget=current
2. **subagent settle 死循环** — 必须停 Gateway 删 DB，重启无效
3. **不同表缓存策略不同** — subagent_runs 必须停 Gateway，task_runs 可 WAL 并发写
4. **凭据不依赖 DB 备份** — 独立备份或保存原始值
5. **AGENTS.md 定期瘦身** — 每新增规则检查总量
6. **WeCom target 格式** — 直接 userId，无 user: 前缀
7. **npm 安装可能挂住** — 需要代理时设 https_proxy/http_proxy

---

Source: memory/2026-10-03.md, memory/2026-10-02-2114.md
