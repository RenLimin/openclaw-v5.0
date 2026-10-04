# OPERATIONS-v1.0.md — 收入确认自动化模块

## 1. 依赖环境

### Python 依赖
- Python 3.10+
- openpyxl >= 3.1.0
- pytest >= 7.0.0

### 系统依赖
- macOS / Linux 均可，无特殊系统依赖

## 2. 安装依赖

```bash
cd L4-proprietary/components/revenue-recognition
pip install openpyxl pytest
```

## 3. 运行方式

### 前置准备
- 将手工确收报表放置到 `reference/` 目录，修改 `config.py` 中 `MANUAL_REPORT_PATH` 为对应路径。
- 根据报表结构，修改 `BudgetCol` / `PlanCol` / Sheet 名称等配置。

### CLI 入口

执行完整流程（初始化 → 导入 → 计算 → 导出 → 验证）：
```bash
cd L4-proprietary/components/revenue-recognition
python3 -m revenue_recognition.v1.main
```

### 运行测试

```bash
cd L4-proprietary/components/revenue-recognition
python3 -m pytest src/ -v
```

### 输出位置
- 数据库：`src/data/revenue.db`
- 自动化报表：`output/确收自动化报表_{period}.xlsx`

## 4. 常见问题排查

### Q1: 导入时报错 "Workbook contains no worksheets by that name"

**原因**: `config.py` 中 Sheet 名称与实际 Excel 中 Sheet 名称不匹配。
**解决方案**: 检查 Excel 中实际 Sheet 名称，更新 `config.py` 中对应 Sheet 常量。

---

### Q2: 结果验证不通过，大量差异

**原因1**: 列映射配置错误，读取了错误的列。
**解决方案**: 检查 `BudgetCol` / `PlanCol` 列号是否匹配实际 Excel，更新配置。

**原因2**: 报表结构变化，配置未更新。
**解决方案**: 更新 `config.py` 中列映射和 Sheet 名称，必要时升级版本到 v2。

---

### Q3: 运行时报 "No such file or directory"

**原因**: 手工报表路径错误。
**解决方案**: 修改 `config.py` 中 `MANUAL_REPORT_PATH` 为正确路径。

---

### Q4: 数据库损坏如何恢复？

**解决方案**: 删除 `src/data/revenue.db`，重新运行 main 脚本，会自动重新初始化数据库。

---

### Q5: 数值比较有差异，但是实际是对的？

**原因**: 浮点精度问题。
**解决方案**: 当前容差是 0.01，可在 `validator.py` `_values_equal` 中调整 `tolerance` 参数。
