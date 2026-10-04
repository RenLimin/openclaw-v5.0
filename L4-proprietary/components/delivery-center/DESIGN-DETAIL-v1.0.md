# DESIGN-DETAIL-v1.0.md — BDMS 交付月报系统详细设计

## 1. 模块详细设计

### 1.1 采集层 (collectors)

| 模块 | 类/函数 | 职责 | 输入 | 输出 |
|------|---------|------|------|------|
| `oa_collector` | `load_oa_contracts` | 从 OA 导出 Excel 读取合同数据 | Excel 文件路径 | 清洗后合同 DataFrame |
| `ones_collector` | `load_ones_workhours` | 从 ONES 导出 Excel 读取工时数据 | Excel 文件路径 | 清洗后工时 DataFrame |
| `data_cleaner` | `clean_*` 系列函数 | 数据清洗：去除空行、去除空格、标准化列名、类型转换 | 原始 DataFrame | 标准化 DataFrame |

### 1.2 引擎层 (engines)

#### 1.2.1 合同引擎 (`contract_engine.py`)
- `calibrate_contract_no`: 合同编号校准，处理大小写、特殊字符
- `load_oa_contracts`: 加载 OA 合同数据
- `join_contract_info`: 关联到主表，补充合同信息
- `summarize_contracts`: 合同金额汇总

#### 1.2.2 工时引擎 (`hours_engine.py`)
- `load_workhour_detail`: 加载工时明细
- `aggregate_by_project`: 按项目汇总工时
- `aggregate_by_contract`: 按合同汇总工时
- `hours_to_person_days`: 工时转换为人天（默认 8 小时/天，支持自定义）

#### 1.2.3 状态引擎 (`status_engine.py`)
- `determine_status`: 根据项目进度和交付时间确定项目状态

#### 1.2.4 异常引擎 (`exception_engine.py`)
- `build_exception_df`: 构建异常列表，识别缺工时、超额、进度偏差
- 状态流分类：按异常类型/状态/影响范围分类

#### 1.2.5 交接引擎 (`handover_engine.py`)
- `build_revenue_handover_df`: 构建收入交接数据
- `build_acceptance_handover_df`: 构建验收交接数据
- `filter_by_period`: 按目标月份过滤交接记录

#### 1.2.6 评分引擎 (`scoring_engine.py`)
- `add_scoring_columns`: 根据配置规则加权计算交付质量分

#### 1.2.7 映射引擎 (`mapping_engine.py`)
- 加载人员/部门映射表，为数据补充映射信息

### 1.3 服务层 (`report_service.py`)
- `generate_report(month)`: 触发月报生成，返回任务 ID
- `get_report_status(task_id)`: 获取任务状态和进度
- `list_reports(limit)`: 列出历史报告
- `_generate_report_async`: 异步执行完整生成流程

流程：
1. 采集 → 清洗 → 各引擎处理 → 生成 Excel → 更新任务状态为完成

### 1.4 入口层

#### 1.4.1 CLI (`bdmsctl.py`)
- `generate <month> [--wait]`: 生成月报，--wait 等待完成
- `list`: 列出所有报告
- `status <task_id>`: 查看任务状态
- `summary <task_id>`: 查看报告概要
- `migrate [--dry-run]`: 从 v1 迁移到 v2
- `serve [--port]`: 启动 Web UI

#### 1.4.2 Web UI (`web/`)
- **页面**：报告列表、生成报告、报告详情
- **API**：健康检查、生成、列表、状态、下载、概要
- 基于 FastAPI + Jinja2，使用 L2 `web-common` 模板和静态资源

### 1.5 存储层

- `db.py`: SQLite 操作，任务表结构定义（id, month, status, progress, created_at, completed_at, file_path）
- `generators/`: Excel 生成器，构建多 Sheet 报告，支持样式、列宽、冻结窗格

## 2. 数据结构

### 2.1 核心数据表结构

- **合同表**: `contract_id`, `contract_name`, `amount`, `start_date`, `end_date`, `pm`, `dept`
- **工时表**: `project_name`, `contract_id`, `person`, `date`, `hours`
- **交接表**: `contract_id`, `handover_date`, `receiver`, `acceptor`, `is_receive`
- **异常表**: `contract_id`, `exception_type`, `status`, `description`, `impact`
- **任务元数据表**: 见上文 db.py

## 3. 接口契约

### 3.1 Python API

```python
from v2.services.report_service import generate_report, get_report_status
task_id = generate_report("202608")
status = get_report_status(task_id)
# status: {id, month, status, progress, ...}
```

### 3.2 Web API

- `GET /api/reports` → 报告列表
- `POST /api/reports/generate {month}` → 触发生成
- `GET /api/reports/{id}` → 获取状态
- `GET /api/reports/{id}/download` → 下载 Excel
- `GET /health` → 健康检查

## 4. 技术方案

- **数据处理**: 全 pandas 实现，高效处理 Excel 和数据转换
- **异步**: 使用 `asyncio` 处理异步任务，不阻塞主进程
- **测试**: pytest，全测试覆盖核心引擎，每条规则对应测试用例
- **部署**: 单实例部署，支持 CLI 和 Web 两种访问方式
