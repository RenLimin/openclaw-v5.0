# CISSP 学习系统 — 使用手册

## 目录

1. [快速开始](#快速开始)
2. [学习计划](#学习计划)
3. [每日学习](#每日学习)
4. [题库练习](#题库练习)
5. [速记卡](#速记卡)
6. [进度追踪](#进度追踪)
7. [常见问题](#常见问题)

---

## 快速开始

### 环境要求

- Python 3.10 或更高
- 不需要安装额外依赖（标准库即可运行）

### 基本命令

```bash
# 进入组件目录
cd L4-proprietary/components/cissp-learning

# 设置路径别名（推荐）
alias cissp='PYTHONPATH=src python3 -m cissp.cli'

# 查看所有命令
cissp --help
```

---

## 学习计划

### 生成新计划

```bash
# 使用默认参数生成（从今天开始，16 周，工作日 1h，周末 3h）
cissp plan --generate

# 指定开始日期
cissp plan --generate --start 2026-09-08

# 自定义时长和周数
cissp plan --generate --weeks 12 --weekday-hours 1.5 --weekend-hours 4
```

### 查看计划

```bash
# 查看第 1 周（默认）
cissp plan

# 查看前 4 周
cissp plan --week 4
```

### 计划说明

- 计划按 **域权重** 分配学习时间，权重高的域分配更多时间
- 工作日每天学 1 个主项，周末可学 2-3 个主项
- 学习顺序：域 1 → 域 2 → ... → 域 8（按 CBK 顺序推进）
- **动态调整**：如果某域做题正确率 < 60%，重新生成计划时该域会追加 20% 复习时间

---

## 每日学习

### 查看今日内容

```bash
cissp today
```

输出包含：
- 今日日期和星期
- 计划学习时长
- 每个学习模块的：
  - 所属域和主项名称
  - 核心考点列表（子项）
  - OSG 参考章节

### 指定日期查看

```bash
cissp today --date 2026-09-15
```

---

## 题库练习

### 快速练习

```bash
# 10 道随机题（默认）
cissp quiz

# 指定数量和域
cissp quiz --count 20 --domain 3
```

### 练习技巧

- 输入 `A/B/C/D` 作答
- 输入 `q` 退出
- 答错的题会自动记录到错题本
- 用 `--show-explanation` 总是显示解析（默认只在答错时显示）

### 题库统计

```bash
cissp stats
```

查看总题数、按域分布、按来源分布。

### 导入新题目

```bash
cissp import my_questions.json --source "custom-2026"
```

导入的 JSON 格式：

```json
[
  {
    "question": "题干...",
    "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "answer": "A",
    "explanation": "解析...",
    "domain": 1,
    "main_topic": "1.1"
  }
]
```

---

## 速记卡

### 交互练习

```bash
# 20 张混合卡（概念 + 题目）
cissp flashcard

# 指定域和数量
cissp flashcard --domain 1 --count 30

# 仅概念卡（从考点结构生成）
cissp flashcard --concepts-only --domain 2
```

操作方式：
- 回车显示答案
- 输入 `y` 表示记住了
- 输入 `n` 表示没记住
- 输入 `q` 退出

### 导出速记卡

```bash
# 文本格式
cissp flashcard --export --export-format text -o cards.txt

# Anki 导入格式（TSV）
cissp flashcard --export --export-format anki -o anki_cards.txt

# JSON 格式
cissp flashcard --export --export-format json -o cards.json
```

**Anki 导入方法**：
1. 打开 Anki → 文件 → 导入
2. 选择导出的 TSV 文件
3. 字段分隔符：Tab
4. 允许 HTML：勾选
5. 选择目标牌组 → 导入

---

## 进度追踪

### 查看进度

```bash
cissp progress
```

显示：
- 总计划天数 / 已完成天数
- 本周进度
- 错题总数和按域分布

### 标记完成

> 目前进度需要手动更新 `data/progress.json`，自动标记功能将在后续版本加入。

手动标记某日完成：编辑 `data/progress.json`，在 `plan_days` 中找到对应日期，设置 `"completed": true`。

---

## 常见问题

### Q1：如何重新生成计划？

```bash
cissp plan --generate
```

注意：重新生成会覆盖原有计划进度。建议在学习周开始前生成，或在需要调整时生成。

### Q2：错题本在哪里？

`data/mistakes.json`，可以直接查看或编辑。

### Q3：可以从 PDF 导入题目吗？

目前支持 JSON 格式导入。PDF 导入需要额外解析脚本，可参考 `考前冲刺-解析版.docx` 的解析逻辑自行扩展。

### Q4：学习时长不够怎么办？

调整计划参数，例如：

```bash
# 每天学 1.5 小时，周末 4 小时
cissp plan --generate --weekday-hours 1.5 --weekend-hours 4
```

### Q5：8 个域的权重可以改吗？

可以，修改 `data/domains.json` 中每个域的 `weight` 字段，总权重不需要等于 100（会自动归一化）。

---

## 数据文件位置

| 文件 | 说明 |
|------|------|
| `data/domains.json` | 8 域结构（CBK 2021） |
| `data/questions.json` | 题库 |
| `data/progress.json` | 学习计划 + 进度 |
| `data/mistakes.json` | 错题本 |
| `data/chapter_map.json` | 考点 → OSG 章节映射 |

⚠️ **备份建议**：定期备份 `progress.json` 和 `mistakes.json`，避免数据丢失。
