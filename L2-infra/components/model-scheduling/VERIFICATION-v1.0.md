# model-scheduling — 产品测试方案（VERIFICATION）

> 版本：v1.0（2026-09-28）
> 层级：L2 基础设施层
> 状态：⏳ 待 Rex 审核

---

## 1. 测试策略

| 层 | 范围 | 工具 | 环境 |
|---|---|---|---|
| 单元测试 | 函数/方法级 | pytest | 内存/临时文件 |
| 集成测试 | 模块间协作 | pytest + mock HTTP | 测试服务器 |
| E2E 测试 | 真实 HTTP 请求 | curl + httpx | 测试服务器 |
| 回归测试 | 路由正确性 | 逐模型验证 | 测试服务器 |

---

## 2. 单元测试

### 2.1 任务分类

| # | 用例 | 输入 | 预期 |
|---|------|------|------|
| UT-01 | coding 任务 | `{"messages":[{"role":"user","content":"def hello():"}]}` | → coding |
| UT-02 | reasoning 任务 | `{"messages":[{"role":"user","content":"分析这个架构"}]}` | → reasoning |
| UT-03 | multimodal 任务 | `{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"..."}}]}]}` | → multimodal |
| UT-04 | chat 任务 | `{"messages":[{"role":"user","content":"你好"}]}` | → chat |
| UT-05 | 空消息 | `{"messages":[]}` | → chat（默认） |

### 2.2 Fallback 链构建

| # | 用例 | 输入 | 预期 |
|---|------|------|------|
| UT-06 | coding 链 | task=coding | [2-0-lite, deepseek-chat, code-preview] |
| UT-07 | multimodal 过滤 | task=multimodal, code-preview 无 image | code-preview 被过滤掉 |
| UT-08 | provider 不可用 | deepseek unreachable | deepseek 被跳过 |
| UT-09 | 全部不可用 | 所有 provider unreachable | 返回空链 |

### 2.3 月份规范化（复用 BDMS）

| # | 用例 | 输入 | 预期 |
|---|------|------|------|
| UT-10 | YYYYMM | `202606` | `202606` |
| UT-11 | YYYY-MM | `2026-06` | `202606` |
| UT-12 | 非法格式 | `bogus` | `bogus`（原样返回） |

---

## 3. E2E 端到端测试

### 3.1 路由正确性

| # | 场景 | 操作 | 预期 |
|---|------|------|------|
| E2E-01 | 纯文本代码 | POST `/v1/chat/completions` body: coding 任务 | 实际模型 = 2-0-lite |
| E2E-02 | 图片+文本 | POST `/v1/chat/completions` body: multimodal 任务 | 实际模型 = 2-1-turbo |
| E2E-03 | fallback 触发 | 模拟 L1 400 → 自动 fallback L2 | 最终成功，返回 fallback_path |
| E2E-04 | 健康检查 | GET `/health` | status=ok, requests>0 |
| E2E-05 | 模型列表 | GET `/v1/models` | 返回所有 active 模型 |

### 3.2 性能

| # | 指标 | 阈值 | 方法 |
|---|------|------|------|
| PERF-01 | 路由延迟 | < 100ms | 计时（不含模型推理） |
| PERF-02 | fallback 延迟 | < 5s/次 | 模拟失败计时 |
| PERF-03 | 热更新生效 | < 10s | 修改配置 → 计时 |

---

## 4. 测试通过标准

| 层 | 标准 |
|---|---|
| 单元测试 | 全部 PASS |
| E2E 测试 | 全部 PASS |
| 路由正确性 | 100% 按 routing.yaml 分配 |
| 性能 | 全部指标达标 |

---

## 附录 A：测试执行报告

> 测试环境：macOS 15.6.2 (arm64) / Python 3.14.7
> 测试日期：2026-09-28

### A.1 单元测试结果

| 模块 | 用例数 | 通过 | 失败 |
|------|--------|------|------|
| 任务分类 | 5 | 5 | 0 |
| Fallback 链 | 4 | 4 | 0 |
| 月份规范化 | 3 | 3 | 0 |
| **合计** | **12** | **12** | **0** |

### A.2 E2E 测试结果

| 场景 | 预期 | 实测 | 状态 |
|------|------|------|------|
| 纯文本代码 → 2-0-lite | 2-0-lite | 2-0-lite | ✅ |
| 图片+文本 → 2-1-turbo | 2-1-turbo | 2-1-turbo | ✅ |
| fallback 触发 | 最终成功 | 最终成功 | ✅ |
| 健康检查 | status=ok | status=ok | ✅ |

---

## 附录 B：人工 E2E 测试操作手册

> 用途：Rex 人工审核时按此步骤执行

### B.0 启动服务

```bash
cd ~/.openclaw/workspace/L2-infra/components/model-scheduling
python3 scripts/proxy.py --host 127.0.0.1 --port 3000
```

验证：
```bash
curl -s http://127.0.0.1:3000/health | python3 -m json.tool
# 预期：{"status": "ok", "requests": 0, "errors": 0}
```

### B.1 路由验证

```bash
# 纯文本代码 → 应走 2-0-lite
curl -s -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"coding-plan/auto","messages":[{"role":"user","content":"def hello(): pass"}],"max_tokens":10}' \
  | python3 -c "import sys,json;print('模型:',json.load(sys.stdin).get('model','ERROR'))"
# 预期：模型: coding-plan/doubao-seed-2-0-lite-260215

# 图片+文本 → 应走 2-1-turbo
curl -s -X POST http://127.0.0.1:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"coding-plan/auto","messages":[{"role":"user","content":[{"type":"text","content":"what is this?"},{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgo="}}]}],"max_tokens":10}' \
  | python3 -c "import sys,json;print('模型:',json.load(sys.stdin).get('model','ERROR'))"
# 预期：模型: coding-plan/doubao-seed-2-1-turbo
```

### B.2 健康检查

```bash
curl -s http://127.0.0.1:3000/health | python3 -m json.tool
# 预期：status=ok, requests>0
```

### B.3 配置热更新验证

```bash
# 1. 记录当前路由
cat config/routing.yaml | grep -A 3 "coding:"

# 2. 修改路由（示例：调整注释）
# 3. 等待 10 秒
# 4. 发送请求验证新路由生效
```

### B.4 测试结果汇总

| # | 场景 | 预期 | 实测 | 状态 |
|---|------|------|------|------|
| 1 | 纯文本代码路由 | 2-0-lite | | ⬜ |
| 2 | 图片+文本路由 | 2-1-turbo | | ⬜ |
| 3 | 健康检查 | status=ok | | ⬜ |
| 4 | 热更新 | < 10s | | ⬜ |
