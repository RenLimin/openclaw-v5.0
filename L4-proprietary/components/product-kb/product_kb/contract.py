"""
Contract matching module: match contract items against product SKU
"""
import difflib
import re
from typing import List, Dict, Optional, Tuple
from .db import ProductKBDB


class ContractMatcher:
    def __init__(self, db: ProductKBDB, match_threshold: float = 0.5,
                 weights: Dict = None):
        self.db = db
        self.match_threshold = match_threshold
        self.weights = weights or {
            "name_similarity": 0.6,
            "version_match": 0.3,
            "category_match": 0.1
        }

    @staticmethod
    def extract_version(text: str) -> Optional[str]:
        """Extract version from text"""
        pattern = re.compile(r'[Vv](?:ersion)?\s*(\d+(?:\.\d+)+)')
        match = pattern.search(text)
        if match:
            return match.group(1)
        pattern2 = re.compile(r'(\d+(?:\.\d+)+)')
        match = pattern2.search(text)
        if match:
            return match.group(1)
        return None

    def compute_score(self, input_name: str, input_version: Optional[str],
                      input_category: Optional[str], product) -> float:
        """Compute match score for a product"""
        # Name similarity: edit distance
        seq_sim = difflib.SequenceMatcher(None, input_name.lower(), product["name"].lower()).ratio()

        # Version match
        version_score = 0.0
        product_version = product["version_latest"]
        if input_version is None and product_version is None:
            version_score = 1.0
        elif input_version is not None and product_version is not None:
            if input_version == product_version:
                version_score = 1.0
            elif input_version.split('.')[0] == product_version.split('.')[0]:
                version_score = 0.5
            else:
                version_score = 0.0
        elif input_version is not None or product_version is not None:
            version_score = 0.0

        # Category match (simplified for now)
        category_score = 0.0

        # Weighted total
        total = (
            self.weights["name_similarity"] * seq_sim +
            self.weights["version_match"] * version_score +
            self.weights["category_match"] * category_score
        )
        return total

    def match_item(self, input_name: str, input_model: Optional[str] = None,
                   input_price: Optional[float] = None) -> Dict:
        """Match a single contract item against SKU database"""
        # FTS search for candidates
        candidates = self.db.fts_search_products(input_name, 20)
        if not candidates:
            return {
                "input_name": input_name,
                "input_model": input_model,
                "input_price": input_price,
                "matched": False,
                "score": 0.0,
                "product": None,
                "sku": None,
                "alert": None
            }

        input_version = self.extract_version(input_name)
        # Score candidates
        scored = []
        for product_id in candidates:
            product = self.db.get_product(product_id)
            if not product:
                continue
            score = self.compute_score(input_name, input_version, None, product)
            scored.append((score, product))

        scored.sort(reverse=True, key=lambda x: x[0])
        best_score, best_product = scored[0]

        if best_score < self.match_threshold:
            return {
                "input_name": input_name,
                "input_model": input_model,
                "input_price": input_price,
                "matched": False,
                "score": best_score,
                "product": dict(best_product) if best_product else None,
                "sku": None,
                "alert": "低匹配度，需人工确认"
            }

        # Find best matching SKU for this product
        cursor = self.db.execute("SELECT * FROM sku WHERE product_id = ?", (best_product["id"],))
        skus = cursor.fetchall()
        if not skus:
            return {
                "input_name": input_name,
                "input_model": input_model,
                "input_price": input_price,
                "matched": False,
                "score": best_score,
                "product": dict(best_product),
                "sku": None,
                "alert": "产品无SKU信息"
            }

        # For now, pick first SKU, improve model matching later
        best_sku = skus[0]
        # TODO: find best SKU by model matching
        if input_model:
            for sku in skus:
                if sku["model"] and input_model in sku["model"]:
                    best_sku = sku
                    break

        # Check price and discount
        alert = None
        unit_price = best_sku["unit_price"]
        if input_price is not None and unit_price is not None and unit_price > 0:
            ratio = input_price / unit_price
            discount_type = best_sku["discount_type"]
            if "折红线" in discount_type:
                # Extract discount
                m = re.search(r'(\d+)折', discount_type)
                if m:
                    discount_line = int(m.group(1)) / 10
                    min_allowed = unit_price * discount_line
                    if input_price < min_allowed - 0.01:
                        alert = f"价格低于折扣红线（红线: {min_allowed:.2f}, 输入: {input_price:.2f}）"

        # Check sale status
        if best_sku["sale_status"] != "启用":
            alert = (alert + "; " if alert else "") + f"SKU状态: {best_sku['sale_status']}"

        return {
            "input_name": input_name,
            "input_model": input_model,
            "input_price": input_price,
            "matched": True,
            "score": best_score,
            "product": dict(best_product),
            "sku": dict(best_sku),
            "alert": alert
        }

    def match_items(self, items: List[Dict]) -> List[Dict]:
        """Match multiple contract items"""
        results = []
        for item in items:
            result = self.match_item(
                item.get("name", ""),
                item.get("model"),
                item.get("price")
            )
            results.append(result)
        return results
