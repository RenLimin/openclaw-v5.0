# 详细设计 DESIGN-DETAIL-v1.0

## 1. 数据模型设计

### 1.1 核心表结构

#### `questions` 题目表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| domain | Integer | 领域编号（1-8） |
| domain_name | String | 领域名称 |
| difficulty | Integer | 难度（1-5） |
| question_type | String | 题型（single/multiple/truefalse） |
| content | Text | 题目内容 |
| options | JSON | 选项（A/B/C/D...） |
| correct_answer | String | 正确答案 |
| explanation | Text | 题目解析 |
| knowledge_point_ids | JSON | 关联知识点 ID 列表 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### `knowledge_points` 知识点表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| name | String | 知识点名称 |
| domain | Integer | 所属领域 |
| mastery_level | Float | 掌握度（0.0-1.0） |
| efactor | Float | SM-2 算法 easiness factor |
| interval | Integer | 下次复习间隔（天） |
| repetitions | Integer | 重复次数 |
| last_reviewed_at | DateTime | 上次复习时间 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### `study_records` 学习记录表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| question_id | Integer | 题目 ID |
| knowledge_point_id | Integer | 知识点 ID |
| is_correct | Boolean | 是否答对 |
| quality | Integer | SM-2 质量评分（0-5） |
| studied_at | DateTime | 学习时间 |

#### `knowledge_edges` 知识关联边表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| source_kp_id | Integer | 源知识点 ID |
| target_kp_id | Integer | 目标知识点 ID |
| edge_type | String | 边类型（prerequisite/related/part_of） |
| weight | Float | 影响权重（0.0-1.0） |

#### `learning_paths` 学习路径表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| name | String | 路径名称 |
| slug | String | 路径唯一标识 |
| description | Text | 路径描述 |
| estimated_days | Integer | 预估天数 |
| daily_question_target | Integer | 每日目标题量 |
| min_difficulty | Integer | 最小难度 |
| max_difficulty | Integer | 最大难度 |
| prerequisites | JSON | 前置依赖路径 |
| milestones | JSON | 里程碑定义列表 |
| created_at | DateTime | 创建时间 |

#### `user_path_progress` 用户路径进度表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| path_id | Integer | 路径 ID |
| status | String | 状态（not_started/in_progress/completed） |
| completion_percent | Float | 完成百分比 |
| current_milestone_index | Integer | 当前里程碑索引 |
| started_at | DateTime | 开始时间 |
| completed_at | DateTime | 完成时间 |
| last_updated_at | DateTime | 最后更新时间 |

#### `exam_sessions` 考试会话表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| title | String | 考试标题 |
| status | String | 状态（running/paused/completed） |
| num_questions | Integer | 题目总数 |
| duration_minutes | Integer | 考试时长（分钟） |
| score | Float | 最终分数 |
| passed | Boolean | 是否及格 |
| question_ids | JSON | 题目 ID 列表 |
| started_at | DateTime | 开始时间 |
| paused_at | DateTime | 暂停时间 |
| submitted_at | DateTime | 交卷时间 |
| duration_minutes_actual | Float | 实际用时（分钟） |

#### `exam_answers` 考试答题记录表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| exam_id | Integer | 考试会话 ID |
| question_id | Integer | 题目 ID |
| user_answer | String | 用户答案 |
| is_correct | Boolean | 是否正确 |
| time_spent_sec | Float | 用时（秒） |
| is_flagged | Boolean | 是否标记 |
| answered_at | DateTime | 答题时间 |

### 1.2 数据关系
- `questions` ←→ `knowledge_points`：多对多（一道题关联多个知识点）
- `study_records` → `questions`：多对一
- `study_records` → `knowledge_points`：多对一
- `knowledge_edges` → `knowledge_points`（source/target）：多对一
- `user_path_progress` → `learning_paths`：多对一
- `exam_answers` → `exam_sessions`：多对一
- `exam_answers` → `questions`：多对一

## 2. 核心接口设计

### 2.1 学习引擎 `engine.Engine`

```python
class Engine:
    def pick_questions(self, mode: str, count: int, domain: Optional[int]) -> List[Question]
        # 根据模式抽题：random/review/weak/exam
        # 返回题目列表

    def submit_answer(self, question_id: int, user_answer: str) -> SubmitResult
        # 提交答案，更新掌握度和间隔重复数据
        # 返回结果：是否正确、正确答案、解析、知识点更新

    def get_overall_stats(self) -> OverallStats
        # 获取总体统计：总题数、正确率、掌握度分布

    def get_domain_stats(self) -> List[DomainStats]
        # 获取分领域统计：每个领域正确率、题量

    def get_weak_knowledge_points(self, limit: int) -> List[WeakKP]
        # 获取薄弱知识点排名：按掌握度升序
```

### 2.2 间隔重复 `spaced_repetition.SM2`

```python
class SM2:
    def calculate_interval(self, quality: int, current_interval: int, current_efactor: float) -> Tuple[int, float]
        # quality: 0-5，0 表示完全错，5 表示完美答对
        # 返回 (new_interval, new_efactor)
        # 简化实现：efactor >= 1.3，首次答对 interval = 1，第二次 = 6，后续 = interval * efactor
```

### 2.3 知识图谱 `knowledge_graph.KnowledgeGraph`

```python
class KnowledgeGraph:
    def get_prerequisites(self, kp_name: str, max_depth: int) -> List[List[KnowledgePoint]]
        # 返回分层前置依赖，depth 从 1 到 max_depth
        # 第一层是直接前置，第二层是前置的前置，依此类推

    def get_successors(self, kp_name: str) -> List[KnowledgePoint]
        # 返回当前知识点作为前置的后继知识点，推荐后续学习

    def get_related(self, kp_name: str) -> List[KnowledgePoint]
        # 返回相关知识点

    def calculate_weak_propagation(self, kp_name: str, max_depth: int) -> List[PropagationResult]
        # 计算薄弱点传播影响，按影响权重排序

    def build_domain_graph(self, domain: int) -> Graph
        # 构建领域知识图谱，用于可视化

    def to_text_tree(self, graph: Graph) -> str
        # 生成文本树格式

    def to_mermaid(self, graph: Graph) -> str
        # 生成 Mermaid 格式

    def generate_mastery_heatmap(self) -> str
        # 生成掌握度热力图（emoji 色块）
```

### 2.4 学习路径 `learning_path.LearningPathEngine`

```python
class LearningPathEngine:
    def list_paths(self) -> List[LearningPath]
        # 列出所有可用路径

    def recommend_path(self) -> LearningPathRecommendation
        # 根据当前学习状态推荐合适路径

    def start_path(self, slug: str) -> None
        # 开始学习某路径，初始化进度

    def get_current_path_status(self) -> Optional[PathStatus]
        # 获取当前进行中路径进度

    def generate_daily_plan(self) -> DailyPlan
        # 根据当前进度生成今日学习计划

    def adjust_path_progress(self) -> None
        # 根据最近正确率动态调整题量和难度
```

### 2.5 模拟考试 `exam_engine.ExamEngine`

```python
class ExamEngine:
    def start_exam(self, num_questions: int, duration_minutes: int, domains: Optional[List[int]]) -> ExamSession
        # 创建并开始新考试，抽题

    def get_current_question(self, exam_id: int) -> CurrentQuestion
        # 获取当前题目

    def answer_question(self, exam_id: int, question_index: int, answer: str) -> None
        # 保存答案

    def flag_question(self, exam_id: int, question_index: int, flagged: bool) -> None
        # 标记/取消标记题目

    def goto_question(self, exam_id: int, index: int) -> int
        # 跳转到指定题目，返回实际跳转索引

    def pause_exam(self, exam_id: int) -> None
        # 暂停考试

    def resume_exam(self, exam_id: int) -> None
        # 恢复考试

    def submit_exam(self, exam_id: int) -> ExamResult
        # 交卷，评分，返回结果

    def list_exam_history(self) -> List[ExamHistoryItem]
        # 获取考试历史

    def get_exam_detail(self, exam_id: int) -> ExamDetail
        # 获取考试详情和错题解析

    def get_score_curve(self) -> List[ScorePoint]
        # 获取成绩曲线用于趋势分析

    def compare_with_previous(self, current_exam_id: int) -> ComparisonResult
        # 和上次考试对比，分析进步和退步领域
```

## 3. 核心算法设计

### 3.1 掌握度更新（EMA）

掌握度使用指数移动平均计算：
```
alpha = 0.3  # 平滑因子
new_mastery = alpha * is_correct + (1 - alpha) * old_mastery
```
- `is_correct` 为 1（答对）或 0（答错）
- 最近练习对掌握度影响更大，自动衰减旧练习影响

### 3.2 间隔重复（简化 SM-2）

算法步骤：
1. 如果 quality < 3，重置 repetitions = 0，interval = 1
2. 如果 quality >= 3：
   - repetitions += 1
   - if repetitions == 1: interval = 1
   - elif repetitions == 2: interval = 6
   - else: interval = round(interval * efactor)
3. 更新 efactor: `efactor = efactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))`
4. 保证 efactor >= 1.3

### 3.3 薄弱点传播

当前知识点薄弱（掌握度 < 0.6），影响后继知识点：
```
new_mastery(target) = current_mastery(target) * (1 - weight * source_weakness)
```
- 传播深度限制，距离越远影响权重衰减
- 只计算 `prerequisite` 类型边，不计算 `related` 和 `part_of`

### 3.4 学习路径动态调整

根据最近 3 天正确率：
- 连续 > 85%：题量 + 20%，难度 + 1（不超过路径最大难度）
- 连续 < 50%：题量 - 20%，难度 - 1（不低于路径最小难度）
- 否则不变

## 4. 目录结构

```
cissp-trainer/
├── README.md
├── DESIGN.md
├── docs/
│   ├── PRD-v1.0.md
│   ├── DESIGN-OUTLINE-v1.0.md
│   ├── DESIGN-DETAIL-v1.0.md
│   ├── VERIFICATION-v1.0.md
│   ├── OPERATIONS-v1.0.md
│   ├── learning-paths.md
│   ├── exam-guide.md
│   └── knowledge-graph.md
├── src/
│   └── cissp_trainer/
│       ├── __init__.py
│       ├── models.py
│       ├── database.py
│       ├── spaced_repetition.py
│       ├── engine.py
│       ├── importer.py
│       ├── knowledge_graph.py
│       ├── learning_path.py
│       ├── exam_engine.py
│       ├── cli.py
│       └── web/
│           ├── __init__.py
│           ├── main.py
│           ├── api.py
│           └── templates/
├── data/
│   ├── db/
│   └── yaml/
│       ├── sample_questions.yaml
│       └── knowledge_graph.yaml
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_spaced_repetition.py
    ├── test_engine.py
    ├── test_importer.py
    ├── test_knowledge_graph.py
    ├── test_learning_path.py
    ├── test_exam_engine.py
    ├── test_cli_v2.py
    └── test_web.py
```
