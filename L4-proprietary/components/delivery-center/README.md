# BDMS — 交付月报系统 (Delivery Report Management System)

BDMS (Bangcle Delivery Monthly Statement) — 面向交付团队的自动化月报生成与管理系统。

v2 版本：模块化引擎 + Web UI + CLI + 元数据 DB，支持异步任务管理。

## 功能特性

| 模块 | 说明 |
|------|------|
| **合同引擎** | 从 OA / 合同库抽取合同数据，金额、周期、负责人映射 |
| **工时引擎** | 从 ONES / 工时系统汇总工时，按项目/人员/月份维度 |
| **状态引擎** | 项目状态追踪（进行中/已交付/已暂停/风险） |
| **异常引擎** | 自动识别异常：缺工时、超额、进度偏差 |
| **交接引擎** | 项目交接记录管理 |
| **评分引擎** | 交付质量评分（多维度加权） |
| **映射引擎** | 人员/项目/合同多源数据关联映射 |
| **报告生成器** | 多 Sheet Excel 月报，含统计/明细/汇总 |

## 目录结构

```
delivery-center/
├── v1/                         # 旧版（保留兼容）
│   ├── collectors/             # 数据采集器
│   ├── engines/                # 计算引擎
│   ├── generators/             # 报告生成器
│   ├── pipeline.py             # 主流程
│   └── scheduler.py            # 定时调度
├── v2/                         # 新版（推荐）
│   ├── engines/                # 7 个业务引擎
│   ├── generators/             # v2 报告生成器
│   ├── services/               # 服务层（异步任务 + 概要提取）
│   ├── web/                    # FastAPI Web UI
│   ├── cli/                    # 命令行工具 (bdmsctl)
│   ├── scripts/                # 迁移脚本等
│   ├── config/                 # 配置（Sheet 格式等）
│   ├── db.py                   # 元数据 DB
│   └── __main__.py             # python -m v2 入口
├── tests/                      # 测试（v1 + v2 共 247 用例）
├── .bak/                       # 历史备份（可清理）
└── README.md                   # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install pandas openpyxl python-docx fastapi uvicorn
```

### 2. CLI 使用

```bash
cd delivery-center

# 生成月报（后台异步）
python -m v2 generate 2026-08

# 生成月报并等待完成
python -m v2 generate 2026-08 --wait

# 查看所有报告
python -m v2 list

# 查看任务状态
python -m v2 status 1

# 查看报告概要
python -m v2 summary 1

# v1 → v2 数据迁移
python -m v2 migrate --dry-run   # 预检
python -m v2 migrate             # 执行

# 启动 Web UI
python -m v2 serve --port 8000
```

### 3. Web UI

启动后访问 http://localhost:8000

| 页面 | 路径 | 说明 |
|------|------|------|
| 报告列表 | `/` | 所有月报一览 + 生成入口 |
| 报告详情 | `/report/{id}` | 概要 + Sheet 预览 + 下载 |
| 生成报告 | `/generate` | 选择月份提交生成任务 |
| 错误页 | — | 统一异常展示 |

### 4. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reports` | 报告列表（分页） |
| POST | `/api/reports/generate` | 触发生成 |
| GET | `/api/reports/{id}` | 任务状态 |
| GET | `/api/reports/{id}/summary` | 报告概要 |
| GET | `/api/reports/{id}/download` | 下载 Excel |
| GET | `/api/health` | 健康检查 |

## v1 → v2 迁移

```bash
# 预检
python -m v2 migrate --dry-run

# 执行迁移
python -m v2 migrate
```

迁移内容：
- 合同数据：v1 内存结构 → v2 SQLite
- 工时数据：v1 CSV/JSON → v2 结构化表
- 生成元数据：历史报告记录重建

详见 `docs/architecture/components/l4-delivery-center-v2/MIGRATION.md`。

## 测试

```bash
cd delivery-center
python -m pytest tests/ -v
```

覆盖：
- 7 个引擎的单元测试
- v2 端到端测试
- Web API 测试
- 迁移测试
- 异常处理测试

共 **247 个测试用例**。

## 数据来源

| 数据 | 采集方式 | v1 实现 | v2 实现 |
|------|---------|---------|---------|
| 合同 | OA 系统导出 | `oa_collector.py` | 合同引擎 + 映射引擎 |
| 工时 | ONES 导出 | `ones_collector.py` | 工时引擎 |
| 项目状态 | 人工 + 自动推断 | `status_engine.py` | 状态引擎 + 异常引擎 |
| 人员映射 | 配置文件 | 硬编码 | 映射引擎 |

## 架构设计

- **引擎层**：纯计算，无副作用，输入数据 → 输出结果
- **服务层**：异步任务管理、缓存、概要提取
- **Web 层**：FastAPI + Jinja2，前后端不分离
- **CLI 层**：argparse，命令行友好
- **存储层**：SQLite 元数据 + Excel 报告文件

设计原则：
1. 引擎可独立测试，不依赖外部服务
2. 异步生成，Web 不阻塞
3. v1/v2 可并存，渐进迁移
