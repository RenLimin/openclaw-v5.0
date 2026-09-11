# CISSP CLI 命令参考

## 总览

```
cissp <command> [options]
```

所有命令都可以通过 `cissp <command> --help` 查看详细帮助。

---

## 命令列表

| 命令 | 说明 |
|------|------|
| [`plan`](#plan) | 生成/查看学习计划 |
| [`today`](#today) | 查看今日学习内容 |
| [`quiz`](#quiz) | 答题练习 |
| [`flashcard`](#flashcard) | 速记卡模式 |
| [`progress`](#progress) | 查看学习进度 |
| [`import`](#import) | 导入题库 |
| [`stats`](#stats) | 题库统计 |

---

## plan

生成或查看 CISSP 学习计划。

```bash
cissp plan [options]
```

### 选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-g, --generate` | flag | false | 生成新计划 |
| `--start` | string | 今天 | 开始日期 (YYYY-MM-DD) |
| `--weeks` | int | 16 | 总周数 |
| `--weekday-hours` | float | 1.0 | 工作日每日时长（小时） |
| `--weekend-hours` | float | 3.0 | 周末每日时长（小时） |
| `-w, --week` | int | 1 | 显示前 N 周（查看模式） |
| `--show-weeks` | int | 0 | 生成后显示前 N 周 |

### 示例

```bash
# 生成默认计划
cissp plan --generate

# 生成自定义计划并显示前 4 周
cissp plan --generate --start 2026-09-08 --weeks 12 --show-weeks 4

# 查看第 1 周
cissp plan

# 查看前 8 周
cissp plan --week 8
```

---

## today

查看今日（或指定日期）的学习内容。

```bash
cissp today [options]
```

### 选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--date` | string | 今天 | 指定日期 (YYYY-MM-DD) |

### 示例

```bash
# 今日内容
cissp today

# 指定日期
cissp today --date 2026-12-25
```

### 输出说明

- 日期和星期
- 计划学习时长
- 每个学习模块：
  - 域名称 / 主项名称
  - 分配时长
  - 核心考点列表（子项）
  - OSG 参考章节

---

## quiz

答题练习。

```bash
cissp quiz [options]
```

### 选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-n, --count` | int | 10 | 题目数量 |
| `-d, --domain` | int | 全部 | 指定域 ID (1-8) |
| `-e, --show-explanation` | flag | false | 总是显示解析（默认只在答错时显示） |

### 交互

- 输入 `A`/`B`/`C`/`D` 作答
- 输入 `Q` 退出
- 答错自动记录到错题本

### 示例

```bash
# 10 道随机题（全 8 域）
cissp quiz

# 20 道题，只考域 1（安全与风险管理）
cissp quiz --count 20 --domain 1

# 总是显示解析
cissp quiz --show-explanation
```

---

## flashcard

速记卡练习或导出。

```bash
cissp flashcard [options]
```

### 选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-n, --count` | int | 20 | 卡片数量 |
| `-d, --domain` | int | 全部 | 指定域 ID (1-8) |
| `--concepts-only` | flag | false | 仅概念卡（不含题目卡） |
| `--export` | flag | false | 导出模式（非交互） |
| `--export-format` | string | text | 导出格式: text / anki / json |
| `-o, --output` | string | stdout | 输出文件路径 |

### 示例

```bash
# 交互练习（20 张混合卡）
cissp flashcard

# 30 张概念卡，仅域 3
cissp flashcard --concepts-only --domain 3 --count 30

# 导出 Anki 格式
cissp flashcard --export --export-format anki -o my_cards.txt --count 50

# 导出 JSON
cissp flashcard --export --export-format json -o cards.json
```

---

## progress

查看学习进度。

```bash
cissp progress
```

### 输出

- 计划总天数 / 已完成天数
- 本周进度
- 错题总数
- 错题按域分布

### 示例

```bash
cissp progress
```

---

## import

导入题目到题库。

```bash
cissp import <file> [options]
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file` | string | JSON 文件路径（必填） |

### 选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--source` | string | imported | 来源标识 |

### 导入格式

```json
[
  {
    "question": "题干...",
    "options": {
      "A": "选项A",
      "B": "选项B",
      "C": "选项C",
      "D": "选项D"
    },
    "answer": "B",
    "explanation": "答案解析...",
    "domain": 1,
    "main_topic": "1.3"
  }
]
```

### 示例

```bash
# 导入新题目
cissp import new_questions.json --source "my-collection-2026"
```

---

## stats

查看题库统计信息。

```bash
cissp stats
```

### 输出

- 总题数
- 按域分布（带进度条）
- 按来源分布

### 示例

```bash
cissp stats
```

---

## 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 参数错误 / 文件不存在 |
| 2 | 运行时错误 |

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `CISSP_DATA_DIR` | 数据目录路径（默认：组件目录下 `data/`） |

> 环境变量支持暂未实现，当前使用相对路径。
