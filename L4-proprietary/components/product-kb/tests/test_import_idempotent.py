"""P3 导入幂等 + 身份别名测试（真实临时 DB + 真实 xlsx）。"""
import os
import tempfile
import unittest

import openpyxl

from product_kb.db import ProductKBDB
from product_kb.io import PriceImporter
from product_kb.identity import ProductIdentityService

HEADERS = ["ID", "销售模式", "销售状态", "注意事项", "货物或应税服务名称",
           "是否定制", "关联产品编码", "产品服务编码", "产品服务类别", "类别",
           "产品服务名称", "产品服务型号", "产品服务单价", "报价基准",
           "服务描述", "折扣类型", "产品线类别", "启用状态"]


def make_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    wb.save(path)


def sample_row(code, name, line="安全服务产品线", sale_mode="服务"):
    r = [None] * 18
    r[1] = sale_mode
    r[2] = "正常销售"
    r[4] = name
    r[7] = code
    r[8] = "安全服务"
    r[9] = "某类别"
    r[10] = name
    r[11] = "MODEL-X"
    r[12] = 10000.0
    r[13] = "套"
    r[16] = line
    r[17] = "启用"
    return r


class IdempotentImportTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dbp = os.path.join(self.tmpdir, "t.db")
        self.xlsx = os.path.join(self.tmpdir, "price.xlsx")
        make_xlsx(self.xlsx, [
            sample_row("SVC-001", "应用安全测评V5.0维保服务"),
            sample_row("SVC-002", "API安全平台软件V3.0", line="安全保护产品线",
                       sale_mode="软件"),
        ])

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def _counts(self, db):
        p = db.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        s = db.execute("SELECT COUNT(*) FROM sku").fetchone()[0]
        return p, s

    def test_triple_import_idempotent(self):
        db = ProductKBDB(self.dbp)
        db.init_db()
        imp = PriceImporter(db)
        first = imp.import_from_xlsx(self.xlsx)
        self.assertEqual(first["products"], 2)
        c1 = self._counts(db)

        for _ in range(2):
            imp2 = PriceImporter(db)
            stats = imp2.import_from_xlsx(self.xlsx)
            self.assertEqual(stats["products"], 0, "重复导入不应新建产品")
            self.assertEqual(self._counts(db), c1, "产品/SKU 数量必须稳定")

        # 身份与别名
        svc = ProductIdentityService(db)
        idents = svc.list()
        self.assertEqual(len(idents), 2)
        # price_excel 别名可解析
        self.assertEqual(
            svc.resolve("price_excel", "API安全平台软件V3.0") is not None, True)
        # internal 编码别名
        self.assertEqual(
            svc.resolve("internal", "SVC-002") is not None, True)
        db.close()

    def test_new_product_on_different_name(self):
        db = ProductKBDB(self.dbp)
        db.init_db()
        PriceImporter(db).import_from_xlsx(self.xlsx)
        # 追加一条新产品的 xlsx
        x2 = os.path.join(self.tmpdir, "p2.xlsx")
        make_xlsx(x2, [sample_row("SVC-003", "内容安全审核平台V2.0",
                                  line="内容安全产品线")])
        stats = PriceImporter(db).import_from_xlsx(x2)
        self.assertEqual(stats["products"], 1)
        self.assertEqual(self._counts(db)[0], 3)
        db.close()


if __name__ == "__main__":
    unittest.main()
