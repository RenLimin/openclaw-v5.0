# DESIGN-DETAIL: CISSP 知识点学习训练引擎 - v1.0

## 1. 数据模型

### 1.1 枚举定义
```python
class CISSPDomain(Enum):
    SECURITY_RISK_MANAGEMENT = 1       # 安全与风险管理
    ASSET_SECURITY = 2                 # 资产安全
    SECURITY_ARCH_ENGINEERING = 3      # 安全架构与工程
    COMMUNICATION_NETWORK_SECURITY = 4 # 通信与网络安全
    IDENTITY_ACCESS_MANAGEMENT = 5     # 身份与访问管理
    SECURITY_ASSESSMENT_TESTING = 6   # 安全评估与测试
    SECURITY_OPERATIONS = 7            # 安全运营
    SOFTWARE_DEVELOPMENT_SECURITY = 8  # 软件开发安全
```

```python
class Difficulty(Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3
```

```python
class QuestionType(Enum):
    SINGLE_CHOICE = 1
    MULTIPLE_CHOICE = 2
```

### 1.2 核心数据结构

#### 1.2.1 KnowledgePoint
```python
@dataclass
class KnowledgePoint:
    kp_id: str               # 知识点唯一ID，格式: D{领域ID}-{序号}
    domain_id: CISSPDomain   # 所属领域
    name: str                # 知识点名称
    description: str         # 知识点描述
    difficulty: Difficulty   # 难度
    tags: List[str]          # 标签
```

#### 1.2.2 Question
```python
@dataclass
class Question:
    q_id: str                # 题目唯一ID
    kp_id: str               # 关联知识点ID
    question_type: QuestionType # 题目类型
    stem: str                # 题干
    options: Dict[str, str]  # 选项：key=选项ID(A/B/C/D), value=选项内容
    correct_answers: List[str] # 正确答案列表
    explanation: str         # 解析
    difficulty: Difficulty   # 难度
```

#### 1.2.3 AnswerRecord
```python
@dataclass
class AnswerRecord:
    ar_id: str               # 记录ID
    q_id: str                # 题目ID
    user_answers: List[str]  # 用户答案
    is_correct: bool         # 是否答对
    timestamp: float         # 答题时间戳
```

#### 1.2.4 UserStats
```python
@dataclass
class DomainStats:
    domain_id: CISSPDomain
    total_questions: int
    correct_answers: int
    attempted: int

@dataclass
class UserStats:
    domain_stats: Dict[CISSPDomain, DomainStats]
    total_attempted: int
    total_correct: int
    last_updated: float
```

## 2. 接口契约

### 2.1 核心引擎接口

```python
class CISSPLearningEngine:
    def __init__(self, data_path: str):
        """初始化引擎，指定数据存储路径"""
    
    def load_knowledge_base(self, kb_file: str) -> None:
        """从指定文件加载知识点和题目"""
    
    def get_available_domains(self) -> List[CISSPDomain]:
        """返回当前知识库中包含题目的领域列表"""
    
    def generate_quiz(self, 
                     domains: Optional[List[CISSPDomain]] = None,
                     difficulty: Optional[List[Difficulty]] = None,
                     count: int = 10,
                     only_wrong: bool = False) -> List[Question]:
        """
        生成练习卷
        :param domains: 限定领域，None=所有领域
        :param difficulty: 限定难度，None=所有难度
        :param count: 题目数量
        :param only_wrong: 只抽错题
        :return: 题目列表
        """
    
    def submit_answer(self, 
                     question: Question, 
                     user_answers: List[str]) -> Tuple[bool, AnswerRecord]:
        """
        提交答案
        :return: (是否正确, 记录对象)
        """
    
    def get_wrong_questions(self) -> List[Question]:
        """获取所有错题列表"""
    
    def get_statistics(self) -> UserStats:
        """获取当前用户统计数据"""
    
    def save_state(self) -> None:
        """保存当前答题状态和统计到文件"""
    
    def export_wrong_questions(self, output_path: str) -> None:
        """导出所有错题到CSV文件"""
```

### 2.2 导入导出接口

```python
class DataImporter:
    @staticmethod
    def from_json(json_path: str) -> Tuple[List[KnowledgePoint], List[Question]]:
        """从JSON文件导入知识点和题目"""
    
    @staticmethod
    def from_csv(csv_path: str) -> List[Question]:
        """从CSV文件批量导入题目"""

class DataExporter:
    @staticmethod
    def to_csv(questions: List[Question], output_path: str) -> None:
        """导出题目到CSV文件"""
    
    @staticmethod
    def export_stats(stats: UserStats, output_path: str) -> None:
        """导出统计数据到CSV文件"""
```

## 3. 技术方案

### 3.1 数据存储
- 知识点和题目：JSON 文件存储（kb.json），格式兼容，易于编辑
- 用户状态和统计：JSON 文件存储（user_state.json），包含答题记录和统计数据
- 纯文件存储，无需数据库，轻量化，单用户场景够用

### 3.2 随机抽题算法
1. 根据筛选条件（领域、难度、错题）生成候选题目池
2. 从候选池中随机不放回抽取指定数量题目
3. 如果候选池大小 < 需要抽取数量，返回全部候选题目

### 3.3 统计更新
每次提交答案后，立即更新对应领域的统计数据：
- 尝试次数 +1
- 如果答对，正确次数 +1
- 掌握率 = 正确次数 / 尝试次数

### 3.4 CLI 交互流程
```
主菜单
├─ 1. 开始新练习
│  ├─ 选择领域（可多选）
│  ├─ 选择难度（可多选）
│  ├─ 输入题目数量
│  ├─ 开始答题（逐个显示题目，用户输入答案）
│  └─ 练习结束，显示本次练习结果
├─ 2. 复习错题
│  ├─ 获取所有错题
│  └─ 开始练习（流程同新练习，仅错题）
├─ 3. 查看统计
│  └─ 显示各领域掌握情况、总统计
├─ 4. 导入数据
│  ├─ 从JSON导入
│  └─ 从CSV导入
├─ 5. 导出数据
│  ├─ 导出错题
│  └─ 导出统计
└─ 6. 退出
```

## 4. 数据文件格式

### 4.1 JSON 知识库格式
```json
{
  "knowledge_points": [
    {
      "kp_id": "D1-001",
      "domain_id": 1,
      "name": "CIA三元组",
      "description": "信息安全的核心三个要素：保密性、完整性、可用性",
      "difficulty": 1,
      "tags": ["基础", "核心概念"]
    }
  ],
  "questions": [
    {
      "q_id": "Q1-0001",
      "kp_id": "D1-001",
      "question_type": 1,
      "stem": "以下哪个不属于CIA三元组？",
      "options": {
        "A": "保密性",
        "B": "完整性",
        "C": "可用性",
        "D": "可审计性"
      },
      "correct_answers": ["D"],
      "explanation": "CIA三元组是保密性(Confidentiality)、完整性(Integrity)、可用性(Availability)",
      "difficulty": 1
    }
  ]
}
```

### 4.2 CSV 题目导入格式
| Column | 说明 |
|--------|------|
| q_id | 题目ID |
| kp_id | 知识点ID |
| type | 1=单选, 2=多选 |
| stem | 题干 |
| option_A | 选项A |
| option_B | 选项B |
| option_C | 选项C |
| option_D | 选项D |
| answer | 正确答案（逗号分隔多个） |
| explanation | 解析 |
| difficulty | 难度 1-3 |

## 5. 错误处理

| 场景 | 处理方式 |
|------|----------|
| 数据文件不存在 | 提示用户，并创建空文件/目录 |
| JSON 解析错误 | 捕获异常，提示文件格式错误 |
| 无符合筛选条件的题目 | 返回空列表，提示用户调整筛选条件 |
| 用户输入格式错误 | 提示正确格式，让用户重新输入 |

