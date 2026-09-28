# model-scheduling — 产品需求文档（PRD）

> 版本：v1.0（2026-09-28）
> 层级：L2 基础设施层
> 状态：⏳ 待 Rex 审核

---

## 1. 功能清单

### 1.1 核心功能

| # | 功能 | 优先级 | 说明 |
|---|------|--------|------|
| F-01 | 模型注册 | P0 | 管理所有 AI 模型（增删改查），外部配置驱动 |
| F-02 | 任务路由 | P0 | 按任务类型（coding/reasoning/research/chat/multimodal）选择最优模型 |
| F-03 | 多级 fallback | P0 | L1 优先 → L2 降级 → L3 保底，自动切换 |
| F-04 | 健康探测 | P1 | 定期检测 provider 延迟/错误率，自动标记不可用 |
| F-05 | 用量追踪 | P1 | 获取各模型 token 用量 + 费用统计 |
| F-06 | 热更新 | P1 | 配置变更 ≤ 10 秒生效，无需重启 |
| F-07 | 模型同步 | P2 | openclaw.json → models.yaml 自动同步 |
| F-08 | 预算告警 | P2 | 超预算时自动降级到便宜模型 |
| F-09 | Token 压缩 | P2 | 工具输出截断，减少上下文 token 消耗 |
| F-10 | OpenClaw provider 注册 | P1 | 注册为 Gateway 的 custom provider，支持 `/model` 切换 |

### 1.2 非功能需求

| # | 需求 | 指标 |
|---|------|------|
| NF-01 | 路由延迟 | 模型选择 < 100ms（不含模型推理时间） |
| NF-02 | fallback 延迟 | 单次 fallback < 5s，总延迟 < 10s |
| NF-03 | 热更新 | 配置变更 ≤ 10 秒生效 |
| NF-04 | 可用性 | 组件故障不影响 OpenClaw 原生能力 |
| NF-05 | 配置隔离 | 外部文件驱动，不回写 openclaw.json |

---

## 2. 验收标准

### 2.1 路由正确性

| # | 场景 | 输入 | 预期路由 |
|---|------|------|---------|
| AC-01 | 纯文本代码请求 | `{"messages":[{"role":"user","content":"def hello()"}]}` | coding-plan/doubao-seed-2-0-lite |
| AC-02 | 图片+文本请求 | `{"messages":[{"role":"user","content":[{"type":"text","content":"..."},{"type":"image_url","image_url":{"url":"..."}}]}]}` | coding-plan/doubao-seed-2-1-turbo |
| AC-03 | 推理任务（含关键词"分析/架构/设计"） | `{"messages":[{"role":"user","content":"分析这个架构"}]}` | deepseek/deepseek-reasoner |
| AC-04 | 闲聊 | `{"messages":[{"role":"user","content":"你好"}]}` | coding-plan/doubao-seed-2-0-lite |
| AC-05 | L1 模型 400 错误 | 不支持的参数 | 自动 fallback 到 L2，最终成功 |
| AC-06 | L1 模型 429/402 | 限流/余额不足 | 自动 fallback 到下一个模型 |
| AC-07 | 所有模型不可用 | 全部超时 | 返回明确错误信息 |

### 2.2 健康探测

| # | 场景 | 预期 |
|---|------|------|
| AC-08 | provider 延迟 < 5s | 标记 healthy |
| AC-09 | provider 延迟 5-15s | 标记 degraded |
| AC-10 | provider 延迟 > 15s 或不可达 | 标记 unavailable，路由时跳过 |

### 2.3 热更新

| # | 场景 | 预期 |
|---|------|------|
| AC-11 | 修改 routing.yaml | ≤ 10 秒生效，新请求使用新路由 |
| AC-12 | 修改 models.yaml | ≤ 10 秒生效 |
| AC-13 | 修改 providers.yaml | ≤ 10 秒生效 |

---

## 3. 问题清单

| # | 问题 | 状态 |
|---|------|------|
| Q-01 | 是否支持用户手动指定模型（覆盖自动路由） | ✅ 通过 `/model` 或 `model` 参数 |
| Q-02 | 是否支持模型级别的上下文窗口自适应 | ✅ 通过 `preferred_context` |
| Q-03 | 是否支持跨 provider 的 token 计费统一 | ⚠️ 部分支持（各 provider 计费方式不同） |
| Q-04 | 是否支持流式传输的 fallback | ✅ 支持（流式中断后 fallback） |
| Q-05 | 是否支持并发请求的模型选择隔离 | ✅ 每个请求独立路由 |

---

## 4. 用户故事

### US-01：日常编码
> 作为开发者，我发送代码生成请求，系统自动选择最合适的 code 模型，
> 如果主模型不可用，自动切换到备用模型，我不需要关心底层细节。

### US-02：图片分析
> 作为用户，我发送包含图片的请求，系统自动选择支持多模态的模型，
> 而不是选择纯文本模型导致 400 错误。

### US-03：成本控制
> 作为管理员，我设置每日 token 上限，超限时系统自动降级到便宜模型，
> 避免产生意外费用。

### US-04：模型运维
> 作为运维，我修改 routing.yaml 调整路由策略，无需重启服务，
> 配置在 10 秒内生效。

---

## 5. 约束与边界

| 约束 | 说明 |
|------|------|
| 不修改 openclaw.json | 运行时只读核心配置，通过外部文件驱动 |
| 不替代 OpenClaw Gateway | 作为 proxy 层，Gateway 故障时直连 provider |
| 不存储对话历史 | 无状态 proxy，不持久化任何请求/响应 |
| 不保证 100% 可用性 | 所有 provider 不可用时返回明确错误 |
