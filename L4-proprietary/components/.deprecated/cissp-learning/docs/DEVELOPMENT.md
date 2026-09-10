# CISSP 学习系统 — 开发说明

## 目录

1. [架构概览](#架构概览)
2. [模块说明](#模块说明)
3. [数据格式](#数据格式)
4. [扩展开发](#扩展开发)
5. [测试指南](#测试指南)
6. [目录结构](#目录结构)

---

## 架构概览

CISSP 学习系统采用模块化设计，遵循 OpenClaw 4 层架构的 L4 层规范。

### 分层依赖

```
L4 cissp-learning (本组件)
  │
  ├─ 知识依赖 → L3 security-engineering 知识库维度（待建设）
  │
  └─ 基础依赖 → 标准库 JSON 持久化（当前简化实现）
                 L2 memory-embedding（未来接入知识库检索）
```

### 设计原则

1. **低耦合**：模块间通过明确的 API 交互，不共享内部状态
2. **数据驱动**：所有数据存储为 JSON 文件，易于查看/编辑/备份
3. **可扩展**：每个模块都预留扩展点，支持增量开发
4. **标准库优先**：尽量使用 Python 标准库，减少外部依赖

---

## 模块说明

### 1. planner.py — 学习规划引擎

**核心类/函数**：

| 函数 | 说明 |
|------|------|
| `load_domains()` | 加载 8 域结构 |
| `load_progress()` | 加载学习进度（用于动态调整） |
| `total_study_hours(start_date, weeks, ...)` | 计算总学习时长 |
| `generate_plan(start_date, weeks, ...)` | 生成学习计划（核心） |
| `save_plan(plan, path)` | 保存计划到 progress.json |
| `get_plan()` | 获取已保存的计划 |
| `get_day_plan(date_str)` | 获取某日计划 |

**计划生成算法**：

1. 计算总学习时长（工作日 × 工作日时长 + 周末日 × 周末时长）
2. 按域权重分配总时长到各域
3. **动态调整**：正确率 < 60% 的域 × 1.2
4. 每个域内按主项数均分
5. 构造主项队列，按日期逐日填充
6. 每天从队列头部取主项，填满当日时长

### 2. daily_content.py — 每日内容生成器

| 函数 | 说明 |
|------|------|
| `load_chapter_map()` | 加载 OSG 章节映射 |
| `get_main_topic_details(domain_id, main_id)` | 获取主项详情（子项 + 章节） |
| `generate_daily_content(day_plan)` | 生成当日内容大纲 |
| `format_daily_content(content)` | 格式化输出（Markdown 风格） |
| `get_today_content()` | 获取今日内容（便捷函数） |

### 3. question_bank.py — 题库管理器

| 函数 | 说明 |
|------|------|
| `load_questions()` | 加载所有题目 |
| `load_mistakes()` / `save_mistakes()` | 错题本读写 |
| `get_questions_by_domain(domain_id)` | 按域筛选 |
| `get_questions_by_main_topic(main_topic_id)` | 按主项筛选 |
| `generate_quiz(count, domain, ...)` | 生成练习题/模拟卷 |
| `record_mistake(question_id, user_answer, ...)` | 记录错题 |
| `import_questions(source_data, source_name)` | 导入题目 |
| `get_stats()` | 题库统计 |

### 4. flashcard.py — 速记卡生成器

| 函数 | 说明 |
|------|------|
| `generate_from_domains(domain_id, ...)` | 从考点结构生成概念卡 |
| `generate_from_questions(domain_id, count)` | 从题库生成题目卡 |
| `generate_flashcards(domain_id, count, mix)` | 混合生成（主入口） |
| `format_flashcards(cards, format)` | 格式化输出：text/anki/json |
| `interactive_flashcards(cards)` | CLI 交互练习 |

### 5. cli.py — 命令行入口

使用 `argparse` 实现，子命令通过 `set_defaults(func=...)` 分发。

每个子命令对应一个 `cmd_<name>(args)` 函数。

---

## 数据格式

### domains.json

```json
{
  "version": "CBK-2021",
  "total_weight": 100,
  "domains": [
    {
      "id": 1,
      "name": "安全与风险管理",
      "weight": 15,
      "main_topics": [
        {
          "id": "1.1",
          "name": "理解、遵从与提升职业道德",
          "sub_topics": ["(ISC)2 职业道德规范", "组织的道德规范"]
        }
      ]
    }
  ]
}
```

### questions.json

```json
[
  {
    "id": "preexam-1",
    "source_qid": 1,
    "question": "题干...",
    "options": {
      "A": "选项A",
      "B": "选项B",
      "C": "选项C",
      "D": "选项D"
    },
    "answer": "B",
    "explanation": "解析...",
    "source": "考前冲刺-解析版.docx",
    "domain": 1,
    "main_topic": "1.3"
  }
]
```

### progress.json

```json
{
  "version": "1.0",
  "plan": {
    "start_date": "2026-09-08",
    "total_weeks": 16,
    "weekday_hours": 1,
    "weekend_hours": 3
  },
  "plan_days": {
    "2026-09-08": {
      "date": "2026-09-08",
      "day_of_week": "Tuesday",
      "is_weekend": false,
      "planned_hours": 1.0,
      "items": [...],
      "completed": false
    }
  },
  "plan_weeks": [...],
  "daily_log": {},
  "domain_progress": {},
  "overall": {
    "days_completed": 0,
    "total_days": 0,
    "avg_correct_rate": 0.0,
    "questions_answered": 0
  }
}
```

### mistakes.json

```json
{
  "version": "1.0",
  "mistakes": [
    {
      "question_id": "preexam-1",
      "question": "题干...",
      "correct_answer": "B",
      "wrong_count": 1,
      "last_wrong_at": "2026-09-08",
      "user_answer": "A",
      "notes": "",
      "domain": 1,
      "main_topic": "1.3"
    }
  ],
  "stats": {
    "total_mistakes": 1,
    "by_domain": {"1": 1},
    "by_main_topic": {}
  }
}
```

---

## 扩展开发

### 添加新的 CLI 子命令

1. 在 `cli.py` 中添加 `cmd_<name>(args)` 函数
2. 在 `main()` 中用 `subparsers.add_parser()` 注册
3. 用 `set_defaults(func=cmd_<name>)` 绑定

### 添加新的题库导入格式

1. 在 `question_bank.py` 中新增 `import_from_<format>()` 函数
2. 在 CLI 的 `import` 子命令中添加 `--format` 选项
3. 根据格式分发到不同的导入函数

### 接入 L3 知识库

规划中的集成点：

```python
# daily_content.py 扩展：从知识库拉取详细内容
def get_knowledge_content(main_topic_id):
    """从 L3 security-engineering 知识库检索主项详细内容"""
    # 调用 L2 memory-embedding 的检索 API
    # 返回 Markdown 内容
    pass
```

### 节假日识别扩展

```python
# planner.py 扩展：中国法定节假日
def is_holiday(date_obj):
    """判断是否为法定节假日"""
    # 方案 1: 维护本地节假日 JSON 表
    # 方案 2: 调用第三方 API（如 中国法定节假日 API）
    pass
```

---

## 测试指南

### 手动测试

```bash
# 1. 生成计划
PYTHONPATH=src python3 -m cissp.cli plan --generate --show-weeks 2

# 2. 今日内容
PYTHONPATH=src python3 -m cissp.cli today

# 3. 答题（用 echo 模拟输入）
echo -e "A\nB\nC\nD\nA\n" | PYTHONPATH=src python3 -m cissp.cli quiz --count 5

# 4. 速记卡导出
PYTHONPATH=src python3 -m cissp.cli flashcard --count 5 --export --export-format text

# 5. 统计
PYTHONPATH=src python3 -m cissp.cli stats

# 6. 进度
PYTHONPATH=src python3 -m cissp.cli progress
```

### 单元测试（待实现）

建议测试覆盖：

- `planner.generate_plan()`：验证 16 周 × 7 天 = 112 天，总时长正确
- `question_bank.generate_quiz()`：验证题数、域分布
- `flashcard.generate_flashcards()`：验证卡片数量、类型比例
- `daily_content.generate_daily_content()`：验证格式正确

### 集成测试

```bash
# 端到端测试：生成计划 → 查看今日 → 做 5 题 → 查看进度
PYTHONPATH=src python3 -m cissp.cli plan --generate > /dev/null
PYTHONPATH=src python3 -m cissp.cli today > /dev/null
echo -e "A\nB\nC\nD\nA\n" | PYTHONPATH=src python3 -m cissp.cli quiz --count 5 > /dev/null
PYTHONPATH=src python3 -m cissp.cli progress
```

---

## 目录结构

```
cissp-learning/
├── DESIGN.md              # 设计文档
├── README.md              # 项目说明
├── SKILL.md               # OpenClaw 技能封装
├── src/
│   └── cissp/
│       ├── __init__.py    # 包初始化
│       ├── planner.py     # 学习规划引擎
│       ├── daily_content.py  # 每日内容生成
│       ├── question_bank.py  # 题库管理
│       ├── flashcard.py   # 速记卡生成
│       └── cli.py         # CLI 入口
├── data/
│   ├── domains.json       # 8 域结构
│   ├── chapter_map.json   # 考点-章节映射
│   ├── questions.json     # 题库
│   ├── progress.json      # 进度 + 计划
│   └── mistakes.json      # 错题本
└── docs/
    ├── USER_GUIDE.md      # 用户手册
    ├── CLI_REFERENCE.md   # CLI 参考
    └── DEVELOPMENT.md     # 本文件
```
