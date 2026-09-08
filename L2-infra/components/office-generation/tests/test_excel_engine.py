"""Excel SDK 单元测试"""

import os
import sys

import pytest


from office_engine import ExcelDocument
from office_engine import OfficeEngineError, OfficeParseError


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class TestExcelCreate:
    """创建文档"""

    def test_create_and_save(self):
        doc = ExcelDocument()
        out = os.path.join(OUTPUT_DIR, "test_create.xlsx")
        path = doc.save(out)
        assert os.path.exists(path)
        doc.close()

    def test_format_property(self):
        doc = ExcelDocument()
        assert doc.format == "xlsx"
        doc.close()

    def test_default_sheet(self):
        doc = ExcelDocument()
        sheets = list(doc._sheets.keys())
        assert "Sheet1" in sheets
        doc.close()


class TestExcelWrite:
    """写入能力"""

    def test_set_cell(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", "Hello", font={"bold": True})
        doc.set_cell("Sheet1", "B1", 123, number_format="0.00")
        out = os.path.join(OUTPUT_DIR, "test_cell.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = result["sheets"][0]
        values = {c["cell"]: c["value"] for c in sheet["cell_values"]}
        assert values["A1"] == "Hello"
        assert values["B1"] == "123"
        doc.close()
        doc2.close()

    def test_set_row(self):
        doc = ExcelDocument()
        doc.set_row("Sheet1", 1, ["姓名", "年龄", "城市"], header=True)
        doc.set_row("Sheet1", 2, ["张三", 30, "北京"])
        out = os.path.join(OUTPUT_DIR, "test_row.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = result["sheets"][0]
        values = {c["cell"]: c["value"] for c in sheet["cell_values"]}
        assert values["A1"] == "姓名"
        assert values["C2"] == "北京"
        doc.close()
        doc2.close()

    def test_add_sheet(self):
        doc = ExcelDocument()
        doc.add_sheet("Data")
        doc.set_cell("Data", "A1", "test")
        out = os.path.join(OUTPUT_DIR, "test_sheet.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        assert "Data" in doc2._sheets
        doc.close()
        doc2.close()

    def test_set_column_width(self):
        doc = ExcelDocument()
        doc.set_column_width("Sheet1", "A", 20)
        out = os.path.join(OUTPUT_DIR, "test_col_width.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestExcelFormula:
    """公式"""

    def test_set_formula(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", 10)
        doc.set_cell("Sheet1", "A2", 20)
        doc.set_formula("Sheet1", "A3", "=SUM(A1:A2)")
        out = os.path.join(OUTPUT_DIR, "test_formula.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = result["sheets"][0]
        values = {c["cell"]: c["value"] for c in sheet["cell_values"]}
        # openpyxl 读出来公式是字符串
        assert "SUM" in values["A3"]
        doc.close()
        doc2.close()


class TestExcelConditionalFormat:
    """条件格式"""

    def test_color_scale(self):
        doc = ExcelDocument()
        for i in range(1, 11):
            doc.set_cell("Sheet1", f"A{i}", i * 10)
        doc.add_conditional_format("Sheet1", "A1:A10", "color_scale", {
            "start_color": "63BE7B",
            "end_color": "F8696B",
        })
        out = os.path.join(OUTPUT_DIR, "test_cf.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()

    def test_cell_is_rule(self):
        doc = ExcelDocument()
        for i in range(1, 6):
            doc.set_cell("Sheet1", f"A{i}", i)
        doc.add_conditional_format("Sheet1", "A1:A5", "cell_is", {
            "operator": "greaterThan",
            "formula": [3],
            "fill_color": "FFC7CE",
        })
        out = os.path.join(OUTPUT_DIR, "test_cell_is.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestExcelChart:
    """图表"""

    def test_add_column_chart(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", "月份")
        doc.set_cell("Sheet1", "B1", "销售额")
        for i, (m, v) in enumerate([("1月", 100), ("2月", 200), ("3月", 150)], start=2):
            doc.set_cell("Sheet1", f"A{i}", m)
            doc.set_cell("Sheet1", f"B{i}", v)
        doc.add_chart("Sheet1", "column", "月度销售额", "B2:B4", "A2:A4")
        out = os.path.join(OUTPUT_DIR, "test_chart.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()

    def test_add_pie_chart(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", "类别")
        doc.set_cell("Sheet1", "B1", "占比")
        for i, (c, v) in enumerate([("A", 30), ("B", 50), ("C", 20)], start=2):
            doc.set_cell("Sheet1", f"A{i}", c)
            doc.set_cell("Sheet1", f"B{i}", v)
        doc.add_chart("Sheet1", "pie", "类别占比", "B2:B4", "A2:A4")
        out = os.path.join(OUTPUT_DIR, "test_pie.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestExcelTable:
    """表格对象"""

    def test_add_table(self):
        data = [
            ["姓名", "年龄", "城市"],
            ["张三", 30, "北京"],
            ["李四", 25, "上海"],
            ["王五", 28, "广州"],
        ]
        doc = ExcelDocument()
        doc.add_table("Sheet1", "A1:C4", data)
        out = os.path.join(OUTPUT_DIR, "test_table.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = result["sheets"][0]
        assert len(sheet["tables"]) >= 1
        doc.close()
        doc2.close()


class TestExcelMergeFreeze:
    """合并单元格 & 冻结窗格"""

    def test_merge_cells(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", "合并标题")
        doc.merge_cells("Sheet1", "A1:C1")
        out = os.path.join(OUTPUT_DIR, "test_merge.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = result["sheets"][0]
        assert len(sheet["merged_cells"]) >= 1
        doc.close()
        doc2.close()

    def test_freeze_panes(self):
        doc = ExcelDocument()
        doc.set_row("Sheet1", 1, ["A", "B", "C"])
        doc.freeze_panes("Sheet1", "A2")
        out = os.path.join(OUTPUT_DIR, "test_freeze.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestExcelParse:
    """解析能力"""

    def test_parse_structure(self):
        doc = ExcelDocument()
        doc.add_sheet("DataSheet")
        doc.set_cell("DataSheet", "A1", "Name")
        doc.set_cell("DataSheet", "B1", "Value")
        doc.set_cell("DataSheet", "A2", "test")
        doc.set_cell("DataSheet", "B2", 42)
        out = os.path.join(OUTPUT_DIR, "test_parse.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        result = doc2.parse()
        assert result["format"] == "xlsx"
        assert len(result["sheets"]) == 2  # Sheet1 + DataSheet
        data_sheet = [s for s in result["sheets"] if s["name"] == "DataSheet"][0]
        assert data_sheet["max_row"] == 2
        assert data_sheet["max_col"] == 2
        doc.close()
        doc2.close()

    def test_get_used_range(self):
        doc = ExcelDocument()
        doc.set_cell("Sheet1", "A1", "X")
        doc.set_cell("Sheet1", "C5", "Y")
        used = doc.get_used_range("Sheet1")
        assert used["max_row"] == 5
        assert used["max_col"] == 3
        doc.close()


class TestExcelToMarkdown:
    """转 Markdown"""

    def test_to_markdown(self):
        doc = ExcelDocument()
        doc.set_row("Sheet1", 1, ["Name", "Age"], header=True)
        doc.set_row("Sheet1", 2, ["Alice", "30"])
        doc.set_row("Sheet1", 3, ["Bob", "25"])
        out = os.path.join(OUTPUT_DIR, "test_md.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        md = doc2.to_markdown("Sheet1")
        assert "## Sheet1" in md
        assert "| Name | Age |" in md
        assert "| Alice | 30 |" in md
        doc.close()
        doc2.close()

    def test_to_markdown_all_sheets(self):
        doc = ExcelDocument()
        doc.add_sheet("Sheet2")
        doc.set_cell("Sheet1", "A1", "S1")
        doc.set_cell("Sheet2", "A1", "S2")
        out = os.path.join(OUTPUT_DIR, "test_md_all.xlsx")
        doc.save(out)

        doc2 = ExcelDocument(out)
        md = doc2.to_markdown()
        assert "## Sheet1" in md
        assert "## Sheet2" in md
        doc.close()
        doc2.close()


class TestExcelXlsxwriter:
    """xlsxwriter 引擎"""

    def test_xlsxwriter_write(self):
        doc = ExcelDocument()
        doc.switch_to_xlsxwriter()
        ws = doc.add_sheet("Data")
        for i in range(100):
            doc.set_cell(ws, f"A{i+1}", i + 1)
        out = os.path.join(OUTPUT_DIR, "test_xlsxwriter.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        # 验证文件大小（100 行数据应该有内容）
        assert os.path.getsize(out) > 1000
        doc.close()

    def test_xlsxwriter_chart(self):
        doc = ExcelDocument()
        doc.switch_to_xlsxwriter()
        ws = doc.add_sheet("Chart")
        for i, v in enumerate([10, 20, 30, 40, 50], start=1):
            doc.set_cell(ws, f"A{i}", f"Item{i}")
            doc.set_cell(ws, f"B{i}", v)
        doc.add_chart(ws, "column", "Test Chart", "B1:B5", "A1:A5")
        out = os.path.join(OUTPUT_DIR, "test_xlsxwriter_chart.xlsx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestExcelRoundTrip:
    """round-trip 验证：写 → 存 → 读 → 解析"""

    def test_full_round_trip(self):
        # 写
        doc = ExcelDocument()
        doc.add_sheet("测试表")
        data = [
            ["产品", "销量", "单价"],
            ["苹果", 100, 5.5],
            ["香蕉", 200, 3.0],
            ["橙子", 150, 4.0],
        ]
        doc.add_table("测试表", "A1:C4", data)
        doc.set_formula("测试表", "D2", "=B2*C2")
        doc.freeze_panes("测试表", "A2")
        out = os.path.join(OUTPUT_DIR, "test_roundtrip.xlsx")
        doc.save(out)
        doc.close()

        # 读
        doc2 = ExcelDocument(out)
        result = doc2.parse()
        sheet = [s for s in result["sheets"] if s["name"] == "测试表"][0]
        assert sheet["max_row"] >= 4
        assert sheet["max_col"] >= 3
        values = {c["cell"]: c["value"] for c in sheet["cell_values"]}
        assert values["A1"] == "产品"
        assert values["B2"] == "100"
        doc2.close()


class TestExcelFromDataFrame:
    """DataFrame 快速导出"""

    def test_from_dataframe(self):
        pytest.importorskip("pandas")
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        out = os.path.join(OUTPUT_DIR, "test_df.xlsx")
        ExcelDocument.from_dataframe(df, out)
        assert os.path.exists(out)

        doc = ExcelDocument(out)
        result = doc.parse()
        sheet = result["sheets"][0]
        values = {c["cell"]: c["value"] for c in sheet["cell_values"]}
        assert values["A2"] == "1"
        assert values["B2"] == "4"
        doc.close()
