---
type: experience-card
id: EXP-YYYYMMDD-xxx
date: YYYY-MM-DD
title: 经验标题（一句话概括问题/方案）
layer: [L2, L3]                # 涉及层级
stage: develop                 # design | develop | manage
severity: medium               # low | medium | high | critical
kind: incorrect                # correct | incorrect
tags: [tag1, tag2]
status: active                 # active | superseded
supersedes: null
superseded_by: null
---

# [EXP-YYYYMMDD-xxx] 经验标题

## 1. 背景
发生了什么场景？涉及什么模块/层级？

## 2. 问题
具体问题是什么？触发条件是什么？

## 3. 方案
- 实际采用的方案
- 或"未找到方案"的状态

## 4. 验证
- 实施后效果
- 是否有副作用

## 5. 教训
- **如果 correct**: 这套做法为什么有效？可推广的条件？
- **如果 incorrect**: 未来如何避免？有哪些早期信号？

## 6. 升级判断
- [ ] 影响 ≥ 2 个层级 → 应升级为 ADR
- [ ] 涉及 L1/L2 契约 → **必须**升级为 ADR
- [ ] 单一模块开发经验 → 保持卡片即可

## 7. 引用
- 相关文档：
- 相关 ADR：
- 相关 issue/PR：

## 8. 变更历史
- YYYY-MM-DD: 创建
