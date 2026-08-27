---
title: 性能测试
description: 负载、压力、稳定性测试与性能基线
source: k6 Docs; JMeter Docs; Google Web Dev
version: 1.0
category: business
dimension: software-development
sub_area: performance
type: knowledge
tags: [performance-testing, k6, jmeter, load-test, benchmark]
last_reviewed: 2026-08-27
---

# 性能测试

## 测试类型

| 类型 | 目的 | 工具 |
|------|------|------|
| 负载测试 | 验证预期负载下的表现 | k6、JMeter、Locust |
| 压力测试 | 找到系统极限 | k6、Gatling |
| 稳定性测试 | 长时间运行的可靠性 | k6（duration 模式） |
| 基准测试 | 建立性能基线 | Benchmark.js、自定义 |

## 关键指标

| 指标 | 说明 | 目标 |
|------|------|------|
| QPS/TPS | 每秒请求/事务数 | 满足业务需求 |
| P99 延迟 | 99%请求的响应时间 | < 500ms（API） |
| 错误率 | 失败请求占比 | < 0.1% |
| CPU/内存 | 资源利用率 | < 70% |

## k6 脚本结构

```javascript
import http from 'k6/http';
export const options = {
  stages: [
    { duration: '1m', target: 50 },   // 渐进加压
    { duration: '3m', target: 50 },   // 稳定运行
    { duration: '1m', target: 0 },    // 逐渐降压
  ],
  thresholds: {
    http_req_duration: ['p(99)<500'],  // P99 < 500ms
    http_req_failed: ['rate<0.01'],     // 错误率 < 1%
  },
};
```

## 最佳实践

1. **建立基线**：每次发布前跑基准测试
2. **渐进加压**：避免瞬时打垮系统
3. **监控全链路**：客户端 + 服务端 + 数据库
4. **回归检测**：性能下降自动告警
