# BDMS v2.1 详细设计 — 数据集成模块（integration）

> Bangcle Delivery Management System — 数据集成模块详细设计
> 版本：v2.1 Detail r2（2026-09-22）
> 层级：L4 专有业务层（横切模块）
> 依据：`PRD-v2.1.md` + `DESIGN-OUTLINE-v2.1.md`（已审核通过）
> 状态：待 Rex 审核

## 目录

1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [五个连接器详细设计](#6-五个连接器详细设计)
7. [频率配置设计](#7-频率配置设计)
8. [暂存 → 业务表流转机制](#8-暂存--业务表流转机制)
9. [错误处理与重试机制](#9-错误处理与重试机制)
10. [本机导入设计](#10-本机导入设计)
11. [浏览器自动化集成](#11-浏览器自动化集成)
12. [凭据管理](#12-凭据管理)
13. [错误处理](#13-错误处理)
14. [CLI 命令 + Web API](#14-cli-命令--web-api)
15. [测试策略](#15-测试策略)
附录 B：[复用资产清单与使用方式](#附录-b复用资产清单与使用方式)
[变更历史](#变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版：5 连接器 + OS 适配矩阵 |
| v2.1 Detail r2 | 2026-09-22 | Rex 审核反馈 2 条：浏览器自动化统一 + OS 依赖标注 + 业界最佳实践 |

---

## 1. 模块概述

### 1.1 业务域

数据集成模块（integration）是 BDMS v2.1 的**横切模块**，负责从外部系统（ONES、OA、工时门户、企微文档）和本机导入（Excel/CSV/手工录入）获取数据，经标准化后写入各业务模块的暂存表，再流转至业务表。

**核心职责**：
1. **连接器管理** — 5 个连接器（ones / oa / timesheet / wecom_doc / local_import），每个连接器独立认证、独立配置
2. **数据拉取** — 浏览器自动化（ONES/OA/工时门户，已通过验证）+ API/浏览器/本机导入（企微文档，预留多种方式）+ 本机导入（Excel/CSV/手工录入）
3. **数据标准化** — 将异构数据源统一为 BDMS 标准格式，写入暂存表
4. **频率控制** — 支持人工触发、定时任务（cron 表达式）、事件驱动三种模式
5. **暂存流转** — 暂存表 → 幂等写入业务表 → 事件通知

### 1.2 横切定位

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Agent 层                              │
│   bdms-cli / FastAPI / WebSocket                              │
├─────────────────────────────────────────────────────────────┤
│  contract │ project │ delivery │ revenue │ profit │ dashboard │
├─────────────────────────────────────────────────────────────┤
│              ★ integration（横切层）★                         │
│   ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│   │  ones  │ │  oa    │ │timesheet │ │wecom_doc │ │local_  │ │
│   │connector│ │connector│ │connector │ │connector │ │import  │ │
│   └───┬────┘ └───┬────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
│       │          │            │            │           │      │
│  ┌────┴──────────┴────────────┴────────────┴───────────┴────┐ │
│  │              Staging Layer（暂存层）                       │ │
│  │   staging_ones / staging_oa / staging_timesheet /          │ │
│  │   staging_wecom / staging_local                            │ │
│  └────────────────────────┬──────────────────────────────────┘ │
│                           │ 幂等写入 + 事件通知                  │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │              Business Tables（业务表）                      │ │
│  │   pm_projects / cr_contracts / ct_timesheets / ...        │ │
│  └───────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                   Base 层                                      │
├─────────────────────────────────────────────────────────────┤
│                   Core 层（DB / EventBus / Registry）          │
├─────────────────────────────────────────────────────────────┤
│                   L2 基础设施层                                │
│   credentials / observability / ones-browser-export           │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **Airbyte** | 连接器注册表 + 同步管道 | 连接器插件化 + 统一接口 | BaseConnector 抽象基类 + 注册表 |
| **Fivetran** | 自动化数据同步 | 增量同步 + 变更数据捕获(CDC) | source_id + batch_id 幂等写入 |
| **n8n** | 工作流编排 | 可视化数据流 + 条件分支 | 频率配置 + 事件驱动触发 |
| **Selenium Grid** | 浏览器自动化 | 多浏览器并行 + 会话复用 | 浏览器连接池（ONES/OA/工时） |
| **Playwright** | 现代浏览器自动化 | 自动等待 + 网络拦截 + Headless | 首选浏览器自动化引擎 |
| **Apache NiFi** | 数据路由 | 背压 + 优先级队列 + 重试 | 暂存流转 + 指数退避重试 |
| **dbt** | 数据转换 | 标准化 + 版本控制 + 测试 | normalize() 标准化 + 字段映射 |
| **Prefect/Dagster** | 数据管道编排 | 依赖管理 + 失败告警 | 分步执行 + 状态监控 |

**当前限制与应对**：

| 限制 | 影响 | 应对方案 |
|---|---|---|
| 无管理员权限 | 无法安装系统级服务/驱动 | 纯 Python 方案（Playwright/selenium），用户目录安装 |
| 无数据库直连 | 无法直接读 ONES/OA/工时 DB | 浏览器自动化导出 CSV/Excel |
| 企微 API 权限受限 | 可能无法获取文档内容 | 多技术降级：API → 浏览器 → 本机导入 |
| 网络隔离 | 部分系统仅内网可达 | 确保 BDMS 运行在内网环境 |
| 浏览器登录态过期 | 自动化失败 | Cookie 持久化 + 自动重新登录 + 告警 |
| 无 root 权限 | 无法绑定低端口/安装系统包 | 用户空间运行，端口 > 1024 |

**OS 依赖与条件限制**：

| 技术方案 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|
| **osascript 浏览器控制** | ✅ 原生支持 | ❌ 不适用 | ❌ 不适用 | macOS 独有，通过 AppleScript 控制 Chrome |
| **Playwright Headless** | ✅ 支持 | ✅ 支持 | ✅ 支持 | 跨平台首选，需安装浏览器二进制 |
| **Selenium + ChromeDriver** | ✅ 支持 | ✅ 支持 | ✅ 支持 | 跨平台，需匹配 Chrome 版本 |
| **Selenium + GeckoDriver** | ✅ 支持 | ✅ 支持 | ✅ 支持 | Firefox 备选 |
| **本机 Chrome Cookie 复用** | ✅ 支持 | ✅ 支持 | ✅ 支持 | 需解密 Cookie（各 OS 密钥链不同） |
| **cron 定时任务** | ✅ launchd/cron | ✅ Task Scheduler | ✅ cron | 各 OS 调度器不同 |
| **文件路径** | `~/Library/` | `%APPDATA%` | `~/.config/` | 配置/缓存目录 |
| **Chrome 默认路径** | `/Applications/Google Chrome.exe` | `C:\Program Files\Google\Chrome\chrome.exe` | `/usr/bin/google-chrome` | 浏览器自动化依赖 |
| **密钥链访问** | Keychain Access | DPAPI | libsecret | Cookie/密码解密 |

**OS 技术方案依赖关系**：

```
浏览器自动化（ONES/OA/工时门户）
├── macOS（当前开发环境）
│   ├── 方案 A: osascript + Chrome（已验证，ones-browser-export 技能）
│   ├── 方案 B: Playwright Headless（跨平台备选）
│   └── 方案 C: Selenium + ChromeDriver（兜底）
├── Windows（待适配）
│   ├── 方案 A: pywinauto + Chrome COM 接口
│   ├── 方案 B: Playwright Headless（推荐）
│   └── 方案 C: Selenium + ChromeDriver
└── Linux（待适配）
    ├── 方案 A: Playwright Headless（推荐，无 GUI 环境）
    ├── 方案 B: Selenium + ChromeDriver（Headless）
    └── 方案 C: xdotool + Chrome（X11 环境）

企微文档（I-04）
├── 企微 API（全平台，需网络 + 权限）
├── 浏览器自动化（依赖上述 OS 方案）
└── 本机导入（全平台，无依赖）
```

**当前开发优先级**：macOS 优先（已验证）→ Linux 适配（Playwright Headless）→ Windows 适配。

### 1.4 与其他模块交互

| 交互模块 | 交互方式 | 数据流向 | 说明 |
|---|---|---|---|
| `delivery_report` | 暂存表 → `dr_sheet_row` | integration → delivery_report | ONES 签约/POC/异常/确收/验收数据 |
| `revenue` | 暂存表 → `rr_sheet_row` | integration → revenue | 企微文档确收凭证 + 本机导入预算执行表 |
| `project_management` | 暂存表 → `pm_projects` | integration → project_management | ONES 项目数据 + OA 立项/结项 |
| `contract_management` | 暂存表 → `cr_contracts` | integration → contract_management | OA 合同流程数据 |
| `profit_management` | 暂存表 → `ct_timesheets` | integration → profit_management | 工时门户数据 |
| `dashboard` | 只读各模块数据 | ← dashboard | 不直接交互，通过业务表 |
| `core/event_bus` | 事件通知 | integration → event_bus → 各模块 | 同步完成事件 |

**依赖规则**：
- integration **单向写入**各业务模块的暂存表，不反向依赖
- 各业务模块通过事件总线感知数据更新，不直接调用 integration
- integration 不依赖任何业务模块的实现，只依赖 Core 层（DB / EventBus / Paths）

---

## 2. OS 依赖与限制

> 本模块的浏览器自动化方案与操作系统强相关。详见 §1.3 业界最佳实践中的 OS 适配矩阵，以及 §11 浏览器自动化集成的完整 OS 方案。

## 3. 技术方案

### 3.1 架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                    IntegrationService（编排层）                    │
│  list_connectors / get_connector_status / sync /               │
│  get_staging_data / configure_frequency                          │
├──────────────────────────────────────────────────────────────────┤
│                    Connector Registry（连接器注册表）               │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  name → class 映射（动态加载，支持插件扩展）                 │    │
│  └──────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────┤
│                    BaseConnector（抽象基类）                        │
│  authenticate() / fetch() / normalize() / load_to_staging()       │
├──────┬──────┬──────┬──────┬──────┬────────────────────────────────┤
│ ones │ oa   │ time │ wecom│ local│                                │
│      │      │sheet │ _doc │_import│                               │
├──────┴──────┴──────┴──────┴──────┴────────────────────────────────┤
│                    Data Source Adapters                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │Browser   │ │Browser   │ │HTTP API  │ │WeCom API │ │File    │ │
│  │Automation│ │Automation│ │Client    │ │Client    │ │Parser  │ │
│  │(osascript)│ │(osascript)│ │          │ │          │ │        │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                    Staging Layer（暂存层）                          │
│  int_staging（统一暂存表，JSON 存储异构数据）                        │
├──────────────────────────────────────────────────────────────────┤
│                    Sync Pipeline（同步管道）                        │
│  fetch → normalize → validate → load_to_staging →                │
│  promote_to_business → notify_event                               │
├──────────────────────────────────────────────────────────────────┤
│                    Scheduler（调度器）                              │
│  cron / manual / event-driven                                     │
├──────────────────────────────────────────────────────────────────┤
│                    Error Handler（错误处理）                        │
│  retry w/ backoff / dead letter queue / alert                    │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
src/bdms/modules/integration/
├── __init__.py                    # 模块导出
├── service.py                     # IntegrationService（编排层）
├── registry.py                    # Connector Registry（连接器注册表）
├── base_connector.py              # BaseConnector（抽象基类）
├── connectors/                    # 5 个连接器实现
│   ├── __init__.py
│   ├── ones_connector.py          # I-01: ONES 浏览器自动化
│   ├── oa_connector.py            # I-02: OA 浏览器自动化
│   ├── timesheet_connector.py     # I-03: 工时门户 API
│   ├── wecom_doc_connector.py     # I-04: 企微文档 API
│   └── local_import_connector.py  # I-05: 本机导入（Excel/CSV/手工）
├── adapters/                      # 数据源适配器
│   ├── __init__.py
│   ├── browser_adapter.py         # osascript 浏览器自动化封装
│   ├── http_adapter.py            # HTTP API 客户端（通用）
│   ├── file_parser.py             # Excel/CSV 解析器
│   └── wecom_api_adapter.py       # 企微 API 专用客户端
├── staging.py                     # 暂存层操作（CRUD + 查询）
├── sync_pipeline.py               # 同步管道（fetch→normalize→load→promote）
├── scheduler.py                   # 调度器（cron / manual / event-driven）
├── frequency.py                   # 频率配置管理
├── error_handler.py               # 错误处理（重试 / 死信 / 告警）
├── cli.py                         # CLI 入口
└── schemas.py                     # 模块 Schema 定义（追加到 core/schemas_v21.py）
```

### 3.3 连接器插件机制

连接器采用**注册表 + 动态加载**模式，支持未来扩展：

```python
# registry.py
class ConnectorRegistry:
    """连接器注册表 — 管理所有可用连接器。"""

    _connectors: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, name: str, connector_class: type[BaseConnector]) -> None:
        """注册连接器。"""
        cls._connectors[name] = connector_class

    @classmethod
    def get(cls, name: str) -> BaseConnector:
        """获取连接器实例。"""
        if name not in cls._connectors:
            raise ValueError(f"未知连接器: {name}，可用: {list(cls._connectors.keys())}")
        return cls._connectors[name]()

    @classmethod
    def list_all(cls) -> list[dict]:
        """列出所有已注册连接器。"""
        return [
            {
                "name": name,
                "class": klass.__name__,
                "data_source": klass.data_source,
                "target_modules": klass.target_modules,
                "auth_type": klass.auth_type,
                "default_frequency": klass.default_frequency,
            }
            for name, klass in cls._connectors.items()
        ]


# 各连接器在模块加载时自动注册
# ones_connector.py
from .registry import ConnectorRegistry
from .base_connector import BaseConnector

class OnesConnector(BaseConnector):
    name = "ones"
    data_source = "ONES 项目管理"
    target_modules = ["project_management", "delivery_report"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    # ... 实现 ...

ConnectorRegistry.register(OnesConnector.name, OnesConnector)
```

**扩展方式**：新增连接器只需：
1. 在 `connectors/` 下新建文件，实现 `BaseConnector`
2. 调用 `ConnectorRegistry.register()` 注册
3. 无需修改 Service 层代码

---

## 4. 接口设计

### 4.1 Python API

#### 3.1.1 IntegrationService

```python
class IntegrationService:
    """数据集成编排服务。"""

    def list_connectors(self) -> list[dict]:
        """列出所有可用连接器及其状态。

        Returns:
            [{
                "name": "ones",
                "data_source": "ONES 项目管理",
                "target_modules": ["project_management", "delivery_report"],
                "auth_type": "browser_cookie",
                "default_frequency": "manual",
                "status": "ready" | "error" | "not_configured",
                "last_sync_at": "2026-09-22T14:00:00",
                "last_sync_status": "success" | "failed",
            }]
        """

    def get_connector_status(self, name: str) -> dict:
        """获取指定连接器的详细状态。

        Args:
            name: 连接器名称（ones / oa / timesheet / wecom_doc / local_import）

        Returns:
            {
                "name": "ones",
                "status": "ready",
                "authenticated": true,
                "last_sync_at": "2026-09-22T14:00:00",
                "last_sync_status": "success",
                "last_sync_result": {
                    "total_fetched": 15682,
                    "new_count": 100,
                    "updated_count": 50,
                    "error_count": 0,
                },
                "frequency_config": {
                    "mode": "manual",       # manual | cron | event
                    "cron_expr": null,
                    "event_triggers": [],
                },
                "error": null,
            }
        """

    def sync(self, connector_name: str, **params) -> SyncResult:
        """执行同步。

        Args:
            connector_name: 连接器名称
            **params: 连接器特定参数
                - ones: filter_id, month
                - oa: contract_type, date_range
                - timesheet: project_id, month
                - wecom_doc: doc_type, date_range
                - local_import: file_path, target_module, field_mapping

        Returns:
            SyncResult(
                connector_name="ones",
                batch_id="20260922_140000_abc123",
                status="success",          # success | partial | failed
                total_fetched=15682,
                new_count=100,
                updated_count=50,
                unchanged_count=15532,
                error_count=0,
                errors=[],
                started_at="2026-09-22T14:00:00",
                completed_at="2026-09-22T14:05:00",
            )
        """

    def sync_all(self, **params) -> list[SyncResult]:
        """同步所有已配置连接器（按频率配置过滤）。"""

    def get_staging_data(
        self, connector_name: str, batch_id: str,
        status: str = "pending",    # pending | processed | error | all
        limit: int = 100, offset: int = 0,
    ) -> list[dict]:
        """查询暂存数据。"""

    def promote_staging(
        self, connector_name: str, batch_id: str,
        target_module: str, target_table: str,
    ) -> dict:
        """将暂存数据提升到业务表。

        Returns:
            {
                "batch_id": "20260922_140000_abc123",
                "target_module": "delivery_report",
                "target_table": "dr_sheet_row",
                "promoted_count": 100,
                "skipped_count": 50,
                "error_count": 0,
            }
        """

    def configure_frequency(
        self, connector_name: str, schedule: str,
        cron_expr: str = None, event_triggers: list[str] = None,
    ) -> dict:
        """配置同步频率。

        Args:
            connector_name: 连接器名称
            schedule: "manual" | "cron" | "event"
            cron_expr: cron 表达式（schedule="cron" 时必填）
            event_triggers: 事件触发列表（schedule="event" 时必填）
                如 ["delivery_report.generate", "revenue.generate"]

        Returns:
            {"connector_name": "ones", "schedule": "cron", "cron_expr": "0 2 * * *"}
        """

    def get_frequency_config(self, connector_name: str) -> dict:
        """获取频率配置。"""

    def retry_failed(self, connector_name: str, batch_id: str) -> SyncResult:
        """重试失败的同步。"""

    def get_sync_history(
        self, connector_name: str = None,
        limit: int = 20, offset: int = 0,
    ) -> list[dict]:
        """查询同步历史。"""
```

#### 3.1.2 SyncResult

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SyncResult:
    """同步结果。"""
    connector_name: str
    batch_id: str
    status: str                        # success | partial | failed
    total_fetched: int = 0
    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    params: dict = field(default_factory=dict)
```

#### 3.1.3 BaseConnector

```python
from abc import ABC, abstractmethod

class BaseConnector(ABC):
    """连接器抽象基类。"""

    # 类属性（子类必须覆盖）
    name: str = ""                    # 连接器标识
    data_source: str = ""             # 数据源描述
    target_modules: list[str] = []    # 目标模块列表
    auth_type: str = ""               # 认证方式
    default_frequency: str = "manual" # 默认频率

    def __init__(self):
        self._credentials = None
        self._logger = get_logger(f"integration.{self.name}")

    @abstractmethod
    def authenticate(self) -> bool:
        """认证并返回是否成功。

        浏览器自动化连接器：检查浏览器 Cookie 是否有效
        API 连接器：验证 Token / API Key
        local_import：始终返回 True（无需认证）
        """

    @abstractmethod
    def fetch(self, **params) -> list[dict]:
        """从数据源拉取原始数据。

        Returns:
            原始数据列表（dict 格式，字段名保持源系统命名）
        """

    @abstractmethod
    def normalize(self, raw: list[dict]) -> list[dict]:
        """将原始数据标准化为 BDMS 格式。

        Args:
            raw: fetch() 返回的原始数据

        Returns:
            标准化数据列表，每条记录包含：
            {
                "source_id": "唯一标识（源系统 ID）",
                "source_data": { ... },      # 原始数据（JSON）
                "normalized_data": { ... },  # 标准化数据（JSON）
                "target_module": "delivery_report",
                "target_table": "dr_sheet_row",
            }
        """

    @abstractmethod
    def load_to_staging(self, records: list[dict]) -> int:
        """将标准化数据写入暂存表。

        Returns:
            写入记录数
        """

    def validate(self, records: list[dict]) -> tuple[list[dict], list[dict]]:
        """校验数据质量（可选覆盖）。

        Returns:
            (valid_records, invalid_records)
        """
        return records, []

    def pre_sync(self, **params) -> dict:
        """同步前钩子（可选覆盖）。

        Returns:
            context dict，传递给 fetch()
        """
        return {}

    def post_sync(self, result: SyncResult) -> None:
        """同步后钩子（可选覆盖）。"""
        pass
```

### 4.2 Web API 路由

```
# ========== 数据集成 ==========

GET  /api/integration/connectors                    # 列出所有连接器
GET  /api/integration/connectors/{name}/status      # 连接器状态
POST /api/integration/sync                          # 执行同步
     Body: { "connector_name": "ones", "params": { "month": "202606" } }
POST /api/integration/sync/all                      # 同步所有已配置连接器
GET  /api/integration/staging                       # 查询暂存数据
     Query: connector_name, batch_id, status, limit, offset
POST /api/integration/staging/promote               # 暂存→业务表
     Body: { "connector_name": "ones", "batch_id": "xxx",
             "target_module": "delivery_report", "target_table": "dr_sheet_row" }
GET  /api/integration/frequency/{connector}         # 获取频率配置
PUT  /api/integration/frequency/{connector}         # 配置频率
     Body: { "schedule": "cron", "cron_expr": "0 2 * * *" }
POST /api/integration/retry                         # 重试失败同步
     Body: { "connector_name": "ones", "batch_id": "xxx" }
GET  /api/integration/history                       # 同步历史
     Query: connector_name, limit, offset
```

### 4.3 CLI 命令

```bash
# 列出所有连接器
bdms integration list

# 查看连接器状态
bdms integration status ones

# 执行同步
bdms integration sync ones --month 202606
bdms integration sync oa --date-range 2026-01,2026-06
bdms integration sync timesheet --month 202606
bdms integration sync wecom_doc --doc-type revenue
bdms integration sync local --path ./报表.xlsx --target delivery_report

# 同步所有已配置连接器
bdms integration sync-all

# 查询暂存数据
bdms integration staging --connector ones --batch-id xxx --status pending

# 暂存→业务表
bdms integration promote --connector ones --batch-id xxx \
    --target-module delivery_report --target-table dr_sheet_row

# 配置频率
bdms integration configure ones --schedule cron --cron "0 2 * * *"
bdms integration configure oa --schedule manual
bdms integration configure timesheet --schedule event \
    --triggers delivery_report.generate,revenue.generate

# 重试失败
bdms integration retry ones --batch-id xxx

# 同步历史
bdms integration history --connector ones --limit 10
```

---

## 5. 数据模型

### 5.1 DDL（追加到 `core/schemas_v21.py`）

```sql
-- ===== 数据集成模块 =====

-- 统一暂存表（已有 int_staging，此处扩展索引）
-- 注意：int_staging 已在 schemas_v21.py 中定义，此处不重复

-- 频率配置表
CREATE TABLE IF NOT EXISTS int_frequency_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL DEFAULT 'manual',  -- manual | cron | event
    cron_expr TEXT,                           -- cron 表达式（schedule=cron 时）
    event_triggers TEXT,                      -- JSON array（schedule=event 时）
    enabled INTEGER DEFAULT 1,
    last_triggered_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_int_freq_connector ON int_frequency_config(connector_name);

-- 同步日志表（已有 int_sync_log，此处扩展索引）
-- 注意：int_sync_log 已在 schemas_v21.py 中定义，此处不重复

-- 死信队列表
CREATE TABLE IF NOT EXISTS int_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_data TEXT,                         -- JSON: 原始数据
    error_msg TEXT NOT NULL,
    error_type TEXT,                          -- auth | network | parse | validate | system
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    status TEXT DEFAULT 'pending',            -- pending | retrying | resolved | abandoned
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    resolved_at TEXT,
    resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_int_dl_status ON int_dead_letter(status);
CREATE INDEX IF NOT EXISTS idx_int_dl_connector ON int_dead_letter(connector_name);

-- 字段映射配置表（本机导入用）
CREATE TABLE IF NOT EXISTS int_field_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,             -- local_import
    target_module TEXT NOT NULL,
    target_table TEXT NOT NULL,
    source_field TEXT NOT NULL,               -- 源字段名（Excel 列名 / CSV header）
    target_field TEXT NOT NULL,               -- 目标字段名
    transform_rule TEXT,                      -- 转换规则（JSON，如 {"type": "date", "format": "YYYY-MM-DD"}）
    is_required INTEGER DEFAULT 0,
    default_value TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(connector_name, target_module, target_table, source_field, target_field)
);
CREATE INDEX IF NOT EXISTS idx_int_fm_target ON int_field_mapping(target_module, target_table);
```

### 5.2 表关系图

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ int_frequency_config│     │     int_staging     │     │    int_sync_log     │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│ connector_name (PK) │     │ connector_name (FK) │     │ connector_name (FK) │
│ schedule            │     │ batch_id            │     │ batch_id (UQ)       │
│ cron_expr           │     │ source_id           │     │ mode                │
│ event_triggers      │     │ status              │     │ status              │
│ enabled             │     │ source_data (JSON)  │     │ total_fetched       │
│ last_triggered_at   │     │ normalized_data     │     │ new_count           │
└─────────────────────┘     │   (JSON)            │     │ updated_count       │
                            │ target_module       │     │ error_count         │
                            │ target_table        │     │ started_at          │
                            │ error_msg           │     │ completed_at        │
                            │ retry_count         │     └─────────────────────┘
                            └──────────┬──────────┘
                                       │
                            ┌──────────┴──────────┐
                            │                     │
                     ┌──────┴──────┐       ┌──────┴──────┐
                     │   promote   │       │   retry     │
                     │   (幂等写入) │       │   (重新同步) │
                     └──────┬──────┘       └──────┬──────┘
                            │                     │
                            ▼                     ▼
              ┌──────────────────────┐  ┌─────────────────────┐
              │    Business Tables   │  │   int_dead_letter   │
              │ (pm_projects /       │  ├─────────────────────┤
              │  cr_contracts /      │  │ connector_name      │
              │  ct_timesheets / ...)│  │ batch_id            │
              └──────────────────────┘  │ source_id           │
                                        │ error_msg           │
                                        │ error_type          │
                                        │ retry_count         │
                                        │ status              │
                                        └─────────────────────┘
```

### 5.3 统一暂存表设计说明

`int_staging` 表采用**通用 JSON 存储**模式，不区分数据源：

| 字段 | 说明 |
|---|---|
| `connector_name` | 连接器名称（ones / oa / timesheet / wecom_doc / local_import） |
| `batch_id` | 同步批次 ID（格式：`YYYYMMDD_HHMMSS_<random6>`） |
| `source_id` | 源系统唯一标识（用于幂等去重） |
| `status` | 状态：pending → processed → error |
| `source_data` | 原始数据（JSON，保留源系统完整字段） |
| `normalized_data` | 标准化数据（JSON，BDMS 标准格式） |
| `target_module` | 目标模块（delivery_report / revenue / project_management / ...） |
| `target_table` | 目标表名（dr_sheet_row / rr_sheet_row / pm_projects / ...） |
| `error_msg` | 错误信息 |
| `retry_count` | 重试次数 |
| `created_at` | 创建时间 |
| `processed_at` | 处理时间 |

**唯一约束**：`(connector_name, batch_id, source_id)` — 同一批次内同一源记录只保留一条。

---

## 6. 五个连接器详细设计

### 6.1 I-01: ONES 连接器（`ones_connector.py`）

> **拉取方式：浏览器自动化**（已通过之前开发验证，复用 `ones-browser-export` 技能）

#### 5.1.1 概述

| 属性 | 值 |
|---|---|
| 连接器名称 | `ones` |
| 数据源 | ONES 项目管理（ones.bangcle.com） |
| 落地目标 | `project_management` / `delivery_report` |
| 认证方式 | 浏览器 Cookie（复用已登录的 Chrome 会话） |
| 默认频率 | 人工触发 |
| 适配器 | BrowserAdapter（osascript） |

#### 5.1.2 认证方式

```python
class OnesConnector(BaseConnector):
    name = "ones"
    data_source = "ONES 项目管理"
    target_modules = ["project_management", "delivery_report"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """检查 Chrome 中 ONES 标签页是否已登录。

        通过 osascript 执行 JS 检查页面是否包含登录用户信息。
        """
        try:
            result = self._browser.execute_js(
                "document.querySelector('.user-info') !== null"
            )
            return result == "true"
        except Exception:
            return False
```

#### 5.1.3 数据拉取

ONES 数据通过浏览器自动化导出 CSV，支持以下筛选器：

| 筛选器 | 目标数据 | 对应月报 Sheet |
|---|---|---|
| 签约项目统计 | 签约合同数据 | 签约 |
| POC&提前实施统计 | POC/提前实施数据 | POC&提前实施 |
| 异常处置 | 异常项目数据 | 异常项目 |
| 确收交接 | 确收交接数据 | 确收交接 |
| 验收交接 | 验收交接数据 | 验收交接 |

```python
def fetch(self, **params) -> list[dict]:
    """从 ONES 导出 CSV 并解析。

    Args:
        filter_name: 筛选器名称（签约项目统计 / POC&提前实施统计 / ...）
        month: 目标月份（YYYYMM），用于数据过滤

    Returns:
        原始数据列表
    """
    filter_name = params.get("filter_name", "签约项目统计")
    month = params.get("month")

    # 1. 通过浏览器自动化导出 CSV
    csv_path = self._browser.export_filter(filter_name)

    # 2. 解析 CSV
    raw_data = self._parse_csv(csv_path)

    # 3. 按月份过滤（如果指定）
    if month:
        raw_data = [r for r in raw_data if self._match_month(r, month)]

    return raw_data
```

#### 5.1.4 标准化逻辑

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """将 ONES CSV 数据标准化。

    签约项目统计 → delivery_report.dr_sheet_row
    字段映射：
        BI履约ID → perf_id
        销售合同编号 → sales_contract_no
        合同名称 → contract_name
        所属产线 → prod_line
        状态 → status
        负责人 → owner
        事业部（区域） → dept
    """
    normalized = []
    for row in raw:
        record = {
            "source_id": row.get("BI履约ID", ""),
            "source_data": row,
            "normalized_data": {
                "perf_id": row.get("BI履约ID"),
                "sales_contract_no": row.get("销售合同编号"),
                "contract_name": row.get("合同名称"),
                "prod_line": row.get("所属产线"),
                "status": row.get("状态"),
                "owner": row.get("负责人"),
                "dept": row.get("事业部（区域）"),
            },
            "target_module": "delivery_report",
            "target_table": "dr_sheet_row",
        }
        normalized.append(record)
    return normalized
```

#### 5.1.5 落地映射

| ONES 字段 | 目标表字段 | 目标表 | 说明 |
|---|---|---|---|
| BI履约ID | data->perf_id | dr_sheet_row | 履约 ID |
| 销售合同编号 | data->sales_contract_no | dr_sheet_row | 合同编号 |
| 合同名称 | data->contract_name | dr_sheet_row | 合同名称 |
| 所属产线 | data->prod_line | dr_sheet_row | 产线 |
| 状态 | data->status | dr_sheet_row | 项目状态 |
| 负责人 | data->owner | dr_sheet_row | 负责人 |
| 事业部（区域） | data->dept | dr_sheet_row | 部门 |

#### 5.1.6 复用资产

- ✅ `L4-proprietary/skills/ones-browser-export/` — ONES 浏览器自动化导出逻辑
- ✅ `modules/revenue/weekly_importer.py` — 已有 ONES CSV 导入器（重构为连接器的一部分）
- ✅ `L2-infra/components/credentials/` — 凭据管理（浏览器 Cookie 路径）

### 6.2 I-02: OA 连接器（`oa_connector.py`）

#### 5.2.1 概述

| 属性 | 值 |
|---|---|
| 连接器名称 | `oa` |
| 数据源 | OA 合同流程（oa.bangcle.com） |
| 落地目标 | `contract_management` / `project_management` |
| 认证方式 | 浏览器 Cookie |
| 默认频率 | 人工触发 |
| 适配器 | BrowserAdapter（osascript） |

#### 5.2.2 认证方式

与 ONES 连接器类似，复用浏览器已登录的 OA 会话。

```python
class OaConnector(BaseConnector):
    name = "oa"
    data_source = "OA 合同流程"
    target_modules = ["contract_management", "project_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """检查 Chrome 中 OA 标签页是否已登录。"""
        try:
            result = self._browser.execute_js(
                "document.querySelector('.user-info') !== null"
            )
            return result == "true"
        except Exception:
            return False
```

#### 5.2.3 数据拉取

OA 合同数据通过浏览器自动化导出，支持以下数据类型：

| 数据类型 | 导出方式 | 目标模块 |
|---|---|---|
| 合同列表 | 筛选器导出 | contract_management |
| 立项审批 | 流程导出 | project_management |
| 结项审批 | 流程导出 | project_management |

```python
def fetch(self, **params) -> list[dict]:
    """从 OA 导出合同/审批数据。

    Args:
        data_type: 数据类型（contract / project_init / project_close）
        date_range: 日期范围（YYYY-MM-DD,YYYY-MM-DD）
    """
    data_type = params.get("data_type", "contract")
    date_range = params.get("date_range")

    # 通过浏览器自动化导出
    csv_path = self._browser.export_oa_data(data_type, date_range)
    return self._parse_csv(csv_path)
```

#### 5.2.4 标准化逻辑

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """将 OA 合同数据标准化。

    OA 合同 → contract_management.cr_contracts
    字段映射：
        合同编号 → contract_no
        合同名称 → title
        甲方 → party_a
        乙方 → party_b
        合同金额 → amount
        生效日期 → effective_date
        到期日期 → expiry_date
    """
    normalized = []
    for row in raw:
        record = {
            "source_id": row.get("合同编号", ""),
            "source_data": row,
            "normalized_data": {
                "contract_no": row.get("合同编号"),
                "title": row.get("合同名称"),
                "party_a": row.get("甲方"),
                "party_b": row.get("乙方"),
                "amount": self._parse_amount(row.get("合同金额")),
                "effective_date": row.get("生效日期"),
                "expiry_date": row.get("到期日期"),
                "status": self._map_status(row.get("状态")),
            },
            "target_module": "contract_management",
            "target_table": "cr_contracts",
        }
        normalized.append(record)
    return normalized
```

#### 5.2.5 落地映射

| OA 字段 | 目标表字段 | 目标表 | 说明 |
|---|---|---|---|
| 合同编号 | contract_no | cr_contracts | 合同编号 |
| 合同名称 | title | cr_contracts | 合同名称 |
| 甲方 | party_a | cr_contracts | 甲方 |
| 乙方 | party_b | cr_contracts | 乙方 |
| 合同金额 | amount | cr_contracts | 金额 |
| 生效日期 | effective_date | cr_contracts | 生效日期 |
| 到期日期 | expiry_date | cr_contracts | 到期日期 |
| 状态 | status | cr_contracts | 状态映射 |

### 6.3 I-03: 工时门户连接器（`timesheet_connector.py`）

#### 5.3.1 概述

| 属性 | 值 |
|---|---|
| 连接器名称 | `timesheet` |
| 数据源 | 工时门户（timesheet.bangcle.com） |
| 落地目标 | `profit_management` |
| **拉取方式** | **浏览器自动化**（已通过之前开发验证） |
| 认证方式 | 浏览器 Cookie（复用已登录会话） |
| 默认频率 | 人工触发 |
| 适配器 | BrowserAdapter |

> **技术选型依据**：工时门户与 ONES/OA 同属 Web 系统，浏览器自动化方案已通过之前开发验证（ones-browser-export 技能）。相比 API 调用，浏览器自动化无需申请 API 权限（无管理员权限限制），且能直接导出 Excel/CSV。

#### 5.3.2 认证方式

```python
class TimesheetConnector(BaseConnector):
    name = "timesheet"
    data_source = "工时门户"
    target_modules = ["profit_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """检查浏览器中工时门户是否已登录。"""
        return self._browser.check_login("timesheet.bangcle.com")
```

#### 5.3.3 数据拉取

```python
def fetch(self, **params) -> list[dict]:
    """通过浏览器自动化从工时门户导出工时数据。

    Steps:
    1. 导航至工时门户导出页面
    2. 设置筛选条件（月份、项目）
    3. 触发导出（Excel/CSV）
    4. 下载文件并解析

    Args:
        project_id: 项目 ID（可选）
        month: 目标月份（YYYYMM）
    """
    month = params.get("month")
    project_id = params.get("project_id")

    # 通过浏览器自动化导出
    file_path = self._browser.export_data(
        url="https://timesheet.bangcle.com/export",
        filters={"month": month, "project_id": project_id},
        format="csv",
        timeout=60,
    )
    return self._parse_csv(file_path)
```

#### 5.3.4 标准化逻辑

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """化工时数据为标准格式。

    工时门户 → profit_management.ct_timesheets
    字段映射：
        人员ID → person_id
        工作日期 → work_date
        工时 → hours
        工作类型 → work_type
        描述 → description
    """
    normalized = []
    for row in raw:
        record = {
            "source_id": f"{row.get('person_id')}_{row.get('work_date')}",
            "source_data": row,
            "normalized_data": {
                "person_id": row.get("person_id"),
                "work_date": row.get("work_date"),
                "hours": row.get("hours", 0),
                "work_type": row.get("work_type"),
                "description": row.get("description"),
                "status": "submitted",
            },
            "target_module": "profit_management",
            "target_table": "ct_timesheets",
        }
        normalized.append(record)
    return normalized
```

#### 5.3.5 落地映射

| 工时门户字段 | 目标表字段 | 目标表 | 说明 |
|---|---|---|---|
| person_id | person_id | ct_timesheets | 人员 ID |
| work_date | work_date | ct_timesheets | 工作日期 |
| hours | hours | ct_timesheets | 工时 |
| work_type | work_type | ct_timesheets | 工作类型 |
| description | description | ct_timesheets | 描述 |

### 6.4 I-04: 企微文档连接器（`wecom_doc_connector.py`）

#### 5.4.1 概述

| 属性 | 值 |
|---|---|
| 连接器名称 | `wecom_doc` |
| 数据源 | 企业微信文档 |
| 落地目标 | `revenue` / `project_management` |
| **拉取方式** | **预留多种技术实现**（详见 §5.4.6） |
| 认证方式 | 企微 API / 浏览器自动化 / 本机导入（按优先级降级） |
| 默认频率 | 人工触发 |
| 适配器 | WeComApiAdapter / BrowserAdapter / FileParser |

> **技术选型说明**：企微文档 API 未经之前开发验证，预留多种技术实现方式，按优先级降级：
> 1. **企微 API**（优先）：通过企微开放平台 API 获取文档内容
> 2. **浏览器自动化**（备选）：通过浏览器访问企微 Web 端导出文档
> 3. **本机导入**（兜底）：用户手动下载后通过系统通用导入功能上传
>
> **当前限制**：
> - 企微 API 需要 corpId + corpSecret + agentId（需管理员开通权限）
> - 企微文档 API 可能不支持直接导出结构化数据（需调研）
> - 无管理员权限时，优先使用浏览器自动化方案

#### 5.4.2 认证方式

```python
class WecomDocConnector(BaseConnector):
    name = "wecom_doc"
    data_source = "企微文档"
    target_modules = ["revenue", "project_management"]
    auth_type = "wecom_api"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """验证企微 API 凭据是否有效。"""
        corpid = self._get_credential("wecom_corpid")
        corpsecret = self._get_credential("wecom_corpsecret")
        if not corpid or not corpsecret:
            return False
        try:
            # 获取 access_token 验证凭据
            token = self._wecom.get_access_token(corpid, corpsecret)
            return token is not None
        except Exception:
            return False
```

#### 5.4.3 数据拉取

```python
def fetch(self, **params) -> list[dict]:
    """从企微文档拉取确收凭证数据。

    Args:
        doc_type: 文档类型（revenue_voucher / project_doc）
        date_range: 日期范围
    """
    doc_type = params.get("doc_type", "revenue_voucher")
    date_range = params.get("date_range")

    # 获取文档列表
    docs = self._wecom.list_documents(doc_type, date_range)

    # 拉取每个文档的内容
    results = []
    for doc in docs:
        content = self._wecom.get_document_content(doc["doc_id"])
        results.append({
            "doc_id": doc["doc_id"],
            "doc_name": doc["doc_name"],
            "content": content,
            "created_at": doc.get("created_at"),
        })

    return results
```

#### 5.4.4 标准化逻辑

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """将企微文档数据标准化。

    确收凭证 → revenue.rr_sheet_row
    字段映射（从文档内容中提取）：
        合同编号 → contract_no
        确收金额 → actual_amount
        确收日期 → confirm_date
        项目经理 → pm_name
    """
    normalized = []
    for row in raw:
        content = row.get("content", {})
        record = {
            "source_id": row.get("doc_id", ""),
            "source_data": row,
            "normalized_data": {
                "contract_no": content.get("合同编号"),
                "actual_amount": self._parse_amount(content.get("确收金额")),
                "confirm_date": content.get("确收日期"),
                "pm_name": content.get("项目经理"),
                "doc_id": row.get("doc_id"),
            },
            "target_module": "revenue",
            "target_table": "rr_sheet_row",
        }
        normalized.append(record)
    return normalized
```

#### 5.4.5 落地映射

| 企微文档字段 | 目标表字段 | 目标表 | 说明 |
|---|---|---|---|
| 合同编号 | data->contract_no | rr_sheet_row | 合同编号 |
| 确收金额 | data->actual_amount | rr_sheet_row | 确收金额 |
| 确收日期 | data->confirm_date | rr_sheet_row | 确收日期 |
| 项目经理 | data->pm_name | rr_sheet_row | 项目经理 |

### 6.5 I-05: 本机导入连接器（`local_import_connector.py`）

#### 5.5.1 概述

| 属性 | 值 |
|---|---|
| 连接器名称 | `local_import` |
| 数据源 | 本机文件（Excel/CSV）/ 手工录入 |
| 落地目标 | 各模块（由用户指定） |
| 认证方式 | 无需认证 |
| 默认频率 | 人工触发 |
| 适配器 | FileParser |

#### 5.5.2 认证方式

```python
class LocalImportConnector(BaseConnector):
    name = "local_import"
    data_source = "本机导入（Excel/CSV/手工录入）"
    target_modules = ["*"]  # 支持所有模块
    auth_type = "none"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """本机导入无需认证。"""
        return True
```

#### 5.5.3 数据拉取

```python
def fetch(self, **params) -> list[dict]:
    """从本机文件读取数据。

    Args:
        file_path: 文件路径（Excel/CSV）
        file_type: 文件类型（excel / csv / manual）
        sheet_name: Sheet 名称（Excel 多 Sheet 时）
    """
    file_path = params.get("file_path")
    file_type = params.get("file_type", "auto")  # auto 自动检测
    sheet_name = params.get("sheet_name")

    if not file_path:
        raise ValueError("必须指定 file_path")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 自动检测文件类型
    if file_type == "auto":
        file_type = "excel" if path.suffix in (".xlsx", ".xls") else "csv"

    # 解析文件
    if file_type == "excel":
        return self._parse_excel(path, sheet_name)
    elif file_type == "csv":
        return self._parse_csv(path)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}")
```

#### 5.5.4 标准化逻辑

本机导入的标准化依赖**字段映射配置**（`int_field_mapping` 表）：

```python
def normalize(self, raw: list[dict]) -> list[dict]:
    """根据字段映射配置标准化数据。

    Args:
        raw: 原始数据（Excel/CSV 解析结果）

    Returns:
        标准化数据列表
    """
    # 获取字段映射配置
    mappings = self._get_field_mappings(
        connector_name="local_import",
        target_module=self.target_module,
        target_table=self.target_table,
    )

    normalized = []
    for row in raw:
        norm_data = {}
        for mapping in mappings:
            source_field = mapping["source_field"]
            target_field = mapping["target_field"]
            value = row.get(source_field)

            # 应用转换规则
            if mapping.get("transform_rule"):
                value = self._apply_transform(value, mapping["transform_rule"])

            # 必填校验
            if mapping.get("is_required") and value is None:
                raise ValueError(f"必填字段缺失: {source_field}")

            # 默认值
            if value is None and mapping.get("default_value"):
                value = mapping["default_value"]

            norm_data[target_field] = value

        record = {
            "source_id": str(row.get("id", "")),
            "source_data": row,
            "normalized_data": norm_data,
            "target_module": self.target_module,
            "target_table": self.target_table,
        }
        normalized.append(record)
    return normalized
```

#### 5.5.5 字段映射配置示例

```json
// 交付月报 - 签约 Sheet 字段映射
{
  "connector_name": "local_import",
  "target_module": "delivery_report",
  "target_table": "dr_sheet_row",
  "mappings": [
    { "source_field": "BI履约ID", "target_field": "perf_id", "is_required": true },
    { "source_field": "销售合同编号", "target_field": "sales_contract_no" },
    { "source_field": "合同名称", "target_field": "contract_name" },
    { "source_field": "所属产线", "target_field": "prod_line" },
    { "source_field": "状态", "target_field": "status" },
    { "source_field": "负责人", "target_field": "owner" },
    { "source_field": "事业部（区域）", "target_field": "dept" }
  ]
}
```

---

## 7. 频率配置设计

### 7.1 频率模式

| 模式 | 说明 | 配置方式 | 适用场景 |
|---|---|---|---|
| **manual** | 人工触发 | 默认模式 | 按需同步，如生成月报前 |
| **cron** | 定时任务 | cron 表达式 | 定期同步，如每日凌晨 |
| **event** | 事件驱动 | 监听事件列表 | 业务事件触发，如月报生成后 |

### 7.2 频率配置表

```sql
CREATE TABLE IF NOT EXISTS int_frequency_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL DEFAULT 'manual',  -- manual | cron | event
    cron_expr TEXT,                           -- cron 表达式
    event_triggers TEXT,                      -- JSON array
    enabled INTEGER DEFAULT 1,
    last_triggered_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
```

### 7.3 调度器实现

```python
# scheduler.py
import schedule
from datetime import datetime

class SyncScheduler:
    """同步调度器 — 管理 cron 和 event 两种模式。"""

    def __init__(self, service: IntegrationService):
        self._service = service
        self._running = False

    def load_configs(self) -> None:
        """从 DB 加载所有频率配置。"""
        configs = self._get_all_configs()
        for config in configs:
            if not config["enabled"]:
                continue

            if config["schedule"] == "cron" and config["cron_expr"]:
                self._schedule_cron(config)
            elif config["schedule"] == "event" and config["event_triggers"]:
                self._register_event(config)

    def _schedule_cron(self, config: dict) -> None:
        """注册 cron 定时任务。"""
        cron_expr = config["cron_expr"]
        connector = config["connector_name"]

        # 使用 schedule 库解析 cron 表达式
        # 简化：支持标准 5 位 cron 分 时 日 月 周
        parts = cron_expr.split()
        if len(parts) == 5:
            minute, hour, day, month, weekday = parts
            schedule.every().day.at(f"{hour}:{minute}").do(
                self._run_sync, connector
            )

    def _register_event(self, config: dict) -> None:
        """注册事件监听。"""
        triggers = json.loads(config["event_triggers"])
        connector = config["connector_name"]

        for event_name in triggers:
            event_bus.subscribe(event_name, lambda: self._run_sync(connector))

    def _run_sync(self, connector_name: str) -> None:
        """执行同步并更新 last_triggered_at。"""
        try:
            self._service.sync(connector_name)
            self._update_last_triggered(connector_name)
        except Exception as e:
            self._logger.error(f"调度同步失败: {connector_name}: {e}")

    def run_pending(self) -> None:
        """执行所有到期的 cron 任务。"""
        schedule.run_pending()
```

### 7.4 事件驱动触发

支持以下事件触发器：

| 事件名 | 触发时机 | 建议连接器 |
|---|---|---|
| `delivery_report.generate` | 交付月报生成前 | ones, oa |
| `revenue.generate` | 确收分析生成前 | wecom_doc, local_import |
| `project_management.create` | 项目立项时 | ones, oa |
| `profit_management.calculate` | 利润计算前 | timesheet |

```python
# 在业务模块中发布事件
# delivery_report/service.py
class DeliveryReportService(BaseService):
    def generate(self, month: str, mode: str = "auto") -> dict:
        # 发布事件，触发相关连接器同步
        event_bus.publish("delivery_report.generate", {"month": month})
        # ... 继续生成逻辑
```

---

## 8. 暂存 → 业务表流转机制

### 8.1 流转流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  fetch   │ →  │ normalize│ →  │ validate │ →  │  staging │ →  │ promote  │
│ (拉取)   │    │ (标准化) │    │ (校验)   │    │ (暂存)   │    │ (提升)   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                                   │
                                                          ┌────────┴────────┐
                                                          │  幂等写入业务表  │
                                                          │  + 事件通知      │
                                                          └─────────────────┘
```

### 8.2 幂等写入

```python
# sync_pipeline.py
class SyncPipeline:
    """同步管道 — 编排 fetch → normalize → load → promote。"""

    def promote_to_business(
        self, connector_name: str, batch_id: str,
        target_module: str, target_table: str,
    ) -> dict:
        """将暂存数据幂等写入业务表。

        幂等策略：
        1. 按 source_id 去重（同一源记录只保留最新）
        2. 按业务唯一键 UPSERT（INSERT OR REPLACE）
        3. 记录变更日志（new / updated / unchanged）
        """
        conn = get_connection()
        try:
            # 1. 查询待提升的暂存记录
            staging_records = conn.execute(
                "SELECT * FROM int_staging WHERE connector_name=? AND batch_id=? AND status='pending'",
                (connector_name, batch_id),
            ).fetchall()

            new_count = 0
            updated_count = 0
            unchanged_count = 0
            error_count = 0

            for record in staging_records:
                try:
                    normalized = json.loads(record["normalized_data"])

                    # 2. 检查是否已存在（幂等）
                    existing = self._find_existing(conn, target_table, normalized)

                    if existing:
                        # 3. 比较数据是否有变化
                        if self._is_unchanged(existing, normalized):
                            unchanged_count += 1
                            self._mark_staging_processed(record["id"], "unchanged")
                        else:
                            # 4. 更新
                            self._update_business_record(conn, target_table, normalized, existing["id"])
                            updated_count += 1
                            self._mark_staging_processed(record["id"], "updated")
                    else:
                        # 5. 新增
                        self._insert_business_record(conn, target_table, normalized)
                        new_count += 1
                        self._mark_staging_processed(record["id"], "new")

                except Exception as e:
                    error_count += 1
                    self._mark_staging_error(record["id"], str(e))
                    self._add_to_dead_letter(connector_name, batch_id, record, str(e))

            conn.commit()

            # 6. 发布事件通知
            event_bus.publish(
                f"{target_module}.data_updated",
                {
                    "connector_name": connector_name,
                    "batch_id": batch_id,
                    "target_table": target_table,
                    "new_count": new_count,
                    "updated_count": updated_count,
                    "unchanged_count": unchanged_count,
                    "error_count": error_count,
                },
            )

            return {
                "batch_id": batch_id,
                "target_module": target_module,
                "target_table": target_table,
                "new_count": new_count,
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
                "error_count": error_count,
            }
        finally:
            conn.close()
```

### 8.3 事件通知

同步完成后发布事件，各业务模块可订阅：

```python
# event_bus.py（core 层）
class EventBus:
    """简单事件总线。"""

    _subscribers: dict[str, list[callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, callback: callable) -> None:
        cls._subscribers.setdefault(event_name, []).append(callback)

    @classmethod
    def publish(cls, event_name: str, data: dict) -> None:
        for callback in cls._subscribers.get(event_name, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"事件处理失败: {event_name}: {e}")


# 业务模块订阅示例
# delivery_report/service.py
event_bus.subscribe("delivery_report.data_updated", lambda data: logger.info(f"数据已更新: {data}"))
```

---

## 9. 错误处理与重试机制

### 9.1 错误分类

| 错误类型 | 说明 | 处理方式 |
|---|---|---|
| `auth` | 认证失败（Cookie 过期 / Token 失效） | 立即告警，等待人工重新认证 |
| `network` | 网络超时 / 连接失败 | 指数退避重试 |
| `parse` | 数据解析失败（CSV 格式错误 / JSON 解析失败） | 记录死信，跳过该记录 |
| `validate` | 数据校验失败（必填字段缺失 / 格式不符） | 记录死信，跳过该记录 |
| `system` | 系统错误（DB 连接失败 / 磁盘满） | 指数退避重试 + 告警 |

### 9.2 指数退避重试

```python
# error_handler.py
import time
from typing import Callable

class RetryHandler:
    """指数退避重试处理器。"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def execute(self, func: Callable, *args, **kwargs):
        """执行函数，失败时指数退避重试。

        重试间隔：base_delay * (exponential_base ^ retry_count)
        例：1s → 2s → 4s → 8s → ...（不超过 max_delay）
        """
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (self.exponential_base ** attempt),
                        self.max_delay,
                    )
                    logger.warning(
                        f"重试 {attempt + 1}/{self.max_retries}，"
                        f"等待 {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"重试耗尽 ({self.max_retries} 次): {e}")
        raise last_exception
```

### 9.3 死信队列

```python
# error_handler.py
class DeadLetterQueue:
    """死信队列 — 存储无法自动处理的失败记录。"""

    def add(
        self, connector_name: str, batch_id: str,
        source_id: str, source_data: dict,
        error_msg: str, error_type: str,
    ) -> None:
        """添加死信记录。"""
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO int_dead_letter "
                "(connector_name, batch_id, source_id, source_data, error_msg, error_type) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (connector_name, batch_id, source_id,
                 json.dumps(source_data, ensure_ascii=False),
                 error_msg, error_type),
            )
            conn.commit()
        finally:
            conn.close()

    def list_pending(self, connector_name: str = None) -> list[dict]:
        """查询待处理的死信记录。"""
        conn = get_connection()
        try:
            sql = "SELECT * FROM int_dead_letter WHERE status='pending'"
            params = []
            if connector_name:
                sql += " AND connector_name=?"
                params.append(connector_name)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def resolve(self, dead_letter_id: int, resolved_by: str) -> None:
        """标记死信记录为已解决。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE int_dead_letter SET status='resolved', resolved_at=datetime('now','localtime'), resolved_by=? WHERE id=?",
                (resolved_by, dead_letter_id),
            )
            conn.commit()
        finally:
            conn.close()

    def retry(self, dead_letter_id: int) -> None:
        """重试死信记录。"""
        conn = get_connection()
        try:
            record = conn.execute(
                "SELECT * FROM int_dead_letter WHERE id=?", (dead_letter_id,)
            ).fetchone()
            if not record:
                raise ValueError(f"死信记录不存在: {dead_letter_id}")

            # 重新加入暂存表
            conn.execute(
                "INSERT OR REPLACE INTO int_staging "
                "(connector_name, batch_id, source_id, status, source_data, normalized_data, target_module, target_table) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)",
                (record["connector_name"], record["batch_id"], record["source_id"],
                 record["source_data"], record.get("normalized_data", "{}"),
                 record.get("target_module", ""), record.get("target_table", "")),
            )

            # 更新死信状态
            conn.execute(
                "UPDATE int_dead_letter SET status='retrying', retry_count=retry_count+1 WHERE id=?",
                (dead_letter_id,),
            )
            conn.commit()
        finally:
            conn.close()
```

### 9.4 告警机制

```python
# error_handler.py
class AlertManager:
    """告警管理器。"""

    def __init__(self):
        self._logger = get_logger("integration.alert")

    def alert_sync_failed(self, connector_name: str, error: str, batch_id: str = None) -> None:
        """同步失败告警。"""
        self._logger.error(
            f"同步失败: connector={connector_name}, batch_id={batch_id}, error={error}"
        )
        # TODO: 接入企微/邮件告警

    def alert_auth_expired(self, connector_name: str) -> None:
        """认证过期告警。"""
        self._logger.error(
            f"认证过期: connector={connector_name}，请重新登录"
        )
        # TODO: 接入企微/邮件告警

    def alert_dead_letter(self, connector_name: str, count: int) -> None:
        """死信队列积压告警。"""
        if count > 10:
            self._logger.warning(
                f"死信队列积压: connector={connector_name}, 待处理={count}"
            )
            # TODO: 接入企微/邮件告警
```

---

## 10. 本机导入设计

### 10.1 Excel/CSV 解析

```python
# adapters/file_parser.py
import csv
import json
from pathlib import Path

class FileParser:
    """文件解析器 — 支持 Excel 和 CSV。"""

    def parse(self, file_path: Path, sheet_name: str = None) -> list[dict]:
        """解析文件并返回 dict列表。"""
        suffix = file_path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            return self._parse_excel(file_path, sheet_name)
        elif suffix == ".csv":
            return self._parse_csv(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

    def _parse_csv(self, file_path: Path) -> list[dict]:
        """解析 CSV 文件。"""
        with open(file_path, encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    def _parse_excel(self, file_path: Path, sheet_name: str = None) -> list[dict]:
        """解析 Excel 文件。"""
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            if sheet_name:
                ws = wb[sheet_name]
            else:
                ws = wb.active

            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []

            header = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[0])]
            result = []
            for row in rows[1:]:
                record = {}
                for i, value in enumerate(row):
                    if i < len(header):
                        record[header[i]] = value
                result.append(record)
            return result
        finally:
            wb.close()
```

### 10.2 字段映射 UI

本机导入支持通过 Web UI 配置字段映射：

```
┌─────────────────────────────────────────────────────────────┐
│  本机导入 — 字段映射配置                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  源文件: 签约项目统计.csv                                      │
│  目标模块: delivery_report                                    │
│  目标表: dr_sheet_row                                         │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │ 源字段（CSV 列名）    │  │ 目标字段（BDMS 字段）  │         │
│  ├──────────────────────┤  ├──────────────────────┤         │
│  │ BI履约ID             │→ │ perf_id  *           │         │
│  │ 销售合同编号          │→ │ sales_contract_no   │         │
│  │ 合同名称             │→ │ contract_name       │         │
│  │ 所属产线             │→ │ prod_line           │         │
│  │ 状态                │→ │ status              │         │
│  │ 负责人              │→ │ owner               │         │
│  │ 事业部（区域）       │→ │ dept                │         │
│  └──────────────────────┘  └──────────────────────┘         │
│                                                             │
│  [添加映射]  [删除]  [保存配置]  [预览数据]                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 10.3 手工录入 UI

对于少量数据，支持手工录入：

```
┌─────────────────────────────────────────────────────────────┐
│  手工录入 — 签约项目数据                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  BI履约ID:     [______________] *                           │
│  销售合同编号:  [______________]                             │
│  合同名称:     [______________]                             │
│  所属产线:     [______________]                             │
│  状态:         [▼ 选择]                                     │
│  负责人:       [______________]                             │
│  事业部:       [______________]                             │
│                                                             │
│  [添加]  [保存并继续]  [取消]                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 11. 浏览器自动化集成

> **⚠️ OS 依赖声明**：浏览器自动化方案与操作系统强相关。当前开发环境为 **macOS**，以下方案按 OS 分类。

### 11.0 OS 适配矩阵

| OS | 推荐方案 | 状态 | 依赖 |
|---|---|---|---|
| **macOS** | osascript + Chrome | ✅ 已验证 | AppleScript + Chrome Apple Events |
| **macOS** | Playwright Headless | 🔶 待验证 | playwright 包 + Chromium 二进制 |
| **Linux** | Playwright Headless | 🔶 待验证 | playwright 包 + Chromium + 系统依赖库 |
| **Linux** | Selenium + ChromeDriver | 📋 待开发 | chromedriver + chrome-headless-shell |
| **Windows** | Playwright Headless | 📋 待开发 | playwright 包 + Chromium |
| **Windows** | pywinauto + Chrome COM | 📋 待开发 | pywinauto + Chrome COM 接口 |

**OS 检测与自动选择**：
```python
import platform

def create_browser_adapter(domain: str) -> BaseBrowserAdapter:
    """根据 OS 自动选择合适的浏览器适配器。"""
    system = platform.system()
    if system == "Darwin":
        return OsascriptBrowserAdapter(domain)  # macOS 原生
    elif system == "Linux":
        return PlaywrightBrowserAdapter(domain)  # Linux Headless
    elif system == "Windows":
        return PlaywrightBrowserAdapter(domain)  # Windows Headless
    else:
        raise OSError(f"不支持的操作系统: {system}")
```

### 11.1 macOS 方案：osascript + Chrome（已验证）

> **适用环境**：macOS 10.15+，Google Chrome 已安装并登录。

复用 `L4-proprietary/skills/ones-browser-export/` 的成熟方案：

```python
# adapters/browser_adapter.py
import subprocess
import time
from pathlib import Path

class OsascriptBrowserAdapter(BaseBrowserAdapter):
    """macOS 浏览器自动化 — 封装 osascript 操作 Chrome。

    ⚠️ 仅限 macOS。通过 Apple Events 控制 Chrome。
    """

    def __init__(self, domain: str):
        """
        Args:
            domain: 目标域名（如 ones.bangcle.com / oa.bangcle.com）
        """
        self.domain = domain

    def execute_js(self, js: str) -> str:
        """在目标标签页执行 JavaScript。

        ⚠️ 必须遵守：
        1. JS 中不能包含中文字符（osascript 限制）
        2. 复杂 JS 需要先转义引号
        """
        # 转义特殊字符
        js_escaped = js.replace('"', '\\"').replace("\n", " ")

        cmd = [
            "osascript", "-e",
            f'tell application "Google Chrome" to execute '
            f'(first tab of first window whose URL contains "{self.domain}") '
            f'javascript "{js_escaped}"'
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.stdout.strip()

    def export_filter(self, filter_index: int, wait_seconds: int = 15) -> Path:
        """导出 ONES 筛选器数据。

        Args:
            filter_index: 筛选器在左侧导航中的索引
            wait_seconds: 等待下载完成的时间

        Returns:
            下载的 CSV 文件路径
        """

        Args:
            filter_index: 筛选器在左侧导航中的索引
            wait_seconds: 等待下载完成的时间

        Returns:
            下载的 CSV 文件路径
        """
        # 1. 点击筛选器链接
        self.execute_js(
            f"document.querySelectorAll('a')[{filter_index}].click();'clicked'"
        )
        time.sleep(10)  # ONES SPA 加载数据

        # 2. 点击"更多操作"
        self.execute_js(
            "document.querySelectorAll('[class*=more-menu-icon]')[0].click();'clicked'"
        )
        time.sleep(3)

        # 3. 点击"导出工作项"
        self.execute_js(
            "document.querySelectorAll('[class*=dropdown-menu-item-label]')[10].click();'clicked'"
        )
        time.sleep(5)

        # 4. 点击"确定"
        self.execute_js(
            "document.querySelectorAll('button')[7].click();'clicked'"
        )
        time.sleep(wait_seconds)  # 等待下载完成

        # 5. 检查下载文件
        return self._find_latest_download()

    def _find_latest_download(self) -> Path:
        """查找最新下载的文件。"""
        downloads = Path("/Users/bangcle/Downloads")
        csv_files = list(downloads.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError("未找到下载的 CSV 文件")
        return max(csv_files, key=lambda p: p.stat().st_mtime)
```

### 11.2 Linux 方案：Playwright Headless（待验证）

> **适用环境**：Linux（Ubuntu 20.04+ / CentOS 8+），无 GUI 或 X11 环境。

```python
# adapters/playwright_adapter.py
from playwright.sync_api import sync_playwright, Browser, Page

class PlaywrightBrowserAdapter(BaseBrowserAdapter):
    """跨平台浏览器自动化 — Playwright Headless。

    ✅ Linux（推荐）/ macOS / Windows 通用。
    依赖：pip install playwright && playwright install chromium
    """

    def __init__(self, domain: str, headless: bool = True):
        self.domain = domain
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def start(self) -> None:
        """启动浏览器（Headless 模式）。"""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        # 加载已保存的 Cookie（如有）
        cookies = self._load_cookies()
        if cookies:
            self._page.context.add_cookies(cookies)

    def navigate(self, path: str = "") -> None:
        """导航到目标页面。"""
        self._page.goto(f"https://{self.domain}{path}")
        self._page.wait_for_load_state("networkidle")

    def execute_js(self, js: str) -> str:
        """执行 JavaScript。"""
        return str(self._page.evaluate(js))

    def export_data(self, **params) -> Path:
        """导出数据（点击下载按钮 + 等待下载完成）。"""
        with self._page.expect_download() as download_info:
            self._page.click(".export-button")
        download = download_info.value
        path = Path(download.suggested_filename)
        download.save_as(path)
        return path

    def close(self) -> None:
        if self._browser:
            # 保存 Cookie 供下次使用
            self._save_cookies(self._page.context.cookies())
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
```

**Linux 系统依赖**：
```bash
# Ubuntu/Debian
sudo apt-get install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxrandr1 libgbm1 libpango-1.0-0 libcairo2 \
  libasound2 libatspi2.0-0 libxshmfence1

# CentOS/RHEL
sudo yum install -y nss atk atk-bridge gtk3 cups-libs libdrm libxkbcommon \
  libXcomposite libXdamage libXrandr libGbm pango cairo alsa-lib
```

### 11.3 Windows 方案：Playwright/pywinauto（待开发）

> **适用环境**：Windows 10/11，Google Chrome 已安装。

```python
# Windows 方案 A：Playwright Headless（推荐，跨平台一致）
class WindowsPlaywrightAdapter(PlaywrightBrowserAdapter):
    """Windows Playwright 适配器 — 继承 Linux 方案，路径适配。"""

    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            executable_path=self.CHROME_PATH,  # 指定 Chrome 路径
        )
        self._page = self._browser.new_page()

# Windows 方案 B：pywinauto + Chrome COM（备选）
class WindowsComBrowserAdapter(BaseBrowserAdapter):
    """Windows COM 接口控制 Chrome。

    ⚠️ 依赖 pywinauto，仅 Windows 可用。
    """

    def __init__(self, domain: str):
        self.domain = domain
        self._app = None

    def connect(self) -> None:
        """连接到已打开的 Chrome 窗口。"""
        from pywinauto import Application
        self._app = Application(backend="uia").connect(title_re=f".*{self.domain}.*")
```

### 11.4 OA 自动化导出

OA 的浏览器自动化方案与 ONES 类似，但需要适配 OA 的页面结构：

```python
class OaBrowserAdapter(BaseBrowserAdapter):
    """OA 浏览器自动化适配器（OS 无关，由工厂方法选择底层实现）。"""

    def __init__(self):
        super().__init__("oa.bangcle.com")

    def export_contract_list(self, date_range: str = None) -> Path:
        """导出合同列表。"""
        # 1. 导航到合同列表页
        self.navigate("/contract/list")
        # 2. 设置日期范围
        if date_range:
            start, end = date_range.split(",")
            self._page.fill('input[placeholder*="开始"]', start)
            self._page.fill('input[placeholder*="结束"]', end)
        # 3. 点击导出
        return self._click_export()
```

### 11.5 已知限制与规避

| 限制 | 影响 | 规避方案 |
|---|---|---|
| JS 不能包含中文（osascript） | 无法用中文文字匹配元素 | 使用索引定位（已验证的索引） |
| SPA 加载慢 | 数据未就绪时操作失败 | 固定等待 10-15 秒 |
| 菜单索引可能变化 | 页面更新后索引失效 | 每次同步前重新探测索引 |
| 大文件下载慢 | 超时 | 等待 15 秒以上 |
| 需要 Chrome 已打开（macOS） | 未打开时失败 | 同步前检查并提示 |
| Linux 无 GUI | 无法使用 osascript | 使用 Playwright Headless |
| Windows COM 不稳定 | pywinauto 连接失败 | 降级到 Playwright Headless |
| Playwright 浏览器下载慢 | 首次使用需下载 Chromium | 预装或指定系统 Chrome 路径 |
| Linux 缺少系统库 | Playwright 启动失败 | 安装依赖库（见 §10.2） |

---

## 12. 凭据管理

### 12.1 凭据存储

所有连接器的凭据通过 L2 凭据管理组件统一管理：

```python
# 凭据命名规范
# {connector_name}_{credential_type}

# ONES 浏览器 Cookie（存储 Cookie 文件路径）
ones_cookie_path = "~/.openclaw/secrets/ones.cookie"

# OA 浏览器 Cookie
oa_cookie_path = "~/.openclaw/secrets/oa.cookie"

# 工时门户 API Token
timesheet_token = "timesheet_api_token"

# 企微 API 凭据
wecom_corpid = "wecom_corpid"
wecom_corpsecret = "wecom_corpsecret"
```

### 12.2 凭据获取

```python
# base_connector.py
class BaseConnector(ABC):
    def _get_credential(self, key: str) -> str:
        """从 L2 凭据管理获取凭据。

        Args:
            key: 凭据键名

        Returns:
            凭据值，不存在时返回 None
        """
        secrets_dir = Path.home() / ".openclaw" / "secrets"
        cred_file = secrets_dir / key

        if cred_file.exists():
            return cred_file.read_text(encoding="utf-8").strip()
        return None

    def _set_credential(self, key: str, value: str) -> None:
        """存储凭据到 L2 凭据管理。"""
        secrets_dir = Path.home() / ".openclaw" / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        cred_file = secrets_dir / key
        cred_file.write_text(value, encoding="utf-8")
        cred_file.chmod(0o600)
```

### 12.3 凭据轮换

| 连接器 | 凭据类型 | 轮换方式 | 轮换频率 |
|---|---|---|---|
| ones | 浏览器 Cookie | 人工重新登录 | Cookie 过期时 |
| oa | 浏览器 Cookie | 人工重新登录 | Cookie 过期时 |
| timesheet | API Token | 联系管理员获取 | 每季度 |
| wecom_doc | corpid + corpsecret | 联系管理员获取 | 每季度 |
| local_import | 无需凭据 | - | - |

---

## 13. 错误处理

### 13.1 错误分类与处理策略

| 错误类型 | 处理策略 | 用户感知 | 自动恢复 |
|---|---|---|---|
| 认证失败 | 立即停止，告警 | 提示重新登录 | ❌ 需人工 |
| 网络超时 | 指数退避重试 3 次 | 提示网络异常 | ✅ 自动重试 |
| 数据解析失败 | 记录死信，跳过 | 提示部分失败 | ✅ 跳过继续 |
| 数据校验失败 | 记录死信，跳过 | 提示数据质量问题 | ✅ 跳过继续 |
| 系统错误 | 指数退避重试 3 次 | 提示系统异常 | ✅ 自动重试 |
| 重试耗尽 | 记录死信队列 | 提示同步失败 | ❌ 需人工 |

### 13.2 错误日志

所有错误通过 L2 可观测性组件记录：

```python
# 使用 L2 observability 的 logging 模块
from L2.infra.components.observability.scripts.logging import log_event

log_event(
    level="ERROR",
    component="integration.ones",
    event="sync_failed",
    attributes={
        "connector_name": "ones",
        "batch_id": batch_id,
        "error_type": "auth",
        "error_msg": "Cookie 已过期",
        "retry_count": 0,
    },
)
```

### 13.3 用户可见错误信息

| 场景 | 错误信息 | 建议操作 |
|---|---|---|
| ONES Cookie 过期 | "ONES 登录已过期，请重新登录" | 打开 Chrome 登录 ONES |
| OA Cookie 过期 | "OA 登录已过期，请重新登录" | 打开 Chrome 登录 OA |
| 工时门户 Token 失效 | "工时门户 Token 已失效，请联系管理员" | 联系管理员获取新 Token |
| 企微 API 凭据错误 | "企微 API 凭据错误，请联系管理员" | 联系管理员检查配置 |
| 文件不存在 | "文件不存在: {path}" | 检查文件路径 |
| 文件格式错误 | "无法解析文件: {path}，请检查格式" | 确认文件为 Excel/CSV |
| 字段映射缺失 | "字段映射未配置，请先配置" | 在 Web UI 配置字段映射 |
| 网络超时 | "网络超时，请检查网络连接" | 检查网络后重试 |

---

## 14. CLI 命令 + Web API

### 14.1 CLI 命令

```bash
# 列出所有连接器
bdms integration list

# 查看连接器状态
bdms integration status ones

# 执行同步
bdms integration sync ones --month 202606
bdms integration sync oa --date-range 2026-01,2026-06
bdms integration sync timesheet --month 202606
bdms integration sync wecom_doc --doc-type revenue
bdms integration sync local --path ./报表.xlsx --target delivery_report

# 同步所有已配置连接器
bdms integration sync-all

# 查询暂存数据
bdms integration staging --connector ones --batch-id xxx --status pending

# 暂存→业务表
bdms integration promote --connector ones --batch-id xxx \
    --target-module delivery_report --target-table dr_sheet_row

# 配置频率
bdms integration configure ones --schedule cron --cron "0 2 * * *"
bdms integration configure oa --schedule manual
bdms integration configure timesheet --schedule event \
    --triggers delivery_report.generate,revenue.generate

# 重试失败
bdms integration retry ones --batch-id xxx

# 同步历史
bdms integration history --connector ones --limit 10
```

### 14.2 Web API 路由

```
# ========== 数据集成 ==========

GET  /api/integration/connectors                    # 列出所有连接器
GET  /api/integration/connectors/{name}/status      # 连接器状态
POST /api/integration/sync                          # 执行同步
     Body: { "connector_name": "ones", "params": { "month": "202606" } }
POST /api/integration/sync/all                      # 同步所有已配置连接器
GET  /api/integration/staging                       # 查询暂存数据
     Query: connector_name, batch_id, status, limit, offset
POST /api/integration/staging/promote               # 暂存→业务表
     Body: { "connector_name": "ones", "batch_id": "xxx",
             "target_module": "delivery_report", "target_table": "dr_sheet_row" }
GET  /api/integration/frequency/{connector}         # 获取频率配置
PUT  /api/integration/frequency/{connector}         # 配置频率
     Body: { "schedule": "cron", "cron_expr": "0 2 * * *" }
POST /api/integration/retry                         # 重试失败同步
     Body: { "connector_name": "ones", "batch_id": "xxx" }
GET  /api/integration/history                       # 同步历史
     Query: connector_name, limit, offset
```

---

## 15. 测试策略

### 15.1 测试分层

| 层级 | 范围 | 工具 | 覆盖率目标 |
|---|---|---|---|
| 单元测试 | 连接器 / 适配器 / 管道 | pytest | ≥ 80% |
| 集成测试 | 同步管道 + 暂存流转 | pytest + 真实 DB | ≥ 70% |
| E2E 测试 | CLI + Web API | pytest + 真实 HTTP | 核心路径 100% |

### 15.2 单元测试

```python
# tests/integration/test_ones_connector.py
import pytest
from bdms.modules.integration.connectors.ones_connector import OnesConnector

class TestOnesConnector:
    """ONES 连接器单元测试。"""

    def test_authenticate_success(self, mock_browser):
        """认证成功。"""
        connector = OnesConnector()
        connector._browser = mock_browser
        mock_browser.execute_js.return_value = "true"
        assert connector.authenticate() is True

    def test_authenticate_failure(self, mock_browser):
        """认证失败。"""
        connector = OnesConnector()
        connector._browser = mock_browser
        mock_browser.execute_js.side_effect = Exception("Chrome not found")
        assert connector.authenticate() is False

    def test_normalize_signing_data(self):
        """签约数据标准化。"""
        connector = OnesConnector()
        raw = [{"BI履约ID": "P001", "销售合同编号": "C001", "合同名称": "测试合同"}]
        result = connector.normalize(raw)
        assert len(result) == 1
        assert result[0]["normalized_data"]["perf_id"] == "P001"
        assert result[0]["normalized_data"]["sales_contract_no"] == "C001"

    def test_normalize_empty_data(self):
        """空数据处理。"""
        connector = OnesConnector()
        result = connector.normalize([])
        assert result == []
```

### 15.3 集成测试

```python
# tests/integration/test_sync_pipeline.py
import pytest
from bdms.modules.integration.service import IntegrationService
from bdms.modules.integration.sync_pipeline import SyncPipeline

class TestSyncPipeline:
    """同步管道集成测试。"""

    def test_full_sync_flow(self, test_db):
        """完整同步流程：fetch → normalize → staging → promote。"""
        service = IntegrationService()

        # 1. 执行同步
        result = service.sync("ones", filter_name="签约项目统计", month="202606")
        assert result.status == "success"
        assert result.total_fetched > 0

        # 2. 验证暂存数据
        staging = service.get_staging_data("ones", result.batch_id)
        assert len(staging) > 0

        # 3. 提升到业务表
        promote_result = service.promote_staging(
            "ones", result.batch_id,
            target_module="delivery_report",
            target_table="dr_sheet_row",
        )
        assert promote_result["new_count"] > 0

    def test_idempotent_sync(self, test_db):
        """幂等同步：同一数据重复同步不产生重复。"""
        service = IntegrationService()

        # 第一次同步
        result1 = service.sync("ones", filter_name="签约项目统计", month="202606")
        staging1 = service.get_staging_data("ones", result1.batch_id)

        # 第二次同步（相同数据）
        result2 = service.sync("ones", filter_name="签约项目统计", month="202606")
        staging2 = service.get_staging_data("ones", result2.batch_id)

        # 验证：第二次同步的 new_count 应为 0
        promote1 = service.promote_staging(
            "ones", result1.batch_id,
            target_module="delivery_report", target_table="dr_sheet_row",
        )
        promote2 = service.promote_staging(
            "ones", result2.batch_id,
            target_module="delivery_report", target_table="dr_sheet_row",
        )
        assert promote2["new_count"] == 0
        assert promote2["unchanged_count"] == promote1["new_count"]
```

### 15.4 E2E 测试

```python
# tests/integration/test_integration_e2e.py
import pytest
import requests

BASE_URL = "http://localhost:8800"

class TestIntegrationE2E:
    """数据集成 E2E 测试（需要服务运行）。"""

    def test_list_connectors(self):
        """列出所有连接器。"""
        resp = requests.get(f"{BASE_URL}/api/integration/connectors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        names = [c["name"] for c in data]
        assert "ones" in names
        assert "oa" in names
        assert "timesheet" in names
        assert "wecom_doc" in names
        assert "local_import" in names

    def test_sync_ones(self):
        """同步 ONES 数据。"""
        resp = requests.post(
            f"{BASE_URL}/api/integration/sync",
            json={"connector_name": "ones", "params": {"month": "202606"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "partial")
        assert data["total_fetched"] > 0

    def test_get_staging_data(self):
        """查询暂存数据。"""
        # 先同步
        sync_resp = requests.post(
            f"{BASE_URL}/api/integration/sync",
            json={"connector_name": "ones", "params": {"month": "202606"}},
        )
        batch_id = sync_resp.json()["batch_id"]

        # 查询暂存
        resp = requests.get(
            f"{BASE_URL}/api/integration/staging",
            params={"connector_name": "ones", "batch_id": batch_id},
        )
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_promote_staging(self):
        """暂存→业务表。"""
        # 同步
        sync_resp = requests.post(
            f"{BASE_URL}/api/integration/sync",
            json={"connector_name": "ones", "params": {"month": "202606"}},
        )
        batch_id = sync_resp.json()["batch_id"]

        # 提升
        resp = requests.post(
            f"{BASE_URL}/api/integration/staging/promote",
            json={
                "connector_name": "ones",
                "batch_id": batch_id,
                "target_module": "delivery_report",
                "target_table": "dr_sheet_row",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_count"] > 0

    def test_configure_frequency(self):
        """配置频率。"""
        resp = requests.put(
            f"{BASE_URL}/api/integration/frequency/ones",
            json={"schedule": "cron", "cron_expr": "0 2 * * *"},
        )
        assert resp.status_code == 200

        # 验证
        resp = requests.get(f"{BASE_URL}/api/integration/frequency/ones")
        assert resp.status_code == 200
        assert resp.json()["schedule"] == "cron"
        assert resp.json()["cron_expr"] == "0 2 * * *"
```

### 15.5 测试数据

| 测试数据 | 来源 | 用途 |
|---|---|---|
| ONES 签约项目统计 CSV | `tests/fixtures/ones_signing_sample.csv` | ONES 连接器测试 |
| OA 合同列表 CSV | `tests/fixtures/oa_contract_sample.csv` | OA 连接器测试 |
| 工时门户 JSON | `tests/fixtures/timesheet_sample.json` | 工时连接器测试 |
| 企微文档 JSON | `tests/fixtures/wecom_doc_sample.json` | 企微连接器测试 |
| 本机导入 Excel | `tests/fixtures/local_import_sample.xlsx` | 本机导入测试 |

### 15.6 黄金基准对比

| 对比项 | 基准来源 | 对比方式 |
|---|---|---|
| ONES 签约数据 | `~/Downloads/2026周报-签约项目统计.csv` | 行数 + 关键字段值 |
| OA 合同数据 | OA 系统导出 | 合同编号 + 金额 |
| 工时数据 | 工时门户导出 | 人员 + 日期 + 工时 |

---

## 附录 B：复用资产清单与使用方式

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| ONES 浏览器导出技能 | `L4-proprietary/skills/ones-browser-export/` | 重构为 ONES 连接器 | ⭐⭐⭐⭐⭐ |
| 周报导入器 | `modules/revenue/weekly_importer.py` | 重构为 ONES 连接器的一部分 | ⭐⭐⭐⭐ |
| 凭据管理 | `L2-infra/components/credentials/` | 直接调用 | ⭐⭐⭐⭐ |
| 可观测性 | `L2-infra/components/observability/` | 直接调用 | ⭐⭐⭐ |
| BaseImporter | `modules/base.py` | 继承扩展 | ⭐⭐⭐ |
| BaseService | `modules/base.py` | 继承扩展 | ⭐⭐⭐ |
| DB 层 | `core/db.py` | 直接调用 | ⭐⭐⭐⭐ |
| Schema 定义 | `core/schemas_v21.py` | 扩展 | ⭐⭐⭐⭐ |
| 事件总线 | `core/event_bus.py` | 直接调用 | ⭐⭐⭐ |
| 路径管理 | `core/paths.py` | 直接调用 | ⭐⭐⭐ |

---

## 16. 开发计划

### Phase 1：基础设施（2 天）

- [ ] BaseConnector 抽象基类
- [ ] ConnectorRegistry 注册表
- [ ] IntegrationService 编排层
- [ ] int_frequency_config 表
- [ ] int_dead_letter 表
- [ ] int_field_mapping 表

### Phase 2：连接器实现（3 天）

- [ ] ONES 连接器（复用 ones-browser-export）
- [ ] OA 连接器
- [ ] 工时门户连接器
- [ ] 企微文档连接器
- [ ] 本机导入连接器

### Phase 3：同步管道（2 天）

- [ ] SyncPipeline 同步管道
- [ ] 暂存层操作
- [ ] 幂等写入
- [ ] 事件通知

### Phase 4：调度器 + 频率配置（1 天）

- [ ] SyncScheduler 调度器
- [ ] cron 模式
- [ ] event 模式
- [ ] 频率配置 API

### Phase 5：错误处理（1 天）

- [ ] RetryHandler 指数退避
- [ ] DeadLetterQueue 死信队列
- [ ] AlertManager 告警

### Phase 6：CLI + Web API（1 天）

- [ ] CLI 命令
- [ ] Web API 路由
- [ ] 前端页面（连接器管理 + 同步监控）

### Phase 7：测试（2 天）

- [ ] 单元测试
- [ ] 集成测试
- [ ] E2E 测试
- [ ] 黄金基准对比

**总计：12 天**

---

## 变更历史

- 2026-09-22: v2.1 Detail 初版
