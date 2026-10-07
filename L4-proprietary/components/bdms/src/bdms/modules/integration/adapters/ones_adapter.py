# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ONES 数据源适配器 — 浏览器自动化 + CSV 缓存。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.1。
ONES 连接器优先从 CSV 缓存读取，缓存缺失时触发浏览器自动化导出。
"""
from __future__ import annotations
import csv
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional

from bdms.core.paths import ones_dir


class OnesAdapter:
    """ONES 项目管理数据源适配器。"""

    # ONES 导出筛选器名称
    FILTERS = {
        "sign": "签约项目统计",
        "poc": "POC&提前实施统计",
        "exception": "异常处置",
        "revenue": "确收交接",
        "acceptance": "验收交接",
    }

    def __init__(self):
        self._cache_dir = ones_dir()

    def fetch(self, filter_name: str, month: str, use_cache: bool = True,
              file_path: str = None) -> List[Dict]:
        """获取 ONES 数据。
        
        1. 本机文件（最高优先级）
        2. 尝试读取缓存 CSV
        3. 缓存缺失 → 浏览器自动化导出
        4. 导出失败 → 抛出 MissingSourceError
        
        Args:
            filter_name: sign | poc | exception | revenue | acceptance
            month: YYYYMM 格式
            use_cache: 是否使用缓存
            file_path: 本机文件路径（可选，最高优先级）
            
        Returns:
            List[Dict] 原始数据
            
        Raises:
            MissingSourceError: 数据源不可用
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            return self._read_csv(Path(file_path))

        # 2. 查找缓存 CSV
        if use_cache:
            csv_path = self._find_csv(filter_name, month)
            if csv_path:
                return self._read_csv(csv_path)

        # 3. 浏览器自动化导出
        exported = self._export_from_browser(filter_name, month)
        if exported:
            return exported

        # 4. 报错
        raise MissingSourceError(
            f"ONES {filter_name} {month} 数据不可用。缓存不存在且浏览器自动化导出失败。"
            f"请手动导出 {self.FILTERS.get(filter_name, filter_name)} 数据到 {self._cache_dir}"
        )

    def _find_csv(self, filter_name: str, month: str) -> Optional[Path]:
        """查找当月缓存 CSV。
        
        严格只匹配当月文件，不回退到前月或通用名。
        缺失时返回 None，由调用方决定是否走浏览器自动化。
        """
        patterns = {
            "sign": f"{month}周报-签约项目统计.csv",
            "poc": f"{month}周报-POC&提前实施统计.csv",
            "exception": f"{month}-签约项目异常处置.csv",
            "revenue": None,  # revenue 使用 month_dir 而非 ones_dir
            "acceptance": None,  # acceptance 使用 month_dir 而非 ones_dir
        }
        if filter_name not in patterns:
            return None
        # revenue/acceptance 在 month_dir 中查找
        if filter_name in ("revenue", "acceptance"):
            return self._find_in_month_dir(month, filter_name)
        p = self._cache_dir / patterns[filter_name]
        return p if p.exists() else None
    
    def _find_in_month_dir(self, month: str, filter_name: str) -> Optional[Path]:
        """在 month_dir 中查找 revenue/acceptance CSV。"""
        from bdms.core.paths import month_dir
        d = month_dir(month)
        if not d.exists():
            return None
        # revenue: 匹配「确收凭证交接-确收」
        # acceptance: 匹配「确收凭证交接-验收」
        if filter_name == "revenue":
            for f in d.glob(f"{month}*确收*.csv"):
                if "验收" not in f.name:
                    return f
        elif filter_name == "acceptance":
            for f in d.glob(f"{month}*验收*.csv"):
                return f
        return None

    def _read_csv(self, path: Path) -> List[Dict]:
        """读取 CSV 文件。"""
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    def _export_from_browser(self, filter_name: str, month: str) -> Optional[List[Dict]]:
        """通过浏览器自动化从 ONES 导出数据。
        
        TODO: 实现 ones-browser-export 技能的集成
        当前返回 None，表示导出失败
        """
        # 浏览器自动化依赖 ONES 登录态
        # 当前版本依赖手动导出到 ones_exports 目录
        return None


class MissingSourceError(Exception):
    """数据源缺失异常。当月数据不可用且无法自动提取时抛出。"""
    pass
