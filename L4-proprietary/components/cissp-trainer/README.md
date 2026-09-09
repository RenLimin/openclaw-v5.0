# CISSP Trainer — CISSP 学习引擎

> L4 专有业务层组件 · 结构化题库 + 间隔重复 + 薄弱点识别

---

## 功能概览

- **📚 结构化题库** — SQLite + SQLAlchemy，题目/学习记录/知识点 三表模型
- **🎯 智能出题** — 4 种模式：随机 / 到期复习 / 薄弱点强化 / 模拟考试
- **🔄 间隔重复** — 简化 SM-2 算法，自动安排复习时间
- **📊 学习统计** — 总体正确率、分域表现、薄弱知识点排名、进度曲线
- **🧠 知识点掌握度** — 基于指数移动平均的掌握度追踪
- **💻 CLI 接口** — `start` / `stats` / `weak` / `import` / `init`
- **📝 YAML 题库** — 人工友好的题库格式，便于批量维护

---

## 快速开始

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

# 初始化数据库 + 导入 52 道样例题
PYTHONPATH=src python3 -m cissp_trainer.cli init --sample
```

### 常用命令

```bash
# 开始练习（随机 10 题）
PYTHONPATH=src python3 -m cissp_trainer.cli start

# 指定领域 + 到期复习模式
PYTHONPATH=src python3 -m cissp_trainer.cli start -d 1 -m review -n 20

# 薄弱点强化
PYTHONPATH=src python3 -m cissp_trainer.cli start -m weak

# 模拟考试
PYTHONPATH=src python3 -m cissp_trainer.cli start -m exam -n 100

# 查看统计
PYTHONPATH=src python3 -m cissp_trainer.cli stats

# 薄弱知识点排名
PYTHONPATH=src python3 -m cissp_trainer.cli weak -n 10

# 导入 YAML 题库
PYTHONPATH=src python3 -m cissp_trainer.cli import path/to/questions.yaml
```

### 设为别名

```bash
alias cissp-trainer='PYTHONPATH=/path/to/cissp-trainer/src python3 -m cissp_trainer.cli'
```

---

## 题库格式（YAML）

```yaml
questions:
  - id: "d1-001"              # 外部 ID（可选）
    domain: 1                  # 领域 1-8
    difficulty: 3              # 难度 1-5
    question_type: single      # single / multiple / truefalse
    stem: "题干内容"
    options:
      A: "选项 A"
      B: "选项 B"
      C: "选项 C"
      D: "选项 D"
    correct_answer: "B"        # 单选: "A", 多选: "A,B", 判断: "A"/"B"
    explanation: "答案解析..."
    tags: ["知识点1", "知识点2"]  # 知识点标签，用于掌握度追踪
    source: "CISSP OSG 第8版"
    main_topic: "1.2"           # CBK 主项编号
```

### 8 大领域

| 编号 | 名称 | 样例题数 |
|------|------|---------|
| 1 | 安全与风险管理 | 6 |
| 2 | 资产安全 | 6 |
| 3 | 安全架构与工程 | 7 |
| 4 | 通信与网络安全 | 6 |
| 5 | 身份与访问管理 | 7 |
| 6 | 安全评估与测试 | 6 |
| 7 | 安全运营 | 7 |
| 8 | 软件开发安全 | 7 |
| **合计** | | **52** |

---

## 核心算法

### 间隔重复（简化 SM-2）

每次答题后自动计算下次复习时间：

- **答对**：间隔递增（1 天 → 3 天 → 3×EF 天 → ...）
- **答错**：间隔重置为 1 天，连续正确次数归零
- **易度因子（EF）**：答对不变或微升，答错降低，最低 1.3

### 知识点掌握度

使用指数移动平均（EMA）：

```
新掌握度 = 旧掌握度 × 0.7 + 本次结果 × 0.3
```

- 答对 = 1.0，答错 = 0.0
- 答错的权重隐含更高（因为基线低，下降幅度大）
- 至少复习 2 次才纳入薄弱点排名

### 出题优先级

| 模式 | 优先级规则 |
|------|-----------|
| random | 完全随机 |
| review | 到期时间 × 易度因子倒数 |
| weak | 薄弱知识点命中数 × 10 + 错误率 × 5 |
| exam | 按 CISSP 官方域权重分配 |

---

## 数据模型

```
┌──────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  questions   │       │  study_records   │       │ knowledge_points│
├──────────────┤       ├──────────────────┤       ├─────────────────┤
│ id (PK)      │◄──────│ question_id (FK) │       │ id (PK)         │
│ domain       │       │ study_date       │       │ name            │
│ difficulty   │       │ user_answer      │       │ domain          │
│ question_type│       │ is_correct       │       │ mastery_level   │
│ stem         │       │ time_spent_sec   │       │ total_questions │
│ options (JSON)│      │ quality (SM-2)   │       │ correct_count   │
│ correct_answer│      │ efactor          │       │ wrong_count     │
│ explanation  │       │ interval         │       │ review_count    │
│ tags (JSON)  │       │ repetition       │       │ last_reviewed_at│
│ source       │       │ next_review_date │       └─────────────────┘
│ times_shown  │       └──────────────────┘
│ times_correct│
└──────────────┘
```

---

## 目录结构

```
cissp-trainer/
├── README.md                 # 本文件
├── src/
│   └── cissp_trainer/
│       ├── __init__.py
│       ├── models.py         # 数据模型（SQLAlchemy ORM）
│       ├── database.py       # 数据库初始化与会话管理
│       ├── spaced_repetition.py  # SM-2 间隔重复算法
│       ├── engine.py         # 学习引擎核心（出题/答题/统计）
│       ├── importer.py       # YAML/JSON 题库导入器
│       └── cli.py            # CLI 入口
├── data/
│   ├── db/                   # SQLite 数据库（运行时生成）
│   └── yaml/
│       └── sample_questions.yaml  # 52 道样例题
└── tests/                    # 38 个测试用例
    ├── conftest.py
    ├── test_models.py
    ├── test_spaced_repetition.py
    ├── test_engine.py
    └── test_importer.py
```

---

## 测试

```bash
cd L4-proprietary/components/cissp-trainer
PYTHONPATH=src python3 -m pytest tests/ -v
```

38 个测试用例，覆盖：
- 数据模型 CRUD（4）
- 间隔重复算法（7）
- 出题模块（7）
- 答题模块（6）
- 统计模块（6）
- 题库导入（8）

---

## 与现有 cissp-learning 的关系

本组件（cissp-trainer）专注于**学习引擎核心**：结构化数据模型、间隔重复、智能出题、掌握度追踪、薄弱点分析。

现有 `cissp-learning` 组件专注于**学习规划与内容组织**：16 周学习计划、每日内容生成、速记卡。

两者可以互补使用：

| 组件 | 定位 | 核心能力 |
|------|------|---------|
| cissp-learning | 学习规划 | 16 周计划、每日内容、速记卡 |
| **cissp-trainer** | **学习引擎** | **智能出题、间隔重复、掌握度追踪、薄弱点分析** |

---

## 架构层级

```
L4 专有业务层
└── cissp-trainer (本组件)
    ├─ 依赖：SQLAlchemy + PyYAML（标准库级）
    ├─ 数据：SQLite (data/db/)
    └─ 扩展方向：Web UI / 移动端 / Anki 同步
```

---

## 后续路线图

- [ ] 从现有 cissp-learning 迁移 554 道题（补齐难度/标签）
- [ ] 与 cissp-learning 学习规划引擎联动
- [ ] Web UI（FastAPI + 前端）
- [ ] 错题本导出 / Anki 同步
- [ ] 学习报告生成（周/月）
- [ ] 多设备数据同步
