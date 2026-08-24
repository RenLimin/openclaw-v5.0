---
type: adr
id: ADR-202608-012
date: 2026-08-24
title: Agent 运行时作为可变因素 — 架构范式转换
status: accepted
deciders: [Rex]
layers: [L1, L2]
stage: design
tags: [architecture, runtime, abstraction, plug-and-play, paradigm-shift]
supersedes: null
superseded_by: null
---

# [ADR-202608-012] Agent 运行时作为可变因素

## 1. 状态
**accepted** (2026-08-24)

## 2. 背景

**业务目标**: 将 AI Agent 作为一个变量,系统安装部署完开始整体建设时,由使用人来指定 Agent 运行时。

当前 v1.3 架构文档的核心假设是 "L1 = OpenClaw,不可改"。这导致:
- 68 处 OpenClaw 特有概念(SecretRef / alsoAllow / plugins.allow / heartbeat / cron)硬编码在 L2 定义中
- 切换 Agent 运行时 = 推倒重来
- 上层业务设计绑定在 OpenClaw 的实现细节上

**核心问题**: 如果 Agent 运行时是可变的,架构文档应该如何调整?

## 3. 考虑的选项

### 选项 A: 维持现状(L1 = OpenClaw 不可改)
- 优点: 零工作量,文档与当前实现一致
- 缺点: 切换 Agent 运行时 = 重写整个架构;与业务目标矛盾

### 选项 B: 最小变更(只加选型原则 + ADR)
- 优点: 改动小
- 缺点: 文档和实际仍然不一致(L2 仍绑定 OpenClaw 细节),抽象层缺失

### 选项 C: 全量调整(引入运行时抽象层,文档 2.0)
- 优点: 文档与业务目标一致;切换运行时只改适配层;L3/L4 完全运行时无关
- 缺点: 约 60-70% 文档内容需要重写

## 4. 决策

我们选择 **选项 C** —— 全量调整,文档版本 1.3 → 2.0(主版本号变更,反映范式转换)。

理由:
1. **业务目标驱动**: "Agent 作为变量"不是技术偏好,是业务需求
2. **抽象层是核心**: L2-L4 必须只依赖抽象契约,不绑定任何具体运行时
3. **OpenClaw 是当前默认实现**: 不是唯一选项,适配层模式允许平滑切换
4. **成本可控**: L3/L4 定义保持不变,知识库/沙箱等已运行时无关的组件无需重写

## 5. 后果

### 5.1 正面
- **运行时可选**: OpenClaw / Claude Code / CrewAI / LangGraph / 自研 — 安装时由使用人选定
- **切换成本隔离**: 切换运行时只改 L1 适配层,L2-L4 通过抽象接口保持不变
- **业务层稳定**: L3/L4 完全不感知底层运行时,业务设计可跨运行时复用
- **未来证明**: 新运行时出现时,只需写一个适配层,不影响已有业务

### 5.2 负面
- **文档重写**: 约 60-70% 内容需要重构
- **适配层开发**: 每个新运行时需要写适配层(但这是一次性的)
- **抽象层设计难度**: 契约设计过严会限制运行时选择,过松会失去约束力

### 5.3 风险
- **抽象层过度设计**: 防范 —— 最小契约原则,只抽象当前实际需要的接口
- **OpenClaw 适配层维护**: 防范 —— 适配层与 OpenClaw 版本绑定,升级时同步更新

## 6. 架构调整规范

### 6.1 新分层结构

```
L4  专有业务层  ← 运行时无关
L3  通用业务层  ← 运行时无关
L2  基础设施层  ← 只依赖抽象契约
L1  运行时抽象层(新增) ← 定义最小能力契约
L0  系统安装层(新增) ← 0→1 安装 + 运行时选型
```

### 6.2 L1 运行时契约(最小能力集)

Agent 运行时必须提供以下能力,无论底层框架是什么:

| 能力 | 抽象接口 | 说明 |
|---|---|---|
| Agent Loop | `execute(message) → response` | 接收消息,推理,工具调用,返回结果 |
| 工具执行 | `register_tool(name, fn)` / `call_tool(name, input)` | 注册和调用工具 |
| 记忆 | `memory_read(key)` / `memory_write(key, val)` / `memory_search(query)` | 记忆读写检索 |
| 定时调度 | `schedule(cron, task)` / `cancel(task_id)` | 定时触发任务 |
| 通道接入 | `register_channel(name, adapter)` | 消息输入输出 |
| 配置管理 | `config_get(path)` / `config_set(path, val)` | 配置读写 |
| 凭据管理 | `credential_get(ref)` | 凭据安全引用 |
| 沙箱隔离 | `sandbox_execute(command, opts)` | 隔离执行环境 |

### 6.3 适配层规范

每个 Agent 运行时需要一个适配层,实现 L1 抽象接口:

```
adapters/
├── openclaw/      ← 当前默认实现
├── claude-code/   ← 未来可选
├── crewai/        ← 未来可选
└── custom/        ← 自研运行时
```

适配层职责:
- 将 L1 抽象接口翻译为具体运行时的 API 调用
- 处理运行时特有概念到抽象契约的映射
- 提供运行时健康检查和能力报告

## 7. 实现计划

- [x] 本 ADR 定义架构决策
- [x] 重写架构文档 1.3 → 2.0
- [ ] 新增 L0 系统安装层(具体实现)
- [ ] 实现适配层代码骨架
- [ ] 解耦 L2 组件描述(68 处)

## 8. 验证标准

- L2-L4 定义中零 OpenClaw 特有概念(当前 68 处 → 目标 0)
- L1 抽象契约覆盖当前所有 L2 实际依赖
- 切换运行时的成本评估: 只改适配层,< 1 人周

## 9. 相关决策

- supersedes: ADR-202608-001(4 层架构 → 调整为 5 层)
- superseded_by: null
- 相关 ADR: ADR-202608-011(Error Contract)
- 外部参考: v4.0 v9.1 L0 安装流水线 / L1 HAL 层设计

## 10. 变更历史

- 2026-08-24: proposed + accepted
