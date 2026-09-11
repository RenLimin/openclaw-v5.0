# delivery-center

## 设计目标

为交付团队提供自动化月报生成与管理能力，覆盖合同、工时、状态、异常、交接、评分、映射七大引擎。解决手工汇总数据耗时、月报格式不统一、异常识别滞后的问题。

## 架构决策

- **v1/v2 双版本并存**：v1 保留兼容，v2 为推荐版本，渐进迁移
- **引擎层纯计算**：引擎无副作用，输入数据 → 输出结果，可独立测试
- **异步任务管理**：v2 引入服务层，月报生成异步执行，Web 不阻塞
- **多源数据采集**：collectors 从 OA/ONES/工时系统多源抽取，统一清洗
- **元数据 DB**：v2 使用 SQLite 存储生成记录和报告元数据
- **三入口**：CLI（bdmsctl）/ Web UI（FastAPI）/ Python API

## 模块划分

```
delivery-center/
├── v1/                         # 旧版（保留兼容）
│   ├── collectors/             # 数据采集器
│   │   ├── oa_collector.py     # OA 系统合同数据
│   │   ├── ones_collector.py   # ONES 工时数据
│   │   ├── workhour_collector.py
│   │   ├── ones_export_auto.py
│   │   ├── ones_explore.py
│   │   ├── ones_filter_query.py
│   │   ├── ones_pyautogui.py
│   │   ├── data_cleaner.py
│   │   └── iam_auth.py
│   ├── engines/                # 计算引擎
│   │   ├── join_engine.py
│   │   ├── summary_engine.py
│   │   ├── month_rollup.py
│   │   ├── variance_engine.py
│   │   ├── status_engine.py
│   │   └── scoring_engine.py
│   ├── generators/             # 报告生成器
│   ├── pipeline.py             # 主流程
│   └── scheduler.py            # 定时调度
├── v2/                         # 新版（推荐）
│   ├── engines/                # 7 个业务引擎
│   │   ├── contract_engine.py  # 合同引擎
│   │   ├── hours_engine.py     # 工时引擎
│   │   ├── status_engine.py    # 状态引擎
│   │   ├── exception_engine.py # 异常引擎
│   │   ├── handover_engine.py  # 交接引擎
│   │   ├── scoring_engine.py   # 评分引擎
│   │   └── mapping_engine.py   # 映射引擎
│   ├── generators/             # v2 报告生成器
│   │   ├── build_v2_report.py
│   │   └── build_stat_sheets.py
│   ├── services/               # 服务层
│   │   └── report_service.py   # 异步任务 + 概要提取
│   ├── web/                    # FastAPI Web UI
│   │   ├── main.py
│   │   └── api.py
│   ├── cli/
│   │   └── bdmsctl.py          # 命令行工具
│   ├── config/                 # 配置（Sheet 格式等）
│   ├── db.py                   # 元数据 DB
│   ├── scripts/                # 迁移脚本
│   └── __main__.py             # python -m v2 入口
└── tests/                      # 247 个测试用例
```

## 关键接口/数据结构

- `ContractEngine`：合同数据抽取与映射
- `HoursEngine`：工时汇总（按项目/人员/月份）
- `StatusEngine`：项目状态追踪
- `ExceptionEngine`：异常识别（缺工时/超额/进度偏差）
- `ScoringEngine`：多维度加权评分
- `MappingEngine`：人员/项目/合同多源关联
- `ReportService`：异步任务管理，`generate(month)` / `get_status(task_id)`
- `delivery_report_generator`：多 Sheet Excel 月报生成

## 依赖关系

- **依赖**：Python 3.10+、pandas、openpyxl、python-docx、FastAPI、uvicorn
- **被依赖**：`dms-framework`（L3 层，delivery-center 是 dms-framework 的 L4 专有实现）

## 演进方向

1. **v1 废弃**：待 v2 稳定后清理 v1 代码
2. **实时数据接入**：从手动导出改为 API 实时拉取
3. **智能分析**：引入 LLM 自动生成月报分析文字
4. **多团队支持**：支持多个交付团队并行使用
5. **告警联动**：异常引擎触发自动告警通知
