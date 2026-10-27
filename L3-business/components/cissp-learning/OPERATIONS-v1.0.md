# OPERATIONS: CISSP 知识点学习训练引擎 - v1.0

## 1. 环境要求

- Python 3.8 或更高版本
- 无强制第三方依赖，可选安装 `rich` 美化 CLI 输出

## 2. 安装/启动

### 2.1 克隆/获取代码
本组件位于 `L3-business/components/cissp-learning/`，直接使用即可。

### 2.2 可选安装依赖（美化输出）
```bash
pip install rich
```

### 2.3 准备数据
将你的知识库 JSON 文件放在 `data/` 目录下，示例文件名 `kb.json`。

可以使用示例数据：
```bash
cp data/sample_kb.json data/kb.json
```

### 2.4 启动程序
```bash
python cli.py
```

## 3. 使用指南

### 3.1 主菜单
启动后显示主菜单，输入对应数字选择功能：
```
=== CISSP 学习训练引擎 ===
1. 开始新练习
2. 复习错题
[!] 这里省略，实际运行会显示完整菜单
...
6. 退出
请选择:
```

### 3.2 开始新练习
1. 选择要练习的领域（输入编号，多个用逗号分隔，0=全选）
2. 选择难度范围（输入编号，多个用逗号分隔，0=全选）
3. 输入题目数量
4. 开始答题：逐个显示题目，输入选项字母（多选用逗号分隔）
5. 每道题答完后显示正确答案和解析
6. 练习结束后显示本次练习结果（答对/总题数、正确率）

### 3.3 复习错题
自动抽取所有错题开始练习，流程同新练习。

### 3.4 查看统计
显示各领域练习情况和掌握率，以及总统计。

示例输出：
```
=== 学习统计 ===
领域 1: 安全与风险管理: 答对 5/8 (62.5%)
领域 2: 资产安全: 答对 3/4 (75%)
...
总计: 答对 18/24 (75%)
```

### 3.5 导入数据

#### 3.5.1 从 JSON 导入
JSON 格式见 DESIGN-DETAIL-v1.0.md，使用：
```python
from importer import DataImporter
kp_list, q_list = DataImporter.from_json("path/to/data.json")
```

#### 3.5.2 从 CSV 批量导入
CSV 格式见 DESIGN-DETAIL-v1.0.md，使用：
```python
from importer import DataImporter
q_list = DataImporter.from_csv("path/to/questions.csv")
```

### 3.6 导出数据

#### 3.6.1 导出错题
```python
from exporter import DataExporter
DataExporter.to_csv(engine.get_wrong_questions(), "wrong_questions.csv")
```

或者在 CLI 菜单中选择导出功能。

#### 3.6.2 导出统计
```python
from exporter import DataExporter
stats = engine.get_statistics()
DataExporter.export_stats(stats, "stats.csv")
```

## 4. 文件结构

```
cissp-learning/
├── __init__.py
├── cissp_engine.py    # 核心引擎
├── models.py          # 数据模型
├── cli.py             # CLI 入口
├── importer.py        # 导入工具
├── exporter.py        # 导出工具
├── tests/             # 单元测试
├── data/              # 数据目录
│   └── sample_kb.json # 示例数据
├── PRD-v1.0.md
├── DESIGN-OUTLINE-v1.0.md
├── DESIGN-DETAIL-v1.0.md
├── VERIFICATION-v1.0.md
└── OPERATIONS-v1.0.md
```

## 5. 故障排查

### 5.1 提示"没有找到符合条件的题目"
**原因**：筛选条件太严格，没有符合条件的题目。
**解决**：放宽筛选条件，检查是否有该领域的题目。

### 5.2 导入 CSV 失败
**原因**：CSV 格式不对，缺少列或列名错误。
**解决**：对照 DESIGN-DETAIL 中的 CSV 格式检查表头和列，确保所有必填列都存在。

### 5.3 加载知识库失败
**原因**：JSON 格式错误，或者字段缺失。
**解决**：使用 JSON 格式化工具检查格式，对照示例 JSON 检查必填字段。

### 5.4 用户状态丢失
**原因**：异常退出没有保存，或者文件权限问题。
**解决**：确保程序通过菜单"退出"选项正常退出，检查目录写权限。默认状态文件保存在 `data/user_state.json`。

### 5.5 Python 版本太低，运行报错
**原因**：使用了 dataclass，Python < 3.7 不支持。
**解决**：升级 Python 到 3.8+。

## 6. FAQ

**Q: 可以添加更多题目吗？**
A: 可以，通过 CSV 或 JSON 批量导入即可。

**Q: 支持多用户吗？**
A: 当前版本不支持，单用户单数据文件。未来版本可能会支持。

**Q: 可以清除答题记录重新开始吗？**
A: 删除 `data/user_state.json` 文件即可重新开始。

**Q: 错题答对后还会出现在错题本里吗？**
A: 如果再次答错会重新加入，答对后就不会再出现在错题本中了。

**Q: 支持判断题吗？**
A: 当前版本只支持单选和多选，未来可以扩展支持。
