# DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md

> **Bangcle 交付管理系统（BDMS）v2.1 — 项目管理模块详细设计**
> 版本：v2.1 Detail r2（2026-09-24）
> 层级：L4 专有业务层 — 核心域模块
> 依据：`PRD-v2.1.md`（已审核通过）+ `DESIGN-OUTLINE-v2.1.md`（已审核通过）
> 状态：待 Rex 审核
> 作者：BDMS 设计团队

---

## 目录

0. [版本记录](#0-版本记录)
1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [项目生命周期状态机](#6-项目生命周期状态机)
7. [风险横向覆盖设计](#7-风险横向覆盖设计)
8. [成本子引擎接口](#8-成本子引擎接口)
9. [风险子引擎接口](#9-风险子引擎接口)
10. [四类实施管理](#10-四类实施管理)
11. [错误处理](#11-错误处理)
12. [CLI 命令](#12-cli-命令)
13. [测试策略](#13-测试策略)
附录 A：[数据库迁移注意事项](#附录-a数据库迁移注意事项)
附录 B：[复用资产清单与使用方式](#附录-b复用资产清单与使用方式)
[变更历史](#变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版 |
| v2.1 Detail r2 | 2026-09-24 | Rex 审核反馈 2 条：售后管理编排（after_sales 状态 + 工单 + SLA）+ 业界最佳实践 + 角色权限 §1.6 |

---

## 1. 模块概述

### 1.1 业务域

项目管理模块（`project_management`）是 BDMS 的**核心域模块**，负责 Bangcle 交付项目的全生命周期管理：

```
立项 → 规划 → 执行 → 交付 → 确收 → 验收 → 售后 → 结项
```

覆盖 PRD 定义的 **16 个流程阶段 / 62 个流程节点** 中的 **#3 ~ #16**（共 14 个阶段），是 BDMS 流程覆盖范围最广的模块。

### 1.2 L3 域归属

| 维度 | 归属 |
|---|---|
| L1 平台 | OpenClaw |
| L3 框架 | `delivery-management-framework`（DMS 通用管理框架） |
| L4 专有域 | `bdms.project_management` |
| 域类型 | **核心域**（Core Domain）— 业务差异化竞争力 |

### 1.3 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **PMBOK 第 7 版** | 项目管理标准 | 12 原则 + 8 绩效域，生命周期阶段化 | 7 阶段默认模板 + 状态机 |
| **PRINCE2** | 受控环境项目管理 | 阶段边界管理（Stage Gate）+ 例外管理 | 阶段转换前置校验 + 风险关闭检查 |
| **Jira/ONES** | 敏捷项目追踪 | 工作流状态机 + 可配置看板 | VALID_TRANSITIONS 状态机 + 驾驶舱 |
| **ITIL 4** | IT 服务管理（售后） | 事故/问题/变更三流程 + SLA 管理 | as_tickets 工单 + SLA 分级监控 |
| **Zendesk/Freshdesk** | 工单系统 | 优先级 SLA + 升级机制 + 知识库联动 | SLA 响应/解决时限 + 超时升级 PMO |
| **SAP PS** | 项目系统 | WBS + 里程碑 + 预算控制 | pm_milestones + budget_usage |
| **MS Project** | 计划管理 | 甘特图 + 基线对比 + 关键路径 | 里程碑基线（v2.2 占位：甘特图） |
| **Scrum/SAFe** | 敏捷框架 | 迭代 + 冲刺 + 回顾 | 阶段模板可配置（pm.default_phase_template） |

**售后管理设计原则（对齐 ITIL 4）**：
- **事故管理**：工单受理→分派→解决→关闭（§3.2.8.2~8.5）
- **SLA 管理**：优先级分级时限 + 超时升级（§3.2.8.6）
- **服务级别目标**：维保合同定义服务范围与响应标准（as_warranty_contracts）
- **持续改进**：SLA 快照定期分析，反哺服务优化（as_sla_snapshots）

### 1.4 与其他模块交互

```
                    ┌─────────────────────┐
                    │  contract_management │
                    │  （合同审核管理）      │
                    └──────────┬──────────┘
                               │ contract_id (FK)
                               ▼
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│ master_data  │────▶│ project_management  │◀────│ integration  │
│ （主数据）    │     │ （项目管理·核心域）   │     │ （数据集成）  │
└──────────────┘     └──────────┬──────────┘     └──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
    ┌─────────────────┐ ┌─────────────┐  ┌──────────────────┐
    │ delivery_report │ │  revenue    │  │ profit_management│
    │ （交付月报）     │ │ （确收分析） │  │ （项目利润）      │
    └─────────────────┘ └─────────────┘  └────────────────────┘
              ▲                 ▲                  ▲
              │                 │                  │
              └─────────────────┴──────────────────┘
                              │
                    ┌─────────────────────┐
                    │     dashboard       │
                    │  （驾驶舱·只读）     │
                    └─────────────────────┘
```

**交互规则**：
- **上游输入**：`contract_management`（合同信息）、`master_data`（字典/图例）、`integration`（ONES/OA 数据同步）
- **下游输出**：`delivery_report`（交付数据）、`revenue`（确收数据）、`profit_management`（成本数据）
- **只读消费者**：`dashboard`（驾驶舱聚合展示）
- **模块间不直接调用**，通过 DB 共享数据 + Outbox 事件总线解耦

### 1.5 子模块划分

| 子模块 | 类型 | 职责 |
|---|---|---|
| `project_management/engine.py` | 核心引擎 | 项目主数据 CRUD + 状态机 + 阶段/团队/里程碑管理 |
| `project_management/service.py` | 编排服务 | 跨子引擎事务编排 + 生命周期推进（含售后管理） |
| `project_management/financial_service.py` | 财务服务 | 利润视图 + 财务健康度评估 |
| `project_management/after_sales/` | 售后子引擎 | 维保合同 + 工单受理→分派→解决→关闭 + SLA 监控 |
| `project_management/cost/` | 成本子引擎 | 工时×费率 + 设备 + 差旅成本归集 |
| `project_management/risk/` | 风险子引擎 | 风险报备→评估→处置→关闭 |
| `project_management/change/` | 变更子引擎 | 变更请求→评估→审批→执行 |
| `project_management/models.py` | 数据契约 | 枚举定义 + 状态转换矩阵 + 数据类 |

> **售后定位**：售后管理是项目生命周期的**结项前置环节**（验收后 → 售后服务期 → 结项），不是独立于生命周期之外的阶段。

---

### 1.6 角色与权限

> 对齐全局角色体系（PRD §2）：本系统仅针对交付团队，无财务角色（相关操作由 PMO 承担）。

| 角色 | 编码 | 可执行操作 |
|---|---|---|
| 项目经理 | `pm` | 创建/更新项目、提交交付、查看自己项目、风险报备 |
| PMO | `pmo` | 全部项目操作 + 验收 + 结项审批 + 售后管理 + 财务对接 |
| 交付技术部 | `tech` | 工单处理（售后分派/解决）、实施记录 |
| 高管 | `gm` | 全量只读 |
| 管理员 | `admin` | 全部操作 + 取消/重新激活项目 |
| 超级管理员 | `super_admin` | 所有操作权限（含系统级配置、跨模块数据访问） |

**状态流转权限矩阵**：

| 操作 | pm | pmo | tech | gm | admin | super_admin |
|---|---|---|---|---|---|---|
| 创建项目 | ✅(自己) | ✅ | ❌ | ❌ | ✅ | ✅ |
| 启动项目 | ✅(自己) | ✅ | ❌ | ❌ | ✅ | ✅ |
| 提交交付 | ✅(自己) | ✅ | ✅ | ❌ | ✅ | ✅ |
| 验收通过 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 转售后 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 工单分派/解决 | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ |
| 结项 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| 取消项目 | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 风险报备/处置 | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |


## 2. OS 依赖与限制

> 项目管理模块自身逻辑 OS 无关，但依赖 integration 模块（ONES/OA 数据导入）和 WeCom 回调。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| ONES 项目数据导入 | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-01 |
| OA 立项/结项数据 | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-02 |
| WeCom 消息回调 | HTTP 回调 | ✅ 支持 | ✅ 支持 | ✅ 支持 | OS 无关 |
| 项目状态流转 | SQLite | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 风险处置 | SQLite | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 售后工单 | SQLite | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
project_management
├── ONES 数据 → integration I-01 → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
├── OA 数据 → integration I-02 → 浏览器自动化（同上）
├── WeCom 回调 → HTTP（OS 无关）
└── 状态/风险/售后/Web/CLI → 纯 Python + SQLite（全平台）
```

## 3. 技术方案

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         接入层                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐   │
│  │  bdms-cli       │  │  FastAPI Router │  │  AI Agent 直接调用  │   │
│  │  (CLI 命令)     │  │  (REST API)     │  │  (Python import)   │   │
│  └────────┬────────┘  └────────┬────────┘  └─────────┬──────────┘   │
│           │                    │                     │              │
├───────────┴────────────────────┴─────────────────────┴──────────────┤
│                       Service 层（编排）                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              ProjectManagementService                         │   │
│  │  create_project │ start_project │ submit_delivery │ close_... │   │
│  └────────────────────────┬─────────────────────────────────────┘   │
│                           │                                          │
│  ┌────────────────────────┼──────────────────────────────────────┐  │
│  │                        ▼                                       │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │  │
│  │  │ ProjectEngine  │  │  CostEngine    │  │  RiskEngine    │  │  │
│  │  │ 主数据+状态机  │  │ 工时+设备+差旅 │  │ 报备→处置→关闭 │  │  │
│  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘  │  │
│  │          │                   │                   │            │  │
│  │          ▼                   ▼                   ▼            │  │
│  │  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │               SQLite (pm_*/ct_*/rk_*/ch_*)                │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  │                    Engine 层（计算 + 持久化）                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  ProjectFinancialService（跨引擎利润视图）                     │  │
│  │  get_profit_summary │ get_profit_trend │ check_profit_alert   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
modules/project_management/
├── __init__.py                  # 模块导出
├── models.py                    # 枚举 + 数据类 + 状态转换矩阵
├── engine.py                    # ProjectEngine — 核心引擎
├── service.py                   # ProjectManagementService — 编排服务
├── financial_service.py         # ProjectFinancialService — 利润视图
├── cost/
│   ├── __init__.py
│   ├── engine.py                # CostEngine — 成本核算引擎
│   ├── service.py               # CostService — 成本管理服务
│   ├── exporter.py              # CostExporter — 成本导出
│   └── importer.py              # CostImporter — 成本导入
├── risk/
│   ├── __init__.py
│   ├── engine.py                # RiskEngine — 风险管理引擎
│   ├── service.py               # RiskService — 风险管理服务
│   └── exporter.py              # RiskExporter — 风险导出
└── change/
    ├── __init__.py
    └── engine.py                # ChangeManagementEngine — 变更管理引擎
```

### 2.3 依赖关系

```
project_management
  ├── 依赖 core/db.py（数据库连接 + schema）
  ├── 依赖 core/paths.py（路径配置）
  ├── 依赖 modules/base.py（BaseEngine / BaseService / 异常体系）
  ├── 依赖 modules/base_repository.py（仓储接口）
  └── 子引擎间依赖：
      ├── ProjectManagementService → CostEngine（懒加载）
      ├── ProjectManagementService → RiskEngine（懒加载）
      └── ProjectFinancialService → CostEngine + ProjectEngine（懒加载）
```

**设计要点**：
- 子引擎**懒加载**（避免循环导入）
- 所有引擎共享 SQLite 连接（`isolation_level = None` autocommit 模式）
- 软删除统一通过 `deleted_at` 字段实现
- 审计字段：`created_at`, `updated_at`, `created_by`, `updated_by`

---

## 4. 接口设计

### 3.1 ProjectEngine（核心引擎）

#### 3.1.1 `create_project(**data) -> int`

创建项目（立项）。初始状态: `initiating`。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_name` | str | ✅ | - | 项目名称 |
| `project_type` | str | ❌ | `""` | 项目类型（等保测评/风险评估/...） |
| `dept` | str | ❌ | `""` | 所属部门 |
| `pm` | str | ❌ | `""` | 项目经理 |
| `contract_id` | int | ❌ | `None` | 关联合同 ID（FK → cr_contracts.id） |
| `start_date` | str | ❌ | `None` | 计划开始日期 YYYY-MM-DD |
| `end_date` | str | ❌ | `None` | 计划结束日期 YYYY-MM-DD |
| `budget` | float | ❌ | `0.0` | 预算金额 |
| `created_by` | str | ❌ | `"system"` | 创建人 |
| `project_no` | str | ❌ | 自动生成 | 项目编号（PROJ-YYYYMMDD-NNNN） |

**Returns**: `int` — 新项目 ID

**Raises**:
- `ValidationError` — `project_name` 为空

**生成规则**：
- 项目编号格式：`PROJ-{YYYYMMDD}-{4位序号}`，按日自增
- 初始状态固定为 `initiating`

---

#### 3.1.2 `update_project(project_id, **data) -> None`

更新项目基本信息。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | int | ✅ | 项目 ID |
| `**data` | kwargs | ❌ | 可更新字段（project_name, project_type, dept, pm, start_date, end_date, budget） |

**约束**：
- 禁止直接修改 `status`（使用 `transition_state()`）
- 禁止修改 `id`, `project_no`, `created_by`, `created_at`

**Raises**:
- `NotFoundError` — 项目不存在

---

#### 3.1.3 `transition_state(project_id, to_state, operator, comment) -> str`

推进项目状态。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `to_state` | str | ✅ | - | 目标状态（7 种合法状态之一） |
| `operator` | str | ❌ | `"system"` | 操作人 |
| `comment` | str | ❌ | `""` | 备注 |

**Returns**: `str` — 新状态值

**Raises**:
- `StateTransitionError` — 状态转换非法
- `NotFoundError` — 项目不存在

**幂等性**：同一状态转换请求返回原状态，不报错。

---

#### 3.1.4 `get_status(project_id) -> str`

获取项目当前状态。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | int | ✅ | 项目 ID |

**Returns**: `str` — 状态值（如 `"executing"`）

**Raises**: `NotFoundError`

---

#### 3.1.5 `list_projects(filters) -> tuple[list, int]`

项目列表查询（支持搜索 + 筛选 + 分页）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `status` | str | ❌ | `None` | 按状态筛选 |
| `pm` | str | ❌ | `None` | 按项目经理筛选 |
| `project_type` | str | ❌ | `None` | 按项目类型筛选 |
| `dept` | str | ❌ | `None` | 按部门筛选 |
| `keyword` | str | ❌ | `None` | 关键词搜索（匹配 project_name 或 project_no） |
| `page` | int | ❌ | `1` | 页码（≥1） |
| `page_size` | int | ❌ | `20` | 每页条数 |

**Returns**: `tuple[list[dict], int]` — (项目列表, 总条数)

---

#### 3.1.6 `add_phase(project_id, phase_name, **data) -> int`

添加项目阶段。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `phase_name` | str | ✅ | - | 阶段名称 |
| `phase_order` | int | ❌ | `0` | 阶段顺序 |
| `planned_start` | str | ❌ | `None` | 计划开始日期 |
| `planned_end` | str | ❌ | `None` | 计划结束日期 |

**Returns**: `int` — 新阶段 ID

---

#### 3.1.7 `add_team_member(project_id, member_name, **data) -> int`

添加项目成员。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `member_name` | str | ✅ | - | 成员姓名 |
| `role` | str | ❌ | `""` | 角色 |
| `allocation` | float | ❌ | `1.0` | 投入比例（0-1） |
| `start_date` | str | ❌ | `None` | 开始日期 |
| `end_date` | str | ❌ | `None` | 结束日期 |

**Returns**: `int` — 新成员 ID

**唯一约束**：`(project_id, member_name, role)` 唯一。

---

#### 3.1.8 `add_milestone(project_id, milestone_name, **data) -> int`

添加里程碑。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `milestone_name` | str | ✅ | - | 里程碑名称 |
| `planned_date` | str | ❌ | `None` | 计划日期 |
| `status` | str | ❌ | `"pending"` | 状态 |

**Returns**: `int` — 新里程碑 ID

---

#### 3.1.9 `submit_delivery_report(project_id, report_type, title, **data) -> int`

提交交付报告。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `report_type` | str | ✅ | - | 报告类型 |
| `title` | str | ✅ | - | 报告标题 |
| `content` | str | ❌ | `""` | 报告内容 |
| `attachments` | str | ❌ | `""` | 附件（逗号分隔路径） |
| `created_by` | str | ❌ | `"system"` | 提交人 |

**Returns**: `int` — 新交付报告 ID

---

### 3.2 ProjectManagementService（编排服务）

#### 3.2.1 `create_project(**data) -> int`

创建项目 + 初始化默认阶段模板（6 个核心阶段）。

**默认阶段模板**：

| 阶段名称 | 顺序值 |
|---|---|
| 立项阶段 | 10 |
| 规划阶段 | 20 |
| 执行阶段 | 30 |
| 交付阶段 | 40 |
| 验收阶段 | 50 |
| **售后阶段** | **55** |
| 结项阶段 | 60 |

> 售后阶段插在验收与结项之间（顺序值 55），对应状态机 `after_sales` 状态。

**Returns**: `int` — 新项目 ID

---

#### 3.2.2 `start_project(project_id, operator) -> None`

启动项目：`initiating → planning → executing`（两步走完）。

**前置校验**：
- 必须有 PM（`project.pm` 非空）
- 至少有一个团队成员

**Raises**:
- `ValidationError` — 缺少 PM 或团队成员

---

#### 3.2.3 `submit_delivery(project_id, report_type, title, **data) -> int`

提交交付报告并推进到 `delivering` 状态。

**前置校验**：
- 项目状态必须是 `executing` 或 `delivering`

**Returns**: `int` — 交付报告 ID

---

#### 3.2.4 `accept_project(project_id, **data) -> None`

项目验收：`delivering → accepting`。

**前置校验**：
- 项目状态必须是 `delivering`
- 无未关闭的高风险/严重风险（critical/high）

**Raises**:
- `ValidationError` — 存在未关闭的高风险

---

#### 3.2.5 `close_project(project_id, **data) -> None`

结项：`accepting → closing → closed`。

**前置校验**：
- 项目状态必须是 `accepting` 或 `closing`
- 所有风险已关闭
- 所有交付报告已审核通过（无 `draft` 或 `submitted` 状态）

**Raises**:
- `ValidationError` — 存在未关闭风险或待审核交付报告

---

#### 3.2.6 `cancel_project(project_id, reason, operator) -> None`

取消项目（任意非 `closed` 状态 → `cancelled`）。

**Raises**:
- `ValidationError` — 项目已结项

---

#### 3.2.7 `reactivate_project(project_id, operator) -> None`

重新激活已取消的项目：`cancelled → initiating`。

---

#### 3.2.8 售后管理（结项前置环节）

> **定位**：验收通过 → 售后服务期 → 结项。售后管理是结项的前置环节，结项前必须完成售后交接。

##### 3.2.8.1 `transfer_to_after_sales(project_id, operator) -> dict`

转售后：验收通过后创建维保合同，进入售后服务期。

**前置校验**：
- 项目状态为 `accepting`（验收通过）
- 合同包含维保条款或免费服务期（查 `cr_contracts.warranty_clause`，无则提示确认）

**事务动作**：
1. 创建 `as_warranty_contracts` 记录（维保合同，含服务起止日期）
2. 项目状态 `accepting → after_sales`（新增状态，见 §5.1）
3. 写入 outbox 事件 `project.after_sales_started`

**Returns**: `dict` — `{project_id, warranty_id, status, service_start, service_end}`

---

##### 3.2.8.2 `create_ticket(project_id, **data) -> int`（售后工单）

创建售后工单（售后服务期内或维保期内）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | int | ✅ | 项目 ID |
| `title` | str | ✅ | 工单标题 |
| `description` | str | ❌ | 问题描述 |
| `priority` | str | ❌ | 优先级（critical/high/medium/low，默认 medium） |
| `reporter` | str | ❌ | 报告人（客户/PM） |
| `source` | str | ❌ | 来源（warranty/paid/free，默认 warranty） |

**Returns**: `int` — ticket_id

**SLA 初始化**：按优先级自动设定响应/解决时限（见 §3.2.8.6）

---

##### 3.2.8.3 `assign_ticket(ticket_id, assignee, operator) -> None`

分派工单。

**前置校验**：工单状态为 `open`

---

##### 3.2.8.4 `resolve_ticket(ticket_id, resolution, operator) -> None`

解决工单（写入解决方案 + 状态 `resolved`）。

**前置校验**：工单状态为 `assigned` 或 `in_progress`

---

##### 3.2.8.5 `close_ticket(ticket_id, operator) -> None`

关闭工单（客户确认解决后，状态 `closed`）。

**前置校验**：工单状态为 `resolved`

---

##### 3.2.8.6 SLA 监控规则

| 优先级 | 响应时限 | 解决时限 | 超时动作 |
|---|---|---|---|
| critical | 2h | 24h | 升级 PMO + 企微通知 |
| high | 4h | 48h | 企微通知 |
| medium | 8h | 5 工作日 | 系统提醒 |
| low | 24h | 10 工作日 | 无 |

**SLA 快照**：每日定时扫描，超时工单写入 `as_sla_snapshots`（快照表）+ 触发告警事件。

---

##### 3.2.8.7 `get_after_sales_summary(project_id) -> dict`

售后概览（结项前检查依据）。

**Returns**:
```python
{
    "warranty": {"id": int, "service_start": str, "service_end": str, "status": str},
    "tickets": {"total": int, "open": int, "resolved": int, "closed": int},
    "sla": {"breached": int, "at_risk": int},
    "ready_to_close": bool,   # 无未关闭工单 → 可结项
}
```

---

##### 3.2.8.8 结项前置检查（修改 close_project）

`close_project()` 新增前置校验（见 §3.2.5）：
- 项目已转售后（`after_sales` 状态）或确认无需售后
- **无未关闭工单**（`as_tickets` 中无 `open/assigned/in_progress/resolved` 状态）
- SLA 无未处理超时

不满足时 `ValidationError`，提示先完成售后处置。

---

#### 3.2.9 `report_risk(**data) -> int`

风险报备入口（委托 RiskEngine）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | int | ✅ | 项目 ID |
| `title` | str | ✅ | 风险标题 |
| `description` | str | ❌ | 风险描述 |
| `risk_type` | str | ❌ | 风险类型 |
| `probability` | str | ❌ | 概率（high/medium/low） |
| `impact` | str | ❌ | 影响（high/medium/low） |
| `reporter` | str | ❌ | 上报人 |
| `owner` | str | ❌ | 责任人 |
| `due_date` | str | ❌ | 截止日期 |

**Returns**: `int` — risk_id

---

#### 3.2.10 `resolve_risk(risk_id, action, **data) -> None`

风险处置（委托 RiskEngine）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `risk_id` | int | ✅ | 风险 ID |
| `action` | str | ✅ | 处置策略（mitigate/accept/transfer/avoid） |
| `reviewer` | str | ❌ | 评审人 |
| `action_plan` | str | ❌ | 处置计划 |
| `owner` | str | ❌ | 责任人 |
| `due_date` | str | ❌ | 截止日期 |

---

#### 3.2.11 `list_risks(filters) -> tuple[list, int]`

查询风险列表（委托 RiskEngine）。

---

#### 3.2.12 `get_project_detail(project_id) -> dict`

获取项目完整详情（聚合所有子引擎数据）。

**Returns**:
```python
{
    "project": dict,           # 项目基本信息
    "phases": list[dict],      # 阶段列表
    "team_members": list[dict],# 团队成员
    "milestones": list[dict],  # 里程碑
    "delivery_reports": list[dict],  # 交付报告
    "cost_summary": dict,      # 成本概览
    "risk_summary": dict,      # 风险概览
}
```

---

#### 3.2.13 `get_project_dashboard(project_id) -> dict`

项目仪表盘：进度 / 成本 / 收入 / 风险 概览。

**Returns**:
```python
{
    "project_id": int,
    "project_name": str,
    "status": str,
    "progress_pct": float,        # 进度百分比
    "budget": float,              # 预算
    "total_cost": float,          # 总成本
    "budget_usage_pct": float,    # 预算使用率
    "milestones_total": int,
    "milestones_completed": int,
    "risk_total": int,
    "risk_open": int,
    "risk_critical": int,
    "team_size": int,
}
```

---

### 3.3 ProjectFinancialService（财务服务）

#### 3.3.1 `get_profit_summary(project_id) -> dict`

获取项目利润汇总。

**Returns**:
```python
{
    "budget": float,
    "total_revenue": float,       # 总收入（按进度估算）
    "total_cost": float,          # 总成本
    "gross_profit": float,        # 毛利润
    "gross_margin": float,        # 毛利率 %
    "budget_usage_pct": float,    # 预算使用率 %
    "estimated_progress": float,  # 估算进度 0-1
}
```

**收入估算策略**：
- 现阶段：`budget × estimated_progress`
- 后续：接入 RevenueEngine 实际确收数据

---

#### 3.3.2 `get_profit_trend(project_id, range_months) -> list[dict]`

获取利润趋势（按月）。

**Returns**: `[{month, revenue, cost, profit, margin}]`

---

#### 3.3.3 `check_profit_alert(project_id, threshold_pct) -> dict`

检查利润预警。

**Returns**:
```python
{
    "alert": bool,
    "current_margin": float,
    "threshold": float,
    "level": "info" | "warning" | "critical",
}
```

---

#### 3.3.4 `get_financial_health_score(project_id) -> dict`

财务健康度评分（0-100 分）。

**评估维度**：

| 维度 | 满分 | 评分规则 |
|---|---|---|
| 预算执行率 | 25 | <70%: 25分; 70-90%: 20分; 90-100%: 10分; >100%: 0分 |
| 毛利率 | 25 | ≥30%: 25分; ≥20%: 20分; ≥10%: 12分; ≥0%: 5分; <0%: 0分 |
| 成本增长率 | 25 | ≤10%: 25分; ≤25%: 18分; ≤50%: 10分; >50%: 3分 |
| 现金流匹配度 | 25 | 成本/收入 ≤0.7: 25分; ≤0.9: 18分; ≤1.0: 10分; >1.0: 3分 |

**Returns**:
```python
{
    "score": int,              # 总分 0-100
    "level": "excellent" | "good" | "fair" | "poor" | "critical",
    "breakdown": {维度得分详情},
    "recommendations": [改进建议],
}
```

---

## 5. 数据模型

### 4.1 完整 DDL

#### 4.1.1 pm_projects（项目主表）

```sql
CREATE TABLE IF NOT EXISTS pm_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no TEXT UNIQUE NOT NULL,           -- 项目编号 PROJ-YYYYMMDD-NNNN
    project_name TEXT NOT NULL,                -- 项目名称
    contract_id INTEGER,                       -- 关联合同 FK → cr_contracts.id
    project_type TEXT,                         -- 项目类型（等保测评/风险评估/...）
    dept TEXT,                                 -- 所属部门
    pm TEXT,                                   -- 项目经理
    status TEXT DEFAULT 'initiating',          -- 项目状态（7 种）
    start_date TEXT,                           -- 计划开始日期 YYYY-MM-DD
    end_date TEXT,                             -- 计划结束日期 YYYY-MM-DD
    budget REAL DEFAULT 0,                     -- 预算金额
    -- 实施类型标记
    impl_product INTEGER DEFAULT 0,            -- 产品实施 0/1
    impl_security INTEGER DEFAULT 0,           -- 安服实施 0/1
    impl_custom INTEGER DEFAULT 0,             -- 定制开发 0/1
    impl_outsourcing INTEGER DEFAULT 0,        -- 外包/外采 0/1
    -- 审计字段
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    -- 软删除
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id)
);
CREATE INDEX IF NOT EXISTS idx_pm_status ON pm_projects(status);
CREATE INDEX IF NOT EXISTS idx_pm_pm ON pm_projects(pm);
CREATE INDEX IF NOT EXISTS idx_pm_type ON pm_projects(project_type);
CREATE INDEX IF NOT EXISTS idx_pm_deleted ON pm_projects(deleted_at);
CREATE INDEX IF NOT EXISTS idx_pm_contract ON pm_projects(contract_id);
```

#### 4.1.2 pm_phases（项目阶段表）

```sql
CREATE TABLE IF NOT EXISTS pm_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    phase_name TEXT NOT NULL,                  -- 阶段名称
    phase_order INTEGER DEFAULT 0,             -- 阶段顺序
    status TEXT DEFAULT 'pending',             -- pending | in_progress | completed | skipped
    planned_start TEXT,                        -- 计划开始日期
    planned_end TEXT,                          -- 计划结束日期
    actual_start TEXT,                         -- 实际开始日期
    actual_end TEXT,                           -- 实际结束日期
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ppm_project ON pm_phases(project_id);
CREATE INDEX IF NOT EXISTS idx_ppm_order ON pm_phases(project_id, phase_order);
```

#### 4.1.3 pm_team_members（项目成员表）

```sql
CREATE TABLE IF NOT EXISTS pm_team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    member_name TEXT NOT NULL,                 -- 成员姓名
    role TEXT,                                 -- 角色（PM/工程师/测试/...）
    allocation REAL DEFAULT 1.0,               -- 投入比例 0.0-1.0
    start_date TEXT,                           -- 开始日期
    end_date TEXT,                             -- 结束日期
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, member_name, role)
);
CREATE INDEX IF NOT EXISTS idx_ptm_project ON pm_team_members(project_id);
```

#### 4.1.4 pm_milestones（里程碑表）

```sql
CREATE TABLE IF NOT EXISTS pm_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    milestone_name TEXT NOT NULL,              -- 里程碑名称
    planned_date TEXT,                         -- 计划日期
    actual_date TEXT,                          -- 实际完成日期
    status TEXT DEFAULT 'pending',             -- pending | achieved | missed
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pml_project ON pm_milestones(project_id);
```

#### 4.1.5 pm_delivery_reports（交付报告表）

```sql
CREATE TABLE IF NOT EXISTS pm_delivery_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    report_type TEXT,                          -- 报告类型（delivery/acceptance/transfer）
    title TEXT NOT NULL,                       -- 报告标题
    content TEXT,                              -- 报告内容
    attachments TEXT DEFAULT '',                -- 附件（逗号分隔路径）
    status TEXT DEFAULT 'draft',               -- draft | submitted | approved | rejected
    created_by TEXT DEFAULT '',                 -- 提交人
    submitted_at TEXT,                         -- 提交时间
    reviewed_at TEXT,                          -- 审核时间
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pdr_project ON pm_delivery_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_pdr_status ON pm_delivery_reports(status);
CREATE INDEX IF NOT EXISTS idx_pdr_deleted ON pm_delivery_reports(deleted_at);
```

### 4.2 成本子引擎表

#### 4.2.1 ct_timesheets（工时记录表）

```sql
CREATE TABLE IF NOT EXISTS ct_timesheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    person_id TEXT NOT NULL,                   -- 人员标识（姓名或工号）
    work_date TEXT NOT NULL,                   -- 工作日期 YYYY-MM-DD
    hours REAL NOT NULL DEFAULT 0,             -- 工时数（0-24）
    work_type TEXT,                            -- 工作类型
    description TEXT,                          -- 工作描述
    status TEXT DEFAULT 'pending',             -- pending | approved | rejected
    approver TEXT,                             -- 审批人
    approved_by TEXT,                          -- 审批人（冗余）
    approved_at TEXT,                          -- 审批时间
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_ts_project ON ct_timesheets(project_id);
CREATE INDEX IF NOT EXISTS idx_ct_ts_person ON ct_timesheets(person_id);
CREATE INDEX IF NOT EXISTS idx_ct_ts_date ON ct_timesheets(work_date);
CREATE INDEX IF NOT EXISTS idx_ct_ts_status ON ct_timesheets(status);
CREATE INDEX IF NOT EXISTS idx_ct_ts_deleted ON ct_timesheets(deleted_at);
```

#### 4.2.2 ct_staff_rates（人员单价表）

```sql
CREATE TABLE IF NOT EXISTS ct_staff_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_name TEXT NOT NULL DEFAULT '',       -- 人员姓名
    role TEXT NOT NULL,                        -- 角色
    level TEXT DEFAULT '',                     -- 级别
    rate REAL NOT NULL DEFAULT 0,              -- 工时单价（元/小时）
    currency TEXT DEFAULT 'CNY',               -- 币种
    effective_date TEXT,                       -- 生效日期
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    UNIQUE(person_name, role, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_ct_sr_person ON ct_staff_rates(person_name);
```

#### 4.2.3 ct_device_usage（设备使用表）

```sql
CREATE TABLE IF NOT EXISTS ct_device_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    device_name TEXT NOT NULL,                 -- 设备名称
    start_date TEXT,                           -- 开始日期
    end_date TEXT,                             -- 结束日期
    cost_per_day REAL DEFAULT 0,               -- 日租金
    total_cost REAL DEFAULT 0,                 -- 总成本
    status TEXT DEFAULT 'in_use',              -- in_use | returned
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_du_project ON ct_device_usage(project_id);
```

#### 4.2.4 ct_travel_costs（差旅费用表）

```sql
CREATE TABLE IF NOT EXISTS ct_travel_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    employee_name TEXT NOT NULL,               -- 员工姓名
    travel_date TEXT NOT NULL,                 -- 出差日期
    cost_type TEXT,                            -- 费用类型（交通/住宿/餐饮/...）
    amount REAL DEFAULT 0,                     -- 金额
    description TEXT,                          -- 描述
    status TEXT DEFAULT 'submitted',           -- submitted | approved | rejected
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_tc_project ON ct_travel_costs(project_id);
CREATE INDEX IF NOT EXISTS idx_ct_tc_date ON ct_travel_costs(travel_date);
```

### 4.3 风险子引擎表

#### 4.3.1 rk_risks（风险记录表）

```sql
CREATE TABLE IF NOT EXISTS rk_risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_no TEXT UNIQUE NOT NULL,              -- 风险编号 RISK-YYYYMMDD-NNNN
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    risk_type TEXT NOT NULL,                   -- 风险类型（scope/schedule/cost/resource/quality）
    risk_level TEXT DEFAULT 'medium',          -- critical | high | medium | low
    title TEXT NOT NULL,                       -- 风险标题
    description TEXT,                          -- 风险描述
    impact TEXT,                               -- 影响（high/medium/low）
    probability TEXT,                          -- 概率（high/medium/low）
    reporter TEXT NOT NULL,                    -- 上报人
    status TEXT DEFAULT 'open',                -- open | assessing | mitigating | accepted | transferred | avoided | closed
    owner TEXT,                                -- 责任人
    due_date TEXT,                             -- 截止日期
    closed_at TEXT,                            -- 关闭时间
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_rk_project ON rk_risks(project_id);
CREATE INDEX IF NOT EXISTS idx_rk_status ON rk_risks(status);
CREATE INDEX IF NOT EXISTS idx_rk_level ON rk_risks(risk_level);
CREATE INDEX IF NOT EXISTS idx_rk_type ON rk_risks(risk_type);
CREATE INDEX IF NOT EXISTS idx_rk_deleted ON rk_risks(deleted_at);
```

#### 4.3.2 rk_risk_history（风险历史记录表）

```sql
CREATE TABLE IF NOT EXISTS rk_risk_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id INTEGER NOT NULL,                  -- FK → rk_risks.id
    from_status TEXT,                          -- 原状态
    to_status TEXT,                            -- 新状态
    action TEXT NOT NULL,                      -- 操作类型
    operator TEXT NOT NULL,                    -- 操作人
    comment TEXT,                              -- 备注
    detail TEXT,                               -- 详情
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (risk_id) REFERENCES rk_risks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rkh_risk ON rk_risk_history(risk_id);
```

#### 4.3.3 rk_risk_actions（风险处置动作表）

```sql
CREATE TABLE IF NOT EXISTS rk_risk_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id INTEGER NOT NULL,                  -- FK → rk_risks.id
    action_type TEXT NOT NULL,                 -- 动作类型（mitigation/escalation/...）
    description TEXT,                          -- 描述
    owner TEXT,                                -- 责任人
    due_date TEXT,                             -- 截止日期
    status TEXT DEFAULT 'pending',             -- pending | in_progress | completed
    completed_at TEXT,                         -- 完成时间
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (risk_id) REFERENCES rk_risks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rka_risk ON rk_risk_actions(risk_id);
```

### 4.4 变更管理表

#### 4.4.1 ch_change_requests（变更请求表）

```sql
CREATE TABLE IF NOT EXISTS ch_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,               -- FK → pm_projects.id
    change_type TEXT NOT NULL,                 -- scope | schedule | cost | resource | quality
    title TEXT NOT NULL,                       -- 变更标题
    description TEXT,                          -- 变更描述
    reason TEXT,                               -- 变更原因
    proposed_changes TEXT,                     -- 拟变更内容
    status TEXT DEFAULT 'draft',               -- draft | submitted | assessing | approved | rejected | executing | completed | cancelled
    impact_delivery_days INTEGER DEFAULT 0,    -- 交付影响天数
    impact_cost_delta REAL DEFAULT 0,          -- 成本影响金额
    impact_revenue_delta REAL DEFAULT 0,       -- 收入影响金额
    submitted_by TEXT,                         -- 提交人
    submitted_at TEXT,                         -- 提交时间
    approved_by TEXT,                          -- 审批人
    approved_at TEXT,                          -- 审批时间
    executed_at TEXT,                          -- 执行时间
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ch_project ON ch_change_requests(project_id);
CREATE INDEX IF NOT EXISTS idx_ch_status ON ch_change_requests(status);
CREATE INDEX IF NOT EXISTS idx_ch_deleted ON ch_change_requests(deleted_at);
```

### 4.5 枚举定义

```python
class ProjectStatus(str, Enum):
    INITIATING = "initiating"    # 立项中
    PLANNING = "planning"        # 规划中
    EXECUTING = "executing"      # 执行中
    DELIVERING = "delivering"    # 交付中
    ACCEPTING = "accepting"      # 验收中
    CLOSING = "closing"          # 结项中
    CLOSED = "closed"            # 已结项
    CANCELLED = "cancelled"      # 已取消

class RiskStatus(str, Enum):
    OPEN = "open"
    ASSESSING = "assessing"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    TRANSFERRED = "transferred"
    AVOIDED = "avoided"
    CLOSED = "closed"

class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ChangeStatus(str, Enum):
    SUBMITTED = "submitted"
    ASSESSING = "assessing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TimesheetStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
```

---

## 6. 项目生命周期状态机

### 5.1 状态转换图

```
                    ┌──────────┐
                    │ cancelled │
                    └────▲─────┘
                         │ reactivate
          ┌──────────────┼──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
          │              │              │              │              │              │              │
   ┌──────┴──────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
   │ initiating  │ │ planning  │ │ executing │ │delivering │ │ accepting │ │ closing   │ │  closed   │
   └──────┬──────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └───────────┘
          │              │              │              │              │              │
          │ cancel       │ cancel       │ cancel       │ cancel       │ cancel       │ cancel
          ▼              ▼              ▼              ▼              ▼              ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
   │                                         cancelled                                                │
   └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 合法状态转换矩阵

| From State | 允许的 To State | 触发条件 |
|---|---|---|
| `initiating` | `planning`, `cancelled` | 项目立项完成 / 取消 |
| `planning` | `executing`, `cancelled` | 规划完成，开始执行 / 取消 |
| `executing` | `delivering`, `cancelled` | 实施完成，进入交付 / 取消 |
| `delivering` | `accepting`, `cancelled` | 交付完成，进入验收 / 取消 |
| `accepting` | **`after_sales`**, `closing`, `cancelled` | 验收通过：转售后（含维保） / 直接结项（无维保） / 取消 |
| **`after_sales`** | `closing`, `cancelled` | 售后服务期结束或工单全部关闭，进入结项 / 取消 |
| `closing` | `closed`, `cancelled` | 结项完成 / 取消 |
| `closed` | （终态） | - |
| `cancelled` | `initiating` | 重新激活 |

### 5.3 状态转换与业务操作映射

| 业务操作 | 状态转换 | 前置条件 | 后置动作 |
|---|---|---|---|
| 创建项目 | → `initiating` | - | 创建默认 7 阶段 |
| 启动项目 | `initiating → planning → executing` | 有 PM + 有团队成员 | 更新执行阶段实际开始时间 |
| 提交交付 | `executing → delivering` | 状态为 executing 或 delivering | 创建交付报告记录 |
| 验收通过 | `delivering → accepting` | 无未关闭高风险 | 触发成本结算检查 |
| **转售后** | `accepting → after_sales` | 合同含维保条款 | 创建维保合同 + 事件通知 |
| **售后结束** | `after_sales → closing` | 无未关闭工单 + SLA 无起时 | 售后归档 |
| 结项 | `accepting/after_sales → closing → closed` | 所有风险关闭 + 交付报告已审核 + **无未关闭工单** | 归档项目数据 |
| 取消 | `→ cancelled` | 非 closed 状态 | 记录取消原因 |
| 重新激活 | `cancelled → initiating` | 状态为 cancelled | 重置阶段状态 |

### 5.4 状态机实现

```python
# models.py
VALID_TRANSITIONS: Dict[str, set[str]] = {
    "initiating": {"planning", "cancelled"},
    "planning": {"executing", "cancelled"},
    "executing": {"delivering", "cancelled"},
    "delivering": {"accepting", "cancelled"},
    "accepting": {"after_sales", "closing", "cancelled"},   # 新增 after_sales
    "after_sales": {"closing", "cancelled"},                 # 新增状态
    "closing": {"closed", "cancelled"},
    "closed": set(),
    "cancelled": {"initiating"},
}

def is_valid_transition(from_state: str, to_state: str) -> bool:
    if from_state not in VALID_TRANSITIONS:
        return False
    if to_state == "cancelled":
        return True  # 任意状态都可取消（需权限校验）
    return to_state in VALID_TRANSITIONS[from_state]
```

---

## 7. 风险横向覆盖设计

### 6.1 设计原则

风险横向覆盖 = **每个项目阶段都有风险报备入口** + **独立风险模块贯穿项目生命周期**。

### 6.2 各阶段风险报备入口

| 项目阶段 | 风险报备入口 | 典型风险类型 | 报备时机 |
|---|---|---|---|
| 立项中（initiating） | `report_risk()` | scope, resource | 立项评审时 |
| 规划中（planning） | `report_risk()` | schedule, resource | 规划评审时 |
| 执行中（executing） | `report_risk()` | schedule, cost, resource | 周会/里程碑评审 |
| 交付中（delivering） | `report_risk()` | quality, schedule | 交付评审时 |
| 验收中（accepting） | `report_risk()` | quality, scope | 验收评审时 |
| 结项中（closing） | `report_risk()` | cost, resource | 结项评审时 |

**实现方式**：
- `report_risk()` 不限制项目当前状态（任何阶段均可报备）
- 风险记录通过 `project_id` 关联到项目
- 风险等级自动计算（probability × impact 矩阵）

### 6.3 独立风险模块

风险子引擎（`risk/`）是独立于项目管理主引擎的子模块：

```
project_management/
├── engine.py              # 项目主引擎（不处理风险）
├── service.py             # 编排服务（委托风险引擎）
└── risk/
    ├── engine.py          # 风险引擎（独立生命周期）
    ├── service.py         # 风险服务（独立事务）
    └── exporter.py        # 风险导出
```

**独立性体现**：
- 风险引擎有独立的状态机（open → assessing → mitigating → closed）
- 风险引擎有独立的数据表（rk_risks, rk_risk_history, rk_risk_actions）
- 风险引擎可独立使用（不依赖项目引擎）
- 风险引擎有独立的 CLI 命令

### 6.4 风险等级矩阵

| Probability \ Impact | High | Medium | Low |
|---|---|---|---|
| **High** | **critical** | **high** | medium |
| **Medium** | **high** | medium | low |
| **Low** | medium | low | low |

```python
RISK_LEVEL_MATRIX: Dict[tuple[str, str], str] = {
    ("high", "high"): "critical",
    ("high", "medium"): "high",
    ("high", "low"): "medium",
    ("medium", "high"): "high",
    ("medium", "medium"): "medium",
    ("medium", "low"): "low",
    ("low", "high"): "medium",
    ("low", "medium"): "low",
    ("low", "low"): "low",
}
```

### 6.5 风险状态机

```
┌──────┐    review     ┌──────────┐   mitigate   ┌───────────┐
│ open │─────────────▶│ assessing│─────────────▶│ mitigating│
└──────┘              └────┬─────┘              └─────┬─────┘
                          │                          │
                          │ accept                   │
                          ▼                          │
                    ┌──────────┐                    │
                    │ accepted │                    │
                    └────┬─────┘                    │
                         │                          │
                          │ transfer                │
                          ▼                          │
                    ┌───────────┐                  │
                    │ transferred│                 │
                    └─────┬─────┘                  │
                          │                        │
                          │ avoid                  │
                          ▼                        │
                    ┌──────────┐                  │
                    │ avoided  │                  │
                    └────┬─────┘                  │
                         │                        │
                         └──────────┬─────────────┘
                                    ▼
                              ┌──────────┐
                              │  closed  │
                              └──────────┘
```

### 6.6 风险与项目生命周期联动

| 项目操作 | 风险联动 |
|---|---|
| 启动项目 | 无强制要求（允许有 open 风险） |
| 提交交付 | 无强制要求 |
| 验收（accept_project） | **强制检查**：无未关闭的 critical/high 风险 |
| 结项（close_project） | **强制检查**：所有风险已关闭 |
| 取消项目 | 所有 open 风险自动标记为 `transferred` |

---

## 8. 成本子引擎接口

### 7.1 CostEngine（成本核算引擎）

#### 7.1.1 `submit_timesheet(project_id, person_id, work_date, hours, **data) -> int`

提交工时记录。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `person_id` | str | ✅ | - | 人员标识 |
| `work_date` | str | ✅ | - | 工作日期 YYYY-MM-DD |
| `hours` | float | ✅ | - | 工时数（0-24） |
| `work_type` | str | ❌ | `""` | 工作类型 |
| `description` | str | ❌ | `""` | 工作描述 |

**Returns**: `int` — timesheet_id

**幂等性**：同一项目+人+日期+类型的 `pending` 记录，更新 hours 而非新建。

**Raises**:
- `ValidationError` — hours ≤ 0 或 > 24，或缺少必填字段

---

#### 7.1.2 `approve_timesheet(timesheet_id, approver, approved, comment) -> None`

审批工时记录。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `timesheet_id` | int | ✅ | 工时记录 ID |
| `approver` | str | ✅ | 审批人 |
| `approved` | bool | ✅ | 是否通过 |
| `comment` | str | ❌ | 审批意见 |

**状态转换**：`pending → approved | rejected`

**Raises**:
- `NotFoundError` — 记录不存在
- `ValidationError` — 记录非 pending 状态

---

#### 7.1.3 `set_staff_rate(person_name, rate, **data) -> int`

设置人员工时单价。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `person_name` | str | ✅ | - | 人员姓名 |
| `rate` | float | ✅ | - | 单价（元/小时） |
| `role` | str | ❌ | `""` | 角色 |
| `currency` | str | ❌ | `"CNY"` | 币种 |
| `effective_date` | str | ❌ | 今天 | 生效日期 |

**Returns**: `int` — rate_id

---

#### 7.1.4 `get_staff_rate(person_name, currency) -> float`

获取人员工时单价。找不到返回 0。

---

#### 7.1.5 `record_device_usage(project_id, device_id, usage_hours, **data) -> int`

登记设备使用记录。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `device_id` | str | ✅ | - | 设备标识 |
| `usage_hours` | float | ✅ | - | 使用小时数 |
| `cost` | float | ❌ | `0.0` | 成本 |
| `usage_date` | str | ❌ | 今天 | 使用日期 |

**Returns**: `int` — 记录 ID

---

#### 7.1.6 `add_travel_cost(project_id, person_name, amount, **data) -> int`

添加差旅费用记录。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `person_name` | str | ✅ | - | 员工姓名 |
| `amount` | float | ✅ | - | 金额（≥0） |
| `destination` | str | ❌ | `""` | 目的地 |
| `expense_date` | str | ❌ | 今天 | 费用日期 |
| `description` | str | ❌ | `""` | 描述 |

**Returns**: `int` — 记录 ID

---

#### 7.1.7 `get_cost_summary(project_id, **data) -> dict`

获取项目成本汇总。

**Returns**:
```python
{
    "total": float,               # 总成本
    "labor_cost": float,          # 工时成本（approved × rate）
    "device_cost": float,         # 设备成本
    "travel_cost": float,         # 差旅成本
    "total_hours": float,         # 总工时
    "by_person": [{               # 按人统计
        "person_id": str,
        "hours": float,
        "rate": float,
        "cost": float
    }],
    "by_month": [{                # 按月统计
        "month": str,
        "labor_cost": float,
        "device_cost": float,
        "travel_cost": float,
        "total": float
    }]
}
```

**成本计算规则**：
- 工时成本 = `SUM(approved_hours × staff_rate)`，仅 `approved` 状态计入
- 设备成本 = `SUM(total_cost)`
- 差旅成本 = `SUM(amount)`

---

### 7.2 CostService（成本管理服务）

| 方法 | 说明 |
|---|---|
| `submit_timesheet(**kwargs) -> int` | 提交工时 |
| `approve_timesheet(timesheet_id, approver, approved, comment) -> None` | 审批工时 |
| `list_timesheets(**kwargs) -> tuple[list, int]` | 查询工时记录 |
| `batch_approve_timesheets(timesheet_ids, approver, approved) -> int` | 批量审批工时 |
| `record_device_usage(**kwargs) -> int` | 登记设备使用 |
| `list_device_usage(project_id, **kwargs) -> list[dict]` | 查询设备使用 |
| `add_travel_cost(**kwargs) -> int` | 添加差旅费用 |
| `sync_travel_cost(project_id, records) -> int` | 批量同步差旅 |
| `list_travel_costs(project_id, **kwargs) -> list[dict]` | 查询差旅费用 |
| `set_staff_rate(**kwargs) -> int` | 设置人员单价 |
| `get_staff_rate(person_name) -> float` | 获取人员单价 |
| `get_cost_summary(project_id, **kwargs) -> dict` | 成本汇总 |

---

## 9. 风险子引擎接口

### 8.1 RiskEngine（风险管理引擎）

#### 8.1.1 `report_risk(**data) -> int`

上报风险。初始状态: `open`。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_id` | int | ✅ | - | 项目 ID |
| `title` | str | ✅ | - | 风险标题 |
| `description` | str | ❌ | `""` | 风险描述 |
| `risk_type` | str | ❌ | `""` | 风险类型 |
| `probability` | str | ❌ | `"medium"` | 概率 |
| `impact` | str | ❌ | `"medium"` | 影响 |
| `reporter` | str | ❌ | `"system"` | 上报人 |
| `owner` | str | ❌ | `""` | 责任人 |
| `due_date` | str | ❌ | `None` | 截止日期 |

**Returns**: `int` — risk_id

**自动计算**：`risk_level = calculate_risk_level(probability, impact)`

**Raises**:
- `ValidationError` — title 为空，或 probability/impact 非法

---

#### 8.1.2 `review_risk(risk_id, reviewer, action, **data) -> None`

风险评审：确定处置策略。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `risk_id` | int | ✅ | 风险 ID |
| `reviewer` | str | ✅ | 评审人 |
| `action` | str | ✅ | 处置策略（mitigate/accept/transfer/avoid） |
| `action_plan` | str | ❌ | 处置计划 |
| `owner` | str | ❌ | 责任人 |
| `due_date` | str | ❌ | 截止日期 |

**状态转换**：
- `open → assessing → mitigating`（mitigate）
- `open → assessing → accepted`（accept）
- `open → assessing → transferred`（transfer）
- `open → assessing → avoided`（avoid）

**Raises**:
- `ValidationError` — action 非法或状态不允许

---

#### 8.1.3 `escalate(risk_id, escalate_to, reason, operator) -> None`

风险升级：上报给更高级别处理。

**效果**：
- 写入历史记录
- 风险等级升一级（low→medium→high→critical）

---

#### 8.1.4 `close_risk(risk_id, closer, close_reason) -> None`

关闭风险。

**允许从以下状态关闭**：`assessing`, `mitigating`, `accepted`, `transferred`, `avoided`

**幂等性**：已关闭的风险再次关闭不报错。

---

#### 8.1.5 `get_risk_summary(project_id) -> dict`

获取项目风险汇总。

**Returns**:
```python
{
    "total": int,
    "open": int,
    "assessing": int,
    "mitigating": int,
    "accepted": int,
    "transferred": int,
    "avoided": int,
    "closed": int,
    "by_level": {"critical": int, "high": int, "medium": int, "low": int},
    "by_type": {type: count, ...}
}
```

---

### 8.2 RiskService（风险管理服务）

| 方法 | 说明 |
|---|---|
| `report_risk(**kwargs) -> int` | 上报风险 |
| `review_risk(**kwargs) -> None` | 评审风险 |
| `close_risk(risk_id, closer, close_reason) -> None` | 关闭风险 |
| `escalate_risk(risk_id, escalate_to, reason, operator) -> None` | 升级风险 |
| `get_risk(risk_id) -> dict` | 获取风险详情（含历史和处置动作） |
| `list_risks(**kwargs) -> tuple[list, int]` | 查询风险列表 |
| `get_risk_summary(project_id) -> dict` | 风险汇总 |
| `update_risk(risk_id, **kwargs) -> None` | 更新风险信息 |
| `batch_close_risks(risk_ids, closer, reason) -> int` | 批量关闭风险 |

---

## 10. 四类实施管理

### 9.1 实施类型定义

| 实施类型 | 字段标记 | 核心交付物 | 适用场景 |
|---|---|---|---|
| **产品实施** | `impl_product = 1` | 产品授权 + 部署文档 | 标准产品交付 |
| **安服实施** | `impl_security = 1` | 安全服务报告 | 等保测评/风险评估/渗透测试 |
| **定制开发** | `impl_custom = 1` | 定制功能 + 验收文档 | 客户定制需求 |
| **外包/外采** | `impl_outsourcing = 1` | 外包交付物 + 验收记录 | 第三方外包服务 |

### 9.2 实施类型与流程节点映射

| 实施类型 | PRD 流程节点 | 关键活动 |
|---|---|---|
| 产品实施 | #5-1 任务 → #5-2 执行 → #5-3 管理 | 产品部署、授权配置、操作培训 |
| 安服实施 | #6-1 任务 → #6-2 执行 → #6-3 管理 | 安全测评、报告编制、整改建议 |
| 定制开发 | #7-1 需求 → #7-2 执行 | 需求确认、开发、测试、部署 |
| 外包/外采 | #8-1 申请 → #8-2 管理 | 外包申请、合同签订、验收 |

### 9.3 实施类型与成本归集

| 实施类型 | 工时归集 | 设备归集 | 差旅归集 |
|---|---|---|---|
| 产品实施 | ✅ 工程师工时 | ✅ 测试设备 | ✅ 客户现场差旅 |
| 安服实施 | ✅ 安服工程师工时 | ✅ 安全设备 | ✅ 客户现场差旅 |
| 定制开发 | ✅ 开发人员工时 | ✅ 开发设备 | ✅ 客户现场差旅 |
| 外包/外采 | ❌（外包工时单独核算） | ❌ | ✅ 差旅（如有） |

### 9.4 实施类型与里程碑模板

| 实施类型 | 默认里程碑 |
|---|---|
| 产品实施 | ① 合同签订 → ② 设备到货 → ③ 部署完成 → ④ 培训完成 → ⑤ 确收交接 → ⑥ 验收通过 |
| 安服实施 | ① 合同签订 → ② 方案确认 → ③ 现场实施 → ④ 报告编制 → ⑤ 报告提交 → ⑥ 验收通过 |
| 定制开发 | ① 需求确认 → ② 方案设计 → ③ 开发完成 → ④ 测试通过 → ⑤ 部署上线 → ⑥ 验收通过 |
| 外包/外采 | ① 外包申请 → ② 合同签订 → ③ 交付物验收 → ④ 集成测试 → ⑤ 验收通过 |

### 9.5 实施类型与风险特征

| 实施类型 | 典型风险 | 建议概率 | 建议影响 |
|---|---|---|---|
| 产品实施 | 设备到货延迟 | medium | high |
| 产品实施 | 客户环境不兼容 | low | high |
| 安服实施 | 客户配合度低 | high | medium |
| 安服实施 | 测评范围变更 | medium | high |
| 定制开发 | 需求变更频繁 | high | high |
| 定制开发 | 技术方案不可行 | low | critical |
| 外包/外采 | 供应商交付延迟 | high | high |
| 外包/外采 | 交付质量不达标 | medium | critical |

### 9.6 实施类型与交付报告模板

| 实施类型 | 交付报告类型 | 必填内容 |
|---|---|---|
| 产品实施 | `delivery_product` | 部署清单、授权信息、培训记录 |
| 安服实施 | `delivery_security` | 测评报告、整改建议、复测结果 |
| 定制开发 | `delivery_custom` | 需求文档、测试报告、部署文档 |
| 外包/外采 | `delivery_outsourcing` | 验收记录、测试报告、交接清单 |

---

## 11. 错误处理

### 10.1 异常体系

```
BDMSBaseError (code: BDMS_BASE_ERROR)
├── NotFoundError (code: NOT_FOUND)
│   └── 资源不存在（项目、阶段、成员、风险、工时记录等）
├── ValidationError (code: VALIDATION_ERROR)
│   └── 数据校验失败（必填字段、值范围、业务规则等）
├── StateTransitionError (code: STATE_TRANSITION_ERROR)
│   └── 状态转换非法（项目状态、风险状态等）
├── ImportError_ (code: IMPORT_ERROR)
│   └── 数据导入失败
└── ExportError (code: EXPORT_ERROR)
    └── 数据导出失败
```

### 10.2 错误码定义

| 错误码 | HTTP 状态码 | 说明 | 触发场景 |
|---|---|---|---|
| `NOT_FOUND` | 404 | 资源不存在 | 项目/风险/工时记录 ID 不存在 |
| `VALIDATION_ERROR` | 400 | 数据校验失败 | 必填字段为空、值越界、业务规则违反 |
| `STATE_TRANSITION_ERROR` | 409 | 状态转换非法 | 非法的项目状态转换 |
| `IMPORT_ERROR` | 422 | 数据导入失败 | 文件格式错误、数据格式不匹配 |
| `EXPORT_ERROR` | 500 | 数据导出失败 | 文件写入失败、磁盘空间不足 |
| `BDMS_BASE_ERROR` | 500 | 通用错误 | 其他未分类错误 |

### 10.3 错误处理策略

| 策略 | 说明 |
|---|---|
| **快速失败** | 参数校验失败立即抛出 `ValidationError`，不进入业务逻辑 |
| **状态保护** | 状态转换前校验合法性，非法转换抛出 `StateTransitionError` |
| **软删除** | 删除操作只标记 `deleted_at`，不物理删除数据 |
| **幂等设计** | 重复执行同一操作不产生副作用（如重复关闭风险） |
| **事务保护** | 跨表操作使用事务（`with transaction()`），失败自动回滚 |
| **错误传播** | 引擎层抛出原始异常，服务层包装为业务异常，API 层映射为 HTTP 状态码 |

### 10.4 关键校验规则

| 校验项 | 规则 | 错误类型 |
|---|---|---|
| 项目名称 | 非空 | `ValidationError` |
| 项目编号 | 唯一 | `ValidationError`（DB 约束） |
| 项目状态转换 | 必须在 `VALID_TRANSITIONS` 中 | `StateTransitionError` |
| 工时数 | 0 < hours ≤ 24 | `ValidationError` |
| 人员单价 | rate ≥ 0 | `ValidationError` |
| 差旅金额 | amount ≥ 0 | `ValidationError` |
| 风险概率 | high/medium/low | `ValidationError` |
| 风险影响 | high/medium/low | `ValidationError` |
| 风险类型 | scope/schedule/cost/resource/quality | `ValidationError` |
| 变更类型 | scope/schedule/cost/resource/quality | `ValidationError` |
| 结项前置 | 所有风险已关闭 | `ValidationError` |
| 结项前置 | 所有交付报告已审核 | `ValidationError` |
| 验收前置 | 无未关闭高风险 | `ValidationError` |
| 启动前置 | 必须有 PM | `ValidationError` |
| 启动前置 | 至少有一个团队成员 | `ValidationError` |

---

## 12. CLI 命令

### 11.1 项目命令

```bash
# 创建项目
bdms project create \
  --name "等保测评-某银行" \
  --type "等保测评" \
  --dept "安全服务部" \
  --pm "张三" \
  --budget 50000 \
  --start 2026-09-01 \
  --end 2026-12-31

# 查看项目详情
bdms project show <project_id>

# 项目列表
bdms project list [--status executing] [--pm 张三] [--keyword 银行]

# 启动项目
bdms project start <project_id> --operator 张三

# 提交交付报告
bdms project deliver <project_id> \
  --type delivery_product \
  --title "产品部署完成" \
  --content "已完成产品部署和培训"

# 验收项目
bdms project accept <project_id> --operator 张三

# 结项
bdms project close <project_id> --operator 张三 --summary "项目正常结项"

# 取消项目
bdms project cancel <project_id> --reason "客户原因取消" --operator 张三

# 重新激活
bdms project reactivate <project_id> --operator 张三

# 项目仪表盘
bdms project dashboard <project_id>

# 利润汇总
bdms project profit <project_id>

# 财务健康度评分
bdms project health <project_id>
```

### 11.2 成员与里程碑命令

```bash
# 添加团队成员
bdms project member add <project_id> \
  --name "李四" --role "工程师" --allocation 0.8

# 添加里程碑
bdms project milestone add <project_id> \
  --name "部署完成" --date 2026-10-15

# 查看阶段
bdms project phases <project_id>
```

### 11.3 成本命令

```bash
# 提交工时
bdms project timesheet submit \
  --project <project_id> \
  --person "李四" \
  --date 2026-09-20 \
  --hours 8 \
  --type "安服实施"

# 审批工时
bdms project timesheet approve <timesheet_id> --approver 张三

# 批量审批
bdms project timesheet batch-approve <id1> <id2> <id3> --approver 张三

# 设置人员单价
bdms project rate set --person "李四" --role "工程师" --rate 500

# 登记设备使用
bdms project device add \
  --project <project_id> \
  --device "渗透测试设备" \
  --hours 16 \
  --cost 2000

# 添加差旅费用
bdms project travel add \
  --project <project_id> \
  --person "李四" \
  --amount 3500 \
  --destination "北京" \
  --date 2026-09-15

# 成本汇总
bdms project cost-summary <project_id>

# 导出成本明细
bdms project cost-export <project_id> --out cost_detail.csv
```

### 11.4 风险命令

```bash
# 上报风险
bdms project risk report \
  --project <project_id> \
  --title "客户配合度低" \
  --type resource \
  --probability high \
  --impact medium \
  --reporter 张三 \
  --owner 张三

# 风险评审
bdms project risk review <risk_id> \
  --reviewer 张三 \
  --action mitigate \
  --plan "安排专人对接客户"

# 风险升级
bdms project risk escalate <risk_id> \
  --to "部门经理" \
  --reason "客户多次推迟"

# 关闭风险
bdms project risk close <risk_id> --closer 张三 --reason "已解决"

# 风险列表
bdms project risk list --project <project_id> [--status open]

# 风险汇总
bdms project risk summary --project <project_id>

# 导出风险登记册
bdms project risk export --project <project_id> --out risk_register.csv
```

### 11.5 变更命令

```bash
# 提交变更请求
bdms project change submit \
  --project <project_id> \
  --title "增加测评范围" \
  --type scope \
  --description "客户要求增加 3 个系统" \
  --reason "客户需求变更"

# 评估变更影响
bdms project change assess <change_id> \
  --assessor 张三 \
  --delivery-impact "延期 5 天" \
  --cost-impact 10000

# 审批变更
bdms project change approve <change_id> --approver 张三 --decision approved

# 执行变更
bdms project change execute <change_id> --executor 张三

# 变更日志
bdms project change log --project <project_id>
```

---

## 13. 测试策略

### 12.1 测试分层

| 测试类型 | 覆盖范围 | 工具 | 执行频率 |
|---|---|---|---|
| **单元测试** | 引擎层 CRUD + 状态机 + 计算逻辑 | pytest | 每次提交 |
| **集成测试** | 服务层编排 + 跨引擎事务 | pytest + 真实 SQLite | 每次提交 |
| **E2E 测试** | 完整项目生命周期（立项→结项） | pytest + 真实 SQLite | 每次提交 |
| **API 测试** | REST API 全路径 | 真实 HTTP（urllib） | 发布前 |
| **回归测试** | 黄金基准对比（项目数据完整性） | pytest | 发布前 |

### 12.2 单元测试用例

#### 12.2.1 项目 CRUD + 软删除

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 创建项目（正常） | project_name="测试项目" | 返回 project_id > 0，状态为 initiating |
| 创建项目（无名称） | project_name="" | 抛出 ValidationError |
| 更新项目 | project_name="新名称" | 名称更新成功 |
| 更新项目（改状态） | status="executing" | 状态字段被忽略 |
| 软删除项目 | project_id=1 | deleted_at 非空，list 查不到 |
| 恢复已删除项目 | include_deleted=True | 能查到已删除项目 |

#### 12.2.2 状态机

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 合法转换 | initiating → planning | 成功，新状态为 planning |
| 非法转换 | initiating → executing | 抛出 StateTransitionError |
| 取消（任意状态） | executing → cancelled | 成功 |
| 重新激活 | cancelled → initiating | 成功 |
| 幂等转换 | planning → planning | 返回原状态，不报错 |
| 已结项 → 任意 | closed → executing | 抛出 StateTransitionError |

#### 12.2.3 阶段/团队/里程碑

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 添加阶段 | phase_name="执行阶段" | 返回 phase_id > 0 |
| 添加团队成员 | member_name="张三", role="PM" | 返回 member_id > 0 |
| 重复成员 | 同一 project_id + member_name + role | 违反唯一约束 |
| 添加里程碑 | milestone_name="部署完成" | 返回 milestone_id > 0 |
| 更新里程碑状态 | status="completed" | 更新成功 |

#### 12.2.4 成本引擎

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 提交工时（正常） | hours=8 | 返回 timesheet_id > 0 |
| 提交工时（超限） | hours=25 | 抛出 ValidationError |
| 提交工时（负数） | hours=-1 | 抛出 ValidationError |
| 审批工时（通过） | approved=True | 状态变为 approved |
| 审批工时（重复） | 再次审批 | 抛出 ValidationError |
| 设置人员单价 | rate=500 | 返回 rate_id > 0 |
| 工时成本计算 | 8h × 500元/h | labor_cost=4000 |
| 成本汇总 | 三类成本 | total = labor + device + travel |

#### 12.2.5 风险引擎

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 上报风险（正常） | title="测试风险" | 返回 risk_id > 0，状态为 open |
| 风险等级计算 | probability=high, impact=high | risk_level=critical |
| 风险评审（mitigate） | action=mitigate | 状态: open→assessing→mitigating |
| 风险评审（accept） | action=accept | 状态: open→assessing→accepted |
| 关闭风险 | risk_id | 状态变为 closed |
| 重复关闭 | 再次关闭 | 幂等，不报错 |
| 风险升级 | escalate_to="部门经理" | 风险等级升一级 |

### 12.3 集成测试用例

| 用例 | 步骤 | 预期输出 |
|---|---|---|
| 创建项目 + 启动 | create → add_member → start | 状态: initiating→planning→executing |
| 创建项目 + 启动（无 PM） | create(no pm) → start | 抛出 ValidationError |
| 创建项目 + 启动（无成员） | create → start | 抛出 ValidationError |
| 提交交付 + 验收 | submit_delivery → accept | 状态: executing→delivering→accepting |
| 验收（有高风险） | submit_delivery → report_risk(critical) → accept | 抛出 ValidationError |
| 全流程 | create → start → deliver → accept → close | 最终状态: closed |
| 结项（有未关闭风险） | create → start → deliver → accept → report_risk → close | 抛出 ValidationError |
| 利润汇总 | create(budget=100000) → submit_timesheet(approved) → profit | 返回利润汇总 |

### 12.4 E2E 测试用例

#### 12.4.1 完整项目生命周期

```python
def test_project_lifecycle_e2e(db_path):
    """端到端：立项 → 启动 → 执行 → 交付 → 验收 → 结项"""
    svc = ProjectManagementService(db_path=db_path)

    # 1. 立项
    pid = svc.create_project(
        project_name="等保测评-测试",
        project_type="等保测评",
        dept="安全服务部",
        pm="张三",
        budget=50000,
    )
    assert svc.get_project(pid)["status"] == "initiating"

    # 2. 添加团队成员
    svc.project_engine.add_team_member(pid, "李四", "工程师")

    # 3. 启动
    svc.start_project(pid, "张三")
    assert svc.get_project(pid)["status"] == "executing"

    # 4. 提交工时
    svc.cost_service.submit_timesheet(
        project_id=pid, person_id="李四",
        work_date="2026-09-20", hours=8, work_type="安服实施"
    )

    # 5. 提交交付
    svc.submit_delivery(pid, "delivery_security", "安全测评报告", "张三")
    assert svc.get_project(pid)["status"] == "delivering"

    # 6. 验收
    svc.accept_project(pid, operator="张三")
    assert svc.get_project(pid)["status"] == "accepting"

    # 7. 结项
    svc.close_project(pid, operator="张三", summary="正常结项")
    assert svc.get_project(pid)["status"] == "closed"
```

#### 12.4.2 风险处置全流程

```python
def test_risk_lifecycle_e2e(db_path):
    """端到端：风险上报 → 评审 → 处置 → 关闭"""
    svc = ProjectManagementService(db_path=db_path)
    pid = svc.create_project(project_name="测试", pm="张三")
    svc.project_engine.add_team_member(pid, "李四", "工程师")
    svc.start_project(pid)

    # 上报风险
    rid = svc.report_risk(
        project_id=pid,
        title="客户配合度低",
        probability="high",
        impact="medium",
        reporter="张三",
    )
    risk = svc.risk_service.get_risk(rid)
    assert risk["risk"]["status"] == "open"
    assert risk["risk"]["risk_level"] == "high"

    # 评审
    svc.resolve_risk(rid, action="mitigate", reviewer="张三", action_plan="专人对接")
    risk = svc.risk_service.get_risk(rid)
    assert risk["risk"]["status"] == "mitigating"

    # 关闭
    svc.risk_service.close_risk(rid, closer="张三", close_reason="已解决")
    risk = svc.risk_service.get_risk(rid)
    assert risk["risk"]["status"] == "closed"
```

### 12.5 API 测试（真实 HTTP）

| 用例 | 请求 | 预期响应 |
|---|---|---|
| 创建项目 | `POST /project/create` | 200, project_id |
| 获取项目 | `GET /project/{id}` | 200, 项目详情 |
| 项目列表 | `GET /project/list` | 200, items + total |
| 不存在项目 | `GET /project/99999` | 404 |
| 启动项目 | `POST /project/{id}/start` | 200 |
| 非法状态转换 | `POST /project/{id}/transition` | 409 |
| 风险报备 | `POST /project/{id}/risk` | 200, risk_id |
| 成本汇总 | `GET /project/{id}/cost-summary` | 200, 成本数据 |

### 12.6 性能测试基准

| 场景 | 数据量 | 目标响应时间 |
|---|---|---|
| 创建项目 | 单次 | < 100ms |
| 项目列表（分页） | 1000 个项目 | < 200ms |
| 成本汇总 | 10000 条工时记录 | < 500ms |
| 风险汇总 | 500 条风险记录 | < 200ms |
| 项目仪表盘 | 全量聚合 | < 300ms |

---

## 附录 A：数据库迁移注意事项

从 v1.0 到 v2.1 的迁移：

1. **新增表**：`pm_projects`, `pm_phases`, `pm_team_members`, `pm_milestones`, `pm_delivery_reports`, `ct_timesheets`, `ct_staff_rates`, `ct_device_usage`, `ct_travel_costs`, `rk_risks`, `rk_risk_history`, `rk_risk_actions`, `ch_change_requests`
2. **外键约束**：`pm_projects.contract_id` → `cr_contracts.id`（需先创建合同表）
3. **索引**：所有外键列和查询列已建索引
4. **数据迁移**：v1.0 无项目管理数据，无需历史数据迁移

## 附录 B：复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `BaseEngine` | `modules/base.py` | **继承** | 子类化 | `class ProjectEngine(BaseEngine): ...` |
| `BaseService` | `modules/base.py` | **继承** | 子类化 | `class ProjectService(BaseService): ...` |
| `BaseExporter` | `modules/base.py` | **继承** | 子类化 | `class ProjectExporter(BaseExporter): ...` |
| `BaseImporter` | `modules/base.py` | **继承** | 子类化 | `class ProjectImporter(BaseImporter): ...` |
| `BaseRepository` | `modules/base_repository.py` | **继承** | 子类化 | `class ProjectRepository(BaseRepository): ...` |
| `AuditMixin` | `modules/base.py` | **Mixin 组合** | 多继承 | `class ProjectService(BaseService, AuditMixin): ...` |
| `SoftDeleteMixin` | `modules/base.py` | **Mixin 组合** | 多继承 | `class ProjectService(BaseService, SoftDeleteMixin): ...` |
| `get_connection()` | `core/db.py` | **import 引用** | 直接调用 | `from bdms.core.db import get_connection` |
| `transaction()` | `core/db.py` | **import 引用** | 上下文管理器 | `from bdms.core.db import transaction` |
| `CostEngine` | `modules/project_management/cost/engine.py` | **import 引用** | 直接调用 | `from bdms.modules.project_management.cost.engine import CostEngine` |
| `CostService` | `modules/project_management/cost/service.py` | **import 引用** | 直接调用 | `from bdms.modules.project_management.cost.service import CostService` |
| `RiskEngine` | `modules/project_management/risk/engine.py` | **import 引用** | 直接调用 | `from bdms.modules.project_management.risk.engine import RiskEngine` |
| `RiskService` | `modules/project_management/risk/service.py` | **import 引用** | 直接调用 | `from bdms.modules.project_management.risk.service import RiskService` |
| `OnesConnector` | `modules/integration/connectors/ones.py` | **组合** | 实例化调用 | `from bdms.modules.integration.connectors.ones import OnesConnector` |
| `OaConnector` | `modules/integration/connectors/oa.py` | **组合** | 实例化调用 | `from bdms.modules.integration.connectors.oa import OaConnector` |
| `WeCom API` | `modules/integration/wecom_api.py` | **组合** | 实例化调用 | `from bdms.modules.integration.wecom_api import WeComAPI` |
| L2 OCR-001 | `L2-infra/skills/ocr-digitalization/` | **组合** | 实例化调用 | `from ocr_engine import digitalize_document_v5` |
| L2 Office-011 | `L2-infra/skills/office-generation/` | **组合** | 实例化调用 | `from office_gen import generate_docx` |
| L2 Persistence-006 | `L2-infra/components/persistence/` | **DB 共享** | 读写 SQLite | `get_connection(DATA_DIR/bdms.db)` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] 继承关系正确（子类 → BaseEngine/BaseService/BaseExporter/BaseImporter/BaseRepository）
- [ ] Mixin 组合正确（AuditMixin/SoftDeleteMixin）
- [ ] 子引擎（Cost/Risk）通过 import 引用（非复制）
- [ ] integration 连接器通过组合调用（非本模块重复实现）
- [ ] 无复制粘贴代码块
- [ ] 如需修改源文件功能，通过 PR 修改源文件（非本模块内重写）

## 附录 C：配置项

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `pm.default_phase_template` | `["立项","规划","执行","交付","验收","售后","结项"]` | 默认阶段模板（7 阶段，含售后） |
| `pm.max_daily_hours` | `24` | 每日最大工时 |
| `pm.risk_auto_close_on_cancel` | `true` | 项目取消时自动关闭风险 |
| `pm.profit_alert_threshold` | `15.0` | 利润预警阈值（%） |
| `pm.health_score_weights` | `{"budget":25,"margin":25,"growth":25,"cash":25}` | 健康度评分权重 |
| `pm.sla_response_hours` | `{"critical":2,"high":4,"medium":8,"low":24}` | 售后 SLA 响应时限（小时） |
| `pm.sla_resolve_hours` | `{"critical":24,"high":48,"medium":120,"low":240}` | 售后 SLA 解决时限（小时） |
| `pm.after_sales_warranty_days` | `365` | 默认维保期（天） |

---

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r2 | 2026-09-24 | Rex 审核反馈 2 条：<br>① 编排服务增加售后管理（结项前置）：新增 §3.2.8 完整售后编排（转售后/工单 CRUD/SLA 分级/结项前置检查）；状态机新增 `after_sales` 状态（accepting→after_sales→closing）；阶段模板 6→7 阶段（+售后 55）；close_project 增加无未关闭工单前置校验；配置项 +3（SLA/维保期）<br>② 新增业界最佳实践参考（§1.3）：PMBOK 7 / PRINCE2 / Jira / ITIL 4 / Zendesk / SAP PS / MS Project / SAFe；售后设计原则对齐 ITIL 4（事故/SLA/服务级别/持续改进） |
| v2.1 r1 | 2026-09-22 | 初版 |

---

> **文档结束**
> 下一步：Rex 审核通过后，进入 IMPLEMENTATION-PLAN 阶段。
