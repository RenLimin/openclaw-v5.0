"""健康指标记录模块测试。"""

from datetime import datetime, timedelta

from metrics.models import MetricsRecord, MetricsType, MetricSource
from metrics.repository import MetricsRecordRepository


def test_create_metric_default_unit():
    m = MetricsRecordRepository.create(
        profile_id="P001",
        metrics_type=MetricsType.HEART_RATE,
        value=72.0,
        source=MetricSource.WEARABLE,
    )
    assert m.metrics_type == MetricsType.HEART_RATE
    assert m.value == 72.0
    assert m.unit == "bpm"
    assert m.source == MetricSource.WEARABLE
    assert m.is_abnormal is False


def test_bp_systolic_unit():
    m = MetricsRecord(
        profile_id="P001",
        metrics_type=MetricsType.BLOOD_PRESSURE_SYSTOLIC,
        value=120,
    )
    assert m.unit == "mmHg"


def test_weight_unit():
    m = MetricsRecord(
        profile_id="P001",
        metrics_type=MetricsType.WEIGHT,
        value=70.5,
    )
    assert m.unit == "kg"


def test_repository_list_by_profile_and_type():
    profile_id = "P001"
    for i in range(5):
        MetricsRecordRepository.create(
            profile_id=profile_id,
            metrics_type=MetricsType.HEART_RATE,
            value=60 + i * 2,
            measured_at=datetime(2026, 1, 1, 8, 0) + timedelta(days=i),
        )
    # 加一条其他类型
    MetricsRecordRepository.create(
        profile_id=profile_id,
        metrics_type=MetricsType.WEIGHT,
        value=70,
    )
    # 加一条其他 profile
    MetricsRecordRepository.create(
        profile_id="P002",
        metrics_type=MetricsType.HEART_RATE,
        value=80,
    )

    hr_records = MetricsRecordRepository.list_by_profile(
        profile_id, metrics_type=MetricsType.HEART_RATE
    )
    assert len(hr_records) == 5
    # 按时间正序
    assert hr_records[0].measured_at < hr_records[-1].measured_at


def test_repository_latest():
    profile_id = "P001"
    for i in range(3):
        MetricsRecordRepository.create(
            profile_id=profile_id,
            metrics_type=MetricsType.BLOOD_GLUCOSE_FASTING,
            value=5.0 + i,
            measured_at=datetime(2026, 1, 1 + i),
        )
    latest = MetricsRecordRepository.latest(
        profile_id, MetricsType.BLOOD_GLUCOSE_FASTING
    )
    assert latest is not None
    assert latest.value == 7.0


def test_repository_list_abnormal():
    MetricsRecordRepository.create(
        profile_id="P001",
        metrics_type=MetricsType.BLOOD_PRESSURE_SYSTOLIC,
        value=160,
        is_abnormal=True,
        abnormal_flag="high",
    )
    MetricsRecordRepository.create(
        profile_id="P001",
        metrics_type=MetricsType.HEART_RATE,
        value=70,
    )
    abnormal = MetricsRecordRepository.list_abnormal("P001")
    assert len(abnormal) == 1
    assert abnormal[0].abnormal_flag == "high"


def test_repository_list_by_source():
    MetricsRecordRepository.create(
        profile_id="P001",
        metrics_type=MetricsType.STEPS,
        value=8000,
        source=MetricSource.WEARABLE,
    )
    MetricsRecordRepository.create(
        profile_id="P001",
        metrics_type=MetricsType.WEIGHT,
        value=70,
        source=MetricSource.SMART_SCALE,
    )
    wearable = MetricsRecordRepository.list_by_source(
        "P001", MetricSource.WEARABLE
    )
    assert len(wearable) == 1
    assert wearable[0].metrics_type == MetricsType.STEPS


def test_time_range_filter():
    profile_id = "P001"
    for i in range(10):
        MetricsRecordRepository.create(
            profile_id=profile_id,
            metrics_type=MetricsType.WEIGHT,
            value=70.0 + i * 0.5,
            measured_at=datetime(2026, 1, 1) + timedelta(days=i),
        )
    records = MetricsRecordRepository.list_by_profile(
        profile_id,
        metrics_type=MetricsType.WEIGHT,
        start=datetime(2026, 1, 3),
        end=datetime(2026, 1, 7),
    )
    assert len(records) == 5  # 3,4,5,6,7
