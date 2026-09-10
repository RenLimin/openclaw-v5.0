---
adr_id: ADR-202609-031
title: 合同审批模块 L3/L4 职责边界梳理与重构
status: accepted
date: 2026-09-10
deciders: Rex
layers: L3 + L4
component_id: SCA-001
component_name: 销售合同审批工作流
tags: [adr, contract-approval, l3-l4-boundary, refactoring, architecture]
---

# ADR-031: 合同审批模块 L3/L4 职责边界梳理与重构

## 背景（Context）

销售合同审批模块（SCA-001）在演进过程中出现了**层间职责模糊**和**代码重复**的问题：

### 问题清单

1. **L3 skill 混入了 L4 职责**
   - `approval_engine.py`（407 行）包含完整的数据库 CRUD + CLI，本质是一个独立的"小应用"而非"通用能力"
   - `risk_scanner.py` 同时包含纯规则引擎和数据库读取逻辑
   - `contract_gen.py` 同时包含纯工具函数和数据库读取 + docx 生成

2. **L4 office-contract 重写了一遍状态机逻辑**
   - `contract_service.py`（565 行）中审批流转、驳回回退、签署归档等逻辑与 L3 `approval_engine.py` 高度重复（~90% 相同）
   - 两边各自维护一套状态流转判断，未来修改容易不一致

3. **两套数据库**
   - L3 skill 有自己的 `contracts.db` + `schema.sql`
   - L4 office-contract 也有自己的 DB 初始化逻辑（虽然复用了同一个 schema 文件）
   - 实际使用时容易混淆哪个是"正式的"数据库

4. **调用方向不清晰**
   - L4 通过 `sys.path.insert` hack 方式 import L3 脚本模块
   - L3 skill 的 README 把自己定位成"L4 专有业务层组件"，与 L3 的定位矛盾

### 现状代码分布

| 模块 | 行数 | 纯逻辑占比 | 数据库/IO 占比 |
|------|------|-----------|---------------|
| L3 approval_engine.py | 407 | ~20% | ~80% |
| L3 risk_scanner.py | 338 | ~60% | ~40% |
| L3 contract_gen.py | 264 | ~20% | ~80% |
| L3 contract_parser.py | 1183 | ~95% | ~5% |
| L3 contract_auditor.py | 1093 | ~90% | ~10% |
| L3 audit_standard.py | 541 | 100% | 0% |
| L4 contract_service.py | 565 | ~10% | ~90% |
| **合计** | **4391** | | |

---

## 决策（Decision）

### 核心原则：L3 纯净化，L4 持久化 + 编排

**L3 = 纯逻辑（零副作用），L4 = 持久化 + 业务编排 + 场景定制**

### 具体措施

#### 1. 新建 L3 `core/` 纯逻辑核心模块

将 L3 中的纯计算逻辑提取到独立的 `core/` 目录下，确保：
- 不 import 任何 L4 模块
- 不操作数据库
- 不读写文件（CLI 入口除外）
- 不调用外部服务

**core 模块组成：**
- `core/models.py` — 数据模型（dataclass）
- `core/state_machine.py` — 审批状态机 + 分级规则
- `core/risk_engine.py` — 22 条风险扫描规则 + 综合评级
- `core/amount_utils.py` — 金额工具（中文大写等）

#### 2. L4 Service 层调用 L3 core

L4 `contract_service.py` 不再自己实现状态机逻辑，改为：
- 从数据库读取合同 → 构造 L3 Contract 对象
- 调用 L3 状态机计算下一状态 + 审批记录 + 审计日志
- 将 L3 返回的内存对象持久化到数据库

#### 3. L3 旧脚本标记为 DEPRECATED

`scripts/` 目录下的 CLI 入口文件保留为**演示/兼容用途**：
- 文件顶部明确标注 DEPRECATED
- 内部逻辑改为调用 L3 core
- 数据库操作保留为"演示模式"，不推荐生产使用
- 生产使用指引转向 L4 office-contract

#### 4. 数据库统一归 L4 管理

- `schema.sql` 保留在 L3 作为**数据契约定义**（表结构 = 数据模型的持久化映射）
- 实际数据库的创建、连接、CRUD 全部由 L4 负责
- L3 core 完全不感知数据库存在

---

## 理由（Rationale）

### 1. 符合 4 层架构定义

- **L3 通用业务层**：提供可复用的业务能力（规则、状态机、算法），不绑定具体场景
- **L4 专有业务层**：针对具体业务场景做编排，绑定持久化和外部依赖

将状态机和风险扫描纯化为 L3 能力后，未来其他 L4 业务（如采购合同审批、NDA 审批）可以直接复用 L3 core，只需：
- 注入自定义审批分级表
- 注入自定义风险规则
- 实现自己的持久化层

### 2. 可测试性大幅提升

L3 core 是纯函数，单元测试：
- 不需要数据库 setup/teardown
- 不需要文件系统
- 运行速度快（毫秒级）
- 边界条件易覆盖

L4 保留 e2e 测试验证集成正确性。

### 3. 消除了双源问题

重构前：审批状态机逻辑在 L3 和 L4 各有一份，修改时需要同步两边，容易出错。

重构后：
- **状态机逻辑唯一源**：L3 `core/state_machine.py`
- **风险规则唯一源**：L3 `core/risk_engine.py`
- **持久化唯一源**：L4 `services/contract_service.py`

### 4. 依赖方向正确

- L4 → L3 ✅（业务层调用通用能力）
- L3 不依赖 L4 ✅（通用层不感知具体业务）

符合"依赖倒置原则"：L3 定义抽象（接口 + 数据模型），L4 负责具体实现和配置注入。

---

## 代价（Consequences）

### 正面

1. **代码复用性提升**：L3 core 可被多个 L4 业务复用
2. **测试成本降低**：纯逻辑单元测试快、覆盖全
3. **架构清晰**：职责边界明确，新人易理解
4. **演进路径明确**：新增业务场景只需在 L4 适配

### 负面

1. **多了一层间接调用**：L4 需要做 Row ↔ Contract 对象转换（~30 行模板代码）
2. **旧 CLI 迁移成本**：如果有用户在直接用 L3 scripts/ 的 CLI，需要引导迁移到 L4 contractctl
3. **文件数量增加**：core/ 下新增 5 个文件，但总代码量减少

### 风险 & 缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构引入 bug | 中 | 高 | 25 个 e2e 测试全量通过作为验收标准 |
| L3 CLI 用户受影响 | 低 | 中 | 保留 CLI 兼容入口，内部重定向到 core，功能不变 |
| 未来修改两边遗忘同步 | 低 | 中 | 架构文档明确"唯一源"位置，代码内加注释指引 |

---

## 替代方案（Alternatives）

### 方案 A：维持现状（不重构）

- **优点**：零成本
- **缺点**：技术债持续累积，下一次修改审批逻辑时成本翻倍
- **结论**：不采纳

### 方案 B：把 L3 整个搬到 L4，L3 只留接口

- **优点**：L3 更"干净"
- **缺点**：L3 变成空壳，失去"通用能力"的意义；其他 L4 业务无法复用
- **结论**：不采纳

### 方案 C：本方案（L3 纯化 + L4 编排）⭐

- **优点**：复用性最高，架构最清晰，符合 4 层架构定义
- **缺点**：有少量模板代码（数据转换）
- **结论**：**采纳**

---

## 验证标准（Acceptance Criteria）

- ✅ L3 `core/` 目录下无 sqlite3 导入
- ✅ L3 `core/` 目录下无 L4 模块导入
- ✅ L4 `contract_service.py` 中没有手写的状态流转判断（全委托给 L3）
- ✅ 25 个 e2e 测试全部通过
- ✅ ARCHITECTURE.md 文档已写，职责边界清晰
- ✅ ADR 已记录
- ✅ 新增 L3 API 契约测试（验证不依赖 L4 + 无数据库操作）

---

## 参考（References）

- [4 层架构定义](../../00-system-architecture.md)
- [L3 通用业务层规范](../02-generic-business-layer.md)
- [OpenClaw Skills 规范](https://docs.openclaw.ai)
- ARCHITECTURE.md: `L3-business/skills/contract-approval/ARCHITECTURE.md`
