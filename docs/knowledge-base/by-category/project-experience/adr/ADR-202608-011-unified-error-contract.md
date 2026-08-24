---
type: adr
id: ADR-202608-011
date: 2026-08-24
title: 统一错误契约 (Unified Error Contract)
status: accepted
deciders: [Rex]
layers: [L1, L2, L3, L4]
stage: develop
tags: [error-handling, cross-layer, contract, observability]
supersedes: null
superseded_by: null
---

# [ADR-202608-011] 统一错误契约

## 1. 状态
**accepted** (2026-08-24)

## 2. 背景

v4.0 v9.1 架构(L4.6)定义了跨层错误协议,但 v5.0 当前缺失。错误处理散落在各 EXP 卡片中:

| 错误场景 | 当前位置 | 问题 |
|---|---|---|
| compaction 跨 provider 单点 | EXP-20260821-003 | 只记录方案,无错误码 |
| memory_search 静默降级 | ADR-009 | 只记录现象,无统一分类 |
| 凭据泄漏 | EXP-20260823-010 | 只记录教训,无错误契约 |
| 沙箱配置未重载 | EXP-20260824-012 | 只记录诊断,无标准格式 |

**核心问题**: 不同层(L1-L4)产生的错误没有统一结构,导致:
- 跨层错误无法追溯(上游错误引发下游连锁,但看不出来)
- 自愈规则无法按错误码精确匹配
- 监控告警无法按 severity 分级

## 3. 考虑的选项

### 选项 A: 维持现状(错误散落在 EXP/ADR 中)
- 优点: 零工作量
- 缺点: 跨层错误不可追溯,自愈规则碎片化

### 选项 B: 定义统一 Error Contract,新错误按契约记录
- 优点: 向后兼容(旧 EXP 不需改),渐进采纳
- 缺点: 需要团队共识

### 选项 C: 定义统一 Error Contract,回溯改写所有历史 EXP
- 优点: 完全一致
- 缺点: 工作量大,历史 EXP 的叙事性会被破坏

## 4. 决策

我们选择 **选项 B** —— 定义统一契约,新错误按契约记录,旧 EXP 保持原样(在其 `相关决策` 字段中链接到本 ADR)。

理由:
1. 历史 EXP 是叙事性记录,强制改写会破坏可读性
2. 新错误(尤其是跨层错误)必须按契约记录,确保可追溯
3. 与 v4.0 L4.6 Error Contract 对齐,但字段精简(去掉 v4.0 中我们用不到的 `source_layer`,因为 v5.0 的四层模型与 v4.0 九层不同)

## 5. 后果

### 5.1 正面
- 跨层错误可追溯: 通过 `code` 前缀快速定位责任层
- 自愈规则可匹配: Hook/cron 可按 `code` + `severity` 精确触发
- 监控可分级: `severity` 直接映射告警级别

### 5.2 负面
- 新增错误记录需填写更多字段(但模板化后成本极低)

### 5.3 风险
- 旧 EXP 未改写,可能遗漏历史错误的分类(通过 `相关决策` 链接缓解)

## 6. Error Contract 规范

### 6.1 字段定义

```json
{
  "code": "ERR_L2_CREDENTIAL_LEAK",
  "severity": "Sev2",
  "recoverable": true,
  "retryable": false,
  "message": "凭据泄漏到公开仓库",
  "context": {
    "layer": "L2",
    "component": "credentials",
    "session_id": "agent:main:main"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `code` | string | ✅ | 全局唯一,格式 `ERR_{LAYER}_{TYPE}` |
| `severity` | enum | ✅ | `Sev1` 致命 / `Sev2` 严重 / `Sev3` 警告 / `Sev4` 信息 |
| `recoverable` | bool | ✅ | 系统能否自动恢复 |
| `retryable` | bool | ✅ | 是否可以重试 |
| `message` | string | ✅ | 人类可读的错误描述 |
| `context` | object | ✅ | 至少含 `layer` + `component` |
| `retry_count` | int | ❌ | 当前重试次数(重试时填) |
| `max_retries` | int | ❌ | 最大重试次数(重试时填) |

### 6.2 错误码命名

| 前缀 | 责任层 | 示例 |
|---|---|---|
| `ERR_L1_` | OpenClaw 基座 | `ERR_L1_COMPACTION_FAILED` |
| `ERR_L2_` | 基础设施层 | `ERR_L2_CREDENTIAL_LEAK` |
| `ERR_L3_` | 通用业务层 | `ERR_L3_VALIDATION_FAILED` |
| `ERR_L4_` | 专有业务层 | `ERR_L4_COMPLIANCE_VIOLATION` |

### 6.3 Severity 映射

| severity | 含义 | 告警行为 |
|---|---|---|
| `Sev1` | 致命 — 系统不可用 | 立即通知 Rex + 停止相关服务 |
| `Sev2` 严重 — 核心功能受损 | 下次 heartbeat 通知 Rex |
| `Sev3` 警告 — 功能降级但可用 | 记入日志,每日观测摘要汇总 |
| `Sev4` 信息 — 预期内的异常 | 仅记入日志 |

### 6.4 已分类的历史错误(链接)

| 错误 | code | severity | 来源 |
|---|---|---|---|
| compaction 跨 provider 单点 | `ERR_L1_COMPACTION_PROVIDER_DOWN` | Sev2 | EXP-20260821-003 |
| memory_search 静默降级 | `ERR_L2_MEMORY_DEGRADED` | Sev2 | ADR-009 |
| 凭据泄漏到公开仓库 | `ERR_L2_CREDENTIAL_LEAK` | Sev1 | EXP-20260823-010 |
| 沙箱配置未重载 | `ERR_L2_SANDBOX_NOT_LOADED` | Sev3 | EXP-20260824-012 |
| 上下文压缩失效(四环) | `ERR_L1_COMPACTION_CASCADE` | Sev2 | MEMORY.md 08-24 |

## 7. 实现计划

- [x] 本 ADR 定义契约规范
- [ ] 更新 ADR 模板,增加 `error_contract` 字段(可选)
- [ ] 更新 EXP 模板,增加 `error_code` 字段(可选)
- [ ] 在 §3.2 上下文管理组件中引用本 ADR
- [ ] 在 §5(契约边界)中引用本 ADR

## 8. 验证标准

- 新产生的跨层错误 100% 使用 `ERR_{LAYER}_{TYPE}` 格式
- 自愈规则可按 `code` 精确匹配(至少 3 条规则在 3 个月内创建)

## 9. 相关决策

- supersedes: null
- superseded_by: null
- 相关 ADR: ADR-202608-009(记忆检索降级即 ERR_L2_MEMORY_DEGRADED 的一个实例)
- 相关 EXP: EXP-20260821-003, EXP-20260823-010, EXP-20260824-012
- 外部参考: v4.0 v9.1 L4.6 Error Contract

## 10. 变更历史

- 2026-08-24: proposed + accepted
