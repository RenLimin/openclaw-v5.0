# CISSP 学习系统 — 组件设计文档 (CISSP-L4-001)

> L4 专有业务层组件，面向 Rex 的 CISSP 备考需求。
> 定位：结构化备考系统 = 学习规划 + 每日内容 + 题库练习 + 速记卡 + CLI

---

## 1. 组件定位

### 1.1 业务目标

为 CISSP CBK 8 域备考提供端到端结构化学习系统，覆盖 16 周学习周期的全流程：
从学习规划 → 每日内容生成 → 题库练习 → 错题管理 → 速记复习 → 进度追踪。

### 1.2 层级归属

| 层级 | 组件 | 说明 |
|------|------|------|
| **L4** | `cissp-learning` (本组件) | 业务逻辑层：规划引擎、内容生成、题库管理、速记卡、CLI |
| **L3** | `security-engineering` 知识库维度 | 知识层：CISSP CBK 8 域知识（待建设） |
| **L2** | `memory-embedding` (间接) | 知识库检索能力（通过 L3 调用） |
| **L2** | 标准库 JSON 持久化 | 数据存储（不直接依赖 L2 persistence 组件，降低耦合） |

**分层原则**：L4 只依赖 L3 知识维度和 L2 基础能力，不反向依赖。

### 1.3 与 L3 的关系

```
L3 security-engineering 维度
  └─ CISSP CBK 8 域知识库 (Markdown + frontmatter)
      ↓ 知识供给
L4 cissp-learning 组件
  ├─ planner.py          ← 调用域结构做规划
  ├─ daily_content.py    ← 调用知识库生成每日内容
  ├─ question_bank.py    ← 题库独立管理
  ├─ flashcard.py        ← 从知识库/题库生成速记卡
  └─ cli.py              ← 用户交互入口
```

---

## 2. 架构图

```
┌──────────────────────────────────────────────────────┐
│                   CLI 入口 (cli.py)                   │
│  plan / today / quiz / flashcard / progress / stats  │
└──────────────┬───────────┬───────────┬───────────────┘
               │           │           │
    ┌──────────▼──┐  ┌────▼─────┐  ┌──▼──────────┐
    │  学习规划引擎│  │ 每日内容 │  │  题库管理器  │
    │ planner.py  │  │ 生成器   │  │question_bank│
    └──────┬──────┘  │daily_cont│  └──────┬──────┘
           │         │  ent.py  │         │
           │         └─────┬────┘  ┌──────▼──────┐
           │               │       │  错题本      │
           │               │       │mistakes.json │
    ┌──────▼──────┐        │       └─────────────┘
    │ 进度存储     │        │
    │progress.json│        │
    └─────────────┘        │
                    ┌──────▼──────┐
                    │  速记卡生成  │
                    │ flashcard.py│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ 数据层       │
                    │ domains.json │
                    │ questions.json│
                    │ chapter_map. │
                    │     json     │
                    └──────────────┘
```

---

## 3. 核心模块

### 3.1 学习规划引擎 (planner.py)

**职责**：根据 8 域权重 + 每日可用时长 + 开始日期，生成 16 周日粒度学习计划。

**输入**：
- 8 域权重（来自 domains.json）
- 开始日期（默认今天）
- 工作日/周末每日时长（默认 1h / 3h）
- 总周数（默认 16）

**输出**：
- 16 周 × 7 天的日计划
- 每天：学习域、主项、分配时长
- 存储到 progress.json

**核心算法**：
1. 计算总学习时长（按工作日/周末加权）
2. 按权重分配到 8 个域
3. 域内按主项数均分
4. 逐日填充队列（按域顺序）
5. **动态调整**：某域正确率 < 60% 时追加 20% 复习时间

**扩展点**：节假日识别、多轮复习循环、个性化节奏调整。

### 3.2 每日内容生成器 (daily_content.py)

**职责**：根据当日计划，输出结构化的学习内容大纲。

**功能**：
- 列出当日所有主项及核心考点（子项）
- 关联 OSG 参考章节（来自 chapter_map.json）
- 建议学习顺序

### 3.3 题库管理器 (question_bank.py)

**职责**：题库 CRUD、模拟卷生成、错题管理。

**数据模型**：
```json
{
  "id": "preexam-1",
  "question": "题干...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "B",
  "explanation": "解析...",
  "source": "考前冲刺-解析版.docx",
  "domain": 1,
  "main_topic": "1.1"
}
```

**功能**：
- 从 JSON 导入题目（可扩展 Excel/Docx）
- 按域/主项筛选
- 按权重生成模拟卷
- 错题记录 + 统计
- 答题练习（CLI 交互）

### 3.4 速记卡生成器 (flashcard.py)

**职责**：生成 Q&A 格式速记卡，支持多种输出。

**卡片类型**：
- **概念卡**：从 8 域考点结构自动生成（子项 → Q&A）
- **题目卡**：从题库抽取（题干 = 正面，答案+解析 = 反面）

**输出格式**：
- Text（CLI 打印）
- Anki TSV（导入 Anki）
- JSON

**交互**：CLI 自测模式（y/n 反馈）。

### 3.5 CLI 封装 (cli.py)

**入口**：`python -m cissp.cli <command>`

| 子命令 | 功能 |
|--------|------|
| `plan` | 生成/查看学习计划 |
| `today` | 查看今日学习内容 |
| `quiz` | 答题练习 |
| `flashcard` | 速记卡模式 |
| `progress` | 查看学习进度 |
| `import` | 导入题库 |
| `stats` | 题库统计 |

---

## 4. 数据流

```
domains.json ──┐
chapter_map.json ───→ daily_content.py ──→ 每日内容大纲 (stdout / md)
               │
               ├──→ planner.py ──→ progress.json (plan_days)
               │
questions.json ├──→ question_bank.py ──→ quiz (CLI交互)
               │                    ├──→ mistakes.json
               │                    └──→ 模拟卷输出
               │
               └──→ flashcard.py ──→ 速记卡 (text / anki / json)

progress.json ──→ planner.py (动态调整输入)
mistakes.json ──→ question_bank.py (错题练习)
```

---

## 5. 数据结构

### 5.1 目录结构

```
cissp-learning/
├── DESIGN.md              # 本文件
├── README.md              # 快速开始
├── SKILL.md               # OpenClaw 技能封装
├── src/
│   └── cissp/             # Python 包
│       ├── __init__.py
│       ├── planner.py
│       ├── daily_content.py
│       ├── question_bank.py
│       ├── flashcard.py
│       └── cli.py
├── data/
│   ├── domains.json       # 8 域结构
│   ├── chapter_map.json   # 考点-章节映射
│   ├── questions.json     # 题库
│   ├── progress.json      # 进度 + 计划
│   └── mistakes.json      # 错题本
└── docs/
    ├── USER_GUIDE.md      # 使用手册
    ├── CLI_REFERENCE.md   # CLI 命令参考
    └── DEVELOPMENT.md     # 开发说明
```

### 5.2 关键文件格式

- **domains.json**：8 域 → 62 主项 → 274 子项（CBK 2021 版）
- **chapter_map.json**：275 条考点 → OSG 章节映射
- **questions.json**：题库数组，每题 8 个字段
- **progress.json**：计划 + 每日日志 + 域进度 + 总体统计
- **mistakes.json**：错题列表 + 按域/主项统计

---

## 6. 扩展点

### 6.1 可扩展方向

| 扩展 | 优先级 | 说明 |
|------|--------|------|
| L3 知识库集成 | 高 | 从 security-engineering 维度的 Markdown 文档生成每日精读内容 |
| 节假日识别 | 中 | 接入中国法定节假日 API，自动调增学习量 |
| Spaced Repetition | 中 | 基于艾宾浩斯遗忘曲线调整复习计划 |
| 多数据源导入 | 中 | 支持 Excel/PDF 直接导入题目 |
| 学习报告 | 低 | 周/月度学习报告生成 |
| Web UI | 低 | 简单 Web 界面（FastAPI + 前端） |
| Anki 同步 | 低 | 直接同步到 Anki 桌面端 |

### 6.2 与 L3 security-engineering 的集成方案

当前阶段：L4 组件独立运行，数据来自 `data/` 目录下的 JSON 文件。

未来集成：
1. L3 建设完成后，`daily_content.py` 可直接从知识库检索对应考点的详细内容
2. `flashcard.py` 可从知识库文档生成更高质量的速记卡
3. 知识库的 frontmatter 元数据（domain/main_topic/difficulty）可用于智能出题

---

## 7. 约束与边界

### 7.1 不做的事

- 不直接对外发送消息/通知（由 L3 或上层调度）
- 不管理用户认证/多用户（单用户系统）
- 不做全文知识库检索（依赖 L3）
- 不做图形界面（CLI 优先）

### 7.2 依赖

- Python 3.10+ 标准库
- python-docx（题库导入，可选）
- pypdf / PyPDF2（PDF 题库导入，可选）

---

## 8. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1.0 | 2026-09-08 | 初版：规划引擎 + 题库 + 速记卡 + CLI |
