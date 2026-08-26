---
title: 领域驱动设计（DDD）
description: DDD 战略设计与战术设计核心概念，含实体、值对象、聚合、领域事件
source: Eric Evans "Domain-Driven Design"; Vaughn Vernon "Implementing DDD"
version: 1.0
category: business
dimension: software-development
sub_area: system-architecture
type: knowledge
tags: [DDD, domain-modeling, aggregate, entity, value-object, domain-event]
xref: [software-development/knowledge/system-architecture/microservices.md]
last_reviewed: 2026-08-26
---

# 领域驱动设计（DDD）

## 核心思想

DDD 的核心是**将业务领域的复杂性作为软件设计的驱动力**，通过统一语言（Ubiquitous Language）和领域模型（Domain Model）弥合业务与技术的鸿沟。

## 战略设计（Strategic Design）

### 统一语言（Ubiquitous Language）

```
业务人员和开发人员使用同一套术语
├── 代码中的类名/方法名 = 业务术语
├── 文档中的描述 = 业务术语
└── 会议中的讨论 = 业务术语

❌ "订单表"（技术术语）
✅ "订单"（业务术语）
```

### 限界上下文（Bounded Context）

| 概念 | 说明 |
|------|------|
| 定义 | 模型适用的明确边界 |
| 内部 | 模型在上下文内一致且完整 |
| 外部 | 通过防腐层与其他上下文交互 |
| 映射 | 上下文映射图描述关系 |

### 上下文映射关系

| 关系 | 说明 |
|------|------|
| 合作关系（Partnership） | 共同演进 |
| 客户-供应商（Customer-Supplier） | 上游适配下游 |
| 防腐层（Anti-Corruption Layer） | 隔离外部模型 |
| 开放主机服务（OHS） | 标准化协议暴露 |
| 共享内核（Shared Kernel） | 共享部分模型 |

### 子域（Subdomain）

| 类型 | 说明 | 投入 |
|------|------|------|
| 核心域（Core Domain） | 业务差异化竞争力 | 最大投入 |
| 支撑域（Supporting Domain） | 业务必需但非核心 | 适度投入 |
| 通用域（Generic Domain） | 行业通用能力 | 购买/开源 |

## 战术设计（Tactical Design）

### 实体（Entity）

```python
class Order:
    """订单实体 - 有唯一标识，生命周期中可变"""
    
    def __init__(self, order_id: OrderId, customer_id: CustomerId):
        self.order_id = order_id          # 唯一标识
        self.customer_id = customer_id
        self.items: list[OrderItem] = []
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now()
    
    def add_item(self, product_id, quantity, price):
        """业务行为，不是简单的 setter"""
        if self.status != OrderStatus.PENDING:
            raise InvalidOperation("只能向待支付订单添加商品")
        self.items.append(OrderItem(product_id, quantity, price))
    
    def total_amount(self) -> Money:
        return sum(item.subtotal() for item in self.items)
```

**特征**：
- 有唯一标识（ID）
- 生命周期中可变
- 通过 ID 判断相等性
- 包含业务行为

### 值对象（Value Object）

```python
@dataclass(frozen=True)
class Money:
    """金额值对象 - 不可变，通过属性判断相等"""
    amount: Decimal
    currency: str
    
    def add(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError("币种不同，无法相加")
        return Money(self.amount + other.amount, self.currency)
```

**特征**：
- 无唯一标识
- 不可变（immutable）
- 通过属性值判断相等性
- 可替换（而非修改）

### 聚合（Aggregate）

```
聚合根（Aggregate Root）
├── 实体 A
├── 实体 B
├── 值对象 C
└── 外部只能通过聚合根访问内部
```

**规则**：
1. 聚合根是唯一的入口
2. 聚合内部保持一致性强一致性
3. 聚合之间通过 ID 引用（非对象引用）
4. 聚合尽量小（只包含必须一致的实体）
4. 一个事务只修改一个聚合

### 领域事件（Domain Event）

```python
@dataclass
class OrderPlaced:
    """订单已下单事件"""
    order_id: OrderId
    customer_id: CustomerId
    total_amount: Money
    occurred_at: datetime
```

**用途**：
- 跨聚合通信
- 跨限界上下文通信
- 事件溯源（Event Sourcing）
- 审计日志

### 领域服务（Domain Service）

当业务逻辑不属于任何实体/值对象时，使用领域服务：

```python
class PricingService:
    """定价服务 - 涉及多个聚合的定价逻辑"""
    
    def calculate_discount(self, customer: Customer, order: Order) -> Money:
        if customer.is_vip():
            return order.total_amount() * Decimal("0.1")
        if order.total_amount() > Money(1000, "CNY"):
            return order.total_amount() * Decimal("0.05")
        return Money(0, "CNY")
```

### 仓储（Repository）

```python
class OrderRepository:
    """订单仓储 - 封装持久化细节"""
    
    def save(self, order: Order) -> None:
        ...
    
    def find_by_id(self, order_id: OrderId) -> Order | None:
        ...
    
    def find_by_customer(self, customer_id: CustomerId) -> list[Order]:
        ...
```

**原则**：
- 每个聚合一个仓储
- 接口面向领域模型，非数据库表
- 实现细节（SQL/NoSQL）在基础设施层

## DDD 与微服务的关系

```
限界上下文 ≈ 微服务
├── 一个限界上下文可以是一个微服务
├── 一个微服务可以包含多个限界上下文（不推荐）
└── 关键是边界对齐，不是 1:1 映射
```

## 事件风暴（Event Storming）

### 流程

```
1. 领域事件（橙色） → "发生了什么？"
2. 命令（蓝色）     → "谁触发了事件？"
3. 聚合（黄色）     → "命令在哪个对象上执行？"
4. 策略（紫色）     → "事件触发了什么规则？"
5. 读模型（绿色）   → "用户看到什么？"
6. 外部系统（粉色） → "涉及哪些外部系统？"
```

### 产出

- 领域事件清单
- 聚合边界识别
- 限界上下文划分
- 业务流程全景

## 常见误区

1. **DDD = 四层架构**：DDD 是设计方法论，不限定架构风格
2. **过度设计**：简单 CRUD 不需要 DDD
3. **忽视统一语言**：代码和业务语言脱节，DDD 失去意义
4. **聚合过大**：一个聚合包含太多实体，事务边界失控
5. **贫血模型**：实体只有 getter/setter，没有业务行为

## 参考框架

- Evans, E. "Domain-Driven Design: Tackling Complexity in the Heart of Software"
- Vernon, V. "Implementing Domain-Driven Design"
- Brandolini, A. "Event Storming" (eventstorming.com)
- Microsoft "DDD Microservices Architecture"
