"""利润管理导入 —— ProfitImporter。"""

from pathlib import Path
from typing import Optional, Dict, Any

from bdms.modules.profit_management.service import ProfitService


class ProfitImporter:
    """利润数据导入器，薄封装现有导入方法。"""

    def __init__(self, db_path: Optional[Path] = None):
        self._service = ProfitService(db_path)

    def import_timesheet(
        self,
        project_id: int,
        file_path: Path,
        operator: str = "",
        **row_kwargs,
    ) -> Dict[str, Any]:
        """导入工时数据。

        薄封装 ProfitService：文件级批量导入暂未实现，委托逐行提交
        （submit_timesheet）。row_kwargs 支持 project_id/person_id/work_date/
        hours 等字段，便于批量调用时逐行构造。
        """
        return self._service.submit_timesheet(project_id, **row_kwargs)

    def submit_timesheet(
        self,
        project_id: int,
        person_id: str,
        work_date: str,
        hours: float,
        work_type: str = "",
        description: str = "",
        submitter: str = "",
    ) -> Dict[str, Any]:
        """提交单条工时记录。"""
        return self._service.submit_timesheet(
            project_id, person_id, work_date, hours, work_type, description, submitter
        )

    def approve_timesheet(
        self,
        timesheet_id: int,
        approver: str,
        approved: bool = True,
        comment: str = "",
    ) -> Dict[str, Any]:
        """审批工时记录。"""
        return self._service.approve_timesheet(timesheet_id, approver, approved, comment)

    def import_travel_cost(
        self,
        project_id: int,
        excel_path: Path,
        operator: str = "",
    ) -> Dict[str, Any]:
        """导入差旅费用Excel。"""
        return self._service.import_travel_cost(project_id, str(excel_path), operator)

    def import_all(self, excel_path: Path, project_id: int, operator: str = "") -> Dict[str, Any]:
        """依次导入所有数据（工时+差旅）。

        差旅费用支持文件级批量导入；工时需逐行提交，由调用方构造
        row_kwargs 列表，本方法对每条记录委托 submit_timesheet。
        """
        results = {}
        results["travel_cost"] = self.import_travel_cost(project_id, excel_path, operator)
        return results

