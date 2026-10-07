# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""Data Pipeline — 数据源 → 适配器的统一编排。

负责：按月从各数据源拉取原始数据 → 标准化 → 交付给报表引擎。
缺失数据立即报错，不静默降级。
"""
from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime

from bdms.modules.integration.adapters.ones_adapter import OnesAdapter, MissingSourceError
from bdms.modules.integration.adapters.oa_adapter import OaAdapter
from bdms.modules.integration.adapters.timesheet_adapter import TimesheetAdapter


class DataSourceError(Exception):
    """数据源异常。包含具体的数据源、月份和原因。"""
    def __init__(self, source: str, month: str, reason: str, actionable: str = ""):
        self.source = source
        self.month = month
        self.reason = reason
        self.actionable = actionable
        super().__init__(f"[{source}] {month}: {reason}" + (f" → {actionable}" if actionable else ""))


class DeliveryReportPipeline:
    """交付月报数据管道。
    
    职责：从 ONES/OA/工时/企微等数据源拉取原始数据，
    标准化后交付给 DeliveryReportEngine。
    """
    
    def __init__(self, db_path=None):
        self.db_path = db_path
        self._ones = OnesAdapter()
        self._oa = OaAdapter()
        self._timesheet = TimesheetAdapter()
    
    def extract_raw_data(self, month: str, file_paths: dict = None) -> Dict[str, list]:
        """提取某月全部原始数据。
        
        Args:
            month: YYYYMM 格式
            file_paths: 可选的本机文件映射 {"sign": "/path/to/file.csv", ...}
            
        Returns:
            {"sign": [...], "poc": [...], "exception": [...], 
             "revenue": [...], "acceptance": [...]}
             
        Raises:
            DataSourceError: 任一数据源缺失
        """
        file_paths = file_paths or {}
        errors = []
        result = {}
        
        # 签约数据
        try:
            result["sign"] = self._ones.fetch("sign", month, file_path=file_paths.get("sign"))
        except MissingSourceError as e:
            errors.append(("ONES签约", str(e)))
        
        # POC 数据
        try:
            result["poc"] = self._ones.fetch("poc", month, file_path=file_paths.get("poc"))
        except MissingSourceError as e:
            errors.append(("ONESPOC", str(e)))
        
        # 异常数据
        try:
            result["exception"] = self._ones.fetch("exception", month, file_path=file_paths.get("exception"))
        except MissingSourceError as e:
            errors.append(("ONES异常", str(e)))
        
        # 确收交接
        try:
            result["revenue"] = self._ones.fetch("revenue", month, file_path=file_paths.get("revenue"))
        except MissingSourceError as e:
            errors.append(("ONES确收", str(e)))
        
        # 验收交接
        try:
            result["acceptance"] = self._ones.fetch("acceptance", month, file_path=file_paths.get("acceptance"))
        except MissingSourceError as e:
            errors.append(("ONES验收", str(e)))
        
        if errors:
            # 汇总所有错误，一次性报告
            msg = "; ".join(f"{src}: {reason}" for src, reason in errors)
            raise DataSourceError(
                source="multi", month=month, reason=msg,
                actionable=f"请手动导出 {month} 的原始数据到数据目录"
            )
        
        return result
