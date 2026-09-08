"""健康档案模块测试。"""

from datetime import date

from profile.models import (
    HealthProfile,
    Gender,
    BloodType,
    MaritalStatus,
)
from profile.repository import HealthProfileRepository


def test_create_profile():
    p = HealthProfileRepository.create(
        profile_id="P001",
        name="张三",
        gender=Gender.MALE,
        birth_date=date(1990, 5, 15),
        height_cm=175.0,
        weight_kg=70.0,
        blood_type=BloodType.A,
        marital_status=MaritalStatus.MARRIED,
        allergies=["青霉素"],
        chronic_diseases=[],
    )
    assert p.id
    assert p.profile_id == "P001"
    assert p.name == "张三"
    assert p.age == 36  # 2026 - 1990 = 36
    assert abs(p.bmi - 22.86) < 0.01
    assert p.blood_type == BloodType.A


def test_bmi_missing_data():
    p = HealthProfileRepository.create(
        name="李四",
        gender=Gender.FEMALE,
        birth_date=date(2000, 1, 1),
    )
    assert p.bmi is None
    assert p.ideal_weight_kg is None


def test_ideal_weight_male():
    p = HealthProfile(
        name="男测试",
        gender=Gender.MALE,
        birth_date=date(1990, 1, 1),
        height_cm=180,
    )
    assert abs(p.ideal_weight_kg - 72.0) < 0.1  # (180-100)*0.9 = 72


def test_ideal_weight_female():
    p = HealthProfile(
        name="女测试",
        gender=Gender.FEMALE,
        birth_date=date(1990, 1, 1),
        height_cm=165,
    )
    assert abs(p.ideal_weight_kg - 55.2) < 0.1  # (165-105)*0.92 = 55.2


def test_repository_get_by_profile_id():
    HealthProfileRepository.create(
        profile_id="P002",
        name="王五",
        gender=Gender.MALE,
        birth_date=date(1985, 3, 10),
    )
    found = HealthProfileRepository.get_by_profile_id("P002")
    assert found is not None
    assert found.name == "王五"


def test_repository_search_by_name():
    HealthProfileRepository.create(
        name="张三丰", gender=Gender.MALE, birth_date=date(1990, 1, 1)
    )
    HealthProfileRepository.create(
        name="张三", gender=Gender.MALE, birth_date=date(1990, 1, 1)
    )
    HealthProfileRepository.create(
        name="李四", gender=Gender.FEMALE, birth_date=date(1990, 1, 1)
    )
    results = HealthProfileRepository.search_by_name("张")
    assert len(results) == 2


def test_repository_list_active():
    HealthProfileRepository.create(
        name="激活", gender=Gender.MALE, birth_date=date(1990, 1, 1), is_active=True
    )
    HealthProfileRepository.create(
        name="禁用", gender=Gender.MALE, birth_date=date(1990, 1, 1), is_active=False
    )
    active = HealthProfileRepository.list_active()
    assert len(active) == 1
    assert active[0].name == "激活"


def test_profile_default_profile_id():
    # 不指定 profile_id 时，默认空字符串（创建后可回填）
    p = HealthProfileRepository.create(
        name="测试", gender=Gender.OTHER, birth_date=date(2000, 1, 1)
    )
    assert p.profile_id == ""
