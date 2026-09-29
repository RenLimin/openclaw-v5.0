# model-scheduling 修复时间线

> 本文档记录 model-scheduling 模块从开发到每次修复的完整历史。
> 目的：避免重复踩坑，追溯设计决策，作为后续维护参考。

---

## 状态概览

| 指标 | 值 |
|------|-----|
| 首次开发 | 2026-09-07 |
| 总 commit 数 | 20+ |
| 修复次数 | 6 次 major fix |
| 当前状态 | ✅ 稳定运行 |

---

## 2026-09-29: 健康探测内化 + 运行时失败反馈（修复 15h DNS 故障盲区）

**背景**: 9-28 20:09 ~ 9-29 11:04 公司内网 DNS 解析 api.deepseek.com 连续故障约 15 小时，
4 个模型全部不可用，cron 连续报错 3-5 次。根因不是 DNS 本身，而是 model-scheduling 的
健康检查盲区：`health_check.py` 只检查 proxy 进程存活，不检测 provider 真实可用性。

**变更**:
1. **启动探活 `startup_probe()`**（内化到 proxy.py，替代独立 cron）
   - 启动时并发检测所有 provider：DNS 解析 → TCP 连接 → /models 端点
   - 结果写 usage.json：healthy / degraded / unreachable
   - 全部不可用 → degraded 模式启动（路由层跳过），`--skip-probe` 可跳过
2. **运行时失败反馈**（零额外网络请求）
   - 真实请求连续 3 次网络失败(502/504) → 标记 unreachable（1h TTL 自愈）
   - 成功后重置计数 — 复用现有 TTL 机制，无新增后台任务
3. **删除独立 cron `Provider 健康探测`(2a027791)** — 逻辑内化到 proxy
4. **文档五件套同步**: PRD / DESIGN / DESIGN-DETAIL / VERIFICATION / OPERATIONS

**验证**:
- 探活实测 3/3 healthy（coding-plan / longCat / deepseek 全 200）
- 语法检查通过，LaunchAgent 重启后自动探活正常
- 删除 cron 后不再有独立健康探测任务（零冗余）

---

## 时间线

### 2026-09-07：首次开发
- **feat**: 添加用量统计（usage stats）
- **feat**: 预算告警检查（budget alert check）
- **设计**: 本地 proxy + OpenAI-compatible API

### 2026-09-11 ~ 09-13：架构集成
- **chore**: 清理 .deprecated / .bak 残留
- **docs**: 架构文档 v3.9 L0/L1/L2 对齐
- **test**: session-recovery / DMF 测试补全
- **refactor**: finance engine split + 输出格式修复

### 2026-09-14：首次配置管理
- **chore**: 同步模型配置时间戳
- **fix**: 修正 log gitignore 路径，移除已跟踪的日志文件
- **问题**: 日志文件被误跟踪到 git

### 2026-09-15：核心功能集中开发（7 个 commit）

| 日期 | 类型 | 内容 | 问题 |
|------|------|------|------|
| 09-15 | feat | 添加 longCat + deepseek 到 fallback 链 | 设计多 provider 容灾 |
| 09-15 | fix | 移除 routing 中死模型引用 + 启用 longCat provider | 旧模型 ID 残留导致 404 |
| 09-15 | feat | 添加 reference integrity check to sync_models.py | 模型同步时引用完整性 |
| 09-15 | feat | 跨 provider fallback（primary unreachable 时） | 单点故障 |
| 09-15 | feat | 自动 cross-provider fallback（primary unavailable） | 自动切换 |
| 09-15 | fix | 补全 `_forward_once` 实现 | 流式传输不完整 |
| 09-15 | 架构 | 资产归位 + Agent 精简 + Cron 合并 | 架构整洁化 |

**⚠️ 同日的教训**：一天内 7 个 commit 导致路由配置混乱，
`models.yaml` 的 priority 字段被遗漏，为后续 fallback 绕弯路埋下隐患。

### 2026-09-16：注册为 OpenClaw 正式 provider
- **feat**: 注册为 OpenClaw custom provider + 分层设计
- **问题背景**: Gateway 不认识 `model-scheduling/auto`，用户切过去报 billing error
- **方案**: 注册为 baseUrl→127.0.0.1:3000 的伪 provider，一个伪 model "auto"

### 2026-09-26：KeepAlive 自动恢复
- **问题**: proxy 进程被杀后无法自动恢复
- **方案**: LaunchAgent KeepAlive + 8 秒自动重启

### 2026-09-27：路由首次修复（未彻底）
- **问题**: 健康探测显示 longCat provider baseUrl 不一致
- **修复**: 统一为 `https://api.longcat.chat/openclaw/v1`
- **遗漏**: 未检查 routing.yaml 的模型优先级

### 2026-09-28（今天）：彻底修复 ★★★

#### 问题 A：月份格式重复（BDMS）
- **现象**: 月份列表显示 "2026年06月" 和 "2026年-06月" 两条
- **根因**: E2E 测试以 YYYY-MM 格式写入 report_month 表，与正规 YYYYMM 并存
- **修复**: `normalize_month()` 全链路 6 处 + 脏数据清理（22058 行）

#### 问题 B：月份输入框无法输入新月份（BDMS）
- **现象**: 交付月报页月份是纯 select，只能选已有月份
- **根因**: 误把 input 改成 select 但没考虑"生成新月份"场景
- **修复**: 改回 input + datalist（可输入可选）

#### 问题 C：model-scheduling 每次请求延迟 5-10 秒 ★★★
- **现象**: 每次请求先试 code-preview → 400 → fallback deepseek → 402 → 成功
- **根因（3 个叠加 bug）**:
  1. `models.yaml` 缺 priority 字段 → select_model 兜底排序不稳定
  2. `coding` 任务缺 `requires_input_types` → 纯文本模型混入图片链路
  3. `select_model` 兜底逻辑用不稳定的 dict 排序
- **修复**:
  1. models.yaml: 加 priority（code-preview=10, 2-0-lite=20, 2-1-turbo=30）
  2. routing.yaml: coding 加 `requires_input_types: [text]`
  3. proxy.py: select_model 改稳定排序 `(priority, id)`

---

## 经验教训

### 1. 路由配置必须有 priority
没有 priority 的路由 = 随机路由。`models.yaml` 必须给每个模型声明 priority。

### 2. 任务路由必须声明能力过滤
`requires_input_types` 不是可选的——没有它，纯文本模型会被选到图片任务里。

### 3. 兜底逻辑必须稳定排序
Python dict 遍历顺序不保证稳定，排序 key 必须包含唯一字段（如 id）。

### 4. 一天不要超过 3 个功能 commit
09-15 一天 7 个 commit 导致路由配置混乱，priority 字段被遗漏。

### 5. 修复必须全链路
只修后端不修前端 = 新 bug。只修路由不修 priority = 假修复。

### 6. E2E 测试数据也会成为脏数据
测试写入的数据如果不清理，会污染生产列表。测试后必须 review 清理。

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `config/models.yaml` | 模型定义 + priority |
| `config/routing.yaml` | 任务→模型路由规则 |
| `config/providers.yaml` | provider 配置 |
| `scripts/proxy.py` | 代理服务 + fallback 逻辑 |
| `scripts/health_check.py` | 健康探测 |
| `scripts/sync_models.py` | 模型同步 |
| `scripts/register_provider.py` | OpenClaw provider 注册 |

### 2026-09-28（续）：P1 + P2 彻底修复 ★★★

**Rex 反馈**：model-scheduling 完全无响应，违背设计初衷。如果做不到就删除。
**Rex 要求**：避免补丁摞补丁，直接重构。满足 OpenClaw 官方文档要求。

#### 问题 P1：手动指定模型被路由覆盖
- **现象**：`model: "longCat/LongCat-2.0"` 被路由到 `doubao-seed-2-0-lite`
- **根因**：`_handle_chat` 完全忽略 `request.model`
- **修复**：加手动路由优先逻辑（检查 request.model 是否非 auto）

#### 问题 P2：longCat API key 获取失败（真正根因）
- **现象**：`get_api_key('longCat')` 返回空，尽管 `~/.zshenv` 有 `LONGCAT_API_KEY`
- **根因（最终确认）**：
  1. `providers.yaml` 的 key 是 `"longcat"`（小写c），`models.yaml` 的 provider 是 `"longCat"`（大写C）
  2. `get_api_key` 的 `env_keys` 字典 key 是 `"longcat"`，但传入的 `provider_id` 是 `"longCat"`
  3. `env_keys.get("longCat")` 返回空列表 → key 获取失败
- **修复**：
  1. `providers.yaml`: `"longcat"` → `"longCat"`（统一大小写）
  2. `get_api_key`: provider 查找改为大小写不敏感
  3. `LaunchAgent plist`: 改用 `bash -c "source ~/.zshenv && exec python3 ..."`

#### 经验教训（新增）
8. **配置 key 大小写必须全链路一致**：models.yaml 的 provider 字段、providers.yaml 的 key、get_api_key 的 env_keys 字典 key，三者必须大小写一致或做大小写不敏感匹配。
9. **nohup 启动的进程不继承 shell 环境**：API key 等敏感配置应通过 LaunchAgent EnvironmentVariables 或启动脚本显式注入。
10. **调试时直接检查进程环境**：`ps -p PID -E` 可以看到进程的实际环境变量，比猜测高效得多。

### 2026-09-28（续2）：上下文感知路由 ★★★

**问题**：Rex 切换 model-scheduling 后报 "billing error"，实际根因是大上下文崩溃被误报。
**根因链**：362k 会话 → doubao(262k) 400 超限 → deepseek 402 → 链耗尽返回 402 → Gateway 误判 billing。
**修复**：estimate_tokens + 上下文感知路由 + 413 诊断错误 + openclaw.json ctx 诚实声明(262k)。
**教训**：E2E 测试必须包含大上下文场景，curl 小请求测不出真实会话行为。

## 2026-09-28 15:15 — ctx 校准 + compaction 兜底链 + 会话水位预警

### 修复（2026-09-28 /compact 失败复盘的加固）

1. **deepseek-v4-flash-ga-260731 ctx 校准**: 131072 → 1048576
   - 实测证据: 850,093 prompt tokens → HTTP 200, 正常回复 OK
   - openclaw.json + models.yaml 双处同步
2. **main agent fallback 链补强**: 首位插入 `coding-plan/deepseek-v4-flash-ga-260731`（1M ctx）
   - 之前链 = auto(262k) → 2-1-turbo(262k) → code-preview(262k)，全是小 ctx，大会话溢出时无人能接
3. **compaction.model 显式指定移除**（longcat/LongCat-2.0 → null）
   - 显式指定 = 放弃 fallback 链（源码 compact-gStBcHDe.js + 官方 compaction.md:127）
   - 现在压缩用会话模型起步，失败时继承 fallback 链（首位 1M deepseek 兜底）
   - 修复 EXP-20260821-003 的设计当初为防小模型压缩死锁，现改为"会话模型 + 1M 兜底"双保险
4. **maxActiveTranscriptBytes**: 20mb → 6mb（约 300k tokens 触发，1M ctx 的 30%）
5. **新增会话上下文水位预警 cron**（每 30 分钟）
   - 脚本: `L2-infra/scripts/maintenance/session_ctx_watch.py`
   - WARN ≥70% / CRIT ≥85% → wecom:1313 通知；OK 静默
   - 防止再次发生"会话膨胀到超过所有模型 ctx → /compact 死局 → /reset"事故

### 教训

- ctx 声明必须实测校准，不能抄默认值（deepseek-v4-flash-ga 声明 131k 实际 1M）
- `openclaw agent --local` 测试必须指定 `--session-key`，否则污染主会话（今日实测踩坑）
