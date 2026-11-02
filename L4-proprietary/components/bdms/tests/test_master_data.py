"""模块3 交付基础数据 —— 测试。

用法：
    cd L4-proprietary/components/bdms && export PYTHONPATH=src && python3 -m pytest tests/test_master_data.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bdms.modules.master_data import MasterDataEngine, MasterDataService  # noqa: E402
from bdms.modules.master_data.engine import make_code                  # noqa: E402


REAL_SOURCE = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026交付月报-20260630.xlsx"
)


@pytest.fixture()
def svc(tmp_path):
    """独立临时库，避免污染主库。"""
    db = tmp_path / "test_master_data.db"
    s = MasterDataService(db)
    s.ensure_schema()
    return s


# ─── 引擎：code 生成 ───

def test_make_code_stable():
    assert make_code("正常确收") == make_code("正常确收")
    assert make_code("正常确收") != make_code("预计确收")
    assert make_code("API") == "api"
    # 中文保留可读，不转 unicode 码点串
    assert make_code("正常确收") == "正常确收"
    assert make_code("差异确收（当年可消除）") == "差异确收_当年可消除"


# ─── 源文件解析 ───

@pytest.mark.skipif(not REAL_SOURCE.exists(), reason="真实验收源文件不存在")
def test_parse_real_legend_excel(svc):
    parsed = svc.engine.parse_legend_excel(REAL_SOURCE)
    assert parsed["sheet"] == "图例"
    assert parsed["header_row"] == 1
    assert parsed["valid_rows"] == 34      # 35 行 - 1 行表头
    assert parsed["max_row"] == 506        # 名义 506 行，尾部为空残留

    blocks = parsed["blocks"]
    # 11 个图例块（48 列交付月报）
    assert set(blocks) == {
        "project_manager", "assessment_rule",
        "obligation_status", "item_stat_status", "project_stat_status",
        "fin_delivery_status", "fin_accept_status",
        "sales_team",
        "delivery_cross_month_reason", "delivery_fail_reason",
        "accept_fail_reason",
    }
    assert len(blocks["project_manager"]) == 33   # 31 真人 + 未立项/已结项（去掉 * 汇总行）
    assert len(blocks["assessment_rule"]) == 20   # 考核规则矩阵（不去重）
    assert len(blocks["obligation_status"]) == 8  # 状态
    assert len(blocks["item_stat_status"]) == 9   # 履约项统计状态
    assert len(blocks["project_stat_status"]) == 5
    assert len(blocks["fin_delivery_status"]) == 4
    assert len(blocks["fin_accept_status"]) == 3
    assert len(blocks["sales_team"]) == 18        # 责任销售所属团队
    assert len(blocks["delivery_cross_month_reason"]) == 3
    assert len(blocks["delivery_fail_reason"]) == 3
    assert len(blocks["accept_fail_reason"]) == 3

    # extra：项目经理带 dept/center/person_status（备注列语义=人员状态）
    cn = [i for i in blocks["project_manager"] if i["label"] == "崔延章"][0]
    assert cn["extra"]["dept"] == "北区客户服务部"
    assert cn["extra"]["center"] == "交付中心"
    assert cn["extra"]["person_status"] == "已离职"
    # * 汇总行已被剔除
    assert all(i["label"] != "*" for i in blocks["project_manager"])
    # 状态带类别；销售带统计组
    assert blocks["obligation_status"][0]["extra"]["category"] == "未实施"
    assert blocks["sales_team"][0]["extra"]["stat"]
    # 考核规则行：第一行 = 交付计划准确率-提前
    assert blocks["assessment_rule"][0]["label"] == "交付计划准确率-提前"
    assert blocks["assessment_rule"][0]["extra"]["weight_factor"] == "1"
    # 合并单元格：item 只在锚点行（第 1、12 行）
    assert blocks["assessment_rule"][0]["extra"]["item"] == "交付计划准确率"
    assert "item" not in blocks["assessment_rule"][1]["extra"]


def test_parse_missing_file_raises(svc):
    with pytest.raises(FileNotFoundError):
        svc.engine.parse_legend_excel(Path("/tmp/__not_exist__.xlsx"))


# ─── CRUD ───

def test_create_get_update_delete(svc):
    r = svc.create_item("legend", "测试图例A", extra={"k": "v"})
    assert r["ok"] and r["action"] == "created"
    code = r["item"]["code"]

    got = svc.get_item("legend", code)
    assert got["label"] == "测试图例A"
    assert got["extra"] == {"k": "v"}
    assert got["enabled"] is True

    # 重复创建 → exists
    assert svc.create_item("legend", "测试图例A")["action"] == "exists"

    # 更新
    u = svc.update_item("legend", code, label="测试图例A2", sort_order=99)
    assert u["ok"] and u["item"]["label"] == "测试图例A2"
    assert u["item"]["sort_order"] == 99

    # 软删除
    d = svc.delete_item("legend", code)
    assert d["action"] == "soft_deleted"
    assert svc.get_item("legend", code)["enabled"] is False
    assert code not in [i["code"] for i in svc.list_items("legend")]
    assert code in [i["code"] for i in svc.list_items("legend", include_disabled=True)]

    # 恢复
    assert svc.restore_item("legend", code)["ok"]
    assert svc.get_item("legend", code)["enabled"] is True

    # 硬删除
    assert svc.delete_item("legend", code, hard=True)["action"] == "deleted_hard"
    assert svc.get_item("legend", code) is None


def test_create_validation(svc):
    with pytest.raises(ValueError):
        svc.create_item("legend", "")
    with pytest.raises(ValueError):
        svc.create_item("", "x")


def test_update_not_found(svc):
    assert svc.update_item("legend", "nope")["action"] == "not_found"
    assert svc.delete_item("legend", "nope")["action"] == "not_found"


def test_sort_order_auto_increments(svc):
    a = svc.create_item("dept", "部门A")["item"]
    b = svc.create_item("dept", "部门B")["item"]
    assert b["sort_order"] > a["sort_order"]
    lst = svc.list_items("dept")
    assert [i["label"] for i in lst] == ["部门A", "部门B"]


# ─── 导入 ───

@pytest.mark.skipif(not REAL_SOURCE.exists(), reason="真实验收源文件不存在")
def test_import_legend_from_excel(svc):
    r = svc.import_legend_from_excel(REAL_SOURCE, month="202606")
    assert r["ok"]
    assert r["total"] == sum(r["imported"].values())
    assert r["imported"]["project_manager"] == 33
    assert r["imported"]["assessment_rule"] == 20
    assert r["imported"]["obligation_status"] == 8
    assert r["imported"]["item_stat_status"] == 9
    assert r["imported"]["project_stat_status"] == 5
    assert r["imported"]["fin_delivery_status"] == 4
    assert r["imported"]["fin_accept_status"] == 3
    assert r["imported"]["sales_team"] == 18
    assert r["imported"]["delivery_cross_month_reason"] == 3
    assert r["imported"]["delivery_fail_reason"] == 3
    assert r["imported"]["accept_fail_reason"] == 3
    assert r["total"] == 109          # 11 类型真实条目数（33+20+8+9+5+4+3+18+3+3+3）

    # 幂等：重复导入 total 不变
    r2 = svc.import_legend_from_excel(REAL_SOURCE, month="202606")
    assert r2["total"] == r["total"]
    assert svc.engine.count() == r["total"]

    # 数据可查
    labels = svc.get_labels("obligation_status")
    assert "实施进行中" in labels
    assert "验收文件已归档" in labels

    # 类型统计
    types = {t["data_type"]: t for t in svc.list_types()}
    assert types["obligation_status"]["total"] == 8
    assert types["project_manager"]["total"] == 33
    assert len(types) == 11


@pytest.mark.skipif(not REAL_SOURCE.exists(), reason="真实验收源文件不存在")
def test_import_selected_types(svc):
    r = svc.import_legend_from_excel(
        REAL_SOURCE, month="202606", data_types=["obligation_status"])
    assert set(r["imported"]) == {"obligation_status"}
    assert svc.engine.count() == 8


def test_import_without_path_and_month(tmp_path):
    svc = MasterDataService(tmp_path / "x.db")
    svc.ensure_schema()
    r = svc.import_legend_from_excel(month="199901")
    assert r["ok"] is False
    assert "未找到" in r["message"]
