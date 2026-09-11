"""智能分类引擎测试 — 关键词匹配、优先级、金额过滤"""

import pytest
import importlib.util
from pathlib import Path

# 直接加载 category_engine.py（避开 services/__init__.py 的 import 错误）
_engine_path = Path(__file__).resolve().parent.parent / "services" / "category_engine.py"
_spec = importlib.util.spec_from_file_location("category_engine_mod", str(_engine_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CategoryEngine = _mod.CategoryEngine
CategoryRule = _mod.CategoryRule


class TestCategoryEngineBasic:
    """基础分类功能"""

    def test_classify_salary(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("工资收入")
        assert result == "cat_salary"

    def test_classify_food(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("午餐外卖")
        assert result == "cat_food"

    def test_classify_transport(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("地铁通勤")
        assert result == "cat_transport"

    def test_classify_shopping(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("淘宝购物")
        assert result == "cat_shopping"

    def test_classify_housing(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("房租")
        assert result == "cat_housing"

    def test_classify_medical(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("医院挂号")
        assert result == "cat_medical"

    def test_classify_education(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("培训课程")
        assert result == "cat_education"

    def test_classify_entertainment(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("电影票")
        assert result == "cat_entertainment"

    def test_classify_insurance(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("保费缴纳")
        assert result == "cat_insurance"

    def test_classify_telecom(self):
        engine = CategoryEngine.default_rules()
        result = engine.classify("话费充值")
        assert result == "cat_telecom"

    def test_classify_default(self):
        """未匹配到任何规则时返回默认分类"""
        engine = CategoryEngine.default_rules()
        result = engine.classify("xyzabc123不存在的描述")
        assert result == "cat_other"

    def test_classify_english(self):
        """英文关键词匹配"""
        engine = CategoryEngine.default_rules()
        result = engine.classify("Uber ride")
        assert result == "cat_transport"


class TestCategoryEnginePriority:
    """优先级测试"""

    def test_priority_order(self):
        """高优先级规则先匹配"""
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(
            id="low", category_id="cat_low",
            keywords=["测试"], priority=1,
        ))
        engine.add_rule(CategoryRule(
            id="high", category_id="cat_high",
            keywords=["测试"], priority=10,
        ))
        result = engine.classify("测试描述")
        assert result == "cat_high"

    def test_list_rules_sorted(self):
        """规则按优先级排序"""
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(id="r1", category_id="c1", keywords=["a"], priority=1))
        engine.add_rule(CategoryRule(id="r2", category_id="c2", keywords=["b"], priority=10))
        engine.add_rule(CategoryRule(id="r3", category_id="c3", keywords=["c"], priority=5))
        rules = engine.list_rules()
        assert rules[0]["id"] == "r2"
        assert rules[1]["id"] == "r3"
        assert rules[2]["id"] == "r1"


class TestCategoryEngineAmountFilter:
    """金额过滤"""

    def test_min_amount_filter(self):
        """低于最小金额时跳过规则"""
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(
            id="r1", category_id="cat_big",
            keywords=["消费"], priority=1,
            min_amount="100",
        ))
        engine.set_default("cat_small")
        # 金额 50 < 100，跳过
        result = engine.classify("消费", "50")
        assert result == "cat_small"

    def test_max_amount_filter(self):
        """超过最大金额时跳过规则"""
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(
            id="r1", category_id="cat_small",
            keywords=["消费"], priority=1,
            max_amount="100",
        ))
        engine.set_default("cat_big")
        # 金额 200 > 100，跳过
        result = engine.classify("消费", "200")
        assert result == "cat_big"

    def test_amount_in_range(self):
        """金额在范围内时匹配"""
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(
            id="r1", category_id="cat_mid",
            keywords=["消费"], priority=1,
            min_amount="50", max_amount="200",
        ))
        result = engine.classify("消费", "100")
        assert result == "cat_mid"


class TestCategoryEngineCustom:
    """自定义规则"""

    def test_add_custom_rule(self):
        engine = CategoryEngine()
        engine.add_rule(CategoryRule(
            id="custom", category_id="cat_custom",
            keywords=["自定义"], priority=100,
        ))
        result = engine.classify("自定义分类")
        assert result == "cat_custom"

    def test_set_default(self):
        engine = CategoryEngine()
        engine.set_default("cat_default")
        result = engine.classify("不匹配任何规则")
        assert result == "cat_default"
