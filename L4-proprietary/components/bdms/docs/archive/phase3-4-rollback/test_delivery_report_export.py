"""交付月报导出回归测试（对齐手工黄金基准）。

覆盖 `exporter.py` 里从手工公式逐条解码的业务规则。测试**不依赖**手工 Excel
文件（CI 上不一定有），而是用构造数据断言公式语义；另有一个可选用例在手工
基准存在时跑真实比对。
"""
import datetime as dt
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pd = pytest.importorskip("pandas")

from bdms.modules.delivery_report.exporter import (   # noqa: E402
    _rebuild_status_columns, _filter_rows, _blank_manual_columns,
    _extract_ssxm, _to_date_obj, _clean_scalar, _month_end_date,
    _legend_manager_region, COLUMN_POS_MAP, MANUAL_COLUMNS,
)

ME = dt.date(2026, 6, 30)


def _df(rows, cols=None):
    return pd.DataFrame(rows, columns=cols)


def _base(proj="【SSXM-2026-0708-1784】X", **kw):
    """一条 `签约` 履约项行，默认 = 正常交付。"""
    row = {
        "项目编号": proj, "所属项目": proj,
        "状态": "实施进行中", "履约项异常/变更类型": None, "项目状态": "",
        "预算-预估交付完成日期": "2026-07-31",
        "预算-预估验收完成日期": "2026-08-31",
        "基线-预估结项日期": "2026-09-30",
        "销售合同编号": "XSZS0001",
    }
    row.update(kw)
    return row


def _mk(rows, extra_cols=()):
    """把 dict 行转成 `_rebuild_status_columns` 需要的完整列集。"""
    cols = ["项目编号", "所属项目", "状态", "履约项异常/变更类型", "项目状态",
            "预算-预估交付完成日期", "预算-预估验收完成日期", "基线-预估结项日期",
            "销售合同编号", "统计项目编号", "统计合同编号", "履约项合计", "校验",
            "统计校验", "项目验收状态（即，财报-验收状态）",
            "履约项统计状态（即，财报-交付/确收状态）",
            "1：正常交付", "2：应交未交", "3：交付异常", "4：正常验收",
            "5：应验未验", "6：验收异常", "7：正常服务", "8：应结未结",
            "9：已结项", "实施未开始", "义务已拆分", "实施进行中", "实施已完成",
            "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档",
            ] + list(extra_cols)
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows],
                        columns=cols)


# ── 工具函数 ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_ssxm_from_project_text(self):
        assert _extract_ssxm("【SSXM-2026-0708-1784】某项目") == "SSXM-2026-0708-1784"

    def test_extract_ssxm_passthrough(self):
        assert _extract_ssxm("SSXM-2026-0708-1784") == "SSXM-2026-0708-1784"

    def test_extract_ssxm_none(self):
        assert _extract_ssxm(None) is None
        assert _extract_ssxm("无编号文本") is None

    def test_to_date_obj_handles_nat(self):
        # pandas.NaT 是 datetime 子类，必须归一为 None（否则比较抛 TypeError）
        assert _to_date_obj(pd.NaT) is None

    def test_to_date_obj_normalizes(self):
        assert _to_date_obj("2026-06-30") == ME
        assert _to_date_obj(dt.datetime(2026, 6, 30)) == ME

    def test_clean_scalar_nan_to_none(self):
        assert _clean_scalar(float("nan")) is None
        assert _clean_scalar("") is None
        assert _clean_scalar("x") == "x"

    def test_month_end_date(self):
        assert _month_end_date("202606") == ME
        assert _month_end_date("202602") == dt.date(2026, 2, 28)


# ── c56 履约项统计状态（手工 ArrayFormula 解码）───────────────────────

class TestStatusFormula:
    def test_normal_delivery_when_budget_in_future(self):
        df = _rebuild_status_columns(_mk([_base()]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "1：正常交付"

    def test_overdue_delivery(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"预算-预估交付完成日期": "2026-05-01"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "2：应交未交"

    def test_delivery_exception_wins(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"履约项异常/变更类型": "履约项交付异常"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "3：交付异常"

    def test_normal_acceptance(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"状态": "交付邮件已归档"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "4：正常验收"

    def test_pending_acceptance(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"状态": "交付邮件已归档",
                          "预算-预估验收完成日期": "2026-05-01"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "5：应验未验"

    def test_acceptance_exception(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"状态": "验收文件交接中",
                          "履约项异常/变更类型": "履约项验收异常"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "6：验收异常"

    def test_normal_service(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"状态": "验收文件已归档", "项目状态": "",
                          "基线-预估结项日期": "2026-12-31"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "7：正常服务"

    def test_pending_settlement(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"状态": "验收文件已归档", "项目状态": "",
                          "基线-预估结项日期": "2026-05-01"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "8：应结未结"

    def test_settled(self):
        # 需 `项目状态=已归档`；IFS 从第 1 支开始判定，故 `状态` 不能落在实施组
        df = _rebuild_status_columns(
            _mk([_base(**{"项目状态": "已归档",
                          "状态": "验收文件已归档"})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "9：已结项"

    def test_empty_budget_date_is_due(self):
        """LEN(日期)=0 视同「未滞后」→ 正常交付。"""
        df = _rebuild_status_columns(
            _mk([_base(**{"预算-预估交付完成日期": None})]), "202606")
        assert df["履约项统计状态（即，财报-交付/确收状态）"].iloc[0] == "1：正常交付"


# ── c57-c65 桶：COUNTIFS(AO, AP, BD, label)，仅项目首行有值 ───────────

class TestBucketColumns:
    def test_bucket_only_on_first_row(self):
        rows = [_base() for _ in range(3)]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["1：正常交付"].tolist() == [3, 0, 0]
        assert df["履约项合计"].tolist() == [3, 0, 0]

    def test_bucket_counts_group_members(self):
        rows = [_base(), _base(**{"状态": "交付邮件已归档"})]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["1：正常交付"].iloc[0] == 1
        assert df["4：正常验收"].iloc[0] == 1

    def test_c53_is_group_size_first_row_only(self):
        rows = [_base() for _ in range(4)]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["履约项合计"].tolist() == [4, 0, 0, 0]

    def test_dedup_columns(self):
        """c42 统计项目编号 / c43 统计合同编号 = 去重列，仅首次出现有值。"""
        rows = [_base() for _ in range(3)]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["统计项目编号"].tolist()[0] == "SSXM-2026-0708-1784"
        assert df["统计项目编号"].isna().tolist()[1:] == [True, True]
        assert df["统计合同编号"].tolist()[0] == "XSZS0001"
        assert df["统计合同编号"].isna().tolist()[1:] == [True, True]

    def test_c54_and_c66_are_zero_when_consistent(self):
        rows = [_base() for _ in range(2)]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["校验"].tolist() == [0, 0]
        assert df["统计校验"].tolist() == [0, 0]


# ── c67 项目验收状态（逐行 IFS）────────────────────────────────────────

class TestAcceptanceStatus:
    def test_all_accepted(self):
        # 全部验收 = SUM(BK:BM) == BA，即 7/8/9 桶合计等于项目履约项数
        rows = [_base(**{"状态": "验收文件已归档", "项目状态": "已归档"})]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["项目验收状态（即，财报-验收状态）"].iloc[0] == "已结项", \
            "已结项优先于全部验收（手工 IFS 第 1 支）"

    def test_acceptance_exception(self):
        rows = [_base(**{"状态": "验收文件交接中",
                         "履约项异常/变更类型": "履约项验收异常"})]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["项目验收状态（即，财报-验收状态）"].iloc[0] == "异常验收"

    def test_settled(self):
        df = _rebuild_status_columns(
            _mk([_base(**{"项目状态": "已归档",
                          "状态": "验收文件已归档"})]), "202606")
        assert df["项目验收状态（即，财报-验收状态）"].iloc[0] == "已结项"

    def test_pending_acceptance(self):
        rows = [_base(**{"状态": "交付邮件已归档",
                         "预算-预估验收完成日期": "2026-05-01"})]
        df = _rebuild_status_columns(_mk(rows), "202606")
        assert df["项目验收状态（即，财报-验收状态）"].iloc[0] == "应验未验"

    def test_normal_acceptance_bucket(self):
        df = _rebuild_status_columns(_mk([_base()]), "202606")
        assert df["项目验收状态（即，财报-验收状态）"].iloc[0] == "正常验收"

    def test_none_on_non_first_row(self):
        rows = [_base(**{"状态": "验收文件已归档", "项目状态": "已归档"})
                for _ in range(3)]
        df = _rebuild_status_columns(_mk(rows), "202606")
        st = df["项目验收状态（即，财报-验收状态）"].tolist()
        assert st[0] == "已结项"
        assert pd.isna(st[1]) and pd.isna(st[2])


# ── 行过滤 ───────────────────────────────────────────────────────────

class TestRowFilter:
    def _cols(self):
        return ["ID", "标题", "合同名称", "BI履约ID", "合同编号1", "订单号"]

    def test_drops_empty_trailer_rows(self):
        cols = self._cols()
        rows = [["#1", "t", "c", "b", "k", "1"],
                [None, None, None, None, None, None],
                ["", "", "", "", "", ""]]
        _, out = _filter_rows("验收交接", cols, rows)
        assert len(out) == 1

    def test_no_id_dedup_for_ys(self):
        """验收交接 ID 不唯一（同一ID可对应不同服务期），不去重。"""
        cols = self._cols()
        rows = [["#345083", "t", "c", "b", "k", "1"],
                ["#345083", "t2", "c", "b", "k", "2"]]
        _, out = _filter_rows("验收交接", cols, rows)
        assert len(out) == 2  # 两条都保留

    def test_keeps_rows_with_source_data_but_no_id(self):
        cols = self._cols()
        rows = [["#1", "t", "c", "b", "k", "1"],
                ["", "有标题", "", "b", "", ""]]
        _, out = _filter_rows("验收交接", cols, rows)
        assert len(out) == 2

    def test_no_filter_for_other_sheets(self):
        cols = self._cols()
        rows = [["#1", "t", "c", "b", "k", "1"], ["", "", "", "", "", ""]]
        _, out = _filter_rows("签约", cols, rows)
        assert len(out) == 2


class TestBlankManualColumns:
    def test_blank_estim_amount_exception_sheet(self):
        df = pd.DataFrame({"预估金额": [1, 2], "ID": ["a", "b"]})
        out = _blank_manual_columns("异常项目", df)
        assert out["预估金额"].isna().all()

    def test_noop_for_other_sheets(self):
        df = pd.DataFrame({"预估金额": [1, 2]})
        out = _blank_manual_columns("签约", df)
        assert out["预估金额"].tolist() == [1, 2]


# ── 列映射完整性 ─────────────────────────────────────────────────────

class TestColumnMaps:
    @pytest.mark.parametrize("sheet", ["签约", "POC&提前实施", "异常项目",
                                       "确收交接", "验收交接"])
    def test_position_map_targets_unique(self, sheet):
        pos = COLUMN_POS_MAP.get(sheet)
        if not pos:
            pytest.skip("该 sheet 用库序")
        dsts = [d for _, d in pos if d]
        assert len(dsts) == len(set(dsts)), "目标列位重复"

    @pytest.mark.parametrize("sheet", ["签约", "POC&提前实施", "异常项目",
                                       "确收交接", "验收交接"])
    def test_manual_columns_match_map_width(self, sheet):
        pos = COLUMN_POS_MAP.get(sheet)
        man = MANUAL_COLUMNS.get(sheet)
        if not pos or not man:
            pytest.skip("无显式映射")
        ncols = max(d for _, d in pos if d)
        assert len(man) == ncols, f"{sheet}: 手工列名 {len(man)} vs 映射宽 {ncols}"

    def test_exception_sheet_has_38_columns(self):
        assert len(MANUAL_COLUMNS["异常项目"]) == 38
        assert MANUAL_COLUMNS["异常项目"][35] == "预估金额"


# ── 图例映射 ─────────────────────────────────────────────────────────

class TestLegend:
    def test_reads_project_manager_dept(self, tmp_path):
        import sqlite3
        db = tmp_path / "t.db"
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE md_reference (data_type TEXT, code TEXT,"
                     " label TEXT, extra TEXT, sort_order INT, id INT)")
        conn.execute("INSERT INTO md_reference VALUES"
                     " ('project_manager','徐亚东','徐亚东',"
                     "'{\"dept\": \"南区客户服务部\"}',1,1)")
        conn.commit()
        got = _legend_manager_region(conn)
        assert got["徐亚东"] == "南区客户服务部"

    def test_ignores_other_data_types(self, tmp_path):
        import sqlite3
        db = tmp_path / "t.db"
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE md_reference (data_type TEXT, code TEXT,"
                     " label TEXT, extra TEXT, sort_order INT, id INT)")
        conn.execute("INSERT INTO md_reference VALUES"
                     " ('legend','正常确收','正常确收',NULL,1,1)")
        conn.commit()
        assert _legend_manager_region(conn) == {}


# ── 端到端（手工基准存在时才跑）─────────────────────────────────────

MANUAL = Path("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/"
              "202606/2026交付月报-20260630.xlsx")


@pytest.mark.skipif(not MANUAL.exists(), reason="手工黄金基准不在本机")
class TestGoldenBaseline:
    def test_exception_sheet_zero_diff(self):
        out = ROOT / "output" / "交付月报_202606.xlsx"
        if not out.exists():
            pytest.skip("先跑 export('202606')")
        import warnings
        import openpyxl
        warnings.filterwarnings("ignore")
        a = openpyxl.load_workbook(out, read_only=True, data_only=True)["异常项目"]
        b = openpyxl.load_workbook(MANUAL, read_only=True,
                                   data_only=True)["异常项目"]
        ra = [r for r in a.iter_rows(values_only=True)]
        rb = [r for r in b.iter_rows(values_only=True)]
        diffs = []
        for i in range(max(len(ra), len(rb))):
            A = ra[i] if i < len(ra) else ()
            B = rb[i] if i < len(rb) else ()
            for j in range(max(len(A), len(B))):
                x = A[j] if j < len(A) else None
                y = B[j] if j < len(B) else None
                x = None if x == "" else x
                y = None if y == "" else y
                if x != y:
                    diffs.append((i + 1, j + 1, x, y))
        assert not diffs, f"异常项目 与手工基准有 {len(diffs)} 格差异: {diffs[:5]}"
