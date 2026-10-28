"""product-kb 满足度匹配 — DETAIL §5。

把合同标的（来自 parser 浅解析）映射到 product-kb（PKB-001）
ContractMatcher，输出满足度判定 satisfied / partial / unsatisfied。

契约要点：
- 连真实本地 product_kb.db（只读），不 mock 冒充结论
- 低置信一律标"需人工确认"，不自动判满足
- db 不可达 → 流程不中断，结果标注"未做参照"，绝不静默通过
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .parser import ShallowParseResult, parse_shallow


class KbMatchError(RuntimeError):
    """product-kb 匹配异常。"""


@dataclass
class ContractItem:
    """合同标的（喂给 product-kb 的入参）。"""

    name: str
    model: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None


@dataclass
class KbMatchResult:
    """单个标的的匹配结果。"""

    input_name: str
    matched: bool = False
    score: float = 0.0
    product: Optional[str] = None
    sku: Optional[str] = None
    alert: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_name": self.input_name,
            "matched": self.matched,
            "score": self.score,
            "product": self.product,
            "sku": self.sku,
            "alert": self.alert,
        }


@dataclass
class KbReview:
    """整份合同的 KB 参照结果。"""

    satisfaction: str = "unsatisfied"     # satisfied / partial / unsatisfied
    referenced: bool = True               # False = 未做参照（db 不可达）
    items: List[KbMatchResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "satisfaction": self.satisfaction,
            "referenced": self.referenced,
            "items": [i.to_dict() for i in self.items],
        }


def _default_product_kb_root() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "product-kb",
    )


def _default_product_kb_db() -> str:
    return os.path.join(_default_product_kb_root(), "data", "product_kb.db")


def load_matcher(product_kb_root: Optional[str] = None,
                 db_path: Optional[str] = None):
    """加载 product-kb 组件并构造 ContractMatcher（sys.path 注入，不改源码）。

    Returns:
        ContractMatcher（已连接真实 db）

    Raises:
        KbMatchError: 组件/db 缺失
    """
    root = os.path.abspath(product_kb_root or _default_product_kb_root())
    if not os.path.isdir(root):
        raise KbMatchError("product-kb 组件不存在: %s" % root)
    if root not in os.sys.path:
        os.sys.path.insert(0, root)
    db_file = os.path.abspath(db_path or _default_product_kb_db())
    if not os.path.isfile(db_file):
        raise KbMatchError("product_kb.db 不存在: %s（可先 import_price 重建）" % db_file)
    try:
        from product_kb.db import ProductKBDB
        from product_kb.contract import ContractMatcher
        db = ProductKBDB(db_file)
        db.connect()
        return ContractMatcher(db)
    except Exception as e:  # noqa: BLE001 - 包装为组件错误
        raise KbMatchError("product-kb 加载失败: %s" % e) from e


def items_from_text(full_text: str,
                    parsed: Optional[ShallowParseResult] = None) -> List[ContractItem]:
    """从合同全文（或已有浅解析结果）提取标的清单。

    parser 浅解析给 items 名称清单；价格/型号无法从名称可靠推断时置 None，
    由 matcher 只做名称+版本匹配。
    """
    parse = parsed or parse_shallow(full_text or "")
    items = []
    for name in parse.items:
        items.append(ContractItem(name=name))
    # 浅解析无标的时：尝试按金额/主体生成一个"整体标的"兜底无意义，
    # 直接返回空列表（由上层判定 unsatisfied + 需人工）
    return items


def match_items(matcher, items: List[ContractItem]) -> List[KbMatchResult]:
    """逐标的匹配，返回结构化结果列表。"""
    out: List[KbMatchResult] = []
    if not items:
        return out
    try:
        raw_results = matcher.match_items(
            [
                {"name": it.name, "model": it.model, "price": it.price}
                for it in items
            ]
        )
    except Exception as e:  # noqa: BLE001 - 匹配失败不中断整份合同
        raise KbMatchError("match_items 失败: %s" % e) from e

    for it, r in zip(items, raw_results):
        out.append(
            KbMatchResult(
                input_name=it.name,
                matched=bool(r.get("matched")),
                score=float(r.get("score") or 0.0),
                product=(r.get("product") or {}).get("name") if r.get("product") else None,
                sku=(r.get("sku") or {}).get("sku") if r.get("sku") else None,
                alert=r.get("alert"),
            )
        )
    return out


def decide_satisfaction(results: List[KbMatchResult]) -> str:
    """DETAIL §5.2 满足度判定。

    - satisfied：全部 matched 且 alert 为空
    - unsatisfied：任一 matched=False / 有"红线/停售"类 alert
    - partial：其余（低置信/需人工确认等）
    """
    if not results:
        # 无标的可参照 → 保守判"需人工"，satisfaction 用 unsatisfied
        return "unsatisfied"
    has_hard_fail = False
    has_soft_warn = False
    for r in results:
        if not r.matched:
            has_hard_fail = True
            continue
        if r.alert:
            if any(k in (r.alert or "") for k in ("红线", "停售", "无SKU", "SKU状态", "未匹配", "低匹配度")):
                # 红线/停售/无SKU = 不可满足
                if "红线" in r.alert or "停售" in r.alert or "无SKU" in r.alert:
                    has_hard_fail = True
                else:
                    has_soft_warn = True
            else:
                has_soft_warn = True
    if has_hard_fail:
        return "unsatisfied"
    if has_soft_warn:
        return "partial"
    return "satisfied"


def run_kb_match(full_text: str,
                 product_kb_root: Optional[str] = None,
                 db_path: Optional[str] = None,
                 parsed: Optional[ShallowParseResult] = None) -> KbReview:
    """对合同全文跑 KB 满足度参照（主入口）。

    db 不可达时返回 referenced=False 的 KbReview（不抛异常、不中断）。
    """
    try:
        matcher = load_matcher(product_kb_root, db_path)
    except KbMatchError:
        return KbReview(satisfaction="unsatisfied", referenced=False)

    items = items_from_text(full_text, parsed)
    results = match_items(matcher, items)
    satisfaction = decide_satisfaction(results)
    return KbReview(satisfaction=satisfaction, referenced=True, items=results)
