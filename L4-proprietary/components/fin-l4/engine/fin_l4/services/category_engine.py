"""智能分类引擎 — 基于关键词匹配 + 规则优先级"""

from typing import Optional, Dict, List
from dataclasses import dataclass, field


@dataclass
class CategoryRule:
    """分类规则"""
    id: str
    category_id: str
    keywords: List[str]
    priority: int = 0  # 越大越优先
    min_amount: Optional[str] = None
    max_amount: Optional[str] = None


class CategoryEngine:
    """智能分类引擎"""

    def __init__(self):
        self._rules: List[CategoryRule] = []
        self._default_category: Optional[str] = None

    def set_default(self, category_id: str):
        """设置默认分类"""
        self._default_category = category_id

    def add_rule(self, rule: CategoryRule):
        """添加分类规则"""
        self._rules.append(rule)
        # 按优先级排序（高优先在前）
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def classify(self, description: str, amount: str = None) -> Optional[str]:
        """
        根据描述和金额自动分类
        返回 category_id 或 None
        """
        from decimal import Decimal

        amt = Decimal(amount) if amount else None

        for rule in self._rules:
            # 金额范围过滤
            if rule.min_amount and amt is not None:
                if amt < Decimal(rule.min_amount):
                    continue
            if rule.max_amount and amt is not None:
                if amt > Decimal(rule.max_amount):
                    continue

            # 关键词匹配
            desc_lower = description.lower()
            for kw in rule.keywords:
                if kw.lower() in desc_lower:
                    return rule.category_id

        return self._default_category

    def list_rules(self) -> List[Dict]:
        """列出所有规则"""
        return [
            {
                "id": r.id,
                "category_id": r.category_id,
                "keywords": r.keywords,
                "priority": r.priority,
            }
            for r in self._rules
        ]

    @staticmethod
    def default_rules() -> 'CategoryEngine':
        """创建默认分类规则集"""
        engine = CategoryEngine()

        # 收入类
        engine.add_rule(CategoryRule(
            id="rule_salary", category_id="cat_salary",
            keywords=["工资", "薪资", "salary", "奖金", "分红", "报销"],
            priority=10,
        ))
        engine.add_rule(CategoryRule(
            id="rule_investment_income", category_id="cat_invest_income",
            keywords=["利息", "股息", "理财收益", "基金收益", "dividend", "interest"],
            priority=10,
        ))

        # 餐饮
        engine.add_rule(CategoryRule(
            id="rule_food", category_id="cat_food",
            keywords=["餐", "饭", "面", "粉", "咖啡", "奶茶", "外卖",
                      "restaurant", "food", "lunch", "dinner", "breakfast"],
            priority=5,
        ))

        # 交通
        engine.add_rule(CategoryRule(
            id="rule_transport", category_id="cat_transport",
            keywords=["地铁", "公交", "打车", "滴滴", "uber", "加油", "停车",
                      "transport", "subway", "taxi"],
            priority=5,
        ))

        # 购物
        engine.add_rule(CategoryRule(
            id="rule_shopping", category_id="cat_shopping",
            keywords=["淘宝", "京东", "天猫", "拼多多", "amazon", "购物",
                      "shopping", "taobao", "jd"],
            priority=5,
        ))

        # 住房
        engine.add_rule(CategoryRule(
            id="rule_housing", category_id="cat_housing",
            keywords=["房租", "房贷", "物业", "水电", "燃气", "rent", "housing"],
            priority=8,
        ))

        # 医疗
        engine.add_rule(CategoryRule(
            id="rule_medical", category_id="cat_medical",
            keywords=["医院", "药", "诊所", "medical", "hospital", "pharmacy"],
            priority=8,
        ))

        # 教育
        engine.add_rule(CategoryRule(
            id="rule_education", category_id="cat_education",
            keywords=["学费", "培训", "课程", "书", "education", "course", "book"],
            priority=5,
        ))

        # 娱乐
        engine.add_rule(CategoryRule(
            id="rule_entertainment", category_id="cat_entertainment",
            keywords=["电影", "游戏", "ktv", "旅游", "旅行", "movie", "game",
                      "travel", "entertainment"],
            priority=3,
        ))

        # 保险
        engine.add_rule(CategoryRule(
            id="rule_insurance", category_id="cat_insurance",
            keywords=["保险", "保费", "insurance", "premium"],
            priority=8,
        ))

        # 通讯
        engine.add_rule(CategoryRule(
            id="rule_telecom", category_id="cat_telecom",
            keywords=["话费", "流量", "宽带", "mobile", "phone", "telecom"],
            priority=5,
        ))

        engine.set_default("cat_other")
        return engine
