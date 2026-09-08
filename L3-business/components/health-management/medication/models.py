"""用药记录领域模型。

支持处方记录、长期用药计划、服药打卡、不良反应记录。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field

from repository.base import TenantModel


class MedicationFrequency(str, Enum):
    """服药频次。"""
    ONCE_DAILY = "qd"           # 每日一次
    TWICE_DAILY = "bid"         # 每日两次
    THREE_TIMES_DAILY = "tid"   # 每日三次
    FOUR_TIMES_DAILY = "qid"    # 每日四次
    EVERY_OTHER_DAY = "qod"     # 隔日一次
    WEEKLY = "qw"               # 每周一次
    AS_NEEDED = "prn"           # 必要时
    BEFORE_MEAL = "ac"          # 饭前
    AFTER_MEAL = "pc"           # 饭后
    AT_BEDTIME = "hs"           # 睡前
    CUSTOM = "custom"           # 自定义


class MedicationStatus(str, Enum):
    ACTIVE = "active"           # 进行中
    COMPLETED = "completed"     # 已完成
    DISCONTINUED = "discontinued"  # 已停药
    PAUSED = "paused"           # 暂停
    EXPIRED = "expired"         # 已过期


class MedicationRecord(TenantModel):
    """用药记录 / 处方。"""

    profile_id: str

    # ── 药品信息 ────────────────────────────────────────────────
    drug_name: str                   # 药品通用名
    brand_name: Optional[str] = None  # 商品名
    drug_category: Optional[str] = None  # 分类：降压药/降糖药/抗生素...
    dosage: str                      # 剂量，如 "10mg"
    strength: Optional[str] = None   # 规格，如 "10mg×30片"
    form: Optional[str] = None       # 剂型：片剂/胶囊/注射液/外用...

    # ── 用法 ────────────────────────────────────────────────────
    frequency: MedicationFrequency = MedicationFrequency.ONCE_DAILY
    frequency_detail: Optional[str] = None  # 自定义频次描述
    route: str = "口服"                       # 给药途径
    quantity_per_dose: Optional[float] = None  # 每次数量（片/粒/ml）
    duration_days: Optional[int] = None      # 用药天数

    # ── 周期 ────────────────────────────────────────────────────
    start_date: date
    end_date: Optional[date] = None
    prescription_date: Optional[date] = None

    # ── 医生/处方 ───────────────────────────────────────────────
    prescriber: Optional[str] = None         # 开方医生
    hospital: Optional[str] = None           # 医院
    prescription_no: Optional[str] = None    # 处方编号
    indication: Optional[str] = None         # 适应症

    # ── 状态 ────────────────────────────────────────────────────
    status: MedicationStatus = MedicationStatus.ACTIVE
    refill_count: int = 0                    # 已续方次数
    max_refills: Optional[int] = None        # 最大续方次数

    # ── 提醒/备注 ───────────────────────────────────────────────
    reminder_enabled: bool = False
    reminder_times: List[str] = Field(default_factory=list)  # ["08:00", "20:00"]
    side_effects: List[str] = Field(default_factory=list)
    notes: str = ""
    tags: List[str] = Field(default_factory=list)

    @property
    def is_active_today(self) -> bool:
        """今天是否在用药期内且状态为进行中。"""
        if self.status != MedicationStatus.ACTIVE:
            return False
        today = date.today()
        if self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return True

    @property
    def days_remaining(self) -> Optional[int]:
        """剩余用药天数。"""
        if not self.end_date:
            return None
        today = date.today()
        delta = (self.end_date - today).days
        return max(delta, 0)
