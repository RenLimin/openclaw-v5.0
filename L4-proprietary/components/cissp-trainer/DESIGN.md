# cissp-trainer

## 设计目标

为 CISSP 认证学习提供智能刷题、学习路径规划、模拟考试、知识图谱四大核心能力。解决传统学习方式中复习无规划、薄弱点不清晰、考试体验缺失的问题。

## 架构决策

- **SQLite + SQLAlchemy**：轻量级本地存储，零外部依赖
- **SM-2 间隔重复**：简化 SM-2 算法自动安排复习时间，提升记忆效率
- **模块化引擎**：核心引擎（出题/答题/统计）与扩展模块（路径/考试/图谱）分离
- **CLI 优先**：13 个子命令覆盖全部功能，后续扩展 Web UI
- **数据驱动掌握度**：基于指数移动平均（EMA）追踪知识点掌握度
- **知识图谱驱动路径**：137 条关系边支撑前置依赖查询和学习推荐

## 模块划分

```
cissp-trainer/
├── src/cissp_trainer/
│   ├── models.py               # 数据模型（8 张表）
│   ├── database.py             # 数据库初始化与会话管理
│   ├── spaced_repetition.py    # SM-2 间隔重复算法
│   ├── engine.py               # 学习引擎核心（出题/答题/统计）
│   ├── importer.py             # YAML/JSON 题库 + 图谱导入
│   ├── knowledge_graph.py      # 知识图谱服务
│   ├── learning_path.py        # 学习路径引擎
│   ├── exam_engine.py          # 模拟考试引擎
│   ├── cli.py                  # CLI 入口（13 个子命令）
│   └── web/                    # Web UI
│       ├── main.py             # Flask 入口
│       ├── api.py              # REST API
│       └── templates/          # Jinja2 模板（9 页面）
├── data/
│   ├── db/                     # SQLite 数据库
│   └── yaml/
│       ├── sample_questions.yaml
│       └── knowledge_graph.yaml
├── docs/
│   ├── learning-paths.md
│   ├── exam-guide.md
│   └── knowledge-graph.md
└── tests/                      # 110 个测试用例
```

## 关键接口/数据结构

- `models.Question`：题目模型（domain/difficulty/options/explanation）
- `models.StudyRecord`：学习记录（question_id/is_correct/SM-2 字段）
- `models.KnowledgePoint`：知识点（name/domain/mastery_level）
- `models.KnowledgeEdge`：知识关联边（source/target/edge_type/weight）
- `models.LearningPath`：学习路径（name/slug/milestones/daily_target）
- `models.ExamSession`：考试会话（status/score/question_ids）
- `engine.Engine`：核心引擎，`start_session()` / `submit_answer()` / `get_stats()`
- `spaced_repetition.SM2`：间隔重复，`calculate_interval(quality)`
- `knowledge_graph.KnowledgeGraph`：图谱查询，`prereq()` / `next()` / `impact()`
- `learning_path.LearningPathEngine`：路径引擎，`recommend()` / `today_plan()`
- `exam_engine.ExamEngine`：考试引擎，`start()` / `pause()` / `submit()`

## 依赖关系

- **依赖**：Python 3.10+、SQLAlchemy 2.0+、PyYAML
- **被依赖**：`cissp-learning`（L3 层，互补关系：cissp-learning 负责"学什么"，cissp-trainer 负责"怎么练"）

## 演进方向

1. **Web UI**：FastAPI + 前端，替代 CLI 成为主要交互方式
2. **Anki 同步**：学习记录与 Anki 双向同步
3. **CAT 自适应考试**：还原真实 CISSP 考试的自适应抽题逻辑
4. **多用户支持**：用户鉴权 + 数据隔离
5. **学习报告**：自动生成周/月学习报告
6. **从 cissp-learning 迁移 554 道题**：补齐题库规模
