# 操作手册 OPERATIONS-v1.0

## 1. 依赖环境

### 系统要求
- macOS / Linux
- Python 3.10+

### Python 依赖
```
pip install sqlalchemy pyyaml pytest flask
```

| 包 | 最低版本 | 必需 | 说明 |
|----|----------|------|------|
| sqlalchemy | 2.0 | ✅ | ORM + 数据库连接 |
| pyyaml | 6.0 | ✅ | YAML 题库导入 |
| pytest | 7.0 | - | 运行测试 |
| flask | 2.0 | ⚠️ | 仅 Web UI 需要，CLI 不需要 |

## 2. 运行方式

### 初始化

```bash
cd /path/to/cissp-trainer

# 初始化数据库 + 导入样例题和知识图谱
PYTHONPATH=src python3 -m cissp_trainer.cli init --sample
```

### 设置别名（推荐）
```bash
alias cissp-trainer='cd /path/to/cissp-trainer && PYTHONPATH=src python3 -m cissp_trainer.cli'
```

### CLI 常用命令

| 模块 | 命令 | 说明 |
|------|------|------|
| 基础 | `cissp-trainer init --sample` | 初始化 + 导入样例 |
| 基础 | `cissp-trainer start -n 20` | 随机 20 题 |
| 基础 | `cissp-trainer start -d 1 -m review` | 域 1 到期复习 |
| 基础 | `cissp-trainer start -m weak` | 薄弱点强化 |
| 基础 | `cissp-trainer stats` | 学习统计 |
| 基础 | `cissp-trainer weak -n 15` | Top 15 薄弱知识点 |
| 基础 | `cissp-trainer import questions.yaml` | 导入题库 |
| 路径 | `cissp-trainer path list` | 列出所有学习路径 |
| 路径 | `cissp-trainer path start beginner` | 开始入门路径 |
| 路径 | `cissp-trainer path status` | 当前路径进度 |
| 路径 | `cissp-trainer path today` | 今日学习计划 |
| 路径 | `cissp-trainer path recommend` | 推荐路径 |
| 考试 | `cissp-trainer exam start` | 开始 100 题 3 小时模拟考 |
| 考试 | `cissp-trainer exam start -n 50 -t 120` | 50 题 2 小时 |
| 考试 | `cissp-trainer exam history` | 考试历史 |
| 考试 | `cissp-trainer exam detail <id>` | 考试详情 |
| 图谱 | `cissp-trainer knowledge graph 1` | 域 1 知识图谱（文本） |
| 图谱 | `cissp-trainer knowledge graph 1 --mermaid` | Mermaid 格式 |
| 图谱 | `cissp-trainer knowledge prereq "安全模型"` | 查询前置依赖 |
| 图谱 | `cissp-trainer knowledge next "CIA三元组"` | 推荐下一步 |
| 图谱 | `cissp-trainer knowledge impact "加密基础"` | 薄弱传播分析 |
| 图谱 | `cissp-trainer knowledge heatmap` | 掌握度热力图 |

### Web UI 运行方式

```bash
cd /path/to/cissp-trainer
# 默认端口 8888
PYTHONPATH=src python3 -m cissp_trainer.web.main
# 指定端口
PYTHONPATH=src python3 -m cissp_trainer.web.main --port 8000
```

然后打开浏览器访问 `http://localhost:8888`。

## 3. 常见问题排查

### Q: 提示 `ModuleNotFoundError: No module named 'cissp_trainer'`

**A:** 运行时需要设置 `PYTHONPATH=src`，确保 Python 能找到源码目录。参考上面初始化和别名设置。

### Q: 导入题库报错，提示格式错误

**A:** 检查题目 YAML/JSON 格式，必填字段：
- `id`: 题目 ID
- `domain`: 领域编号（1-8）
- `content`: 题目内容
- `options`: 选项字典
- `correct_answer`: 正确答案

`knowledge_points` 字段可选，用于关联知识点。

### Q: 学习路径无法开始，提示前置依赖未满足

**A:** 学习路径有前置依赖链：beginner → advanced → sprint。需要完成上一阶段才能解锁下一阶段。如果还没开始任何路径，推荐从 `beginner` 开始。

### Q: Web UI 无法访问，提示连接被拒绝

**A:** 检查：
1. Flask 是否已正确安装：`pip install flask`
2. 端口是否被占用：`lsof -i :8888`，换个端口启动
3. 防火墙是否阻止访问

### Q: 数据库损坏/数据错误，想重新初始化怎么办

**A:** 删除 `data/db/cissp_trainer.db` 文件，然后重新运行 `init --sample`。

### Q: 如何导入完整题库？

**A:** 当前版本只提供 52 道样例题。完整题库需要从 cissp-learning 迁移，后续版本会提供。你也可以自己按样例格式编写 YAML 题库导入。

### Q: 测试运行有一堆 DeprecationWarning 警告，有问题吗？

**A:** 警告只是提示 `datetime.utcnow()` 会在未来版本移除，不影响当前功能运行，不影响使用。后续版本会修复。
