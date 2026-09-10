"""FIN-L4 银行流水导入测试 — 解析/分类/去重/服务/CLI/边界情况"""

import os
import sys
import unittest
import tempfile
import json


from fin_l4.db import init_db, get_db
from fin_l4.db.repositories import FamilyRepository, AccountRepository

from fin_l4.services.importer.parser import (
    StatementParser, parse_csv_rows, parse_excel_rows,
    detect_bank, load_templates, ParsedTransaction,
)
from fin_l4.services.importer.classifier import (
    RuleClassifier, ClassificationRule, ClassifyResult,
)
from fin_l4.services.importer import TransactionImporter, ImportResult


# ==================== 辅助函数 ====================

def _make_tmp_csv(content, encoding="utf-8", suffix=".csv"):
    """生成临时 CSV 文件"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding=encoding) as f:
        f.write(content)
    return path


def _setup_db():
    """初始化测试 DB + family + 基础账户"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = init_db(db_path)
    # 用 "default" 作为 family_id（和 API/现有测试风格一致）
    family_id = "default"
    # 手动插入（控制 ID）
    conn.execute(
        "INSERT OR IGNORE INTO fin4_family (id, name, currency) VALUES (?, ?, ?)",
        (family_id, "测试家庭", "CNY"),
    )
    conn.commit()
    # 建账户
    acc_repo = AccountRepository(conn)
    accounts = [
        ("1001", "现金", "ASSET"),
        ("1002", "招商银行", "ASSET"),
        ("1003", "支付宝", "ASSET"),
        ("5001", "餐饮费", "EXPENSE"),
        ("5002", "交通费", "EXPENSE"),
        ("5003", "住房费", "EXPENSE"),
        ("5004", "医疗费", "EXPENSE"),
        ("5099", "其他费用", "EXPENSE"),
        ("4001", "工资收入", "INCOME"),
        ("4002", "投资收益", "INCOME"),
        ("4099", "其他收入", "INCOME"),
    ]
    for code, name, atype in accounts:
        acc_repo.create(family_id, code, name, atype)
    return conn, db_path, family_id


# ==================== 测试 1: CSV 解析 ====================

class TestCSVParser(unittest.TestCase):
    """CSV 解析测试"""

    def test_utf8_csv_comma(self):
        """UTF-8 + 逗号分隔 CSV"""
        csv = "日期,金额,摘要\n2026-09-01,100.00,测试\n"
        path = _make_tmp_csv(csv)
        try:
            parser = StatementParser()
            result = parser.parse_file(path, source_type="auto")
            # 未识别银行但格式正确
            self.assertEqual(result.format, "csv")
            self.assertEqual(result.encoding, "utf-8")
        finally:
            os.unlink(path)

    def test_gbk_encoding(self):
        """GBK 编码 CSV"""
        csv = "记账日期,交易金额,摘要\n2026-09-01,100.00,测试内容\n"
        path = _make_tmp_csv(csv, encoding="gbk")
        try:
            headers, rows, enc = parse_csv_rows(
                open(path, "rb").read(),
                encoding_candidates=["gbk", "utf-8"],
            )
            self.assertEqual(enc, "gbk")
            self.assertEqual(len(rows), 1)
        finally:
            os.unlink(path)

    def test_auto_detect_delimiter_tab(self):
        """自动检测 Tab 分隔符"""
        csv = "日期\t金额\t摘要\n2026-09-01\t100.00\t测试\n"
        path = _make_tmp_csv(csv)
        try:
            headers, rows, _ = parse_csv_rows(open(path, "rb").read())
            self.assertEqual(len(headers), 3)
            self.assertEqual(len(rows), 1)
        finally:
            os.unlink(path)

    def test_amount_with_commas_and_currency(self):
        """金额含逗号和货币符号"""
        from fin_l4.services.importer.parser import _parse_amount
        from decimal import Decimal
        self.assertEqual(_parse_amount("1,234.56"), Decimal("1234.56"))
        self.assertEqual(_parse_amount("¥1,000.00"), Decimal("1000.00"))
        self.assertEqual(_parse_amount("￥99.9"), Decimal("99.9"))
        self.assertEqual(_parse_amount(""), Decimal("0"))


# ==================== 测试 2: Excel 解析 ====================

class TestExcelParser(unittest.TestCase):
    """Excel 解析测试"""

    def setUp(self):
        import openpyxl
        self.openpyxl = openpyxl

    def test_xlsx_parse(self):
        """解析 .xlsx 文件"""
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb = self.openpyxl.Workbook()
            ws = wb.active
            ws.append(["日期", "金额", "摘要"])
            ws.append(["2026-09-01", 100.0, "测试1"])
            ws.append(["2026-09-02", 200.0, "测试2"])
            wb.save(path)

            with open(path, "rb") as f:
                headers, rows = parse_excel_rows(f.read())
            self.assertEqual(len(headers), 3)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["金额"], "100")
        finally:
            os.unlink(path)

    def test_xlsx_date_cell(self):
        """Excel 日期单元格（datetime 类型）"""
        from datetime import date
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb = self.openpyxl.Workbook()
            ws = wb.active
            ws.append(["日期", "金额"])
            ws.append([date(2026, 9, 1), 100.0])
            wb.save(path)

            with open(path, "rb") as f:
                headers, rows = parse_excel_rows(f.read())
            self.assertEqual(rows[0]["日期"], "2026-09-01")
        finally:
            os.unlink(path)


# ==================== 测试 3: 银行模板识别 ====================

class TestBankDetection(unittest.TestCase):
    """银行模板自动识别测试"""

    def test_detect_cmb(self):
        """识别招商银行"""
        templates = load_templates()
        headers = ["记账日期", "交易金额", "币种", "余额", "收支", "对方户名"]
        tpl = detect_bank(headers, templates)
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.bank_id, "cmb")

    def test_detect_alipay(self):
        """识别支付宝"""
        templates = load_templates()
        headers = ["交易创建时间", "金额（元）", "收/支", "交易对方", "商品名称"]
        tpl = detect_bank(headers, templates)
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.bank_id, "alipay")

    def test_detect_unknown(self):
        """未知格式不识别"""
        templates = load_templates()
        headers = ["col1", "col2", "col3"]
        tpl = detect_bank(headers, templates)
        self.assertIsNone(tpl)

    def test_cmb_template_parse(self):
        """招商银行 CSV 完整解析"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-01,08:30:00,15000.00,CNY,15000.00,收入,公司工资代发,12345,8月工资
2026-09-02,12:15:00,-35.50,CNY,14964.50,支出,星巴克咖啡,23456,拿铁
"""
        path = _make_tmp_csv(csv)
        try:
            parser = StatementParser()
            result = parser.parse_file(path, source_type="cmb")
            self.assertEqual(result.bank, "cmb")
            self.assertEqual(result.valid_count, 2)
            txn0 = result.transactions[0]
            self.assertEqual(txn0.direction, "income")
            self.assertEqual(str(txn0.amount), "15000.00")
            self.assertIn("工资", txn0.counterparty)
        finally:
            os.unlink(path)


# ==================== 测试 4: 智能分类引擎 ====================

class TestClassifier(unittest.TestCase):
    """智能分类引擎测试"""

    def setUp(self):
        self.clf = RuleClassifier.default()

    def test_classify_food_high_confidence(self):
        """餐饮 — 高置信度"""
        from decimal import Decimal
        r = self.clf.classify(
            counterparty="星巴克咖啡", direction="expense",
            amount=Decimal("35.00"),
        )
        self.assertEqual(r.category_id, "cat_food")
        self.assertEqual(r.confidence, "high")

    def test_classify_salary(self):
        """工资 — 高置信度"""
        from decimal import Decimal
        r = self.clf.classify(
            counterparty="公司工资代发", summary="8月工资",
            direction="income", amount=Decimal("15000"),
        )
        self.assertEqual(r.category_id, "cat_salary")
        self.assertEqual(r.confidence, "high")

    def test_classify_housing_rent(self):
        """房租 — 高置信度"""
        from decimal import Decimal
        r = self.clf.classify(
            counterparty="房东张先生", summary="9月房租",
            direction="expense", amount=Decimal("5000"),
        )
        self.assertEqual(r.category_id, "cat_housing")
        self.assertEqual(r.confidence, "high")

    def test_classify_transport(self):
        """交通出行"""
        from decimal import Decimal
        r = self.clf.classify(
            counterparty="滴滴出行", direction="expense",
            amount=Decimal("25.00"),
        )
        self.assertEqual(r.category_id, "cat_transport")

    def test_classify_medical(self):
        """医疗"""
        from decimal import Decimal
        r = self.clf.classify(
            counterparty="人民医院", direction="expense",
            amount=Decimal("350.00"),
        )
        self.assertEqual(r.category_id, "cat_medical")
        self.assertEqual(r.confidence, "high")

    def test_classify_default_low_confidence(self):
        """无匹配 -> 默认分类 low"""
        from decimal import Decimal
        r = self.clf.classify(
            description="xyz_unknown_abc",
            direction="expense", amount=Decimal("100"),
        )
        self.assertEqual(r.category_id, "cat_other")
        self.assertEqual(r.confidence, "low")

    def test_amount_range_filter(self):
        """金额范围过滤"""
        from decimal import Decimal
        # 工资规则要求 5000-200000
        r = self.clf.classify(
            counterparty="工资", summary="工资",
            direction="income", amount=Decimal("100"),  # 太少
        )
        self.assertNotEqual(r.category_id, "cat_salary")

    def test_feedback_learning(self):
        """用户反馈学习"""
        self.clf.learn_feedback(
            "神秘商家", "买东西", "cat_other", "cat_shopping",
        )
        self.clf.learn_feedback(
            "神秘商家", "买东西", "cat_other", "cat_shopping",
        )
        suggestion = self.clf.get_feedback_suggestion("神秘商家", "买东西")
        self.assertEqual(suggestion, "cat_shopping")

    def test_add_custom_rule(self):
        """添加自定义规则"""
        from decimal import Decimal
        rule = ClassificationRule(
            id="custom_test",
            category_id="cat_shopping",
            name="测试自定义",
            priority=200,
            confidence_level="high",
            conditions={
                "keywords_in": ["counterparty"],
                "keywords": ["神秘商户"],
                "direction": "expense",
            },
        )
        self.clf.add_rule(rule)
        r = self.clf.classify(
            counterparty="神秘商户旗舰店", direction="expense",
            amount=Decimal("999"),
        )
        self.assertEqual(r.category_id, "cat_shopping")


# ==================== 测试 5: 导入服务 ====================

class TestTransactionImporter(unittest.TestCase):
    """导入服务完整流程测试"""

    def setUp(self):
        self.conn, self.db_path, self.family_id = _setup_db()
        self.importer = TransactionImporter(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_full_import_flow(self):
        """完整导入流程：解析 -> 分类 -> 去重 -> 入库"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-01,08:30:00,15000.00,CNY,15000.00,收入,公司工资代发,12345,8月工资
2026-09-02,12:15:00,-35.50,CNY,14964.50,支出,星巴克咖啡,23456,拿铁
2026-09-03,19:00:00,-88.00,CNY,14876.50,支出,美团外卖平台,34567,午餐
"""
        path = _make_tmp_csv(csv)
        try:
            result = self.importer.import_file(
                self.family_id, path, source_type="cmb",
            )
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.new_count, 3)
            self.assertEqual(result.duplicate_count, 0)
            self.assertEqual(result.error_count, 0)
            # 高置信度应该至少有 2 条（工资+餐饮）
            self.assertGreaterEqual(result.high_confidence, 2)
        finally:
            os.unlink(path)

    def test_duplicate_detection(self):
        """去重：重复导入 0 新增"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-01,08:30:00,15000.00,CNY,15000.00,收入,公司工资代发,12345,8月工资
"""
        path = _make_tmp_csv(csv)
        try:
            # 第一次导入
            r1 = self.importer.import_file(self.family_id, path, source_type="cmb")
            self.assertEqual(r1.new_count, 1)

            # 第二次导入（应全被去重）
            r2 = self.importer.import_file(self.family_id, path, source_type="cmb")
            self.assertEqual(r2.new_count, 0)
            self.assertEqual(r2.duplicate_count, 1)
        finally:
            os.unlink(path)

    def test_preview_then_confirm(self):
        """预览 -> 确认导入流程"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-05,09:30:00,-5000.00,CNY,9876.50,支出,房东张先生,45678,9月房租
"""
        path = _make_tmp_csv(csv)
        try:
            preview = self.importer.preview_import(
                self.family_id, path, source_type="cmb",
            )
            self.assertEqual(preview.new_count, 1)
            self.assertEqual(preview.detected_bank, "cmb")
            self.assertTrue(preview.import_id)

            # 确认导入
            result = self.importer.confirm_import(
                preview.import_id, self.family_id,
            )
            self.assertEqual(result.new_count, 1)
            self.assertEqual(result.status, "completed")
        finally:
            os.unlink(path)

    def test_import_history(self):
        """导入历史记录"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-01,08:30:00,1000.00,CNY,1000.00,收入,测试公司,123,测试
"""
        path = _make_tmp_csv(csv)
        try:
            self.importer.import_file(self.family_id, path, source_type="cmb")
            history = self.importer.get_import_history(self.family_id)
            self.assertGreaterEqual(len(history), 1)
            self.assertEqual(history[0]["status"], "completed")
        finally:
            os.unlink(path)


# ==================== 测试 6: 边界情况 ====================

class TestEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def setUp(self):
        self.conn, self.db_path, self.family_id = _setup_db()
        self.importer = TransactionImporter(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_empty_file(self):
        """空文件"""
        path = _make_tmp_csv("")
        try:
            result = self.importer.import_file(self.family_id, path, source_type="cmb")
            self.assertEqual(result.error_count, 0)
            self.assertEqual(result.new_count, 0)
        finally:
            os.unlink(path)

    def test_malformed_csv(self):
        """格式错误的 CSV"""
        csv = "乱码内容\nasdf,qwer\n"
        path = _make_tmp_csv(csv)
        try:
            result = self.importer.preview_import(self.family_id, path, source_type="auto")
            # 可能识别为 unknown 或解析出 0 条有效
            self.assertIsNotNone(result)
        finally:
            os.unlink(path)

    def test_zero_amount_rows_skipped(self):
        """金额为 0 的行跳过"""
        csv = """记账日期,交易时间,交易金额,币种,余额,收支,对方户名,对方账号,摘要
2026-09-01,08:00:00,0.00,CNY,0,收入,测试,123,零金额测试
2026-09-02,08:00:00,50.00,CNY,50,支出,星巴克,456,咖啡
"""
        path = _make_tmp_csv(csv)
        try:
            result = self.importer.import_file(self.family_id, path, source_type="cmb")
            self.assertEqual(result.new_count, 1)  # 只有 50 元那条
        finally:
            os.unlink(path)

    def test_alipay_format_skip_rows(self):
        """支付宝格式（有 skip_rows 前导行）"""
        csv = """支付宝（中国）网络技术有限公司  电子客户回单
--------------------------
账号:xxxxxxxxxx
起始日期:2026-09-01
交易创建时间,金额（元）,收/支,交易对方,商品名称,当前状态
2026-09-01 12:00:00,35.50,支出,星巴克,拿铁咖啡,交易成功
2026-09-02 18:30:00,88.00,支出,美团外卖,晚餐,交易成功
"""
        path = _make_tmp_csv(csv)
        try:
            result = self.importer.import_file(self.family_id, path, source_type="alipay")
            self.assertEqual(result.new_count, 2)
        finally:
            os.unlink(path)


# ==================== 入口 ====================

if __name__ == "__main__":
    unittest.main(verbosity=2)
