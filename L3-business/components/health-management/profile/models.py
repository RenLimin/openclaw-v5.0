"""个人健康档案领域模型。

包含个人基本信息、生活方式、家族病史、过敏史等健康基础数据。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field, field_validator

from repository.base import TenantModel


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodType(str, Enum):
    A = "A"
    B = "B"
    AB = "AB"
    O = "O"
    UNKNOWN = "unknown"


class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    OTHER = "other"


class HealthProfile(TenantModel):
    """个人健康档案。

    是所有健康数据的主体锚点，其他模块通过 profile_id 关联。
    """

    # ── 基本身份 ────────────────────────────────────────────────
    profile_id: str = ""  # 业务编码，可与外部系统对齐
    name: str
    gender: Gender
    birth_date: date
    id_card_no: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None

    # ── 生理基础 ────────────────────────────────────────────────
    height_cm: Optional[float] = Field(default=None, gt=0, le=300)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=500)
    blood_type: BloodType = BloodType.UNKNOWN
    rh_factor: Optional[str] = None  # + / - / unknown

    # ── 社会属性 ────────────────────────────────────────────────
    marital_status: MaritalStatus = MaritalStatus.SINGLE
    occupation: Optional[str] = None
    education: Optional[str] = None

    # ── 生活方式 ────────────────────────────────────────────────
    smoking_status: str = "never"   # never / former / current
    drinking_status: str = "never"  # never / occasional / regular / heavy
    exercise_hours_per_week: float = 0.0
    sleep_hours_per_day: float = 7.0
    dietary_preference: str = "normal"  # normal / vegetarian / vegan / low_salt / low_sugar

    # ── 病史 ────────────────────────────────────────────────────
    allergies: List[str] = Field(default_factory=list)
    chronic_diseases: List[str] = Field(default_factory=list)
    family_history: List[str] = Field(default_factory=list)
    past_surgeries: List[str] = Field(default_factory=list)

    # ── 状态 ────────────────────────────────────────────────────
    is_active: bool = True
    tags: List[str] = Field(default_factory=list)
    remark: str = ""

    @field_validator("profile_id", mode="before")
    @classmethod
    def _default_profile_id(cls, v: Optional[str]) -> str:
        # 创建时如未指定，就用 id 填充
        return v or ""

    @property
    def age(self) -> int:
        """计算实足年龄。"""
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def bmi(self) -> Optional[float]:
        """BMI = 体重(kg) / 身高(m)^2。"""
        if not self.height_cm or not self.weight_kg:
            return None
        height_m = self.height_cm / 100.0
        return round(self.weight_kg / (height_m ** 2), 2)

    @property
    def ideal_weight_kg(self) -> Optional[float]:
        """理想体重（Broca 改良公式）。"""
        if not self.height_cm:
            return None
        # 男性: (身高-100)*0.9, 女性: (身高-105)*0.92
        base = self.height_cm - (100 if self.gender == Gender.MALE else 105)
        factor = 0.9 if self.gender == Gender.MALE else 0.92
        return round(base * factor, 2)
