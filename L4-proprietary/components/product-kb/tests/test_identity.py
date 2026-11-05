"""P1 权威身份层单测（真实临时 DB + 真实命令）。"""
import os
import tempfile
import unittest

from product_kb.db import ProductKBDB
from product_kb.identity import canonical_key, ProductIdentityService


class CanonicalKeyTest(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(canonical_key("API 安全平台 V3.0"),
                         canonical_key("ＡＰＩ安全平台V3.0"))
        self.assertEqual(canonical_key("全渠道应用安全监测软件 V6.0"),
                         "全渠道应用安全监测软件v6.0")

    def test_version_distinguishes(self):
        k4 = canonical_key("移动应用安全监测标准版V4.0软件维保服务")
        k5 = canonical_key("移动应用安全监测标准版V5.0软件维保服务")
        self.assertNotEqual(k4, k5)


class IdentityServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = ProductKBDB(self.tmp.name)
        self.db.init_db()
        self.db.init_identity_tables()
        self.svc = ProductIdentityService(self.db)
        # 建一条产品线 + 产品
        self.line_id = self.db.get_or_create_product_line("线", "line_x")
        self.pid = self.db.create_product(
            line_id=self.line_id, category_id=None, name="API安全平台软件V3.0",
            aliases=None, code="C-001", version_latest="3.0", type_="product",
            status="正常销售", summary=None)
        self.pid2 = self.db.create_product(
            line_id=self.line_id, category_id=None, name="API安全平台软件V4.0",
            aliases=None, code="C-002", version_latest="4.0", type_="product",
            status="正常销售", summary=None)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_register_and_get(self):
        iid = self.svc.register(self.pid)
        got = self.svc.get_by_product_id(self.pid)
        self.assertEqual(got["canonical_key"], "api安全平台软件v3.0")
        self.assertEqual(got["status"], "active")

    def test_register_duplicate_product(self):
        import sqlite3
        self.svc.register(self.pid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.svc.register(self.pid)

    def test_alias_resolve_cwa(self):
        iid = self.svc.register(self.pid)
        self.svc.add_alias(iid, "contract_text", "API安全平司软件V3.0", 0.4)
        # 命中
        self.assertEqual(self.svc.resolve("contract_text", "API安全平司软件V3.0"),
                         self.pid)
        # 未命中 -> None
        self.assertIsNone(self.svc.resolve("contract_text", "不存在的产品xyz"))

    def test_alias_unique(self):
        import sqlite3
        iid = self.svc.register(self.pid)
        iid2 = self.svc.register(self.pid2)
        self.svc.add_alias(iid, "contract_text", "DUP")
        with self.assertRaises(sqlite3.IntegrityError):
            self.svc.add_alias(iid2, "contract_text", "DUP")

    def test_merge_transfers_aliases(self):
        i1 = self.svc.register(self.pid)
        i2 = self.svc.register(self.pid2)
        self.svc.add_alias(i1, "contract_text", "旧名V3")
        self.svc.add_alias(i2, "contract_text", "新名V4")
        res = self.svc.merge(i1, i2, actor="rex")
        self.assertEqual(res["into_id"], i2)
        # alias 已转移：旧名现在解析到 pid2
        self.assertEqual(self.svc.resolve("contract_text", "旧名V3"), self.pid2)
        # 源身份 merged
        self.assertEqual(self.svc._get(i1)["status"], "merged")
        # list active 只剩 i2
        actives = self.svc.list(status="active")
        self.assertEqual([a["id"] for a in actives], [i2])

    def test_merge_rejects_double(self):
        i1 = self.svc.register(self.pid)
        i2 = self.svc.register(self.pid2)
        self.svc.merge(i1, i2, "rex")
        with self.assertRaises(ValueError):
            self.svc.merge(i1, i2, "rex")

    def test_unmerge_rollback(self):
        i1 = self.svc.register(self.pid)
        i2 = self.svc.register(self.pid2)
        self.svc.add_alias(i1, "contract_text", "旧名V3")
        self.svc.merge(i1, i2, "rex")
        self.svc.unmerge(i1)
        self.assertEqual(self.svc._get(i1)["status"], "active")
        self.assertIsNone(self.svc._get(i1)["merged_into"])
        # alias 转回：旧名解析回 pid
        self.assertEqual(self.svc.resolve("contract_text", "旧名V3"), self.pid)

    def test_idempotent_ddl(self):
        # 再跑一次建表无副作用
        self.db.init_identity_tables()
        self.assertEqual(len(self.svc.list()), 0)


if __name__ == "__main__":
    unittest.main()
