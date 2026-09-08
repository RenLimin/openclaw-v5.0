"""健康指标记录领域模型。

覆盖常见生理指标：血压、血糖、心率、血氧、体温、体重、体脂等。
单条记录一个指标值（窄表模式，便于扩展指标类型）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from repository.base import TenantModel


class MetricsType(str, Enum):
    """指标类型枚举（可扩展）。"""
    # 生命体征
    HEART_RATE = "heart_rate"            # 心率 次/分
    BLOOD_PRESSURE_SYSTOLIC = "bp_sys"   # 收缩压 mmHg
    BLOOD_PRESSURE_DIASTOLIC = "bp_dia"  # 舒张压 mmHg
    BLOOD_OXYGEN = "blood_oxygen"        # 血氧饱和度 %
    TEMPERATURE = "temperature"          # 体温 ℃
    RESPIRATORY_RATE = "resp_rate"       # 呼吸频率 次/分

    # 体重体脂
    WEIGHT = "weight"                    # 体重 kg
    BODY_FAT = "body_fat"                # 体脂率 %
    BMI = "bmi"                          # BMI
    MUSCLE_MASS = "muscle_mass"          # 肌肉量 kg
    BONE_MASS = "bone_mass"              # 骨量 kg
    WATER_RATIO = "water_ratio"          # 水分率 %

    # 血糖
    BLOOD_GLUCOSE_FASTING = "glucose_fasting"      # 空腹血糖 mmol/L
    BLOOD_GLUCOSE_POSTPRANDIAL = "glucose_pp"      # 餐后 2h 血糖 mmol/L
    BLOOD_GLUCOSE_RANDOM = "glucose_random"        # 随机血糖 mmol/L
    HBA1C = "hba1c"                                # 糖化血红蛋白 %

    # 血脂
    TOTAL_CHOLESTEROL = "chol_total"       # 总胆固醇 mmol/L
    TRIGLYCERIDE = "triglyceride"          # 甘油三酯 mmol/L
    HDL = "hdl"                            # 高密度脂蛋白 mmol/L
    LDL = "ldl"                            # 低密度脂蛋白 mmol/L

    # 其他
    WAIST_CIRCUMFERENCE = "waist"          # 腰围 cm
    HIP_CIRCUMFERENCE = "hip"              # 臀围 cm
    STEPS = "steps"                        # 步数 步
    SLEEP_DURATION = "sleep_duration"      # 睡眠时长 分钟


class MetricSource(str, Enum):
    MANUAL = "manual"               # 手动录入
    WEARABLE = "wearable"           # 可穿戴设备
    SMART_SCALE = "smart_scale"     # 智能秤
    BLOOD_PRESSURE_MONITOR = "bp_monitor"  # 血压计
    GLUCOMETER = "glucometer"       # 血糖仪
    LAB_TEST = "lab_test"           # 实验室检测
    OTHER = "other"


class MetricsRecord(TenantModel):
    """单条指标记录。"""

    profile_id: str
    metrics_type: MetricsType
    value: float
    unit: str = ""
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    source: MetricSource = MetricSource.MANUAL
    device_id: Optional[str] = None
    location: Optional[str] = None  # 测量部位/体位，如 "左臂坐位"

    # 状态标注
    is_abnormal: bool = False
    abnormal_flag: Optional[str] = None  # high / low / normal

    note: str = ""
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_default_unit(self) -> "MetricsRecord":
        if self.unit:
            return self
        type_map = {
            MetricsType.HEART_RATE: "bpm",
            MetricsType.BLOOD_PRESSURE_SYSTOLIC: "mmHg",
            MetricsType.BLOOD_PRESSURE_DIASTOLIC: "mmHg",
            MetricsType.BLOOD_OXYGEN: "%",
            MetricsType.TEMPERATURE: "°C",
            MetricsType.RESPIRATORY_RATE: "rpm",
            MetricsType.WEIGHT: "kg",
            MetricsType.BODY_FAT: "%",
            MetricsType.BMI: "kg/m²",
            MetricsType.MUSCLE_MASS: "kg",
            MetricsType.BONE_MASS: "kg",
            MetricsType.WATER_RATIO: "%",
            MetricsType.BLOOD_GLUCOSE_FASTING: "mmol/L",
            MetricsType.BLOOD_GLUCOSE_POSTPRANDIAL: "mmol/L",
            MetricsType.BLOOD_GLUCOSE_RANDOM: "mmol/L",
            MetricsType.HBA1C: "%",
            MetricsType.TOTAL_CHOLESTEROL: "mmol/L",
            MetricsType.TRIGLYCERIDE: "mmol/L",
            MetricsType.HDL: "mmol/L",
            MetricsType.LDL: "mmol/L",
            MetricsType.WAIST_CIRCUMFERENCE: "cm",
            MetricsType.HIP_CIRCUMFERENCE: "cm",
            MetricsType.STEPS: "steps",
            MetricsType.SLEEP_DURATION: "min",
        }
        if self.metrics_type in type_map:
            self.unit = type_map[self.metrics_type]
        return self
