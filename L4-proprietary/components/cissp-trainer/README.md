# CISSP Trainer — CISSP 学习系统 v2

> L4 专有业务层组件 · 智能刷题 + 学习路径 + 模拟考试 + 知识图谱

---

## ✨ 功能概览

### 核心能力（MVP）
- **📚 结构化题库** — SQLite + SQLAlchemy，题目/学习记录/知识点 三表模型
- **🎯 智能出题** — 4 种模式：随机 / 到期复习 / 薄弱点强化 / 模拟考试抽题
- **🔄 间隔重复** — 简化 SM-2 算法，自动安排复习时间
- **📊 学习统计** — 总体正确率、分域表现、薄弱知识点排名、进度曲线
- **🧠 知识点掌握度** — 基于指数移动平均的掌握度追踪
- **💻 CLI 接口** — `start` / `stats` / `weak` / `import` / `init`

### v2 新增三大能力

| 能力 | 模块 | 核心功能 |
|------|------|---------|
| **🛤️ 学习路径规划** | `learning_path.py` | 3 条预设路径、里程碑解锁、每日计划、动态调整、智能推荐 |
| **📝 模拟考试** | `exam_engine.py` | 完整考试流程、计时暂停、分域评分、错题解析、成绩曲线、对比分析 |
| **🕸️ 知识图谱** | `knowledge_graph.py` | 137 条预设关系、前置/后继查询、学习建议、薄弱点传播、Mermaid/文本可视化、热力图 |

---

## 🚀 快速开始

### 前置条件

- Python 3.10+
- SQLAlchemy 2.0+
- PyYAML

```bash
pip install sqlalchemy pyyaml pytest
```

### 初始化

```bash
cd L4-proprietary/components/cissp-trainer

# 初始化数据库 + 导入 52 道样例题 + 137 条知识图谱关系
PYTHONPATH=src python3 -m cissp_trainer.cli init --sample
```

### 设置别名

```bash
alias cissp-trainer='cd /path/to/cissp-trainer && PYTHONPATH=src python3 -m cissp_trainer.cli'
```

下面用 `cissp-trainer` 代替完整命令。

---

## 📖 完整命令速查

### 基础命令（MVP）

```bash
cissp-trainer init --sample                    # 初始化 + 导入样例
cissp-trainer start -n 20                      # 随机 20 题
cissp-trainer start -d 1 -m review             # 域1 到期复习
cissp-trainer start -m weak                    # 薄弱点强化
cissp-trainer stats                            # 学习统计
cissp-trainer weak -n 15                       # Top 15 薄弱知识点
cissp-trainer import questions.yaml            # 导入题库
```

### 学习路径（v2 新增）

```bash
cissp-trainer path list                        # 列出所有学习路径
cissp-trainer path start beginner              # 开始入门路径
cissp-trainer path status                      # 当前路径进度
cissp-trainer path today                       # 今日学习计划
cissp-trainer path recommend                   # 根据水平推荐路径
```

### 模拟考试（v2 新增）

```bash
cissp-trainer exam start                       # 开始 100 题 3 小时模拟考
cissp-trainer exam start -n 50 -t 120          # 50 题 2 小时
cissp-trainer exam start -d 1 2                # 只考域1 + 域2
cissp-trainer exam history                     # 考试历史记录
cissp-trainer exam detail <id>                 # 考试详情 + 错题解析
```

考试中操作：
- 输入 `A/B/C/D` 作答
- `f` 标记/取消标记当前题
- `#5` 跳转到第 5 题
- `p` 暂停考试
- `q` 交卷

### 知识图谱（v2 新增）

```bash
cissp-trainer knowledge graph 1                # 查看域1 知识图谱（文本树）
cissp-trainer knowledge graph 1 --mermaid      # 输出 Mermaid 格式
cissp-trainer knowledge prereq "安全模型"      # 查询知识点前置依赖
cissp-trainer knowledge next "CIA三元组"       # 推荐下一步学什么
cissp-trainer knowledge impact "加密基础"      # 薄弱点传播影响分析
cissp-trainer knowledge heatmap                # 全领域掌握度热力图
```

---

## 🛤️ 学习路径详解

### 三条预设路径

| 路径 | 时长 | 每日题量 | 难度 | 里程碑 | 适合人群 |
|------|------|---------|------|--------|---------|
| **入门路径 (beginner)** | 30 天 | 10 题 | 1-3 | 5 个 | 零基础、第一次接触 CISSP |
| **强化路径 (advanced)** | 60 天 | 20 题 | 2-5 | 5 个 | 有基础、想系统深度学习 |
| **冲刺路径 (sprint)** | 14 天 | 50 题 | 3-5 | 4 个 | 考前冲刺、模拟考试练手 |

### 路径机制

- **前置依赖链**：beginner → advanced → sprint，按顺序解锁
- **里程碑系统**：每条路径有多个里程碑，达到掌握度阈值自动解锁下一阶段
- **动态调整**：连续 3 天正确率 > 85% 自动加量加难度；< 50% 自动降量降难度
- **每日计划**：根据当前里程碑和薄弱点，自动生成今日学习内容和建议模式
- **智能推荐**：根据累计答题量和正确率，推荐最合适的路径

### 里程碑示例（入门路径）

1. **安全基础入门** — 域 1、2 达到 50% 掌握度
2. **技术核心入门** — 域 3、4 达到 50% 掌握度
3. **身份与运营入门** — 域 5、7 达到 50% 掌握度
4. **测试与开发入门** — 域 6、8 达到 50% 掌握度
5. **入门完成** — 全部 8 领域达到 60% 正确率

详细说明见 [docs/learning-paths.md](docs/learning-paths.md)。

---

## 📝 模拟考试详解

### 考试规则

| 项目 | 默认值 | 说明 |
|------|--------|------|
| 题目数量 | 100 题 | 可配置 1-100+ |
| 考试时长 | 180 分钟 | 可配置，时间到自动交卷 |
| 及格线 | 70 分 | 与真实 CISSP 考试一致 |
| 题型分布 | 按域权重 | 参考 (ISC)² 官方考试大纲权重 |
| 暂停/继续 | ✅ 支持 | 随时暂停，剩余时间保留 |
| 题目跳转 | ✅ 支持 | `#N` 跳题、标记回头题 |

### 评分系统

- **百分制**：正确数 / 总题数 × 100
- **分域分数**：每个领域单独计算正确率
- **薄弱领域识别**：正确率低于 70% 且题数 ≥ 3 的领域
- **错题解析**：每道错题附带正确答案和解析

### 考试分析

- **历史成绩曲线**：查看历次考试分数走势
- **进步对比**：与上一次考试对比，找出进步最大和退步最大的领域
- **错题本**：所有错题集中展示，便于复习

详细说明见 [docs/exam-guide.md](docs/exam-guide.md)。

---

## 🕸️ 知识图谱详解

### 图谱结构

- **8 大领域**，每个领域 15-25 个核心知识点
- **137 条预设关系边**，3 种关系类型：
  - `prerequisite`（前置依赖）：学 B 之前必须先掌握 A
  - `related`（相关）：并列相关，理解互相促进
  - `part_of`（组成部分）：整体-部分关系

### 核心查询

| 查询 | 用途 | 示例 |
|------|------|------|
| **前置依赖** | 学这个之前需要什么基础？ | `knowledge prereq "Bell-LaPadula"` |
| **后继推荐** | 学完这个可以学什么？ | `knowledge next "CIA三元组"` |
| **相关查询** | 还有哪些相关知识点？ | 图谱中自动识别 |
| **薄弱点传播** | 这个点薄弱会影响哪些后续点？ | `knowledge impact "加密基础"` |
| **掌握度热力图** | 各领域整体掌握情况一览 | `knowledge heatmap` |

### 可视化

- **文本树**：终端直接看层级结构
- **Mermaid**：支持渲染流程图（Markdown / Obsidian / GitHub）
- **热力图**：用 emoji 色块直观展示掌握程度

详细说明见 [docs/knowledge-graph.md](docs/knowledge-graph.md)。

---

## 📊 数据模型（8 张表）

```
┌──────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  questions   │       │  study_records   │       │ knowledge_points│
│   题目表      │◄──────│   学习记录表      │       │   知识点表       │
├──────────────┤       ├──────────────────┤       ├─────────────────┤
│ id           │       │ id               │       │ id              │
│ domain       │       │ question_id      │       │ name            │
│ difficulty   │       │ study_date       │       │ domain          │
│ ...          │       │ is_correct       │       │ mastery_level   │
└──────────────┘       │ SM-2 相关字段     │       │ ...             │
                       └──────────────────┘       └─────────────────┘
                              │                            ▲
                              │                            │
┌──────────────────────────┐  │  ┌──────────────────┐      │
│    learning_paths        │  │  │ knowledge_edges  │      │
│      学习路径表           │  │  │   知识关联边表    │──────┘
├──────────────────────────┤  │  ├──────────────────┤
│ id / name / slug         │  │  │ source_kp_id     │
│ estimated_days           │  │  │ target_kp_id     │
│ milestones (JSON)        │  │  │ edge_type        │
│ daily_question_target    │  │  │ weight           │
│ ...                      │  │  └──────────────────┘
└───────────▲──────────────┘
            │
┌───────────┴──────────────┐        ┌──────────────────┐
│  user_path_progress      │        │  exam_sessions   │
│    用户路径进度表          │        │   考试会话表      │
├──────────────────────────┤        ├──────────────────┤
│ path_id (FK)             │        │ id               │
│ status                   │        │ title            │
│ completion_percent       │        │ status           │
│ current_milestone_index  │        │ score            │
│ ...                      │        │ duration_minutes │
└──────────────────────────┘        │ question_ids (JSON)
                                    │ ...              │
                                    └─────────▲────────┘
                                              │
                                    ┌─────────┴────────┐
                                    │   exam_answers    │
                                    │   考试答题记录表   │
                                    ├──────────────────┤
                                    │ exam_id (FK)     │
                                    │ question_id (FK) │
                                    │ user_answer      │
                                    │ is_correct       │
                                    │ time_spent_sec   │
                                    │ is_flagged       │
                                    └──────────────────┘
```

---

## 📁 目录结构

```
cissp-trainer/
├── README.md                       # 本文件
├── docs/
│   ├── learning-paths.md           # 学习路径使用指南
│   ├── exam-guide.md               # 模拟考试说明
│   └── knowledge-graph.md          # 知识图谱说明
├── src/
│   └── cissp_trainer/
│       ├── __init__.py
│       ├── models.py               # 数据模型（8 张表）
│       ├── database.py             # 数据库初始化与会话管理
│       ├── spaced_repetition.py    # SM-2 间隔重复算法
│       ├── engine.py               # 学习引擎核心
│       ├── importer.py             # YAML/JSON 题库 + 图谱导入
│       ├── knowledge_graph.py      # 🆕 知识图谱服务
│       ├── learning_path.py        # 🆕 学习路径引擎
│       ├── exam_engine.py          # 🆕 模拟考试引擎
│       └── cli.py                  # CLI 入口（13 个子命令）
├── data/
│   ├── db/                         # SQLite 数据库
│   └── yaml/
│       ├── sample_questions.yaml   # 52 道样例题
│       └── knowledge_graph.yaml    # 137 条图谱关系
└── tests/                          # 110 个测试用例
    ├── conftest.py
    ├── test_models.py              # MVP
    ├── test_spaced_repetition.py   # MVP
    ├── test_engine.py              # MVP
    ├── test_importer.py            # MVP
    ├── test_knowledge_graph.py     # 🆕 图谱 18 个
    ├── test_learning_path.py       # 🆕 路径 20 个
    ├── test_exam_engine.py         # 🆕 考试 22 个
    └── test_cli_v2.py              # 🆕 CLI 集成 4 个
```

---

## ✅ 测试

```bash
cd L4-proprietary/components/cissp-trainer
PYTHONPATH=src python3 -m pytest tests/ -v
```

**总共 110 个测试用例**，全部通过。

| 模块 | 测试数 | 覆盖范围 |
|------|--------|---------|
| 数据模型 | 4 | CRUD、关系 |
| 间隔重复 | 7 | SM-2 算法 |
| 学习引擎 | 14 | 出题/答题/统计 |
| 题库导入 | 8 | YAML/JSON 导入 |
| **知识图谱** | **18** | 边管理/查询/建议/传播/可视化 |
| **学习路径** | **20** | 预设/推荐/进度/里程碑/每日计划/调整 |
| **模拟考试** | **22** | 创建/流程/暂停/评分/历史/对比 |
| **CLI 集成** | **4** | 三大模块端到端验证 |
| **合计** | **110** | |

---

## 🏗️ 架构层级

```
L4 专有业务层
└── cissp-trainer (本组件)
    ├─ 依赖：SQLAlchemy + PyYAML（轻量标准库级）
    ├─ 数据：SQLite (data/db/)
    ├─ 核心层：models + spaced_repetition + engine
    ├─ 扩展层：knowledge_graph + learning_path + exam_engine
    ├─ 接口层：CLI
    └─ 扩展方向：Web UI / 移动端 / Anki 同步 / 多用户
```

---

## 🔗 与现有 cissp-learning 的关系

| 组件 | 定位 | 核心能力 |
|------|------|---------|
| cissp-learning | 学习规划 | 16 周计划、每日内容、速记卡 |
| **cissp-trainer** | **学习引擎 + 路径 + 考试 + 图谱** | **智能出题、间隔重复、路径规划、模拟考试、知识图谱** |

两者可以互补：cissp-learning 负责"学什么内容"，cissp-trainer 负责"怎么练、测效果、找弱点"。

---

## 🗺️ 后续路线图

- [ ] 从 cissp-learning 迁移 554 道题（补齐难度/标签）
- [ ] 与 cissp-learning 学习规划引擎双向联动
- [ ] Web UI（FastAPI + 前端）
- [ ] 错题本导出 / Anki 同步
- [ ] 学习报告生成（周/月）
- [ ] 多设备数据同步
- [ ] 真实 CISSP 考试场景还原（CAT 自适应）
- [ ] 知识点卡片 + 思维导图导出
