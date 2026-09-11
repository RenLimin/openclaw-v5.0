---
name: cissp-learning
description: "CISSP 备考学习系统：16 周学习规划 + 每日内容生成 + 题库练习 + 速记卡 + 进度追踪。覆盖 CBK 8 域 554 道题。"
user-invocable: true
---

# CISSP 学习系统 (CISSP-L4-001)

> L4 专有业务层组件，面向 CISSP 备考的结构化学习系统。

## When to Use

- 用户需要制定/查看 CISSP 学习计划
- 用户需要今日学习内容安排
- 用户想做 CISSP 练习题/模拟卷
- 用户需要速记卡背诵核心考点
- 用户想查看学习进度/错题本
- 用户要导入新的题目或知识点

## Hard Rules

1. **学习计划默认 16 周**：工作日 1h/天，周末 3h/天，可自定义
2. **题库分类按 CBK 8 域**：domain 参数为 1-8 的整数
3. **错题自动记录**：答错的题自动进入错题本，不可手动删除（用 reset 命令清空）
4. **动态调整规则**：某域正确率 < 60% 时，计划中该域自动追加 20% 复习时间
5. **周末学习量 3 倍于工作日**：周六日默认 3h，工作日 1h
6. **数据持久化到 JSON 文件**：位于 `data/` 目录，不依赖数据库
7. **题目来源标注**：每题必须带 source 字段，便于溯源

## 组件路径

```
L4-proprietary/components/cissp-learning/
├── src/cissp/          # Python 源码
├── data/               # 数据文件
├── docs/               # 文档
├── DESIGN.md           # 设计文档
└── SKILL.md            # 本文件
```

## 快速调用

```bash
# 生成学习计划
python L4-proprietary/components/cissp-learning/src/cissp/cli.py plan --generate --start 2026-09-08

# 今日学习内容
python L4-proprietary/components/cissp-learning/src/cissp/cli.py today

# 答题练习（10 题）
python L4-proprietary/components/cissp-learning/src/cissp/cli.py quiz --count 10

# 按域练习
python L4-proprietary/components/cissp-learning/src/cissp/cli.py quiz --domain 1 --count 20

# 速记卡
python L4-proprietary/components/cissp-learning/src/cissp/cli.py flashcard --count 20

# 学习进度
python L4-proprietary/components/cissp-learning/src/cissp/cli.py progress

# 题库统计
python L4-proprietary/components/cissp-learning/src/cissp/cli.py stats
```

## Python API 调用

```python
import sys
sys.path.insert(0, "L4-proprietary/components/cissp-learning/src")

from cissp.planner import generate_plan, save_plan
from cissp.question_bank import generate_quiz, get_stats
from cissp.flashcard import generate_flashcards, format_flashcards
from cissp.daily_content import get_today_content

# 生成计划
plan = generate_plan(start_date="2026-09-08", weeks=16)

# 出 10 道题
questions = generate_quiz(count=10, domain=1)

# 生成速记卡
cards = generate_flashcards(domain_id=3, count=20)
print(format_flashcards(cards))

# 今日内容
content = get_today_content()
```

## 8 域对照

| ID | 名称 | 权重 |
|----|------|------|
| 1 | 安全与风险管理 | 15% |
| 2 | 资产安全 | 10% |
| 3 | 安全架构与工程 | 13% |
| 4 | 通信与网络安全 | 13% |
| 5 | 身份识别与访问管理 | 13% |
| 6 | 安全评估与测试 | 12% |
| 7 | 安全运营 | 13% |
| 8 | 软件开发安全 | 11% |

## 相关文件

- 设计文档：`DESIGN.md`
- 使用手册：`docs/USER_GUIDE.md`
- CLI 参考：`docs/CLI_REFERENCE.md`
- 开发说明：`docs/DEVELOPMENT.md`
