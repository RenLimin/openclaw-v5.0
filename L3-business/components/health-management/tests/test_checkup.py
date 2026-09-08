"""体检记录模块测试。"""

from datetime import date

from checkup.models import (
    CheckupRecord,
    CheckupItem,
    CheckupStatus,
)
from checkup.repository import CheckupRecordRepository


def _make_item(code, name, value, unit, ref, abnormal=False, flag=None):
    return CheckupItem(
        item_code=code,
        item_name=name,
        value=value,
        unit=unit,
        reference_range=ref,
        is_abnormal=abnormal,
        abnormal_flag=flag,
    )


def test_create_checkup_with_items():
    record = CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2026, 6, 15),
        hospital="北京协和医院",
        package_name="全面体检套餐",
        checkup_type="annual",
        status=CheckupStatus.COMPLETED,
        overall_summary="整体健康状况良好",
        doctor_advice="注意控制体重，增加运动",
        items=[
            _make_item("BP", "血压", 120, "mmHg", "90-140/60-90"),
            _make_item("GLU", "空腹血糖", 6.5, "mmol/L", "3.9-6.1", True, "high"),
            _make_item("TC", "总胆固醇", 5.2, "mmol/L", "<5.2"),
        ],
    )
    assert record.total_items == 3
    assert record.abnormal_count == 1
    assert record.abnormal_items[0].item_code == "GLU"
    assert record.status == CheckupStatus.COMPLETED


def test_get_item():
    item = _make_item("WBC", "白细胞", 6.5, "10^9/L", "4-10")
    record = CheckupRecord(
        profile_id="P001",
        checkup_date=date(2026, 1, 1),
        items=[item],
    )
    found = record.get_item("WBC")
    assert found is not None
    assert found.item_name == "白细胞"
    assert record.get_item("RBC") is None


def test_add_item_new_and_replace():
    record = CheckupRecord(
        profile_id="P001",
        checkup_date=date(2026, 1, 1),
    )
    item1 = _make_item("A", "项目A", 10, "unit", "0-20")
    record.add_item(item1)
    assert record.total_items == 1

    item2 = _make_item("A", "项目A-更新", 15, "unit", "0-20")
    record.add_item(item2)
    assert record.total_items == 1  # 替换，不新增
    assert record.items[0].value == 15
    assert record.items[0].item_name == "项目A-更新"


def test_repository_latest():
    CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2024, 6, 1),
        hospital="旧医院",
        status=CheckupStatus.COMPLETED,
    )
    CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2025, 6, 1),
        hospital="新医院",
        status=CheckupStatus.COMPLETED,
    )
    latest = CheckupRecordRepository.latest("P001")
    assert latest is not None
    assert latest.hospital == "新医院"


def test_repository_list_by_year():
    for year in [2023, 2024, 2025]:
        CheckupRecordRepository.create(
            profile_id="P001",
            checkup_date=date(year, 6, 1),
            status=CheckupStatus.COMPLETED,
        )
    records_2025 = CheckupRecordRepository.list_by_year("P001", 2025)
    assert len(records_2025) == 1


def test_repository_find_abnormal_history():
    r1 = CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2024, 1, 1),
        status=CheckupStatus.COMPLETED,
        items=[
            _make_item("GLU", "空腹血糖", 6.8, "mmol/L", "3.9-6.1", True, "high"),
        ],
    )
    r2 = CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2025, 1, 1),
        status=CheckupStatus.COMPLETED,
        items=[
            _make_item("GLU", "空腹血糖", 5.8, "mmol/L", "3.9-6.1"),
            _make_item("TC", "总胆固醇", 6.5, "mmol/L", "<5.2", True, "high"),
        ],
    )
    history = CheckupRecordRepository.find_abnormal_history("P001", "GLU")
    assert len(history) == 1
    assert history[0].checkup_date == date(2024, 1, 1)


def test_follow_up_fields():
    record = CheckupRecordRepository.create(
        profile_id="P001",
        checkup_date=date(2026, 1, 1),
        hospital="医院",
        follow_up_required=True,
        follow_up_date=date(2026, 7, 1),
        status=CheckupStatus.REPORT_READY,
    )
    assert record.follow_up_required is True
    assert record.follow_up_date == date(2026, 7, 1)
