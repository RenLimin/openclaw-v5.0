---
title: 自动化测试
description: E2E、单元、集成自动化测试工具与实践
source: Playwright Docs; Testing Library; Cypress Docs
version: 1.0
category: business
dimension: software-development
sub_area: automation
type: knowledge
tags: [automation-testing, playwright, vitest, cypress, e2e]
last_reviewed: 2026-08-27
---

# 自动化测试

## E2E 测试

| 工具 | 语言 | 特点 |
|------|------|------|
| Playwright | JS/Python/Java | 多浏览器、自动等待、Trace |
| Cypress | JS | 实时重载、时间旅行 |
| Selenium | 多语言 | 老牌、广泛支持 |

## 单元/组件测试

| 工具 | 框架 | 特点 |
|------|------|------|
| Vitest | Vue/React | ESM 原生、HMR、Vite 集成 |
| Jest | React | 成熟、快照、Mock |
| Testing Library | 框架无关 | 以用户行为测试组件 |

## API 测试

| 工具 | 用途 |
|------|------|
| Supertest | Node.js HTTP 断言 |
| Postman/Newman | 集合运行、CI 集成 |
| REST Assured | Java API 测试 |

## CI 集成

```
代码提交 → Lint → 单元测试 → 集成测试 → 构建 → E2E → 部署
```

## 最佳实践

1. **测试也是代码**：遵循同样的代码规范
2. **独立性**：测试间不依赖执行顺序
3. **确定性**：同样的输入同样的输出
4. **可维护性**：Page Object 模式、数据工厂
5. **速度优先**：慢测试放 E2E，快测试放单元
