# BDMS v2.1 Delivery Report 详细设计

> 版本：v2.1 Detail（2026-09-19）
> 层级：L4 专有业务层 — 模块 2（project_management）子引擎
> 继承：BaseEngine / BaseService（Base 层抽象）
> 状态：设计阶段，待 Rex 审核

---

## 1. 模块概述

Delivery Report（交付月报）是 BDMS 的核心计算模块之一，负责按月份聚合项目交付与验收数据，生成标准化的交付月报。

**L3 域归属**：Project Management → Delivery 子域

**与 v1.0 的关系**：v2.1 保留并重构 v1.0 `modules/delivery_report/` 的全部计算逻辑，将其包装为标准 BaseEngine/BaseService 契约，纳入 project_management 大模块作为子引擎存在，同时保持独立可调用。

**核心职责**：
1. 按月份计算交付项目明细（新签 + 递延）
2. 按月份计算验收项目明细
3. 按产品线 / 区域 / 部门多维度汇总
4. 生成 Excel 输出（15 Sheet 完整报表）
5. 与财务确收数据交叉校验

---

## 2. 技术方案

### 2.1 技术选型

| 维度 | 选型 | 依据 |
|---|---|---|
| 语言 | Python 3.10+ | 现有 BDMS 全栈 Python |
| 数据计算 | pandas + numpy | 现有 v1.0 已使用，性能满足月报规模（< 1000 行/月） |
| Excel 输出 | openpyxl + xlsxwriter | openpyxl 样式精细，xlsxwriter 图表支持好；双库并存（同 v1.0） |
| 持久化 | SQLite（通过 core.db） | 统一 DB 层，与 revenue/cost 等模块共享连接 |
| 模式 | 三模式幂等（auto/read/regenerate） | BaseService 标准契约 |

### 2.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
|---|---|---|
| BaseEngine / BaseService | L4 BDMS Base | 继承四方法契约 + 三模式骨架 |
| bdms.core.db | L4 BDMS Core | get_connection / save_sheet_rows / load_sheet_rows |
| bdms.core.paths | L4 BDMS Core | DATA_DIR / OUTPUT_DIR / ensure_dirs |
| bdms.core.schemas | L4 BDMS Core | DR_SCHEMA（交付报表结构定义） |
| L2 Office-011 | L2 | openpyxl 最佳实践 + 模板填充模式 |
| L2 Persistence-006 | L2 | SQLite + Repository 模式 |
| L3 DMS Framework | L3 | 事件总线（交付完成事件通知 revenue） |

### 2.3 与现有代码的复用/重构关系

现有 `modules/delivery_report/engine.py` 已实现核心计算逻辑。v2.1 改造：

1. **引擎层**：包装 `DeliveryReportEngine(BaseEngine)`，实现 compute/persist/load/has_data 四方法
2. **服务层**：新增 `DeliveryReportService(BaseService)`，实现 generate/export 骨架
3. **数据层**：将原 `monthly_data_YYYYMM` 平铺表升级为结构化三表（见 §4）
4. **兼容层**：保留 v1.0 直接调用入口（`dr_engine.compute_month(month)`），确保 18 个现有测试全绿

---

## 3. 接口契约

### 3.1 Engine 层（纯计算，零副作用）

```python
class DeliveryReportEngine(BaseEngine):
    """交付月报计算引擎 — 纯函数层"""

    def compute(self, month: str, source_data: dict = None) -> dict[str, pd.DataFrame]:
        """
        计算指定月份的交付月报数据。

        Args:
            month: 月份，格式 'YYYYMM'
            source_data: 可选，外部注入的源数据（用于测试/离线计算）
                         包含：projects, deliveries, acceptances, master_data

        Returns:
            dict，key 为 sheet 名，value 为 DataFrame：
            - summary: 月度汇总
            - new_sign: 新签交付明细
            - deferred: 递延交付明细
            - acceptance: 验收明细
            - by_product_line: 按产品线汇总
            - by_region: 按区域汇总
            - by_department: 按部门汇总
        """
        ...

    def persist(self, month: str, data: dict[str, pd.DataFrame],
                overwrite: bool = False) -> dict:
        """持久化计算结果到 SQLite"""
        ...

    def load(self, month: str) -> dict[str, pd.DataFrame]:
        """从 SQLite 加载已计算数据"""
        ...

    def has_data(self, month: str) -> bool:
        """检查指定月份是否已有数据"""
        ...
```

### 3.2 Service 层（编排 + 副作用）

```python
class DeliveryReportService(BaseService):
    """交付月报服务层 — 三模式幂等编排"""

    module_name = "delivery_report"
    engine: DeliveryReportEngine

    def generate(self, month: str, mode: str = "auto") -> dict:
        """
        生成指定月份的交付月报（BaseService 标准入口）。

        Args:
            month: 'YYYYMM'
            mode: auto（有数据就读，没有就算）
                  read（只读，没有就报错）
                  regenerate（强制重算）

        Returns:
            {
                "month": "202608",
                "mode": "auto",
                "action": "computed" | "loaded",
                "sheets": {sheet_name: row_count},
                "generated_at": ISO8601
            }
        """
        ...

    def export(self, month: str, out_path: Path = None) -> Path:
        """
        导出 Excel 报表。
        如无数据先 auto 生成，再导出。
        """
        ...

    def list_months(self) -> list[str]:
        """列出所有有数据的月份（降序）"""
        ...

    def reconcile_with_revenue(self, month: str) -> dict:
        """
        与 revenue 子引擎交叉校验。
        返回差异项列表（交付了但未确收 / 确收了但未交付）。
        """
        ...
```

### 3.3 状态机

| 状态 | 含义 | 触发动作 → 下一个状态 |
|---|---|---|
| `empty` | 无数据 | compute() → `computed` |
| `computed` | 已计算（内存中 / 未持久化） | persist() → `persisted`；丢弃 → `empty` |
| `persisted` | 已持久化到 DB | export() → `exported`；regenerate → `computed` |
| `exported` | 已导出 Excel | regenerate → `computed` |

**非法转换**：
- empty → exported（必须经过计算和持久化）
- persisted → computed（重算需走 regenerate 显式调用）

---

## 4. 数据模型

### 4.1 表清单

| 表名 | 用途 | 主键 | 行数预估 |
|---|---|---|---|
| `dr_monthly_summary` | 月度汇总（顶部指标卡） | month | 1 行/月 |
| `dr_delivery_item` | 交付明细（新签 + 递延） | id (auto) | ~200 行/月 |
| `dr_acceptance_item` | 验收明细 | id (auto) | ~150 行/月 |
| `dr_dimension_rollup` | 维度汇总（产品线/区域/部门） | id (auto) | ~30 行/月 |
| `dr_job` | 计算任务记录（BaseService 用） | id | 少量 |

### 4.2 详细字段

#### dr_monthly_summary

| 字段 | 类型 | 说明 |
|---|---|---|
| month | TEXT PK | 月份 YYYYMM |
| new_sign_count | INTEGER | 新签交付项目数 |
| new_sign_amount | REAL | 新签交付金额 |
| deferred_count | INTEGER | 递延交付项目数 |
| deferred_amount | REAL | 递延交付金额 |
| total_delivery_count | INTEGER | 总交付项目数 |
| total_delivery_amount | REAL | 总交付金额 |
| acceptance_count | INTEGER | 验收项目数 |
| acceptance_amount | REAL | 验收金额 |
| computed_at | TEXT | 计算时间 ISO8601 |
| data_version | INTEGER | 数据版本号（regenerate 时 +1） |

#### dr_delivery_item

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 ID |
| month | TEXT | 月份 YYYYMM |
| delivery_type | TEXT | new_sign / deferred（新签/递延） |
| project_code | TEXT | 项目编号 |
| project_name | TEXT | 项目名称 |
| customer | TEXT | 客户名称 |
| product_line | TEXT | 产品线 |
| region | TEXT | 区域 |
| department | TEXT | 所属部门 |
| contract_amount | REAL | 合同金额 |
| delivery_amount | REAL | 本月交付金额 |
| delivery_date | TEXT | 交付日期 YYYY-MM-DD |
| delivery_note | TEXT | 交付说明 |
| source | TEXT | 数据来源：ones / manual / import |
| created_at | TEXT | 创建时间 |

#### dr_acceptance_item

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 ID |
| month | TEXT | 月份 |
| project_code | TEXT | 项目编号 |
| project_name | TEXT | 项目名称 |
| acceptance_type | TEXT | 初验 / 终验 / 阶段验收 |
| acceptance_amount | REAL | 验收金额 |
| acceptance_date | TEXT | 验收日期 |
| acceptance_doc_ref | TEXT | 验收单编号 / 引用 |
| source | TEXT | 来源 |
| created_at | TEXT | 创建时间 |

#### dr_dimension_rollup

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| month | TEXT | 月份 |
| dimension | TEXT | product_line / region / department |
| dim_value | TEXT | 维度值 |
| delivery_count | INTEGER | 交付数量 |
| delivery_amount | REAL | 交付金额 |
| acceptance_count | INTEGER | 验收数量 |
| acceptance_amount | REAL | 验收金额 |

### 4.3 索引

```sql
CREATE INDEX idx_dr_delivery_month ON dr_delivery_item(month);
CREATE INDEX idx_dr_delivery_project ON dr_delivery_item(project_code);
CREATE INDEX idx_dr_acceptance_month ON dr_acceptance_item(month);
CREATE INDEX idx_dr_rollup_month_dim ON dr_dimension_rollup(month, dimension);
```

---

## 5. 核心数据流

```
                          ┌─────────────────────┐
                          │   数据源层            │
                          │  ONES / 本地Excel /  │
                          │  手动录入 / OA API   │
                          └─────────┬───────────┘
                                    │
                          ┌─────────▼───────────┐
                          │  integration 模块    │
                          │  （统一标准化 + 幂等）│
                          └─────────┬───────────┘
                                    │ 标准化后的数据
                                    ▼
    ┌───────────────────────────────────────────────────────┐
    │              DeliveryReportService.generate()         │
    │  ┌─────────┐    ┌──────────┐    ┌────────────────┐  │
    │  │ auto?   │───▶│ compute()│───▶│ persist()      │  │
    │  └─────────┘    └──────────┘    └────────────────┘  │
    │       │                                    │         │
    │       └────────── load() ◀─────────────────┘         │
    └──────────────────────────────┬────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   dr_* 表（SQLite）          │
                    │   月度交付/验收数据           │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────▼─────────────────────┐
              │  export()  ──▶  Excel 15 Sheet 报表     │
              │  reconcile_with_revenue()               │
              └──────────────────────────────────────────┘
```

**关键数据流说明**：

1. **数据入口**：不直接对接外部系统，通过 integration 模块统一接入
2. **计算触发**：BaseService.generate(mode="auto") 控制是否重算
3. **持久化策略**：regenerate 模式下先删后插（原子事务）
4. **导出时机**：独立于计算，可重复导出（基于已持久化的数据）
5. **跨模块联动**：交付完成后通过事件总线通知 revenue 子引擎更新确收预测

---

## 6. CLI 入口

```bash
# 生成交付月报（auto 模式）
bdms delivery-report generate 202608

# 强制重算
bdms delivery-report generate 202608 --mode regenerate

# 只读已有数据（数据不存在时报错）
bdms delivery-report generate 202608 --mode read

# 导出 Excel
bdms delivery-report export 202608 --output ./202608交付月报.xlsx

# 查看某月汇总
bdms delivery-report summary 202608

# 与确收数据交叉校验
bdms delivery-report reconcile 202608

# 列出所有有数据的月份
bdms delivery-report list
```

---

## 7. 实现路径

| 阶段 | 内容 | 预计工作量 | 依赖 |
|---|---|---|---|
| Phase 1 | 引擎层包装：将现有 `dr_engine.py` 包装为 BaseEngine 子类 | 0.5 天 | 现有 v1.0 引擎 |
| Phase 2 | 服务层实现：DeliveryReportService + 三模式骨架 | 0.5 天 | BaseService |
| Phase 3 | 数据层迁移：dr_* 新表 + 历史数据迁移脚本 | 1 天 | core.db |
| Phase 4 | Excel 导出重构：从 v1.0 导出函数迁移到 service.export() | 0.5 天 | Office-011 |
| Phase 5 | CLI 入口 + API 端点 | 0.5 天 | Base CLI 框架 |
| Phase 6 | 兼容层 + 回归测试 | 0.5 天 | v1.0 测试用例 |
| **合计** | | **3.5 天** | |

---

## 8. 验收标准

| # | 验收项 | 通过标准 |
|---|---|---|
| 1 | 现有 18 个 v1.0 测试全绿 | `pytest tests/test_delivery_report.py` 18 passed |
| 2 | 黄金基准零差异 | 202606 手工报表 vs 生成报表 18/18 项零误差 |
| 3 | 三模式幂等 | auto 第二次运行走 loaded；read 在无数据时报错；regenerate 强制重算且版本号 +1 |
| 4 | CLI 全入口可用 | 上述 7 条 CLI 命令全部执行无崩溃 |
| 5 | 数据完整性 | regenerate 后数据行数与首次计算完全一致（确定性） |
| 6 | 跨模块联动 | 交付数据变更后 revenue 能感知（事件总线测试） |
| 7 | 导出功能 | 导出的 Excel 包含 15 Sheet，格式与 v1.0 一致 |
| 8 | 凭据安全 | 无明文密钥，所有外部接入走 integration 模块 |

---

## 9. 复用资产治理：统一适配规范

### 9.1 原则：复用不是直接搬，而是适配后再用

现有 v1.0 的 `dr_engine.py` 和相关导出代码**不能直接搬进 v2.1**，必须按照 BDMS v2.1 的统一设计框架、接口规格和编码规范进行调整、优化甚至重构。

**核心理念**：v1.0 代码是"业务逻辑的来源"，不是"可以直接运行的成品"。

### 9.2 v1.0 dr_engine.py 的三层适配流程

```
v1.0 dr_engine.py
    │
    ▼
第 1 层：接口对齐
    ├─ 包装为 DeliveryReportEngine(BaseEngine)
    ├─ 实现 compute/persist/load/has_data 四方法
    ├─ compute() 返回统一结构 {sheet_name: DataFrame}
    └─ 所有方法增加 type hints
    │
    ▼
第 2 层：规范统一
    ├─ 命名规范：方法名/变量名对齐 Base 层契约
    ├─ 错误处理：统一异常类型 + 错误码映射
    ├─ 日志规范：结构化日志 + 统一格式
    ├─ 配置规范：从 sys_settings 读取，不硬编码
    └─ 测试规范：pytest + 覆盖率 ≥ 80%
    │
    ▼
第 3 层：优化增强
    ├─ 性能优化：消除 pandas 链式赋值 / 减少内存拷贝
    ├─ 可靠性增强：边界值处理 + 异常兜底
    ├─ 可维护性：拆分超长函数 / 增加 docstring
    └─ 可观测性：增加计算耗时统计 + 行数统计
```

### 9.3 适配质量门禁

所有 v1.0 代码在进入 v2.1 前，必须通过以下检查：

1. ✅ **接口契约对齐**：符合 BaseEngine / BaseService 接口
2. ✅ **命名规范**：模块前缀、方法名、变量名符合 v2.1 规范
3. ✅ **错误处理**：异常类型统一 + 错误码映射
4. ✅ **幂等保证**：regenerate 模式结果确定性
5. ✅ **单元测试**：核心逻辑覆盖率 ≥ 80%
6. ✅ **类型注解**：所有公共方法有完整 type hints
7. ✅ **文档注释**：所有公共类/方法有 docstring
8. ✅ **黄金基准验证**：202606 数据零差异

### 9.4 具体适配动作清单

| v1.0 资产 | 适配动作 | 适配后位置 |
|---|---|---|
| `dr_engine.py compute_month()` | 包装为 `DeliveryReportEngine.compute()`，统一返回格式 | `modules/delivery_report/engine.py` |
| `dr_engine.py` 中的数据加载函数 | 迁移到 `persist()` 和 `load()`，走 DB 层 | `modules/delivery_report/engine.py` |
| `exporter.py` 导出函数 | 迁移到 `DeliveryReportExporter(BaseExporter)` | `modules/delivery_report/exporter.py` |
| 分散的常量定义 | 集中到 `bdms.core.schemas.DR_SCHEMA` | `core/schemas.py` |
| 硬编码的路径配置 | 迁移到 `sys_settings` + `bdms.core.paths` | `core/paths.py` |
| v1.0 直接调用入口 | 保留为兼容层（`dr_engine.compute_month()`），内部调用 Service | `modules/delivery_report/compat.py` |

---

## 10. AI Token 消耗标记

### 10.1 标记规则

| 标记 | 含义 | 本模块是否使用 |
|---|---|---|
| 🔒 **NO_TOKEN** | 纯代码逻辑，零 Token 消耗 | ✅ 本模块所有核心功能 |
| ⚡ **OPTIONAL_TOKEN** | 可选使用大模型，不用也能工作 | ❌ 本模块无 |
| 🔥 **REQUIRED_TOKEN** | 必须使用大模型 | ❌ 本模块无 |

### 10.2 详细标记

| 功能点 | 标记 | 说明 |
|---|---|---|
| 月报计算（compute） | 🔒 NO_TOKEN | 纯 Python 代码，零 AI 依赖 |
| Excel 导出（export） | 🔒 NO_TOKEN | openpyxl 纯代码生成 |
| 数据持久化（persist/load） | 🔒 NO_TOKEN | SQLite 纯代码 |
| 交叉校验（reconcile） | 🔒 NO_TOKEN | 纯 SQL + 逻辑比对 |
| 数据校验/异常检测 | 🔒 NO_TOKEN | 纯规则判断，不用 AI |

> **结论**：Delivery Report 模块是**纯代码计算模块**，零 Token 消耗。开发和运行都不需要大模型。
> 
> 开发阶段可使用 AI 辅助写代码和测试用例（这属于开发过程消耗，不计入系统运行消耗）。

---

## 11. 计算逻辑实现：纯代码优先，pandas/openpyxl 仅作工具

### 11.1 原则：计算逻辑用 Python 代码实现，pandas 仅作数据操作工具

> Rex 一贯建议：交付月报的计算通过代码逻辑实现，而不是依赖 pandas/openpyxl 等库的隐式行为。

**核心理由**：
1. **可控性**：纯代码计算逻辑透明，每一步都可追踪、可调试
2. **可测试性**：纯函数单元测试覆盖所有分支，pandas 的隐式行为难以全测
3. **可维护性**：纯代码比 pandas 链式操作更易读，新人上手成本低
4. **可移植性**：不依赖 pandas 特定版本行为，升级不踩坑
5. **性能可控**：数据量小时纯代码够快，数据量大时再针对性优化

### 11.2 pandas 的使用边界

| 场景 | 用什么 | 说明 |
|---|---|---|
| **计算逻辑**（分类/汇总/分摊/匹配） | **纯 Python 代码** | 业务规则用显式循环/条件判断写 |
| **数据读写**（DB 读取/写入） | pandas + SQL | 作为 IO 层工具，不算计算 |
| **数据整理**（排序/去重/合并） | pandas | 纯数据操作，不含业务规则 |
| **Excel 导出** | openpyxl | 格式化输出，不含业务逻辑 |
| **大批量数据（>10万行）** | pandas 向量化 | 性能瓶颈时再优化，优先纯代码 |

### 11.3 纯代码计算示例（v1.0 对比）

**❌ v1.0 可能的写法（pandas 隐式逻辑）：**
```python
df = merged_df.groupby(['product_line', 'delivery_type']).agg({
    'delivery_amount': 'sum',
    'project_code': 'nunique'
}).reset_index()
```

**✅ v2.1 推荐写法（纯代码 + 显式逻辑）：**
```python
def aggregate_by_product_line(delivery_items: list[dict]) -> dict[tuple, dict]:
    """按产品线汇总交付数据。纯代码实现，逻辑透明。"""
    result = {}
    for item in delivery_items:
        key = (item['product_line'], item['delivery_type'])
        if key not in result:
            result[key] = {
                'delivery_amount': 0.0,
                'project_codes': set(),
                'project_count': 0
            }
        result[key]['delivery_amount'] += item['delivery_amount']
        result[key]['project_codes'].add(item['project_code'])
        result[key]['project_count'] = len(result[key]['project_codes'])
    return result
```

### 11.4 性能保障策略

数据量增大时，纯代码可能变慢。分层优化策略：

| 数据量级 | 方案 | 预期性能 |
|---|---|---|
| < 1000 行/月（当前） | 纯 Python 代码 | < 1s，足够 |
| 1000 - 10000 行/月 | 纯代码 + 局部热点用 pandas 优化 | < 5s |
| > 10000 行/月 | 全量 pandas 向量化 + SQL 预聚合 | < 10s |

**原则**：先写正确的纯代码，等性能瓶颈出现再优化。不要过早用 pandas 优化。

---

## 12. 数据统计与分析能力增强

### 12.1 当前能力 vs 建议增强

| 能力 | 当前 v2.1 设计 | 建议增强 | 优先级 |
|---|---|---|---|
| 月度汇总 | ✅ 有（交付数/金额/验收数） | 保持 | — |
| 多维度汇总 | ✅ 有（产品线/区域/部门） | 保持 | — |
| 环比/同比 | ❌ 无 | **增加** | P0 |
| 趋势分析 | ❌ 无 | **增加** | P1 |
| 交付及时率 | ❌ 无 | **增加** | P0 |
| 项目交付周期统计 | ❌ 无 | **增加** | P1 |
| 异常项目分析 | ❌ 无 | **增加** | P1 |
| 客户经理维度分析 | ❌ 无 | **增加** | P2 |
| 自定义维度交叉分析 | ❌ 无 | **增加** | P2 |

### 12.2 P0 必须增强项

#### 12.2.1 环比/同比计算

```python
def calc_mom_metrics(current_month: str, metrics: dict) -> dict:
    """计算环比（Month-over-Month）。"""
    prev_month = get_previous_month(current_month)
    prev_data = load_month_summary(prev_month)
    return {
        'delivery_amount_mom': calc_rate(metrics['total_delivery_amount'], 
                                          prev_data['total_delivery_amount']),
        'acceptance_amount_mom': calc_rate(metrics['acceptance_amount'],
                                            prev_data['acceptance_amount']),
    }

def calc_yoy_metrics(current_month: str, metrics: dict) -> dict:
    """计算同比（Year-over-Year）。"""
    prev_year_month = get_same_month_last_year(current_month)
    prev_data = load_month_summary(prev_year_month)
    # ... 同比计算
```

#### 12.2.2 交付及时率

```python
# 新增指标：delivery_timely_rate = 按时交付项目数 / 应交付项目数
# 按时 = 实际交付日期 ≤ 计划交付日期
# 应交付 = 本月计划交付的项目数

# 新增表字段（dr_delivery_item）：
#   planned_delivery_date  计划交付日期
#   actual_delivery_date   实际交付日期
#   is_timely              是否及时交付
```

### 12.3 P1 建议增强项

#### 12.3.1 趋势分析（多月份时间序列）

```python
# 方法：trend(metric_key, range_months=12)
# 返回：[{month: "2026-01", value: 123.45}, ...]
# 支持的指标：delivery_count / delivery_amount / acceptance_count / acceptance_amount
# 用于：Dashboard 趋势图、报表趋势 Sheet
```

#### 12.3.2 项目交付周期统计

```python
# 指标：平均交付周期（从项目启动到交付的天数）
# 分位数：P50 / P90 / P95（中位数 + 长尾分布）
# 按维度拆解：产品线 / 部门 / 项目经理 / 项目类型
```

#### 12.3.3 异常项目分析

```python
# 异常定义：
#   - 交付延期 > 30 天
#   - 多次延期（>2 次变更交付日期）
#   - 交付金额与合同金额差异 > 30%
#   - 验收失败（需要复验）
# 输出：异常项目清单 + 异常类型分布 + 趋势
```

### 12.4 P2 远期增强项

- **自定义交叉分析**：用户选择维度（如：产品线 × 区域 × 季度），动态生成交叉表
- **预测分析**：基于历史数据预测下月交付量 / 确收金额
- **归因分析**：交付延期的主要原因分析（需要更多数据维度支撑）

---

## 13. 业界最佳实践对比与优化

### 13.1 对标标准

| 业界实践            | 核心思想                | BDMS 当前做法        | 差距            | 优化建议                                                              |
| --------------- | ------------------- | ---------------- | ------------- | ----------------------------------------------------------------- |
| **星型模型**        | 事实表 + 维度表，报表数据用维度建模 | 宽表 + 明细混合        | 缺乏规范的维度建模     | 核心报表按星型模型设计：fact_delivery + dim_project + dim_customer + dim_date |
| **预计算 + 缓存**    | 报表数据预计算，查询时直读       | 部分预计算（summary 表） | 维度汇总未预计算      | 所有维度汇总预计算到 dr_dimension_rollup，查询时直读                              |
| **累计快照事实表**     | 记录周期末的累积快照          | 只有月度快照           | 缺周度/季度快照      | 增加周度快照表，支持更细粒度趋势分析                                                |
| **缓慢变化维度（SCD）** | 维度属性变化时保留历史         | 维度直接更新，无历史       | 无法分析维度变化影响    | 关键维度（项目/客户）支持 SCD Type 2（版本化）                                     |
| **数据血缘**        | 追踪数据从来源到报表的完整链路     | 部分可追溯            | 缺乏系统化的血缘管理    | 增加数据血缘表，记录每个指标的计算公式和数据来源                                          |
| **增量计算**        | 只计算变更数据，不全量重算       | 全月重算             | 效率低（但数据量小，够用） | 数据量增大后改为增量计算（只处理本月变更的项目）                                          |
| **列式存储**        | 分析型查询用列式存储，性能好      | 行式 SQLite        | 大数据量下慢        | 超量时迁移到 DuckDB（列式 + 向量化）                                           |
| **物化视图**        | 预计算的虚拟表，自动刷新        | 手动 summary 表     | 缺乏自动化         | 用定时任务刷新汇总表，等价于物化视图                                                |

### 13.2 建议的优化项

#### P0（v2.1 必须做）

1. **星型模型重构交付事实表**
   - 问题：当前宽表 + JSON 行，不利于多维分析
   - 方案：`fact_delivery`（事实表）+ `dim_project` + `dim_date` + `dim_department`（维度表）
   - 成本：中（表结构调整 + 计算逻辑调整）
   - 收益：高（多维分析性能 + 可扩展性）

2. **维度汇总预计算**
   - 问题：每次查询都实时聚合维度数据
   - 方案：dr_dimension_rollup 表预计算所有维度组合，查询时直读
   - 成本：低（增加预计算步骤）
   - 收益：中（查询更快，Dashboard 直接读）

#### P1（v2.2 可做）

3. **SCD Type 2 维度版本化**
   - 问题：项目经理变更/部门调整后，历史数据归因不准
   - 方案：关键维度表增加 valid_from/valid_to 字段
   - 成本：中
   - 收益：中（历史数据可追溯）

4. **增量计算**
   - 问题：每次 regenerate 全月重算
   - 方案：基于项目更新时间，只重算变更的项目
   - 成本：中
   - 收益：中（大数据量时性能提升明显）

#### P2（远期）

5. **DuckDB 迁移**
   - 问题：SQLite 行式存储，分析查询慢
   - 方案：数据量超 10 万行时迁移到 DuckDB
   - 成本：高（SQL 方言差异 + 迁移）
   - 收益：高（分析查询性能 10-100 倍提升）

6. **数据血缘管理**
   - 问题：指标计算公式变更后难以追溯影响
   - 方案：增加数据血缘元数据表
   - 成本：中
   - 收益：低（当前指标量不大，文档足够）

---

## 14. 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| v1.0 计算逻辑与新表结构不匹配 | 数据不一致 | 迁移脚本 + 双跑对比验证 |
| Excel 导出格式漂移 | 报表不可用 | 锁定 openpyxl 版本 + 格式快照测试 |
| 历史数据量超预期 | 性能下降 | 纯代码 → pandas → DuckDB 三阶段演进 |
| pandas 版本升级行为变化 | 计算结果偏差 | 锁定 pandas 版本 + 黄金基准测试守护 |
| 跨模块事件丢失 | revenue 不同步 | reconcile_with_revenue() 兜底 + 定时对账 |
| 并发 regenerate | 数据冲突 | 乐观锁 + 串行化调度 |
| 纯代码计算性能不足 | 月报生成慢 | 先上纯代码，性能瓶颈出现再针对性优化 |
| 星型模型重构工作量大 | 开发周期长 | 先跑通宽表方案，v2.2 再重构星型模型 |

---

## 15. 非功能设计

### 15.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| 月报计算（< 1000 行/月） | < 1s | 纯 Python 代码 + 内存计算 |
| 月报导出（15 Sheet Excel） | < 5s | openpyxl 批量写入 + xlsxwriter 图表 |
| 历史月份加载 | < 500ms | SQLite 索引 + 预计算汇总表 |
| 并发计算 | 月度集中计算时稳定 | 幂等骨架 + 乐观锁 |

### 15.2 可靠性

- **幂等保证**：auto/read/regenerate 三模式幂等骨架，重复计算不产生脏数据
- **数据版本化**：regenerate 时 data_version +1，可追溯历史版本
- **黄金基准对齐**：202606 手工报表 18/18 项零差异验证通过
- **降级策略**：纯代码计算稳定，pandas 作为性能优化可选方案

### 15.3 安全

- **数据隔离**：交付数据按项目权限过滤，非授权项目不可见
- **导出权限**：Excel 导出需 operator 权限，审计日志记录
- **输入校验**：外部数据通过 integration 模块标准化，不直接信任

### 15.4 可测试性

- **纯函数测试**：compute() 纯函数，输入确定则输出确定，可单元测试
- **黄金基准测试**：对比手工报表，自动检测计算偏差
- **幂等测试**：连续 generate 3 次，结果 MD5 一致
- **兼容性测试**：v1.0 18 个测试用例全绿

---

## 13. Sheet 完整定义（15 Sheet，以手工报表为黄金基准）

> **原则**：每个 Sheet 必须与手工报表逐列对比。验收标准：行数误差 ≤ 1，列名 100% 一致。

### 13.1 签约（5 Sheet 核心数据）

| Sheet | 数据源 | 列数 | 行数基准 | 说明 |
|---|---|---|---|---|
| 签约 | dr_sheet_row（签约） | 84 | 手工±0 | 原始明细 |
| POC&提前实施 | dr_sheet_row（POC&提前实施） | 84 | 手工±0 | 原始明细 |
| 异常项目 | dr_sheet_row（异常项目） | 38 | 手工±1 | 补录行过滤 |
| 确收交接 | dr_sheet_row（确收交接） | 24 | 手工±0 | 原始明细 |
| 验收交接 | dr_sheet_row（验收交接） | 28 | 手工±0 | 原始明细 |

### 13.2 统计分析（9 Sheet 聚合数据）

| Sheet | 数据源 | 聚合方式 | 说明 |
|---|---|---|---|
| 交付效率统计 | dr_sheet_row（签约） | GROUP BY 项目经理 + 状态 | 按时交付率/差异/考核扣分 |
| 签约统计 | dr_sheet_row（签约） | GROUP BY 部门/产线 | 签约数量+金额汇总 |
| 产品-授权&维保统计 | dr_sheet_row（签约） | GROUP BY 产品类型 | 按产品分类统计 |
| POC&提前实施统计 | dr_sheet_row（POC&提前实施） | GROUP BY 部门/类型 | POC+提前实施汇总 |
| 提前实施分事业部统计 | dr_sheet_row（POC&提前实施） | GROUP BY 部门 | 按事业部分组 |
| 异常统计 | dr_sheet_row（异常项目） | GROUP BY 类型/状态 | 异常分类汇总 |
| 异常台账 | dr_sheet_row（异常项目） | 全量明细 | 异常项目完整列表 |
| 交付异常分事业部统计 | dr_sheet_row（异常项目） | GROUP BY 部门 | 按事业部统计 |
| 交接统计 | dr_sheet_row（确收+验收） | GROUP BY 类型/状态 | 交接分类汇总 |

### 13.3 图例（1 Sheet 静态配置）

| Sheet | 数据源 | 说明 |
|---|---|---|
| 图例 | md_reference（legend 类型） | 枚举定义、颜色映射、状态说明 |

### 13.4 验收标准

| # | 验收项 | 通过标准 |
|---|---|---|
| 1-5 | 5 个核心数据 Sheet | 行数=手工±0，列名 100% 一致 |
| 6-14 | 9 个统计分析 Sheet | 行数=手工±1，聚合逻辑正确 |
| 15 | 图例 | 枚举定义完整 |

---

## 变更历史

| 版本 | 日期 | 变更内容 |
|---|---|---|
| v2.1 | 2026-09-22 | r2 — 新增 Sheet 完整定义（§13），15 Sheet 逐一定义，以手工报表为黄金基准 |
| v2.1 | 2026-09-19 | 初始详细设计，对齐 BDMS v2.1 架构 |
| v2.1 | 2026-09-19 | 新增：复用资产治理 / Token 标记 / 纯代码计算原则 / 统计分析增强 / 业界最佳实践对比 |
