# 模型调度 (L2 基础设施组件)

> 本文档是 [系统架构](../00-system-architecture.md) 的 L2 组件设计文档。
> 无独立 ADR，作为架构 2.3 版本迭代一部分接受。

## 1. 定位

**层级**: L2 基础设施层
**类型**: 横切关注点 (Cross-Cutting Concern)
**状态**: ✅ 已上线 (2026-08-25) — 代理服务 + 自动路由 + 热更新 全量验证通过

模型调度是 L2 的智能路由组件——根据任务类型自动选择最优模型，用量感知，多级 fallback，平衡成本、速度、质量。

## 2. 问题定义

当前 OpenClaw 主模型固定的痛点：
- 闲聊/日常用大模型 → 成本浪费
- 编码/推理用小模型 → 能力不足，质量不够
- provider 网络故障 → 直接失败，不能自动降级
- token 用量无法统计 → 成本不可控
- 模型路由规则固化 → 每次修改需要重启 gateway

模型调度解决以上所有问题：**自动选对模型，自动降级，用量统计，热更新规则**。

## 3. 设计原则

| 原则 | 说明 |
|---|---|
| **任务分类路由** | 按任务类型（编码/推理/研究/闲聊）选最优模型 |
| **多级 fallback** | 优先 → 降级 → 保底，自动重试，永不雪崩 |
| **用量感知** | 统计每个 provider/model 的 token 用量和成本 |
| **热更新** | 配置修改 ≤ 10 秒生效，无需重启 gateway |
| **不侵入 OpenClaw** | 以反向代理方式工作，不修改 OpenClaw 核心配置 |
| **只读 OpenClaw 配置** | 从 `openclaw config get` 同步模型，绝不写入 |

## 4. 架构设计

### 4.1 整体流程

```
用户请求 → 代理 (:3000)
    ↓
任务分类 → 选主模型
    ↓
尝试请求 → 成功 → 返回结果 → 更新用量
    ↓ 失败
尝试下一级 fallback
    ↓
全失败 → 返回错误 → 记录告警
```

### 4.2 目录结构

```
model-scheduling/
├── proxy.py                # 代理服务入口 (:3000)
├── config_watcher.py       # 配置文件热更新监听
├── router.py               # 任务分类 + 路由决策
├── health_check.py         #  provider 健康探测（每小时）
├── sync_models.py          # 从 OpenClaw 同步模型注册表
├── fetch_usage.py          # 从 provider API 获取用量统计
├── config/
│   ├── models.yaml         # 模型注册表（从 openclaw.json 自动同步）
│   ├── routing.yaml        # 路由规则（任务→模型优先级）
│   ├── usage.json          # 用量统计（每周更新）
│   └── rollback-*.json     # 回退方案
├── logs/                   # 运行日志（已 gitignore）
└── DESGIN.md               # 本文档
```

### 4.3 路由规则

| 任务类型 | 优先级（最优 → 保底） | 说明 |
|---|---|---|
| **coding** | ark-code-latest → deepseek-v4-flash → minimax-m3 | 编码/调试/重构 |
| **reasoning** | deepseek-v4-flash → ark-code-latest → glm-5.3 | 架构/设计/推理 |
| **research** | doubao-seed-2.1-turbo → deepseek-v4-flash | 搜索/研究/分析 |
| **chat** | doubao-seed-2.0-lite → doubao-seed-2.1-turbo | 闲聊/日常/简短回复 |

### 4.4 配置同步

- `sync_models.py` 从 `openclaw config get models` 读取模型定义
- 自动写入 `config/models.yaml`，保持与 OpenClaw 一致
- 支持自定义模型覆盖，不影响同步

### 4.5 热更新

- `config_watcher.py` 监听 `config/` 目录文件变更
- 文件变更后 ≤ 10 秒自动加载新配置，无需重启代理
- 回退方案：如果加载失败，自动回退到上一个可用配置

### 4.6 健康探测

- 每小时运行一次 `health_check.py --force`
- 对每个配置的 provider 发送轻量请求，探测连通性和延迟
- 标记不健康的 provider，路由时自动跳过
- 结果写入 `config/usage.json`，路由决策使用

## 5. 运行方式

### 5.1 自动启动

macOS 下通过 LaunchAgent 开机自启：
```
~/Library/LaunchAgents/ai.openclaw.model-scheduling.plist
```
- 监听 `127.0.0.1:3000`
- 崩溃自动重启
- 日志输出到 `model-scheduling/logs/`

### 5.2 OpenClaw 配置

在 `openclaw.json` 中配置主模型为 `model-scheduling/auto`：
```json
{
  "agents": {
    "entries": {
      "main": {
        "model": "model-scheduling/auto"
      }
    }
  }
}
```
OpenClaw 会把请求转发到 `http://127.0.0.1:3000/v1/chat/completions`，由代理自动路由。

## 6. 与其他组件的关系

```
模型调度 (本组件)
  ↑ 被依赖
  ├── L1 OpenClaw 模型调用
  ├── L2 所有需要模型推理的组件
  └── 用户会话请求

  ↓ 依赖
  ├── L1 运行时抽象契约 (模型调用接口)
  ├── L2 可观测性 (日志/指标/健康探测)
  └── L2 错误自动处理 (探测失败告警)
```

## 7. 验证结果 (2026-08-25)

| 检查项 | 结果 |
|---|---|
| 代理服务启动正常 | ✅ pass |
| 任务分类路由正确 | ✅ pass |
| 多级 fallback 生效 | ✅ pass |
| 配置热更新生效 | ✅ pass |
| 健康探测正常 | ✅ pass |
| LaunchAgent 开机自启 | ✅ pass |
| 崩溃自动重启 | ✅ pass |

## 8. 演进计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| 阶段一: 基础代理 + 路由 + 热更新 | ✅ 完成 |
| 阶段二: 用量成本统计 + 预算告警 | 🚧 部分就绪（已收集用量，缺预算告警） |
| 阶段三: 自适应路由（根据历史结果优化） | 📋 架构预留 |
| 阶段四: 原生 OpenClaw 插件集成 | 📋 架构预留（当前 #6 暂缓） |
