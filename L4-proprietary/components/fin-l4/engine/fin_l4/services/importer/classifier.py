"""智能分类引擎 — 基于规则 + 置信度 + 用户反馈学习"""

import re
import os
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from decimal import Decimal
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

RULES_DIR = Path(__file__).parent / "classification_rules"


@dataclass
class ClassifyInput:
    """分类引擎的输入"""
    description: str = ""
    counterparty: str = ""
    summary: str = ""
    product: str = ""
    amount: Decimal = Decimal("0")
    direction: str = ""       # income / expense
    txn_date: str = ""
    txn_type: str = ""


@dataclass
class ClassifyResult:
    """分类结果"""
    category_id: str
    category_name: str = ""
    confidence: str = "low"   # high / medium / low
    matched_rules: List[str] = field(default_factory=list)
    match_score: int = 0


@dataclass
class ClassificationRule:
    """分类规则"""
    id: str
    category_id: str
    name: str = ""
    priority: int = 0
    confidence_level: str = "medium"  # 规则本身的置信度等级
    conditions: Dict[str, Any] = field(default_factory=dict)

    def match(self, inp: ClassifyInput) -> bool:
        """检查规则是否匹配输入"""
        return self._eval_conditions(self.conditions, inp)

    def _eval_conditions(self, cond: Dict, inp: ClassifyInput) -> bool:
        """递归评估条件表达式"""
        if not cond:
            return False

        # all: 所有子条件必须满足
        if "all" in cond:
            return all(
                self._eval_conditions(c, inp)
                for c in cond["all"]
            )

        # any: 任一子条件满足
        if "any" in cond:
            return any(
                self._eval_conditions(c, inp)
                for c in cond["any"]
            )

        # always_true: 兜底规则
        if cond.get("always_true"):
            return True

        # direction: 收支方向
        if "direction" in cond:
            if cond["direction"] != inp.direction:
                return False

        # keywords_in: 在指定字段中匹配关键词
        # YAML 结构: keywords_in: [field1, field2]  +  keywords: [kw1, kw2]
        if "keywords_in" in cond:
            # keywords_in 的值是字段列表
            if isinstance(cond["keywords_in"], list):
                fields = cond["keywords_in"]
            elif isinstance(cond["keywords_in"], dict):
                fields = cond["keywords_in"].get("fields", [])
            else:
                fields = ["description", "counterparty", "summary"]
            
            # keywords 是同级的列表
            keywords = cond.get("keywords", [])
            if not keywords:
                return False

            # 收集所有目标字段的文本
            text_parts = []
            for f in fields:
                val = getattr(inp, f, "")
                if val:
                    text_parts.append(str(val).lower())
            text = " ".join(text_parts)

            if not text:
                return False

            # 任一关键词命中即匹配
            for kw in keywords:
                if str(kw).lower() in text:
                    return True
            return False

        # amount_range: 金额范围 [min, max]
        if "amount_range" in cond:
            rng = cond["amount_range"]
            if not rng or len(rng) != 2:
                return True  # 范围无效则跳过
            min_amt = Decimal(str(rng[0]))
            max_amt = Decimal(str(rng[1]))
            amt = inp.amount
            if amt < min_amt or amt > max_amt:
                return False

        return True


class RuleClassifier:
    """
    基于规则的智能分类引擎

    匹配流程：
    1. 按优先级从高到低遍历所有规则
    2. 收集所有匹配的规则
    3. 取最高优先级规则的分类 + 综合置信度
    4. 置信度计算：高优先级规则命中 + 多条规则同分类 → high
    """

    def __init__(self):
        self._rules: List[ClassificationRule] = []
        self._feedback: Dict[str, Dict] = {}  # 用户反馈记忆

    def add_rule(self, rule: ClassificationRule):
        self._rules.append(rule)
        # 按优先级排序（高优先在前）
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def load_rules_from_yaml(self, path: str = None):
        """从 YAML 文件加载规则"""
        if yaml is None:
            raise ImportError("PyYAML not installed")
        if path is None:
            path = RULES_DIR / "default_rules.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for r in data.get("rules", []):
            rule = ClassificationRule(
                id=r["id"],
                category_id=r["category_id"],
                name=r.get("name", ""),
                priority=r.get("priority", 0),
                confidence_level=r.get("confidence_level", "medium"),
                conditions=r.get("conditions", {}),
            )
            self.add_rule(rule)

    def classify(self, description: str = "", counterparty: str = "",
                 summary: str = "", product: str = "", amount: Decimal = None,
                 direction: str = "", txn_date: str = "",
                 txn_type: str = "") -> ClassifyResult:
        """
        对交易进行分类
        返回 ClassifyResult
        """
        inp = ClassifyInput(
            description=description,
            counterparty=counterparty,
            summary=summary,
            product=product,
            amount=amount or Decimal("0"),
            direction=direction,
            txn_date=txn_date,
            txn_type=txn_type,
        )
        return self._classify_input(inp)

    def classify_txn(self, txn) -> ClassifyResult:
        """从 ParsedTransaction 对象分类"""
        # 合并 description 文本
        desc_parts = [txn.summary, txn.product, txn.txn_type]
        description = " ".join(p for p in desc_parts if p)

        return self.classify(
            description=description,
            counterparty=txn.counterparty,
            summary=txn.summary,
            product=txn.product,
            amount=txn.amount,
            direction=txn.direction,
            txn_date=txn.txn_date,
            txn_type=txn.txn_type,
        )

    def _classify_input(self, inp: ClassifyInput) -> ClassifyResult:
        # 收集所有匹配的规则
        matched = []
        for rule in self._rules:
            try:
                if rule.match(inp):
                    matched.append(rule)
            except Exception:
                continue

        if not matched:
            return ClassifyResult(
                category_id="cat_other",
                confidence="low",
                matched_rules=[],
            )

        # 取最高优先级的规则
        top = matched[0]

        # 计算有多少条匹配规则指向同一分类
        same_cat_count = sum(
            1 for r in matched if r.category_id == top.category_id
        )

        # 置信度判定
        confidence = top.confidence_level
        if same_cat_count >= 2 and confidence != "high":
            # 多条规则都指向同一分类 → 提升置信度
            confidence = "high" if confidence == "medium" else "medium"

        return ClassifyResult(
            category_id=top.category_id,
            confidence=confidence,
            matched_rules=[r.id for r in matched],
            match_score=top.priority,
        )

    def learn_feedback(self, counterparty: str, summary: str,
                       original_cat: str, corrected_cat: str,
                       amount: str = ""):
        """
        用户反馈学习：记录用户修改分类的频次
        简单的频次统计，不做复杂 ML
        """
        key = self._feedback_key(counterparty, summary)
        if key not in self._feedback:
            self._feedback[key] = {
                "counterparty": counterparty,
                "summary": summary,
                "corrections": {},
                "total": 0,
            }

        entry = self._feedback[key]
        entry["corrections"][corrected_cat] = entry["corrections"].get(corrected_cat, 0) + 1
        entry["total"] += 1

    def get_feedback_suggestion(self, counterparty: str, summary: str) -> Optional[str]:
        """根据历史反馈获取分类建议"""
        key = self._feedback_key(counterparty, summary)
        if key not in self._feedback:
            return None
        entry = self._feedback[key]
        # 反馈超过 2 次才建议，避免误操作影响
        if entry["total"] < 2:
            return None
        # 返回次数最多的分类
        return max(entry["corrections"], key=entry["corrections"].get)

    @staticmethod
    def _feedback_key(counterparty: str, summary: str) -> str:
        return f"{counterparty.strip()}|{summary.strip()[:50]}"

    def list_rules(self) -> List[Dict]:
        """列出所有规则"""
        return [
            {
                "id": r.id,
                "category_id": r.category_id,
                "name": r.name,
                "priority": r.priority,
                "confidence_level": r.confidence_level,
            }
            for r in self._rules
        ]

    @classmethod
    def default(cls) -> 'RuleClassifier':
        """创建默认分类器（加载内置规则）"""
        clf = cls()
        try:
            clf.load_rules_from_yaml()
        except Exception:
            # YAML 不可用时，添加基本规则
            pass
        return clf
