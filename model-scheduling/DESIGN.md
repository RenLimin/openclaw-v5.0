# L2 模型调度组件(model-scheduling) — 设计

> **状态**: 已上线(2026-08-24 创建, 2026-08-25 完善)
> **ADR**: ADR-011(Error Contract,分级依据)
> **层级**: L2 基础设施层
> **创建**: 2026-08-24

## 1. 问题定义

### 1.1 业务目标

建设综合模型/供应商调度系统,实现:
1. 模型/供应商自由单独配置(外部文件,不回写核心配置)
2. 已配置在 openclaw.json 中的模型自动同步
3. 用量/期限定期自动获取
4. 按任务类型智能选择最优模型(含网络稳定性、用量等因素)
5. 热更新(配置变更 ≤ 10 秒生效,无需重启)

### 1.2 核心约束

| 约束 | 说明 |
|---|---|
| **不频繁改核心配置** | openclaw.json 只在初始化时读取,运行时通过外部文件驱动 |
| **不影响系统运行** | 组件故障 = 降级到 OpenClaw 原生 fallback,不影响现有能力 |
| **变更前必须验证** | 任何写操作前 dry-run + 读回确认 |

### 1.3 业界参考

| 产品 | 核心能力 | 本组件借鉴 |
|---|---|---|
| **9router** | 3 级 fallback、RTK token 压缩(20-40%节省)、用量追踪 | 多级 fallback + token 压缩 |
| **OpenRouter** | Auto Router、provider 级 failover、30s 健康窗口 | 健康探测 + 自动切换 |
| **Portkey** | 规则引擎、缓存、详细可观测 | 路由规则 + 成本统计 |

## 2. 设计原则

1. **外部配置驱动**:所有状态存储在 `model-scheduling/config/` 下,不回写 openclaw.json
2. **只读核心配置**:通过 `openclaw config get` 读取,绝不 `patch`
3. **多级 fallback**:L1 优先 → L2 降级 → L3 保底
4. **任务感知路由**:编码/推理/研究/闲聊 → 不同模型策略
5. **故障隔离**:组件故障不影响 OpenClaw 运行
6. **热更新**:文件变更 → 自动重载(≤ 10 秒)

## 3. 架构

```
model-scheduling/
├── config/
│   ├── config.yaml           ← 系统配置(端口/热更新/日志/用量)
│   ├── providers.yaml        ← 供应商配置(baseUrl/apiType/auth)
│   ├── models.yaml           ← 模型注册表(10 个模型)
│   ├── routing.yaml          ← 路由规则(多级 fallback + 压缩)
│   ├── usage.json            ← 用量/健康(自动更新)
│   └── rollback_*.json       ← 回退文件(3 份)
├── scripts/
│   ├── proxy.py              ← 代理服务(:3000,任务路由 + 模型选择)
│   ├── config_watcher.py     ← 热更新监听(文件变更 → 自动重载)
│   ├── router.py             ← 路由引擎(任务分类 + 模型选择)
│   ├── sync_models.py        ← 模型同步(openclaw.json → models.yaml)
│   ├── fetch_usage.py        ← 用量获取(provider API)
│   └── health_check.py       ← 网络健康探测
├── LaunchAgent/
│   └── ai.openclaw.model-scheduling.plist  ← 自动启动
├── setup.sh                  ← 一次性初始化
├── setup_agents.sh           ← 注册专用 agent
├── DESIGN.md                 ← 本文件
└── README.md                 ← 使用指南
```

## 4. 数据流

### 4.1 初始化(一次性)

```
setup.sh → sync_models.py → 读取 openclaw.json → 生成 models.yaml
         → fetch_usage.py  → 调用 provider API  → 生成 usage.json
         → health_check.py → ping provider      → 更新 usage.json
```

### 4.2 定期(通过 cron 或手动)

| 任务 | 频率 | 脚本 |
|---|---|---|
| 模型同步 | 每周 | `sync_models.py` |
| 用量获取 | 每周 | `fetch_usage.py` |
| 健康探测 | 每小时 | `health_check.py` |

### 4.3 实时(每次任务)

```
任务消息 → proxy.py → 读 models.yaml + routing.yaml + usage.json
                   → 任务分类(coding/research/chat)
                   → 选择最优模型(按 fallback chain + 用量 + 健康)
                   → 调用对应 provider API
                   → 返回响应(带 model_scheduling 标记)
```

## 5. 路由策略

### 5.1 任务分类

| 类型 | 关键词 | 首选模型 | fallback chain |
|---|---|---|---|
| **coding** | 代码/函数/debug/git | ark-code-latest | ark-code → deepseek-v4-flash → doubao-lite |
| **reasoning** | 推理/架构/设计/分析 | deepseek-v4-flash | deepseek-v4 → glm-5.3 → ark-code |
| **research** | 搜索/研究/分析/比较 | doubao-seed-2.1-turbo | doubao-2.1 → ark-code → doubao-lite |
| **chat** | 日常/简单/状态 | doubao-seed-2.0-lite | doubao-lite → ark-code |

### 5.2 Token 压缩规则(参考 9router RTK)

| 规则 | 匹配 | 动作 |
|---|---|---|
| git_diff | `git diff` 输出 | > 200 行截断为 100 行 |
| grep_output | `grep/find/ls` 输出 | > 100 行截断为 50 行 |
| file_read | 文件读取 | > 500 行截断为 200 行 |

### 5.3 健康阈值

| 指标 | 警告 | 临界 |
|---|---|---|
| 延迟 | > 5s | > 15s |
| 错误率 | > 10% | > 30% |
| 冷却时间 | — | 60s |

## 6. 热更新机制

```python
# config_watcher.py — 监听文件变更
# 间隔: 10 秒
# 文件: providers.yaml / models.yaml / routing.yaml
# 变更 → 自动重载到内存 → 下次请求使用新配置
```

| 操作 | 文件 | 生效时间 |
|---|---|---|
| 新增/修改/禁用 provider | providers.yaml | ≤ 10 秒 |
| 新增/修改/禁用模型 | models.yaml | ≤ 10 秒 |
| 修改路由规则 | routing.yaml | ≤ 10 秒 |

## 7. 与 OpenClaw 核心配置的关系

| 交互 | 方向 | 频率 |
|---|---|---|
| `openclaw config get models` | 只读 | 每次同步时 |
| `openclaw config get agents.defaults.model` | 只读 | 初始化时 |
| `openclaw sessions patch model` | 运行时切换 | 按需(不写文件) |
| `openclaw cron payload.model` | 运行时切换 | 按需(不写文件) |

**绝不执行**: `openclaw config patch models.*` / `openclaw config set agents.defaults.*`

## 8. 自动启动

- **LaunchAgent**: `ai.openclaw.model-scheduling`
- **开机自启**: ✅
- **崩溃重启**: ✅ (KeepAlive)
- **日志**: `logs/proxy.stdout.log` + `logs/proxy.stderr.log`

## 9. 验证标准

- [x] 模型注册表与 openclaw.json 一致(10 个模型)
- [x] 路由引擎正确分类并选择模型
- [x] 健康探测正常返回延迟和状态
- [x] openclaw.json 未被修改(config diff 一致)
- [x] LaunchAgent 自动启动
- [x] 端到端测试通过(闲聊→doubao-lite, 编码→ark-code, 推理→deepseek)
- [x] 热更新机制工作正常

## 10. 回退方案

| 变更 | 回退文件 | 命令 |
|---|---|---|
| provider 注册 | `config/rollback_provider.json` | `openclaw config patch --file ...` |
| main agent fallback | `config/rollback_main_agent.json` | `openclaw config patch --file ...` |
| 默认模型 fallback | `config/rollback_defaults.json` | `openclaw config patch --file ...` |
| 代理服务 | LaunchAgent 停用 | `launchctl unload ...` |

## 11. 已知限制

- 火山方舟用量 API 不可用(无公开 API,需控制台查看)
- coding-plan /models 端点需要 Bearer token(已在 proxy.py 中实现)
- Provider Plugin(TS)未实现(当前使用 provider baseUrl 方案,功能等价)

## 12. 风险

| 风险 | 防范 |
|---|---|
| 误写 openclaw.json | 所有脚本只读,无 patch/set 调用 |
| 路由决策错误 | 保守策略,不确定时降级到便宜模型 |
| provider API 不可用 | 用量获取失败不影响路由,使用缓存数据 |
| token 压缩损失信息 | 仅截断超大输出,保留前 N 行 + 摘要提示 |
| 代理服务故障 | OpenClaw 自动 fallback 到原生 provider |
