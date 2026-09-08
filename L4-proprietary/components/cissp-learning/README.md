# CISSP 学习系统 (cissp-learning)

> L4 专有业务层组件 · 16 周 CISSP 备考结构化学习系统

## 功能概览

- **📅 学习规划引擎** — 基于 8 域权重生成 16 周日粒度计划，支持动态调整
- **📖 每日内容生成** — 自动输出当日学习内容大纲 + OSG 参考章节
- **📝 题库管理** — 554 道题，按域分类，模拟卷生成，错题管理
- **🗂 速记卡生成** — Q&A 格式 Flash Card，支持 Anki 导出
- **💻 CLI 封装** — 统一 `cissp` 命令，7 个子命令

## 快速开始

### 前置条件

- Python 3.10+
- （可选）python-docx / pypdf（题库导入用）

### 安装使用

```bash
cd L4-proprietary/components/cissp-learning

# 查看帮助
PYTHONPATH=src python3 -m cissp.cli --help

# 1. 生成学习计划（默认 16 周，从今天开始）
PYTHONPATH=src python3 -m cissp.cli plan --generate

# 指定开始日期 + 显示前 2 周
PYTHONPATH=src python3 -m cissp.cli plan --generate --start 2026-09-08 --show-weeks 2

# 2. 查看今日学习内容
PYTHONPATH=src python3 -m cissp.cli today

# 3. 答题练习（10 道题）
PYTHONPATH=src python3 -m cissp.cli quiz --count 10

# 指定域练习
PYTHONPATH=src python3 -m cissp.cli quiz --domain 1 --count 20

# 4. 速记卡练习
PYTHONPATH=src python3 -m cissp.cli flashcard --count 20

# 导出 Anki 格式
PYTHONPATH=src python3 -m cissp.cli flashcard --export --export-format anki -o cissp_cards.txt

# 5. 查看学习进度
PYTHONPATH=src python3 -m cissp.cli progress

# 6. 题库统计
PYTHONPATH=src python3 -m cissp.cli stats
```

### 设为命令别名（可选）

```bash
alias cissp='PYTHONPATH=/path/to/cissp-learning/src python3 -m cissp.cli'
```

## 目录结构

```
cissp-learning/
├── DESIGN.md              # 组件设计文档
├── README.md              # 本文件
├── SKILL.md               # OpenClaw 技能封装
├── src/
│   └── cissp/             # Python 包
│       ├── __init__.py
│       ├── planner.py     # 学习规划引擎
│       ├── daily_content.py  # 每日内容生成
│       ├── question_bank.py  # 题库管理
│       ├── flashcard.py   # 速记卡生成
│       └── cli.py         # CLI 入口
├── data/
│   ├── domains.json       # 8 域结构（CBK 2021）
│   ├── chapter_map.json   # 考点 → OSG 章节映射
│   ├── questions.json     # 题库（554 题）
│   ├── progress.json      # 进度存储
│   └── mistakes.json      # 错题本
└── docs/
    ├── USER_GUIDE.md      # 使用手册
    ├── CLI_REFERENCE.md   # CLI 命令参考
    └── DEVELOPMENT.md     # 开发说明
```

## 题库覆盖

| 域 | 名称 | 题数 |
|----|------|------|
| 1 | 安全与风险管理 | 42 |
| 2 | 资产安全 | 24 |
| 3 | 安全架构与工程 | 52 |
| 4 | 通信与网络安全 | 37 |
| 5 | 身份识别与访问管理 | 256 |
| 6 | 安全评估与测试 | 38 |
| 7 | 安全运营 | 86 |
| 8 | 软件开发安全 | 19 |
| **合计** | | **554** |

数据源：考前冲刺-解析版.docx（崔佳 CISSP 题库）

## 学习计划参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 总周数 | 16 周 | 可调整 |
| 工作日时长 | 1h/天 | 周一至周五 |
| 周末时长 | 3h/天 | 周六、周日 |
| 动态调整 | ✅ | 正确率 < 60% 的域追加 20% 复习时间 |

总学习时长约 **176 小时**（110 工作日 × 1h + 32 周末日 × 3h - 约 2 周缓冲）。

## 文档

- [DESIGN.md](./DESIGN.md) — 完整设计文档（架构/模块/数据流/扩展点）
- [docs/USER_GUIDE.md](./docs/USER_GUIDE.md) — 使用手册
- [docs/CLI_REFERENCE.md](./docs/CLI_REFERENCE.md) — CLI 命令参考
- [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) — 开发说明

## 架构层级

```
L4 专有业务层
└── cissp-learning (本组件)  ← 你在这里
    ├─ 依赖 L3: security-engineering 知识库维度
    └─ 依赖 L2: 标准库 JSON 持久化（简化实现）
```

## License

内部使用，版权归属 Rex / 梆梆安全。
