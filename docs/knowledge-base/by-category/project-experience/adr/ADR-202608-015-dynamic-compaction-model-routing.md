---
type: adr
id: ADR-202608-015
date: 2026-08-26
title: 上下文压缩模型动态路由 —— 解耦 compaction 与静态配置
status: accepted
deciders: [Rex, Jerry]
layers: [L2]
stage: design
tags: [compaction, model-scheduling, openclaw, architecture, reliability]
supersedes: null
superseded_by: null
---

# [ADR-202608-015] 上下文压缩模型动态路由 —— 解耦 compaction 与静态配置

| 字段 | 内容 |
|---|---|
| **状态** | accepted |
| **日期** | 2026-08-26 |
| **影响层级** | L2 基础设施层 |
| **关联** | GitHub #59618, EXP-20260824-011, MEMORY.md 2026-08-24 上下文压缩失效 |

## 问题背景

OpenClaw `compaction.model` 当前是**静态硬编码配置**，存在两个致命问题：

1. **跨 provider 单点故障**：如果主会话模型是 `longCat/LongCat-2.0`，而 `compaction.model` 硬编码为 `coding-plan/deepseek-v4-flash`（不同 provider），当 coding-plan 网络故障时，主会话正常运行但压缩完全卡死，导致会话整体死锁 —— 这就是 2026-08-24 四环事故链的核心原因。
2. **强耦合具体模型**：如果 `compaction.model` 硬编码为 `longCat/LongCat-2.0`，而 LongCat 未来可能停用，换模型后配置直接失效，需要手动修改配置，不符合 L2 层基础设施"自动适配"的设计目标。

之前的结论：**压缩模型必须与主会话同 provider**——共享同一条网络/鉴权命运，避免压缩死锁而主会话活着的分裂故障。但如何在不硬编码的情况下实现自动选择？

## 决策

在 L2 层 `model-scheduling` 路由引擎新增 **`compaction_for`** 能力，实现动态路由压缩模型：

1. **核心策略**：`same_provider_largest_ctx` —— 优先选择与**当前主会话模型同 provider**，且**上下文窗口最大**的可用模型。
2. **保底 fallback**：同 provider 找不到可用模型时，走预配置的 fallback chain，保证总能找到压缩模型。
3. **依赖**：复用 `model-scheduling` 已有的模型注册表（`models.yaml`）、健康状态检测、用量检测，不新增状态存储。

## 设计实现

### 路由规则配置（`model-scheduling/config/routing.yaml`）

```yaml
compaction_routing:
  strategy: "same_provider_largest_ctx"    # 核心策略
  fallback_chain:                          # 保底 fallback
    - "coding-plan/deepseek-v4-flash"
    - "coding-plan/glm-5.3"
    - "coding-plan/ark-code-latest"
```

### CLI 使用

```bash
# 为指定主模型推荐压缩模型
python3 model-scheduling/scripts/router.py --compaction-for <main-model-id>

# JSON 输出供 OpenClaw 核心调用
python3 model-scheduling/scripts/router.py --compaction-for <main-model-id> --json
```

### 路由结果示例

| 主模型 | 推荐压缩模型 | Provider | 上下文窗口 | 原因 |
|---|---|---|---|---|
| `longCat/LongCat-2.0` | `longCat/LongCat-2.0` | longCat | 1048576 | 同 provider 最大 ctx |
| `coding-plan/ark-code-latest` | `coding-plan/glm-5.3` | coding-plan | 1048576 | 同 provider 最大 ctx |
| `coding-plan/deepseek-v4-flash` | `coding-plan/deepseek-v4-pro` / `coding-plan/glm-5.3` / `coding-plan/minimax-m3` | coding-plan | 1048576 | 同 provider 最大 ctx |

## 优点

1. **自动适配**：换主模型/新增模型不需要修改 `compaction` 配置，自动选择最优压缩模型。
2. **消除跨 provider 单点**：压缩永远和主会话同 provider，不会出现"主会话活，压缩死"的分裂故障。
3. **最大 ctx 优先**：压缩需要更大上下文窗口来容纳完整历史，自动选最大 ctx 符合压缩场景需求。
4. **不影响现有配置**：核心 OpenClaw 仍使用静态 `compaction.model` 作为兜底，本方案是 L2 层增强，不侵入核心代码。

## 缺点 / 风险

1. **模型注册表需同步**：`model-scheduling/config/models.yaml` 需要与 `openclaw.json` 保持一致，已有 `sync_models.py` 自动同步，风险可控。
2. **同 provider 没有大 ctx 模型**：极端情况下可能选到小 ctx，但仍比跨 provider 更安全；且 fallback chain 保底，不会无模型可用。

## 后续集成计划

1. **短期**：现有 OpenClaw 核心仍用静态 `compaction.model`，但配置改为 `model-scheduling/auto`（类似主会话路由），核心调用本脚本动态获取压缩模型 —— 实现无痛集成。
2. **中期**：推动 OpenClaw 核心原生支持动态 compaction 模型路由，将此能力合并到核心代码。
3. **长期**：结合健康检测，如果当前推荐模型连续失败，自动降级到下一个同 provider 模型。

## 验收标准

- [x] CLI 路由逻辑实现完成 ✅
- [x] 路由规则配置完成 ✅
- [x] 测试验证通过（不同主模型输出符合预期）✅
- [ ] OpenClaw 核心配置修改为 `model-scheduling/auto`（待 Rex 确认）

<!-- project: github.com/RenLimin/openclaw-v5.0 -->
