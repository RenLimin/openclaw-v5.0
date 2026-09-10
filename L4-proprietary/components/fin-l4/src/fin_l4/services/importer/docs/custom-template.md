# 自定义银行模板指南

添加新的银行格式只需创建一个 YAML 文件，无需修改代码。

## 模板位置

```
services/importer/bank_templates/<bank_id>.yaml
```

## 模板结构

```yaml
bank_id: my_bank           # 唯一标识（与文件名一致）
bank_name: 某某银行        # 显示名称
format: csv                # csv / excel
default_encoding: utf-8    # 默认编码（CSV 用）
skip_rows: 0               # 跳过的头部行数

# 列名映射：目标字段 -> 源列名
column_mapping:
  date: 交易日期           # 交易日期列名
  time: 交易时间           # 交易时间列名（可选）
  datetime: 交易时间       # 合并的日期时间列（替代 date+time，可选）
  amount: 金额             # 金额列
  counterparty: 对方户名   # 对方名称
  description: 摘要        # 摘要/备注
  balance: 余额            # 交易后余额（可选）
  currency: 币种           # 币种（可选，默认 CNY）

# 金额方向判断
direction_rules:
  type: separate_columns   # separate_columns / direction_column / amount_sign
  income_column: 收入金额  # separate_columns 用
  expense_column: 支出金额
  # direction_column 模式：
  # direction_column: 收支
  # income_value: 收入
  # expense_value: 支出
  # amount_sign 模式：金额正负号判断

# 自动检测：header 中出现多少个关键字就匹配
detection:
  keywords:
    - 交易日期
    - 收入金额
    - 支出金额
    - 对方户名
  min_match: 3             # 至少匹配几个关键字
```

## 方向规则三种模式

### 1. 收支分列（separate_columns）
收入和支出在两列，一列有值另一列为空/0。

```yaml
direction_rules:
  type: separate_columns
  income_column: 收入金额
  expense_column: 支出金额
```

### 2. 收支方向列（direction_column）
有一列明确写"收入"/"支出"。

```yaml
direction_rules:
  type: direction_column
  direction_column: 收支
  income_value: 收入
  expense_value: 支出
```

### 3. 金额正负号（amount_sign）
金额列本身带正负号，正数收入负数支出（或反过来）。

```yaml
direction_rules:
  type: amount_sign
  amount_column: 交易金额
  positive_is_income: true    # 正数 = 收入
```

## 添加步骤

1. 在 `bank_templates/` 目录新建 `<bank_id>.yaml`
2. 按上述结构填写模板
3. 保存即可 — 系统启动时自动扫描加载
4. 验证：`finctl rules banks` 应该能看到新银行

## 完整示例：某地方银行

```yaml
bank_id: local_bank
bank_name: 某某地方银行
format: csv
default_encoding: gbk
skip_rows: 1

column_mapping:
  date: 交易日期
  time: 交易时间
  amount: 交易金额
  counterparty: 对方账户名称
  description: 交易摘要
  balance: 账户余额
  currency: 币种

direction_rules:
  type: direction_column
  direction_column: 借贷标志
  income_value: 贷
  expense_value: 借

detection:
  keywords:
    - 交易日期
    - 交易金额
    - 借贷标志
    - 对方账户名称
  min_match: 3
```
