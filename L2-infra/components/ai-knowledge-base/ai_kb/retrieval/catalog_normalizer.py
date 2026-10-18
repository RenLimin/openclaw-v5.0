"""
标准产品目录归一化模块
将用户查询中的非标准叫法归一化为价格表标准产品/服务名称，
提升实体匹配和 FTS 检索的准确性。

数据源: agents/bangcle-product-expert/data/product_catalog.json
(由 梆梆_产品价格查询-2026-09-08.xlsx 生成)
"""
import json
import os
import re
from typing import Dict, List, Optional, Tuple


class CatalogNormalizer:
    """归一化用户查询到标准产品目录"""

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = catalog_path or os.path.join(
            os.path.dirname(__file__), '../../agents/bangcle-product-expert/data/product_catalog.json'
        )
        self._load()

    def _load(self):
        path = os.path.abspath(self.catalog_path)
        if not os.path.exists(path):
            # 回退到默认空目录
            self.alias_map = {}
            self.lines = []
            self.line_names = set()
            self.product_names = set()
            self.loaded = False
            return
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.alias_map = data.get('alias_map', {})
        self.lines = data.get('lines', [])
        # 收集标准名称集合
        self.line_names = set()
        self.product_names = set()
        for line in self.lines:
            self.line_names.add(line['name'])
            for cat in line.get('categories', []):
                for prod in cat.get('products', []):
                    self.product_names.add(prod['name'])
        # 产品线全称身份候选（xlsx 中为简称如"安全监测线"，全称用于防止短别名误替换）
        self.full_line_names = {
            '安全保护产品线', '安全检测产品线', '安全监测产品线',
            '内容安全产品线', '安全服务产品线', '物联网服务产品线',
        }
        self.loaded = True

    def normalize(self, query: str) -> Tuple[str, List[str]]:
        """
        归一化查询中的产品/服务叫法。
        贪心最长匹配扫描：标准产品名/产品线名优先于短别名，
        避免短别名（如"安全监测"）替换掉更长产品名（如"全渠道应用安全监测软件V6.0"）的中间部分。
        返回: (归一化后的查询, 匹配到的标准名列表)
        """
        if not self.loaded or not query:
            return query, []

        # 候选替换表: (key, value)，按 key 长度降序
        candidates = []
        for alias, standard in self.alias_map.items():
            if alias and standard and alias != standard:
                candidates.append((alias, standard))
        for name in self.product_names:
            if name:
                candidates.append((name, name))
        for line in self.lines:
            if line['name']:
                candidates.append((line['name'], line['name']))
        for full_name in self.full_line_names:
            candidates.append((full_name, full_name))
        # 去重 + 按长度降序（同长度按字典序保证确定性）
        seen_keys = set()
        uniq = []
        for key, value in sorted(candidates, key=lambda x: (-len(x[0]), x[0])):
            if key not in seen_keys:
                seen_keys.add(key)
                uniq.append((key, value))
        candidates = uniq

        matched = []
        out_parts = []
        i = 0
        result = query
        n = len(result)
        while i < n:
            hit = False
            for key, value in candidates:
                if result.startswith(key, i):
                    if value not in matched:
                        matched.append(value)
                    out_parts.append(value)
                    i += len(key)
                    hit = True
                    break
            if not hit:
                out_parts.append(result[i])
                i += 1

        normalized = ''.join(out_parts)

        # 清理误匹配: 移除是其他更长匹配子串的名称（如"安全产品"是"内容安全产品线"的子串）
        dedup = []
        for name in matched:
            if any(name != other and name in other for other in matched):
                continue
            if name not in dedup:
                dedup.append(name)

        return normalized, dedup

    def get_catalog_info(self, standard_name: str) -> Optional[Dict]:
        """按标准名查询目录信息（产品线/类别/编码）"""
        for line in self.lines:
            for cat in line.get('categories', []):
                for prod in cat.get('products', []):
                    if prod['name'] == standard_name:
                        return {
                            'name': prod['name'],
                            'product_line': line['name'],
                            'category': cat['name'],
                            'codes': prod.get('codes', []),
                            'models': prod.get('models', []),
                        }
        return None
