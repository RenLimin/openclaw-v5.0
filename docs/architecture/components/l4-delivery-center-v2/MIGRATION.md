# BDMS v1 → v2 数据迁移方案

> 版本：1.0
> 日期：2026-09-10
> 状态：active

## 1. 背景

BDMS（Bangcle 交付管理系统）v1 基于 SQLite 持久化 + pipeline 调度，v2 重构为纯文件驱动的 pandas 报表引擎（15 Sheet 精确格式）。

v2 不直接操作数据库 — 它从 ONES 导出 CSV 和企业微信交接 CSV 读取数据。因此"迁移"的核心是：
1. **历史数据导入**：把 v1 SQLite 中的历史数据导出为 v2 兼容的 CSV 格式
2. **元数据补齐**：给 v2 补一个轻量 SQLite 元数据库（存报告生成记录、任务状态、导入日志）
3. **数据校验**：迁移前后行数、金额、关键指标一致

## 2. v1 / v2 架构对比

| 维度 | v1 | v2 |
|---|---|---|
| 数据存储 | SQLite 持久化（6 张表） | 无持久化，纯 CSV 输入 |
| 数据采集 | 5 个采集器（OA/ONES/WeCom/工时/API） | 依赖外部导出 CSV |
| 业务引擎 | 5 个（join/status/scoring/variance/summary） | 7 个（status/scoring/mapping/exception/handover/hours/contract） |
| 报告输出 | 12 Sheet（交付月报 + 确收月报） | 15 Sheet（交付月报 v2） |
| 调度 | scheduler + cron | 无（按需生成） |
| Web UI | 无 | 无（本次补上） |

## 3. 数据模型对比

### 3.1 v1 数据库表

| 表名 | 核心字段 | 行数（参考） |
|---|---|---|
| `oa_contracts` | htbh, 合同名称, 客户名称, 签约金额, 责任销售, 创建日期, 服务起止日期... | 11,177 |
| `ones_projects` | project_id, 项目名称, 合同编号, 客户名称, 项目经理, 项目状态, 立项日期... | - |
| `revenue_vouchers` | voucher_id, 合同编号, 合同名称, 客户名称, 销售部门, 项目经理, 交接日期, 是否接收... | 514 |
| `acceptance_vouchers` | voucher_id, 合同编号, 合同名称, 客户名称, 项目经理, 验收单编号, 交接日期, 验收方式... | 531 |
| `workhours` | 工作项, 总工时, 迁移工时, 剩余工时, 月份 | - |
| `report_history` | month, report_type, file_path, 生成日期 | - |

### 3.2 v2 输入文件

| 文件 | 位置 | 说明 |
|---|---|---|
| 签约项目统计.csv | `ONES_DIR/` | ONES 导出，签约项目明细（~40-50 列） |
| poc_提前实施.csv | `ONES_DIR/` | ONES 导出，POC&提前实施明细 |
| 异常处置.csv | `ONES_DIR/` | ONES 导出，异常项目处置明细 |
| 确收凭证交接-确收.csv | `REF_BASE_DIR/{month}/` | 企业微信导出，确收交接 |
| 确收凭证交接-验收.csv | `REF_BASE_DIR/{month}/` | 企业微信导出，验收交接 |

### 3.3 字段映射关系

v1 的 SQLite 表是"结构化存储"，v2 输入是"原始导出 CSV"。两者不是简单映射，而是：

- **v1 `oa_contracts` → v2 签约统计的合同信息列**：合同编号、客户名称、签约金额、责任销售等基础字段可直接映射
- **v1 `ones_projects` → v2 签约/POC 统计的项目列**：项目名称、项目经理、部门、状态
- **v1 `revenue_vouchers` → v2 确收交接 CSV**：大部分字段可直接映射
- **v1 `acceptance_vouchers` → v2 验收交接 CSV**：大部分字段可直接映射
- **v1 `workhours` → v2 工时明细**：字段差异大，需补充列

> ⚠️ **关键差异**：v2 的签约/POC/异常 CSV 是 ONES 的完整导出（40-55 列），v1 SQLite 只存了关键字段（10-20 列）。因此从 v1 迁移过来的数据**列数不完整**，v2 生成报告时缺失列会用空值填充。这是已知限制。

## 4. 迁移策略

### 4.1 迁移方式

| 方式 | 适用场景 | 说明 |
|---|---|---|
| **全量迁移** | 首次迁移 | 把 v1 全部数据导出到 v2 数据目录，按月组织 |
| **增量导入** | 持续使用 | 支持从 Excel/CSV 单文件导入到 v2 数据目录 |
| **dry-run** | 验证 | 只计算差异不写入，输出迁移预览报告 |

### 4.2 v2 元数据库（新增）

为支撑 Web UI 的列表/状态/下载功能，v2 新增一个轻量 SQLite 元数据库 `bdms_v2.db`：

```sql
-- 报告生成记录
CREATE TABLE report_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,           -- 报告月份 YYYYMM
    status TEXT NOT NULL,          -- pending / running / completed / failed
    file_path TEXT,                -- 生成的 Excel 路径
    progress INTEGER DEFAULT 0,    -- 进度 0-100
    error_msg TEXT,                -- 失败原因
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 数据导入记录
CREATE TABLE import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,     -- v1_sqlite / excel / csv
    source_path TEXT NOT NULL,     -- 源文件路径
    data_type TEXT NOT NULL,       -- sign / poc / exception / revenue / acceptance / workhours
    rows_imported INTEGER,
    status TEXT NOT NULL,          -- success / failed / dry_run
    month TEXT,                    -- 对应月份
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 报告概要缓存（用于预览页）
CREATE TABLE report_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_job_id INTEGER,
    month TEXT NOT NULL,
    sheet_name TEXT NOT NULL,      -- Sheet 名称
    row_count INTEGER,             -- 行数
    summary_json TEXT,             -- 关键指标 JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_job_id) REFERENCES report_jobs(id)
);
```

## 5. 迁移步骤

### 5.1 全量迁移（v1 → v2）

```bash
python v2/scripts/migrate_v1_to_v2.py full \
  --v1-db ~/.openclaw/data/bdms.db \
  --output-dir ~/.openclaw/data/ones_exports \
  --month 202606
```

步骤：
1. **连接 v1 数据库**，读取 5 张业务表
2. **字段映射**：按映射关系转换为 v2 CSV 格式
3. **缺失列填充**：v2 需要但 v1 没有的列填 NaN
4. **写入 CSV**：按 v2 期望的文件名写入数据目录
5. **数据校验**：
   - 行数校验：v1 表行数 = v2 CSV 行数
   - 金额校验：签约金额合计一致（保留 2 位小数）
   - 关键字段非空率：合同编号非空率 ≥ 95%
6. **写入元数据库**：记录 import_logs

### 5.2 增量导入（Excel/CSV → v2）

```bash
python v2/scripts/migrate_v1_to_v2.py import \
  --source ./新签约数据.xlsx \
  --type sign \
  --month 202607
```

支持从 Excel 或 CSV 导入，自动识别列名，写入对应数据目录。

### 5.3 dry-run 模式

加 `--dry-run` 参数，只输出迁移预览（行数、字段映射结果、缺失列），不写入文件。

## 6. 验证方案

| 验证项 | 方法 | 通过标准 |
|---|---|---|
| 行数一致 | 迁移前后 count 对比 | 完全一致 |
| 金额合计一致 | sum(签约金额) 对比 | 误差 < 0.01 元 |
| 关键字段非空率 | 合同编号/客户名称非空比例 | ≥ 95% |
| 可生成报告 | 用迁移数据跑一遍 v2 生成器 | 生成成功，15 Sheet 齐全 |
| 回滚可用 | 执行回滚后数据恢复 | v2 数据目录回到迁移前状态 |

## 7. 风险 & 回滚计划

### 7.1 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| v1 字段不全导致 v2 报告数据缺失 | 高 | 中 | 明确标注"迁移数据"，缺失列留空；建议配合 ONES 完整导出使用 |
| 金额精度问题（浮点误差） | 中 | 低 | 统一用 Decimal 计算，校验容差 0.01 元 |
| 中文列名编码问题 | 中 | 低 | 统一 UTF-8 编码，CSV 加 BOM |
| 迁移过程中断导致数据不一致 | 低 | 中 | 先写临时目录，全部成功后原子 move |

### 7.2 回滚方案

**自动回滚**（迁移失败时）：
1. 迁移前备份被覆盖的文件到 `.backup/` 目录
2. 任一步骤失败 → 从 backup 恢复 → 删除临时文件
3. 元数据库记录失败状态

**手动回滚**：
```bash
python v2/scripts/migrate_v1_to_v2.py rollback --import-id <id>
```

根据 import_logs 中的记录，恢复对应文件的备份版本。

## 8. 迁移工具清单

| 文件 | 说明 |
|---|---|
| `v2/scripts/migrate_v1_to_v2.py` | 迁移工具主入口 |
| `v2/db.py` | v2 元数据库连接 + 初始化 |
| `tests/test_v2_migration.py` | 迁移工具测试（5+ 用例） |

