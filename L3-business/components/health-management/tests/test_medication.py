"""用药记录模块测试。"""

from datetime import date, timedelta

from medication.models import (
    MedicationRecord,
    MedicationFrequency,
    MedicationStatus,
)
from medication.repository import MedicationRecordRepository


def test_create_medication():
    m = MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="氨氯地平",
        brand_name="络活喜",
        drug_category="降压药",
        dosage="5mg",
        strength="5mg×7片",
        form="片剂",
        frequency=MedicationFrequency.ONCE_DAILY,
        route="口服",
        quantity_per_dose=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        prescriber="王医生",
        hospital="北京协和医院",
        prescription_no="RX20260101001",
        indication="高血压",
        reminder_enabled=True,
        reminder_times=["08:00"],
    )
    assert m.drug_name == "氨氯地平"
    assert m.frequency == MedicationFrequency.ONCE_DAILY
    assert m.status == MedicationStatus.ACTIVE
    assert m.prescription_no == "RX20260101001"


def test_is_active_today():
    today = date.today()
    # 当前进行中的药
    m = MedicationRecord(
        profile_id="P001",
        drug_name="测试药",
        dosage="10mg",
        frequency=MedicationFrequency.ONCE_DAILY,
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=20),
    )
    assert m.is_active_today is True

    # 已过期
    m2 = MedicationRecord(
        profile_id="P001",
        drug_name="过期药",
        dosage="10mg",
        frequency=MedicationFrequency.ONCE_DAILY,
        start_date=today - timedelta(days=30),
        end_date=today - timedelta(days=1),
    )
    assert m2.is_active_today is False

    # 已停药
    m3 = MedicationRecord(
        profile_id="P001",
        drug_name="停用药",
        dosage="10mg",
        frequency=MedicationFrequency.ONCE_DAILY,
        start_date=today - timedelta(days=10),
        status=MedicationStatus.DISCONTINUED,
    )
    assert m3.is_active_today is False


def test_days_remaining():
    today = date.today()
    m = MedicationRecord(
        profile_id="P001",
        drug_name="测试",
        dosage="10mg",
        start_date=today,
        end_date=today + timedelta(days=30),
    )
    assert m.days_remaining == 30

    # 无结束日期
    m2 = MedicationRecord(
        profile_id="P001",
        drug_name="长期",
        dosage="10mg",
        start_date=today,
    )
    assert m2.days_remaining is None


def test_repository_list_active():
    today = date.today()
    MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="降压药",
        dosage="5mg",
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=80),
    )
    MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="维生素",
        dosage="1片",
        start_date=today - timedelta(days=100),
        end_date=today - timedelta(days=10),
    )
    active = MedicationRecordRepository.list_active("P001")
    assert len(active) == 1
    assert active[0].drug_name == "降压药"


def test_repository_mark_discontinued():
    m = MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="待停药",
        dosage="10mg",
        start_date=date.today(),
    )
    updated = MedicationRecordRepository.mark_discontinued(
        m.id, reason="出现不良反应"
    )
    assert updated.status == MedicationStatus.DISCONTINUED
    assert updated.notes == "出现不良反应"


def test_repository_find_by_prescription():
    MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="有处方号的药",
        dosage="5mg",
        start_date=date.today(),
        prescription_no="RX-0001",
    )
    found = MedicationRecordRepository.find_by_prescription_no("RX-0001")
    assert found is not None
    assert found.drug_name == "有处方号的药"


def test_repository_list_by_category():
    MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="降压药A",
        dosage="5mg",
        drug_category="降压药",
        start_date=date.today(),
    )
    MedicationRecordRepository.create(
        profile_id="P001",
        drug_name="降糖药B",
        dosage="500mg",
        drug_category="降糖药",
        start_date=date.today(),
    )
    bp_meds = MedicationRecordRepository.list_by_category("P001", "降压药")
    assert len(bp_meds) == 1
    assert bp_meds[0].drug_name == "降压药A"
