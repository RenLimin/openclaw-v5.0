# BDMS v2.1 Integration 模块详细设计

> 版本：v2.1 Detail（2026-09-19）
> 层级：L4 专有业务层 — 横切模块
> 继承：L3 `delivery-management-framework`（整体框架）+ `integration-connector-base`（连接器基类契约）
> 状态：设计阶段，待 Rex 审核

---

## 1. 模块概述

Integration 是 BDMS v2.1 的**外部系统数据接入层**，负责统一认证、数据拉取、标准化处理和幂等落地，为所有业务模块提供干净、一致、可追溯的外部数据。

**核心定位**：唯一数据入口 — 所有外部系统的数据必须经过 Integration 层标准化后进入 BDMS，不允许业务模块直接调用外部 API。

**L3 域归属**：横切（cross-cutting）

**服务的业务阶段**：全阶段（所有需要外部数据的流程节点）

---

## 2. 技术方案

### 2.1 技术选型

| 维度 | 选型 | 依据 |
|---|---|---|
| 语言 | Python 3.10+ | 与 BDMS 全栈一致 |
| HTTP 客户端 | `requests` + `urllib3`（连接池复用） | 标准库生态完善 |
| 浏览器自动化 | `playwright`（无头 Chrome） | ONES 无 API 时可走 UI 自动化 |
| 文件解析 | `openpyxl`（Excel）+ `csv` + `json` | 标准库 + 轻量 |
| 异步调度 | APScheduler（cron + 间隔） | 复用 L2 基础设施 |
| 幂等机制 | source_id + connector_name + batch_id 三键唯一 | 防止重复拉取 |
| 错误退避 | 指数退避（1s → 2s → 4s → 8s → 最大 60s） | 避免雪崩 |

### 2.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
|---|---|---|
| L2 Credential-005 | L2 | SecretRef 凭据管理（每个连接器独立凭据） |
| L2 Persistence-006 | L2 | SQLite + Repository 模式（staging 表） |
| L3 DMS Framework | L3 | 事件总线（同步完成后通知各模块） |
| bdms.core.db | L4 Core | 统一 DB 连接与事务管理 |
| bdms.core.schemas | L4 Core | INTEGRATION_SCHEMA（staging 表结构） |
| bdms.modules.base | L4 Base | BaseImporter 骨架（校验/幂等/重试） |

### 2.3 与现有代码的复用/重构关系

现有 `weekly_importer.py` 是 ONES 数据导入的临时脚本，v2.1 重构为：

1. **ONES 连接器**：`weekly_importer.py` 的核心逻辑提取为 `OnesConnector`，走 API 优先、浏览器自动化兜底
2. **财务报表导入器**：现有确收对比表导入逻辑提取为 `FinanceConnector`（本地文件模式）
3. **新增连接器**：OA / 工时 / 企微文档 — 全新实现
4. **统一调度**：从 cron 脚本迁移到 APScheduler + CLI 双入口

---

## 3. 接口契约

### 3.1 IntegrationService（集成服务）

```python
class IntegrationService:
    """外部系统数据接入统一服务"""

    def list_connectors(self) -> list[dict]:
        """
        列出所有已注册连接器
        返回：[{"name": "ones", "label": "ONES 项目管理", "status": "active",
                "last_sync": "2026-08-15T10:30:00", "connector_type": "api"}, ...]
        """

    def get_connector_status(self, name: str) -> dict:
        """
        查看连接器状态
        返回：{"name": "ones", "status": "active", "last_sync": "...",
               "last_result": {"records": 150, "new": 12, "updated": 5, "unchanged": 133},
               "next_scheduled": "2026-08-16T10:00:00", "health": "ok"}
        """

    def sync(self, connector_name: str, mode: str = "incremental",
             **params) -> 'SyncResult':
        """
        执行数据同步
        connector_name: 连接器名（ones / oa / timesheet / wecom_doc / finance）
        mode: incremental（增量）| full（全量）| dry_run（仅预览不写入）
        **params: 连接器特定参数（如 path / date_range / filters）
        返回：SyncResult 对象
        """

    def get_staging_data(self, connector_name: str, batch_id: str,
                         status: str = None) -> list[dict]:
        """
        查看 staging 数据
        status: pending | processed | error | None=all
        """

    def retry_staging_errors(self, connector_name: str,
                             batch_id: str) -> 'SyncResult':
        """重试 staging 中 status=error 的记录"""

    def register_connector(self, connector: 'BaseConnector') -> None:
        """注册连接器（启动时调用）"""

    def get_connector(self, name: str) -> 'BaseConnector | None':
        """获取连接器实例"""
```

### 3.2 SyncResult（同步结果）

```python
@dataclass
class SyncResult:
    connector_name: str
    batch_id: str              # 本次同步批次 ID（UUID）
    mode: str                  # incremental | full | dry_run
    started_at: str            # ISO8601
    completed_at: str | None
    status: str                # running | success | partial | error
    total_fetched: int         # 从外部系统拉取的记录数
    new_count: int             # 新增到 staging 的记录数
    updated_count: int         # 更新的记录数
    unchanged_count: int       # 未变化的记录数（幂等跳过）
    error_count: int           # 处理失败的记录数
    errors: list[dict]         # 错误详情 [{"record_id": "...", "error": "..."}]
    dry_run: bool = False

    @property
    def is_success(self) -> bool:
        return self.status == "success" and self.error_count == 0
```

### 3.3 BaseConnector（连接器抽象基类）

```python
class BaseConnector(ABC):
    """所有外部系统连接器的抽象基类"""

    # 子类必须声明
    name: str = ""             # 连接器标识（ones / oa / timesheet / wecom_doc / finance）
    label: str = ""            # 显示名称
    connector_type: str = ""   # api | browser | local_file | hybrid
    target_module: str = ""    # 数据落地目标模块

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._credential_name = f"bdms_integration_{self.name}"

    # ---------- 生命周期 ----------

    def authenticate(self) -> bool:
        """
        认证并建立连接
        返回：True=认证成功，False=认证失败（触发告警）
        凭据从 L2 Credential-005 获取（SecretRef）
        """

    def fetch(self, **params) -> list[dict]:
        """
        从外部系统拉取原始数据
        params: 同步参数（date_range / filters / path 等）
        返回：原始数据列表（未标准化）
        """

    def normalize(self, raw: list[dict]) -> list[dict]:
        """
        将原始数据标准化为 BDMS 统一中间格式
        返回：标准化后的记录列表
        统一格式：{
            "source_id": "外部系统唯一 ID",
            "source_system": self.name,
            "source_data": {...},          # 原始数据快照（JSON）
            "normalized_data": {...},      # 标准化后的字段
            "fetched_at": "ISO8601",
            "batch_id": "..."
        }
        """

    def load_to_staging(self, records: list[dict]) -> int:
        """
        将标准化数据写入 staging 表
        幂等：source_id + connector_name + batch_id 唯一
        返回：实际写入条数（跳过重复）
        """

    # ---------- 模板方法（骨架） ----------

    def sync(self, mode: str = "incremental", **params) -> SyncResult:
        """
        同步模板方法 — 子类通常不需要覆盖
        流程：authenticate → fetch → normalize → load_to_staging → emit_event
        """
        ...

    # ---------- 事件 ----------

    def emit_sync_completed(self, result: SyncResult) -> None:
        """同步完成后发布事件到 L3 事件总线"""
        # 事件名：integration.sync.completed
        # 载荷：{"connector": self.name, "batch_id": result.batch_id, "counts": ...}
```

### 3.4 LocalPathConnector（本地文件连接器基类）

```python
class LocalPathConnector(BaseConnector):
    """本地文件路径作为数据源的连接器基类（Excel / CSV / JSON）"""

    supported_extensions: list[str] = [".xlsx", ".xls", ".csv", ".json"]

    def __init__(self, path: Path = None):
        super().__init__()
        self.path = path

    def fetch(self, **params) -> list[dict]:
        """
        从本地路径读取文件
        params: {"path": "..."} 或构造函数传入
        """
        path = Path(params.get("path", self.path))
        if not path.exists():
            raise FileNotFoundError(f"数据文件不存在: {path}")
        if path.suffix in (".xlsx", ".xls"):
            return self._read_excel(path)
        elif path.suffix == ".csv":
            return self._read_csv(path)
        elif path.suffix == ".json":
            return self._read_json(path")
        raise ValueError(f"不支持的文件格式: {path.suffix}")

    def _read_excel(self, path: Path) -> list[dict]:
        """读取 Excel 文件，返回 dict 列表（首行作为 header）"""
        ...

    def _read_csv(self, path: Path) -> list[dict]:
        """读取 CSV 文件"""
        ...

    def _read_json(self, path: Path) -> list[dict]:
        """读取 JSON 文件（期望为数组）"""
        ...
```

---

## 4. 连接器清单

### 4.1 连接器总览

| 连接器 | 数据源 | 落地目标 | 同步方式 | 调度频率 | 连接器类型 |
|---|---|---|---|---|---|
| `ones` | ONES 项目管理 | project_management / delivery_report | API + 浏览器自动化兜底 | 每日 06:00 | hybrid |
| `oa` | OA 系统（合同/立项/验收/采购） | contract_management / project_management | API | 每日 07:00 | api |
| `timesheet` | 工时门户 | project_management → cost | API + 本地文件 | 每周一 08:00 | hybrid |
| `wecom_doc` | 企业微信文档 | after_sales / risk | API + 本地文件 | 每日 09:00 | hybrid |
| `finance` | 财务报表（确收对比表） | project_management → revenue | 本地文件 | 每月 1 日 10:00 | local_file |

### 4.2 ONES 连接器（`OnesConnector`）

**数据映射**：

| ONES 字段 | BDMS 目标字段 | 目标模块 |
|---|---|---|
| project_id | pm_project.ones_id | project_management |
| project_name | pm_project.name | project_management |
| status | pm_project.ones_status | project_manager |
| start_date | pm_project.start_date | project_management |
| end_date | pm_project.end_date | project_management |
| owner | pm_project.owner | project_management |
| custom_fields.delivery_date | dr_delivery.delivery_date | delivery_report |
| custom_fields.acceptance_date | pm_acceptance.acceptance_date | project_management |

**同步策略**：
- 增量：只拉取近 7 天有更新的项目（ONES API `updated_at` 过滤）
- 全量：每月 1 日自动执行一次
- 幂等：`ones_id` 唯一，重复拉取只更新不插入

### 4.3 OA 连接器（`OaConnector`）

**数据映射**：

| OA 流程 | BDMS 目标 | 目标模块 |
|---|---|---|
| 合同审批 | cm_contract.oa_contract_id | contract_management |
| 立项审批 | pm_project.oa_project_id | project_management |
| 验收审批 | pm_acceptance.oa_acceptance_id | project_management |
| 采购审批 | cm_contract.oa_purchase_id | contract_management |

**同步策略**：
- OA 系统通常无增量 API，每次拉取全量后做幂等比对
- 通过 OA 流程状态变更时间做客户端过滤

### 4.4 工时连接器（`TimesheetConnector`）

**数据映射**：

| 工时字段 | BDMS 目标字段 | 目标模块 |
|---|---|---|
| employee_id | cost_record.employee_id | cost |
| project_id | cost_record.project_id | cost |
| date | cost_record.date | cost |
| hours | cost_record.hours | cost |
| task_type | cost_record.task_type | cost |

**同步策略**：
- 优先走 API（如工时系统支持）
- 兜底：从本地 Excel 导出文件导入（`LocalPathConnector`）
- 按周聚合，写入 `cost_record` 表

### 4.5 企微文档连接器（`WecomDocConnector`）

**数据映射**：

| 文档类型 | BDMS 目标 | 目标模块 |
|---|---|---|
| 售后工单记录 | as_ticket.wecom_doc_id | after_sales |
| 风险登记册 | risk_issue.wecom_doc_id | risk |
| 客户沟通记录 | as_ticket.communication_log | after_sales |

**同步策略**：
- 企微文档 API 读取（需企微凭据）
- 本地文件兜底（导出 Excel/CSV）
- 文档解析后按行写入 staging

### 4.6 财务报表连接器（`FinanceConnector`）

**数据映射**：

| 报表字段 | BDMS 目标字段 | 目标模块 |
|---|---|---|
| 项目 ID | revenue.project_id | revenue |
| 确收金额 | revenue.amount | revenue |
| 确收期间 | revenue.period | revenue |
| 对比基数 | revenue.benchmark | revenue |

**同步策略**：
- 纯本地文件模式（`LocalPathConnector` 子类）
- 每月财务提供确收对比表 Excel
- 解析后写入 `rev_recognition` 表

---

## 5. 数据模型

### 5.1 新增表

integration 模块新增 2 张表（前缀 `int_`）：

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `int_staging` | 数据暂存区（所有连接器共用） | id, connector_name, batch_id, source_id, status, source_data, normalized_data, error_msg, created_at, processed_at |
| `int_sync_log` | 同步历史日志 | id, connector_name, batch_id, mode, status, counts, started_at, completed_at, error_msg |

### 5.2 int_staging 表结构

```sql
CREATE TABLE int_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,          -- ones / oa / timesheet / wecom_doc / finance
    batch_id TEXT NOT NULL,                -- 同步批次 ID（UUID）
    source_id TEXT NOT NULL,               -- 外部系统唯一 ID
    status TEXT NOT NULL DEFAULT 'pending',-- pending | processed | error | skipped
    source_data TEXT,                      -- 原始数据 JSON（审计用）
    normalized_data TEXT,                  -- 标准化数据 JSON
    target_module TEXT NOT NULL,           -- 目标业务模块
    target_table TEXT,                     -- 目标业务表
    error_msg TEXT,                        -- 处理失败原因
    retry_count INTEGER DEFAULT 0,         -- 重试次数
    created_at TEXT NOT NULL,
    processed_at TEXT,                     -- 处理完成时间
    UNIQUE(connector_name, batch_id, source_id)
);

CREATE INDEX idx_int_staging_lookup
    ON int_staging(connector_name, batch_id, status);
CREATE INDEX idx_int_staging_target
    ON int_staging(target_module, target_table, status);
```

### 5.3 int_sync_log 表结构

```sql
CREATE TABLE int_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,                    -- incremental | full | dry_run
    status TEXT NOT NULL,                  -- success | partial | error
    total_fetched INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    unchanged_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    params TEXT,                           -- 同步参数 JSON
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_msg TEXT
);

CREATE INDEX idx_int_sync_log_connector
    ON int_sync_log(connector_name, started_at DESC);
```

---

## 6. 核心流程

### 6.1 数据同步主流程

```
触发同步（定时 / CLI / 事件）
    │
    ▼
IntegrationService.sync(connector_name, mode, **params)
    │
    ├─► 创建 batch_id（UUID）+ 写入 int_sync_log（status=running）
    │
    ├─► connector.authenticate()
    │       │
    │       ├─ 成功 ─► 继续
    │       └─ 失败 ─► 更新 int_sync_log（status=error）+ 告警 + 退出
    │
    ├─► connector.fetch(**params)
    │       │
    │       ├─ 成功 ─► 获得 raw_data（list[dict]）
    │       └─ 失败 ─► 指数退避重试（最多 3 次）
    │               ├─ 重试成功 ─► 继续
    │               └─ 全部失败 ─► 更新 int_sync_log + 告警 + 退出
    │
    ├─► connector.normalize(raw_data)
    │       │
    │       ├─ 成功 ─► 获得 normalized_data（统一中间格式）
    │       └─ 失败 ─► 记录错误，跳过该条，继续处理其他
    │
    ├─► connector.load_to_staging(normalized_data)
    │       │
    │       ├─ 幂等检查（source_id + connector_name + batch_id）
    │       │       ├─ 新记录 ─► INSERT（status=pending）
    │       │       ├─ 有变化 ─► UPDATE（status=pending）
    │       │       └─ 无变化 ─► UPDATE（status=skipped）
    │       │
    │       └─ 返回写入计数
    │
    ├─► 发布事件：integration.sync.completed
    │       └─ 订阅者：各业务模块的 staging processor
    │
    ├─► 更新 int_sync_log（status=success/partial, counts, completed_at）
    │
    └─► 返回 SyncResult
```

### 6.2 Staging → 业务表消费流程

```
integration.sync.completed 事件触发
    │
    ▼
各业务模块的 StagingProcessor 订阅处理
    │
    ├─► 查询 int_staging WHERE target_module = self.module AND status = 'pending'
    │
    ├─► 逐条处理：
    │       ├─ 业务规则校验（字段完整性 / 业务逻辑合法性）
    │       │       ├─ 通过 ─► INSERT/UPDATE 业务表
    │       │       │              更新 int_staging.status = 'processed'
    │       │       └─ 不通过 ─► 更新 int_staging.status = 'error'
    │       │                      记录 error_msg
    │       │
    │       └─ 处理失败 ─► retry_count++
    │               ├─ retry_count < 3 ─► 保持 pending，下次重试
    │               └─ retry_count >= 3 ─► status = 'error' + 告警
    │
    └─► 发布事件：integration.staging.processed（各模块独立）
```

### 6.3 错误处理与重试

**三级错误处理**：

| 级别 | 场景 | 处理方式 |
|---|---|---|
| L1 瞬时错误 | 网络超时 / 限流（429） | 指数退避重试（1s/2s/4s/8s/16s/32s/60s），最多 5 次 |
| L2 数据错误 | 字段缺失 / 格式异常 / 业务规则不通过 | 写入 staging status=error，跳过继续处理其他记录 |
| L3 系统错误 | 认证失败 / API 废弃 / 目标模块不可用 | 终止同步，更新 sync_log status=error，触发告警 |

**告警通道**：
- L1 重试 ≥ 3 次：日志 WARN，不告警
- L2 错误率 > 10%：日志 ERROR + 告警通知
- L3 系统错误：立即告警（wecom）

---

## 7. CLI 接口

```bash
# 列出连接器
bdms integration list

# 查看连接器状态
bdms integration status ones
bdms integration status finance

# 执行同步
bdms integration sync ones --mode incremental
bdms integration sync finance --path ./确收对比表_202608.xlsx
bdms integration sync timesheet --mode full
bdms integration sync ones --dry-run    # 仅预览不写入

# 查看 staging 数据
bdms integration staging list ones batch_001
bdms integration staging list finance --status error

# 重试错误
bdms integration staging retry ones batch_001

# 查看同步历史
bdms integration log ones --limit 10
bdms integration log --all --since "2026-08-01"

# 连接器管理
bdms integration config ones --show
bdms integration config finance --path /data/finance/
```

---

## 8. 调度配置

### 8.1 内置调度（APScheduler）

```python
SCHEDULES = {
    "ones": {
        "cron": "0 6 * * *",         # 每天 06:00
        "mode": "incremental",
        "full_sync_cron": "0 6 1 * *"  # 每月 1 日全量
    },
    "oa": {
        "cron": "0 7 * * *",         # 每天 07:00
        "mode": "incremental"
    },
    "timesheet": {
        "cron": "0 8 * * 1",         # 每周一 08:00
        "mode": "incremental"
    },
    "wecom_doc": {
        "cron": "0 9 * * *",         # 每天 09:00
        "mode": "incremental"
    },
    "finance": {
        "cron": "0 10 1 * *",        # 每月 1 日 10:00
        "mode": "full",
        "requires_manual_path": True  # 需要手动指定文件路径
    }
}
```

### 8.2 调度保障

- **幂等性**：同一批次重复触发不会重复写入（batch_id 唯一）
- **并发控制**：同一连接器不允许并发 sync（分布式锁，单实例用 threading.Lock）
- **超时控制**：单次 sync 超时 30 分钟，超时自动终止并标记 error
- **失败告警**：连续 3 次 sync 失败，触发 wecom 告警

---

## 9. 非功能设计

### 9.1 性能

| 场景 | 目标 | 手段 |
|---|---|---|
| ONES 增量同步 | < 30s（~200 条项目） | API 分页 + 批量插入 |
| OA 全量同步 | < 5min | 客户端过滤 + 幂等跳过 |
| 财务报表导入 | < 2min（~5000 行） | openpyxl 批量读取 |
| staging 查询 | < 100ms | 复合索引 |

### 9.2 可靠性

- **断点续传**：sync 中断后，已写入 staging 的数据不丢失，下次 sync 从断点继续
- **数据一致性**：staging → 业务表走事务（单条事务，避免部分成功）
- **审计追溯**：source_data 保留原始快照，可追溯任何一条数据的来源

### 9.3 安全

- **凭据隔离**：每个连接器独立 SecretRef，不共享
- **最小权限**：API Token 只授予读取权限
- **数据脱敏**：staging 表中不保留敏感字段（如密码、Token）
- **访问控制**：sync 操作需 operator 权限，staging retry 需 admin 权限

---

## 10. 实施计划

| 阶段 | 内容 | 预估工时 | 依赖 |
|---|---|---|---|
| P1 | int_staging + int_sync_log 表 + 仓储层 | 0.5d | — |
| P2 | BaseConnector + LocalPathConnector 抽象层 | 0.5d | — |
| P3 | ONES 连接器（API + 浏览器自动化兜底） | 2d | P2 完成 |
| P4 | OA 连接器 | 1d | P2 完成 |
| P5 | 工时连接器 | 1d | P2 完成 |
| P6 | 企微文档连接器 | 1d | P2 完成 |
| P7 | 财务报表连接器 | 0.5d | P2 完成 |
| P8 | IntegrationService + SyncResult + 事件集成 | 1d | P3-P7 完成 |
| P9 | CLI 命令实现 | 1d | P8 完成 |
| P10 | APScheduler 调度配置 | 0.5d | P8 完成 |
| P11 | 单测 + 集成测试（mock 外部 API） | 2d | — |
| **合计** | | **11d** | |

### 10.1 与 v1.0 的兼容性

- `weekly_importer.py` 保留为 CLI 快捷入口，内部调用 `OnesConnector.sync()`
- 现有确收对比表导入逻辑迁移到 `FinanceConnector`，接口不变
- 新增的连接器不影响已有模块的独立运行

---

## 11. 业界最佳实践对比与优化

### 11.1 对标标准

| 业界实践 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **ETL 工具模式**（Airbyte/Fivetran） | 抽取-转换-加载三阶段分离 | 有 ETL 三阶段，但耦合在 BaseConnector 内 | 阶段分离不够彻底 | 将 extract/transform/load 拆分为独立接口，可独立替换 |
| **CDC（变更数据捕获）** | 基于日志的增量同步，无 API 调用 | 全量/增量基于 API 查询 | 缺 CDC 能力 | 未来引入 Debezium/Maxwell 实现数据库级 CDC |
| **数据质量框架**（Great Expectations） | 数据校验规则化、可测试 | 校验逻辑硬编码在 normalize() | 缺统一数据质量框架 | 引入数据质量规则引擎，校验规则可配置 |
| **Schema Registry**（Confluent） | 数据 schema 集中管理、版本化 | schema 分散在各连接器 | 缺 schema 治理 | 建立 schema registry，管理所有外部数据格式 |
| **数据血缘**（Apache Atlas） | 追踪数据从来源到消费的完整链路 | 仅 source_data 字段做简单追溯 | 缺系统化血缘 | 增加数据血缘表，记录字段级来源和转换 |
| **幂等消费**（Kafka Exactly-Once） | 精确一次语义 | 幂等键 + INSERT OR REPLACE | 基本覆盖 | 未来引入事务性 outbox 保证精确一次 |
| **熔断器**（Resilience4j） | 快速失败，防止雪崩 | 有重试，无熔断 | 缺熔断机制 | 增加熔断器（连续 N 次失败后暂停 M 分钟） |
| **数据虚拟化**（Denodo） | 统一查询接口，不搬数据 | 数据必须入 BDMS | 缺虚拟化能力 | 未来可选：高频查询走虚拟化，分析场景入仓 |
| **API 网关**（Kong） | 统一认证/限流/监控 | 各连接器独立调用外部 API | 缺统一网关 | 增加 API 网关层，统一出口和监控 |

### 11.2 建议的优化项

**P0（v2.1 必须做）**：

1. **熔断器机制**
   - 问题：外部连接器失败时持续重试，可能雪崩
   - 方案：BaseConnector 增加熔断器装饰器（连续 5 次失败 → 暂停 15 分钟）
   - 成本：低（+1 个装饰器类）
   - 收益：高（防止级联故障）

2. **数据质量规则引擎**
   - 问题：校验逻辑硬编码，修改需改代码
   - 方案：引入可配置的数据质量规则（JSON/YAML），normalize() 时自动校验
   - 成本：中（+1 个规则引擎模块）
   - 收益：高（数据质量可治理）

**P1（v2.2 可做）**：

3. **Schema Registry**
   - 问题：外部数据格式变化时难以及时发现
   - 方案：建立 schema registry，管理所有外部数据格式和版本
   - 成本：中
   - 收益：中（格式变化自动告警）

4. **数据血缘追踪**
   - 问题：字段级来源和转换难以追溯
   - 方案：增加数据血缘表，记录每个字段的来源和转换规则
   - 成本：中
   - 收益：中（审计和排障）

**P2（远期）**：

5. **CDC 增量同步**
   - 问题：API 查询增量效率低，全量成本高
   - 方案：引入 CDC 工具（Debezium）实现数据库级增量
   - 成本高 | 收益：高（实时 + 零 API 调用）

6. **API 网关统一出口**
   - 问题：各连接器独立调用外部 API，缺统一监控和限流
   - 方案：增加 API 网关层（Kong/Traefik），统一出口
   - 成本高 | 收益：中（统一治理）

---

## 12. 风险与权衡

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 外部 API 变更 | 连接器失效，数据中断 | 抽象 BaseConnector，API 变更只需修改对应连接器；浏览器自动化兜底 |
| 凭据过期 | 同步失败 | SecretRef 过期监控 + 告警；OA/ONES 凭据走 L2 凭据管理，支持热更新 |
| 数据量大导致 staging 膨胀 | DB 性能下降 | staging 数据保留 30 天，过期自动清理（归档到 sync_log） |
| 外部系统限流 | 同步变慢 | 指数退避 + 分页控制 + 请求间隔 |
| 业务模块消费延迟 | 数据不一致 | 事件驱动 + 手动 staging retry + 监控面板展示消费延迟 |
| 浏览器自动化不稳定 | ONES 数据拉取失败 | API 优先，浏览器仅兜底；失败时告警 + 手动导入兜底 |
| 外部系统雪崩 | 级联故障 | 熔断器机制（P0 优化项） |
| 数据质量下降 | 脏数据进入业务层 | 数据质量规则引擎（P0 优化项） |
