# DMS-Framework — 产品需求文档（PRD）

> 版本：v1.0（2026-09-29）
> 层级：L3 通用业务层
> 状态：⏳ 待 Rex 审核

---

## 1. 功能清单

### 1.1 核心功能

| # | 功能 | 优先级 | 说明 |
|---|------|--------|------|
| F-01 | 模块注册引擎 | P0 | ModuleRegistry 自动发现模块、解析依赖、拓扑排序初始化 |
| F-02 | 统一 CLI 框架 | P0 | `dms <module> <command>` 两级命令，模块命令自动聚合 |
| F-03 | 事件总线 | P0 | 发布/订阅 + glob 模式匹配 + 历史回溯 + 防递归 |
| F-04 | 数据持久化 | P0 | Database / BaseModel / Repository / MigrationManager 四层抽象 |
| F-05 | 状态机引擎 | P0 | 通用 FSM：状态定义 + 迁移 + guard + hook + 审计 |
| F-06 | RACI 职责引擎 | P1 | 12 能力原子 × 6 角色模板 + 冲突检测 + 覆盖验证 |
| F-07 | 工作流方案 | P1 | 多套状态机方案（default/agile/waterfall）+ 项目级覆盖 |
| F-08 | SaaS 多租户 | P1 | TenantContext + AuthProvider + TenantRouter |
| F-09 | RESTful API | P1 | FastAPI 应用工厂，自动从模块生成 CRUD 路由 |
| F-10 | Web UI | P2 | Jinja2 模板 + 原生 CSS/JS 开箱即用 |
| F-11 | 配置管理 | P1 | 默认值 → 配置文件 → 环境变量 三级优先级 |
| F-12 | Schema 迁移 | P1 | 版本化 DDL 迁移 + diff + 租户级迁移 |

### 1.2 非功能需求

| # | 需求 | 指标 |
|---|------|------|
| NF-01 | 模块热插拔 | 新增模块只需在 modules/ 下创建子目录 |
| NF-02 | 租户隔离 | 所有数据自动携带 tenant_id，默认 "system" |
| NF-03 | 测试覆盖 | 286 项测试通过，核心引擎全覆盖 |
| NF-04 | 依赖解析 | 模块依赖自动拓扑排序，循环依赖检测 |
| NF-05 | 框架独立 | 不依赖 L4 业务逻辑，L4 继承本框架 |

---

## 2. 验收标准

### 2.1 模块注册与生命周期

| # | 场景 | 输入 | 预期 |
|---|------|------|------|
| AC-01 | 注册 15 个模块 | `build_registry()` | 15 个模块全部注册成功 |
| AC-02 | 依赖拓扑排序 | 模块间有依赖关系 | 按依赖顺序初始化，无循环依赖 |
| AC-03 | 循环依赖检测 | A→B→A | 抛出 ValueError，提示循环依赖 |
| AC-04 | 重复注册 | 同名模块注册两次 | 抛出 ValueError |
| AC-05 | 模块初始化 | `initialize_all(db, config)` | 所有模块 initialize → on_ready 完成 |

### 2.2 CLI 框架

| # | 场景 | 输入 | 预期 |
|---|------|------|------|
| AC-06 | 列出模块 | `dms module list` | 显示 15 个模块信息 |
| AC-07 | 初始化 | `dms init` | 数据库初始化完成 |
| AC-08 | Schema diff | `dms schema diff` | 显示待执行迁移 |
| AC-09 | Schema migrate | `dms schema migrate` | 迁移执行成功 |
| AC-10 | 事件统计 | `dms event stats` | 显示订阅者/历史数量 |
| AC-11 | 工作流列表 | `dms workflow list` | 显示所有方案及当前激活 |

### 2.3 事件总线

| # | 场景 | 输入 | 预期 |
|---|------|------|------|
| AC-12 | 发布/订阅 | subscribe + publish | 订阅者收到事件 |
| AC-13 | 模式匹配 | subscribe("project.*") | 匹配 project.created 等 |
| AC-14 | 防递归 | 发布中再次发布 | 排队后顺序处理 |
| AC-15 | 历史记录 | 发布事件后查询 | 历史记录可回溯 |

### 2.4 状态机

| # | 场景 | 输入 | 预期 |
|---|------|------|------|
| AC-16 | 正常迁移 | fire("submit") | 状态从 draft→review |
| AC-17 | guard 阻止 | guard 返回 False | 抛出 PermissionError |
| AC-18 | 非法迁移 | 从 draft 执行 approve | 抛出 ValueError |
| AC-19 | 终态无迁移 | 终态状态查询可用迁移 | 返回空列表 |

### 2.5 RACI 引擎

| # | 场景 | 输入 | 预期 |
|---|------|------|------|
| AC-20 | 分配 + 查询 | assign + get_assignments | 查询到分配记录 |
| AC-21 | 冲突检测 | 同一人 R+A | 检测到 raci_mismatch |
| AC-22 | 覆盖验证 | 缺 R 或 A | 返回 Gap 列表 |
| AC-23 | 角色模板分配 | assign_by_role | 批量创建分配 |
| AC-24 | 矩阵生成 | get_responsibility_matrix | 完整 RACI 矩阵 |

---

## 3. 问题清单

| # | 问题 | 状态 |
|---|------|------|
| Q-01 | 是否支持模块热插拔（运行时添加/移除模块） | ✅ 支持，注册即可 |
| Q-02 | 是否支持跨模块事件通信 | ✅ 通过 EventBus 解耦 |
| Q-03 | 是否支持状态机持久化 | ⚠️ 当前内存存储，生产环境需持久化到 DB |
| Q-04 | 是否支持多租户数据隔离 | ✅ TenantContext + tenant_id 过滤 |
| Q-05 | 是否支持 RESTful API 自动生成 | ✅ FastAPI 自动从模块生成 CRUD |
| Q-06 | 是否支持工作流方案切换 | ✅ 默认/敏捷/瀑布 + 项目级覆盖 |

---

## 4. 用户故事

### US-01：模块开发者
> 作为模块开发者，我只需在 modules/ 下创建子目录、定义 manifest 和 factory，
> 框架自动发现、注册、初始化，无需修改框架代码。

### US-02：CLI 用户
> 作为运维人员，我通过 `dms <module> <command>` 统一管理所有业务模块，
> 命令自动从模块 manifest 聚合，无需手动注册。

### US-03：API 消费者
> 作为前端开发者，我通过 `/api/v1/{module}` 访问所有模块的 CRUD 接口，
> 自动生成的 API 文档在 `/docs` 可查。

### US-04：项目管理员
> 作为项目管理员，我通过 RACI 引擎为团队成员分配职责，
> 冲突检测和覆盖验证确保职责清晰、无遗漏。

---

## 5. 约束与边界

| 约束 | 说明 |
|------|------|
| 不实现具体业务逻辑 | 框架只提供引擎和契约，业务逻辑在 L4 |
| 不替代 L4 系统 | L4 继承本框架能力，不反向依赖 |
| 不存储敏感数据 | 认证由 L4 实现 AuthProvider |
| 不保证分布式一致性 | 单机 SQLite，分布式需 L4 扩展 |
| 不实现前端复杂交互 | Web UI 为基础展示，复杂交互由 L4 负责 |
