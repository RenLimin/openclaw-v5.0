# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""Data Pipeline — 数据源 → 适配器的统一编排。

负责：按月从各数据源拉取原始数据 → 标准化 → 交付给报表引擎。
缺失数据立即报错，不静默降级。
"""
from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime

from bdms.modules.integration.adapters.ones_adapter import MissingSourceError
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
        from bdms.modules.integration.connectors.ones_connector import OnesConnector
        self._ones = OnesConnector()
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
            raw = self._ones.fetch("sign", month, use_cache=True, file_path=file_paths.get("sign"))
            result["sign"] = self._ones.normalize(raw)
        except Exception as e:
            errors.append(("ONES签约", str(e)))
        
        # POC 数据
        try:
            raw = self._ones.fetch("poc", month, use_cache=True, file_path=file_paths.get("poc"))
            result["poc"] = self._ones.normalize(raw)
        except Exception as e:
            errors.append(("ONESPOC", str(e)))
        
        # 异常数据
        try:
            raw = self._ones.fetch("abnormal", month, use_cache=True, file_path=file_paths.get("exception"))
            result["exception"] = self._ones.normalize(raw)
        except Exception as e:
            errors.append(("ONES异常", str(e)))
        
        # 确收交接
        # 暂不修改，后续企微连接器接入后替换
        from bdms.modules.integration.connectors.wecom_doc_connector import WecomDocConnector
        try:
            wc = WecomDocConnector(db_path=self.db_path)
            raw = wc.fetch("确收交接", month)
            result["revenue"] = raw
        except Exception as e:
            # fallback to old ones adapter lookup
            try:
                from bdms.modules.integration.adapters.ones_adapter import OnesAdapter
                oa = OnesAdapter()
                result["revenue"] = oa.fetch("revenue", month, use_cache=True)
            except MissingSourceError as e:
                errors.append(("确收交接", str(e)))
        
        # 验收交接
        # 暂不修改，后续企微连接器接入后替换
        try:
            wc = WecomDocConnector(db_path=self.db_path)
            raw = wc.fetch("验收交接", month)
            result["acceptance"] = raw
        except Exception as e:
            # fallback to old ones adapter lookup
            try:
                from bdms.modules.integration.adapters.ones_adapter import OnesAdapter
                oa = OnesAdapter()
                result["acceptance"] = oa.fetch("acceptance", month, use_cache=True)
            except MissingSourceError as e:
                errors.append(("验收交接", str(e)))
        
        if errors:
            # 汇总所有错误，一次性报告
            msg = "; ".join(f"{src}: {reason}" for src, reason in errors)
            raise DataSourceError(
                source="multi", month=month, reason=msg,
                actionable=f"请检查数据源配置或手动导出 {month} 的原始数据"
            )
        
        # 提取 raw_data 部分
        for key in result:
            result[key] = [row["source_data"] for row in result[key]]
        
        return result
