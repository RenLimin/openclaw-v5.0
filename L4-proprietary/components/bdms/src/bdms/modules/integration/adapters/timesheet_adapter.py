# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""工时门户数据源适配器 — 浏览器自动化 + 本机导入。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import List, Dict

from bdms.core.paths import ones_dir


class TimesheetAdapter:
    """工时门户数据源适配器。"""

    def fetch(self, project_id: str = "", month: str = "",
              file_path: str = "") -> List[Dict]:
        """获取工时数据。
        
        1. 本机文件
        2. 工时导出 CSV/Excel
        3. 浏览器自动化（待实现）
        """
        if file_path and Path(file_path).exists():
            return self._read_file(Path(file_path))

        base = ones_dir()
        for name in ["工时填报.xlsx", "工时数据.csv", "timesheet.csv"]:
            p = base / name
            if p.exists():
                return self._read_file(p)

        raise MissingSourceError(
            f"工时数据不可用。请手动导出到 {ones_dir()}"
        )

    def _read_file(self, path: Path) -> List[Dict]:
        if path.suffix == '.xlsx':
            import pandas as pd
            df = pd.read_excel(path)
            return df.to_dict(orient='records')
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]


class MissingSourceError(Exception):
    pass
