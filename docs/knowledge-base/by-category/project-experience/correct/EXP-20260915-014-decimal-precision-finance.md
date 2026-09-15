---
type: correct
id: EXP-20260915-014
date: 2026-09-15
title: 财务系统的浮点精度陷阱 — Decimal 全链路实践
layers: [L4]
phase: develop
category: project-experience
severity: high
tags: [finance, decimal, precision, data-model, L4]
status: active
---

# [EXP-20260915-014] 财务系统的浮点精度陷阱 — Decimal 全链路实践

## 1. 背景

财务系统最基本的要求就是「算出来的数必须对」。但浮点数（float）天生不精确：

```python
0.1 + 0.2 == 0.3  # False (0.30000000000000004)
```

对于家庭理财，单笔几厘钱的误差可能不致命，但：
1. 汇总误差（几千笔交易的 sum）会累积
2. 借贷恒等式校验会因为浮点误差误报
3. 贷款分摊/利息计算差几分钱就对不上银行账单

## 2. 问题

如何在 Python + SQLite 技术栈下，保证金额计算的精确性？需要覆盖：
1. 计算过程（加/减/乘/除/百分比）
2. 数据库存储（读/写不丢失精度）
3. 序列化（JSON / API 响应）
4. 展示（格式化输出）

## 3. 方案

### 3.1 全链路 Decimal 策略

```
用户输入 → str → Decimal → 计算 → Decimal → str → 数据库 (TEXT)
                                                              ↓
展示 ← format ← Decimal ← str ← 数据库读取
```

**原则**：全程使用 `decimal.Decimal`，只在最终展示时 round 到 2 位。

### 3.2 数据库存储

SQLite 没有原生 Decimal 类型，REAL 类型会丢失精度。**用 TEXT 存储**：

```python
# 写入时
amount_str = str(decimal_amount)  # "1234.56"

# 读取时
decimal_amount = Decimal(amount_str)
```

代价：SQL 里不能直接做 SUM/AVG 等数值计算，需要读到 Python 层再聚合。
收益：精度 100% 保证，跨数据库迁移不出问题。

### 3.3 精度设置

```python
from decimal import Decimal, getcontext

# 设置 28 位精度（财务场景足够，且不影响性能）
getcontext().prec = 28

# 统一舍入方式：银行家舍入（四舍六入五成双）
getcontext().rounding = ROUND_HALF_EVEN
```

为什么选银行家舍入：
- 比「四舍五入」更公平，大量数据时累计误差更小
- 国际财务标准（IFRS）推荐

### 3.4 常见计算模式

| 场景 | 正确写法 | 错误写法 |
|---|---|---|
| 加法 | `Decimal(a) + Decimal(b)` | `float(a) + float(b)` |
| 百分比 | `amount * Decimal('0.05')` | `amount * 0.05` |
| 平均 | `total / Decimal(n)` | `total / n` |
| 分摊 | `quantize(Decimal('0.01'))` | `round(x, 2)` |
| 比较 | `a == b` (Decimal) | `abs(a - b) < 1e-9` |

### 3.5 贷款分摊的精度问题

等额本息还款中，每月还款额固定，但每月的本金和利息拆分可能出现「最后一期对不上」的问题。

**解决方案**：
```python
# 前 n-1 期按公式算，最后一期倒挤
for i in range(term - 1):
    # 正常计算每期本金和利息
    ...

# 最后一期用剩余本金倒挤，保证精确结清
last_interest = remaining_principal * monthly_rate
last_principal = remaining_principal
last_payment = last_principal + last_interest
```

## 4. 验证

- ✅ 贷款还款计划：每期本金+利息=月供，最后一期精确结清
- ✅ 资产负债表恒等式：资产 = 负债 + 权益，100% 成立
- ✅ 借贷恒等式：每笔交易借方=贷方
- ✅ 预算执行精度：已用 + 剩余 = 总预算，分毫不差
- ✅ 178 个测试用例全部通过（无浮点误差导致的 flaky test）

## 5. 教训

**为什么有效**：
1. **全链路一致**：从输入到存储到计算到展示，全是 Decimal 或 str，没有浮点参与
2. **可复现**：同样的数据永远算出同样的结果（浮点误差是非确定的）
3. **可审计**：每一步计算都可以追溯和验证

**可推广条件**：
- 任何涉及金额计算的系统（不限于财务）
- 精度要求 > 2 位小数的场景
- 需要精确对账的系统

**踩过的坑**：
1. **不要从 float 转 Decimal**：`Decimal(0.1)` → `Decimal('0.10000000000000000555...')`，必须从 str 转
2. **JSON 序列化**：JSON 没有 Decimal 类型，转成字符串或整数（分），别转 float
3. **SQLite SUM**：如果存 TEXT，SQL 的 SUM 会把它当 0，聚合必须在 Python 层做
4. **quantize vs round**：用 `Decimal.quantize()` 控制精度，别用 Python 内置 `round()`

## 6. 升级判断

- [x] 影响 ≥ 2 个层级 → 否（仅 L4 业务层）
- [ ] 涉及 L1/L2 契约 → 否
- [x] 单一模块开发经验 → 保持卡片即可

## 7. 引用

- 相关 ADR: ADR-202609-027 (FIN-L4 架构)
- 相关文件: `L4-proprietary/components/fin-l4/src/fin_l4/services/`
- 业界参考: IEEE 754 浮点数标准 / 银行家舍入法

## 8. 变更历史

- 2026-09-15: 创建
