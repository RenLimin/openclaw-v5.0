# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""OA 数据源适配器 — 本机导入 + 浏览器自动化。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import List, Dict, Optional

from bdms.core.paths import ones_dir


class OaAdapter:
    """OA 合同流程数据源适配器。"""

    def fetch(self, contract_type: str = "", date_range: str = "",
              file_path: str = "") -> List[Dict]:
        """获取 OA 数据。
        
        1. 本机文件（最高优先级）
        2. OA 导出 CSV
        3. 浏览器自动化
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            return self._read_csv(Path(file_path))

        # 2. OA 导出 CSV
        base = ones_dir()
        for name in ["oa_contracts.csv", "合同台账.csv"]:
            p = base / name
            if p.exists():
                return self._read_csv(p)

        # 3. 浏览器自动化（待实现）
        raise MissingSourceError(
            f"OA 数据不可用。请手动导出合同数据到 {ones_dir()}"
        )

    def _read_csv(self, path: Path) -> List[Dict]:
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]


class MissingSourceError(Exception):
    pass
