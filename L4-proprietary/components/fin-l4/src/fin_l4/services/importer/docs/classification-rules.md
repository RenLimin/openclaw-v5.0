# 分类规则编写指南

FIN-L4 使用基于规则的分类引擎，规则以 YAML 配置，支持优先级、置信度分级、条件组合。

## 规则结构

```yaml
- id: rule_unique_id          # 规则唯一 ID
  name: 规则显示名称           # 人类可读名称
  category_id: cat_food        # 匹配到后分配的分类 ID
  priority: 80                 # 优先级（数字越大越先匹配）
  confidence_level: high       # high / medium / low
  conditions:
    # 条件列表，全部满足才触发
    - type: keywords_in
      field: counterparty      # counterparty / description / all
      keywords:                # 命中任意一个关键字即满足
        - 咖啡
        - 奶茶
        - 星巴克
    - type: direction
      value: expense           # expense / income
    - type: amount_range
      min: 1
      max: 10000
```

## 条件类型

### keywords_in — 关键字匹配
在指定字段中搜索关键字，任意一个命中即满足。

```yaml
- type: keywords_in
  field: description           # counterparty / description / all
  keywords:
    - 工资
    - 薪资
    - 代发
```

**字段说明：**
- `counterparty` — 对方户名/交易对方
- `description` — 摘要/商品名称/备注
- `all` — 所有文本字段一起搜

### direction — 收支方向
限定收入或支出。

```yaml
- type: direction
  value: expense               # expense / income
```

### amount_range — 金额范围
限定金额区间（可选）。

```yaml
- type: amount_range
  min: 5000                    # 最小金额（含）
  max: 200000                  # 最大金额（含）
```

## 置信度等级

| 等级 | 说明 | 建议场景 |
|------|------|----------|
| `high` | 非常确定，自动确认 | 强关键字 + 正确方向 + 合理金额 |
| `medium` | 比较确定，建议确认 | 关键字匹配但金额异常或方向不明确 |
| `low` | 不确定，必须人工确认 | 弱匹配、模糊关键字 |

## 优先级

数字越大优先级越高。默认规则优先级参考：

| 优先级 | 用途 |
|--------|------|
| 100 | 工资等极强特征 |
| 90 | 房租/医疗/保险等强特征 |
| 80 | 餐饮/交通/购物等日常消费 |
| 60 | 中等置信度规则 |
| 40 | 弱匹配规则 |
| 10 | 默认兜底规则 |

## 自定义规则

### 通过 CLI 添加

```bash
# 添加一条简单规则（关键字匹配对方户名）
finctl rules add \
  --name "网购" \
  --keywords "淘宝,天猫,京东,拼多多" \
  --category cat_shopping \
  --field counterparty \
  --direction expense \
  --confidence high
```

### 通过 YAML 文件添加

在 `classification_rules/` 目录新建 `my_rules.yaml`，按上述格式编写。

### 通过 Web UI 添加

访问 `/rules` 页面，在"用户规则"部分点击"添加规则"。

## 反馈学习

系统支持用户反馈学习。当用户修改了某条交易的分类后，系统会记录该商家（+摘要）对应的正确分类。多次反馈后，系统会在分类时优先使用反馈建议。

反馈学习不修改规则文件，而是存储在 `fin4_category_feedback` 表中。

## 分类流程

```
输入交易
    ↓
1. 检查用户反馈建议（最高优先级）
    ↓
2. 按优先级从高到低匹配规则
    ├── 第一个完全匹配的规则胜出
    └── 根据规则 confidence_level 给出置信度
    ↓
3. 无匹配 → 使用默认分类（cat_other / low 置信度）
    ↓
输出分类结果（category_id + confidence + matched_rule）
```
