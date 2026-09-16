"""模块3 交付管理基础数据 —— 测试。

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
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
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
    # 8 个图例块
    assert set(blocks) >= {
        "project_manager", "legend", "deviation_reason",
        "delay_accept_reason", "delay_accept_action",
        "abnormal_type", "abnormal_category", "team", "product",
    }
    assert len(blocks["legend"]) == 7            # 偏差-状态/趋势
    assert len(blocks["deviation_reason"]) == 11  # 偏差-原因类别
    assert len(blocks["abnormal_type"]) == 7      # 预算执行进度（7 个互异值）
    # 预算执行进度类别：源数据 7 行但只有 4 个互异值（"异常中" 重复 3 次），
    # 去重后为 4 —— 这是源数据事实，不是解析缺陷
    assert len(blocks["abnormal_category"]) == 4
    assert any("重复 label" in w for w in parsed["warnings"])
    # 产线：源 10 行含末尾汇总行 '*'（= 全部），应跳过 → 9 条
    assert len(blocks["product"]) == 9            # 产线
    assert all(i["label"] != "*" for i in blocks["product"])
    assert any("汇总行" in w for w in parsed["warnings"])
    assert len(blocks["project_manager"]) == 34   # 项目经理
    assert len(blocks["team"]) == 4              # 团队（同样跳过 '*' 汇总行）
    assert len(blocks["dept"]) == 5               # 部门（从第 2 列去重提取）
    assert "北区客户服务部" in [i["label"] for i in blocks["dept"]]
    # extra
    cn = [i for i in blocks["project_manager"] if i["label"] == "崔延章"][0]
    assert cn["extra"]["dept"] == "北区客户服务部"
    assert cn["extra"]["status"] == "已离职"
    # 原因类别说明（第 7 列）挂到 extra.note
    note_items = [i for i in blocks["deviation_reason"] if i["extra"].get("note")]
    assert len(note_items) == 3


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
    assert r["imported"]["legend"] == 7
    assert r["imported"]["project_manager"] == 34
    assert r["imported"]["product"] == 9       # 跳过末尾 '*' 汇总行
    assert r["imported"]["team"] == 4
    assert r["imported"]["abnormal_category"] == 4
    assert r["imported"]["dept"] == 5
    assert r["total"] == 91          # 真实互异条目数（去重 + 跳过汇总行后）

    # 幂等：重复导入 total 不变
    r2 = svc.import_legend_from_excel(REAL_SOURCE, month="202606")
    assert r2["total"] == r["total"]
    assert svc.engine.count() == r["total"]

    # 数据可查
    labels = svc.get_labels("legend")
    assert "正常确收" in labels
    assert "提前确收" in labels

    # 类型统计
    types = {t["data_type"]: t for t in svc.list_types()}
    assert types["legend"]["total"] == 7
    assert types["product"]["total"] == 9   # 跳过末尾 '*' 汇总行
    assert types["team"]["total"] == 4      # 同样跳过汇总行
    assert types["dept"]["total"] == 5
    assert len(types) == 10


@pytest.mark.skipif(not REAL_SOURCE.exists(), reason="真实验收源文件不存在")
def test_import_selected_types(svc):
    r = svc.import_legend_from_excel(REAL_SOURCE, month="202606", data_types=["legend"])
    assert set(r["imported"]) == {"legend"}
    assert svc.engine.count() == 7


def test_import_without_path_and_month(tmp_path):
    svc = MasterDataService(tmp_path / "x.db")
    svc.ensure_schema()
    r = svc.import_legend_from_excel(month="199901")
    assert r["ok"] is False
    assert "未找到" in r["message"]
