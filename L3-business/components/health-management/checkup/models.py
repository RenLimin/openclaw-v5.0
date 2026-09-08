"""体检记录领域模型。

一次体检 = 一条 CheckupRecord 主记录 + 若干 CheckupItem 项目明细。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from repository.base import TenantModel


class CheckupStatus(str, Enum):
    SCHEDULED = "scheduled"    # 已预约
    IN_PROGRESS = "in_progress"  # 检查中
    COMPLETED = "completed"    # 已完成
    REPORT_READY = "report_ready"  # 报告已出
    CANCELLED = "cancelled"    # 已取消


class CheckupItem(BaseModel):
    """单个体检项目。"""

    item_code: str              # 项目编码
    item_name: str              # 项目名称
    category: str = ""          # 分类：血常规/生化/影像...
    result: Optional[str] = None   # 结果值（字符串，兼容文字描述）
    value: Optional[float] = None  # 数值结果（定量项目）
    unit: Optional[str] = None     # 单位
    reference_range: Optional[str] = None  # 参考范围
    is_abnormal: bool = False
    abnormal_flag: Optional[str] = None  # high / low / normal
    method: Optional[str] = None       # 检测方法
    remark: str = ""


class CheckupRecord(TenantModel):
    """体检记录（主表）。"""

    profile_id: str
    checkup_date: date
    hospital: str = ""
    department: Optional[str] = None
    doctor: Optional[str] = None
    package_name: Optional[str] = None     # 套餐名称
    checkup_type: str = "annual"           # annual /入职/复查/专项...

    status: CheckupStatus = CheckupStatus.SCHEDULED
    report_url: Optional[str] = None       # 体检报告文件 URL
    overall_summary: str = ""              # 总检结论
    doctor_advice: str = ""                # 医生建议
    follow_up_required: bool = False       # 是否需要复查
    follow_up_date: Optional[date] = None  # 建议复查日期

    items: List[CheckupItem] = Field(default_factory=list)

    tags: List[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def abnormal_items(self) -> List[CheckupItem]:
        """所有异常项目。"""
        return [item for item in self.items if item.is_abnormal]

    @property
    def abnormal_count(self) -> int:
        """异常项目数量。"""
        return sum(1 for item in self.items if item.is_abnormal)

    @property
    def total_items(self) -> int:
        """项目总数。"""
        return len(self.items)

    def get_item(self, item_code: str) -> Optional[CheckupItem]:
        """按编码查找项目。"""
        for item in self.items:
            if item.item_code == item_code:
                return item
        return None

    def add_item(self, item: CheckupItem) -> None:
        """添加体检项目。"""
        # 已存在则替换
        for i, existing in enumerate(self.items):
            if existing.item_code == item.item_code:
                self.items[i] = item
                return
        self.items.append(item)
