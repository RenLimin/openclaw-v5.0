"""
Database operations for Product KB
"""
import sqlite3
import re
import datetime
from typing import Optional, List, Dict, Any, Tuple


class ProductKBDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def init_db(self):
        """Initialize database tables"""
        if not self.conn:
            self.connect()

        # Create tables
        cursor = self.conn.cursor()

        # product_line
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_line (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """)

        # product_category
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (line_id) REFERENCES product_line (id),
            FOREIGN KEY (parent_id) REFERENCES product_category (id)
        )
        """)

        # product
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id INTEGER NOT NULL,
            category_id INTEGER,
            family TEXT,
            name TEXT NOT NULL,
            aliases TEXT,
            code TEXT UNIQUE,
            version_latest TEXT,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (line_id) REFERENCES product_line (id),
            FOREIGN KEY (category_id) REFERENCES product_category (id)
        )
        """)

        # sku
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sku (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            sku_code TEXT UNIQUE NOT NULL,
            model TEXT,
            unit_price REAL,
            price_base TEXT,
            discount_type TEXT,
            sale_mode TEXT,
            sale_status TEXT,
            notes TEXT,
            service_desc TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (product_id) REFERENCES product (id)
        )
        """)

        # doc_asset
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doc_asset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            doc_type TEXT NOT NULL,
            original_path TEXT NOT NULL,
            relative_path TEXT,
            file_name TEXT NOT NULL,
            version TEXT,
            format TEXT NOT NULL,
            md5 TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (product_id) REFERENCES product (id)
        )
        """)

        # doc_chunk
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doc_chunk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            title TEXT,
            text TEXT NOT NULL,
            embedding BLOB,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (doc_id) REFERENCES doc_asset (id)
        )
        """)

        # kb_relation
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_relation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id INTEGER NOT NULL,
            metadata TEXT,
            created_at DATETIME
        )
        """)

        # Create FTS for product name
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS product_fts USING fts5(name);
        """)

        # Create FTS for doc chunk
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text);
        """)

        self.conn.commit()
        cursor.close()

    def get_now(self) -> str:
        return datetime.datetime.now().isoformat()

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        if not self.conn:
            self.connect()
        return self.conn.execute(sql, params)

    def commit(self):
        if self.conn:
            self.conn.commit()

    # --- Product line operations ---
    def get_or_create_product_line(self, name: str, code: str, description: str = None) -> int:
        """Get existing product line or create new"""
        cursor = self.execute("SELECT id FROM product_line WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            return row[0]

        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO product_line (name, code, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """, (name, code, description, now, now))
        self.commit()
        return cursor.lastrowid

    # --- Category operations ---
    def get_or_create_category(self, line_id: int, name: str, parent_id: int = None) -> int:
        cursor = self.execute("""
        SELECT id FROM product_category WHERE line_id = ? AND name = ?
        """, (line_id, name))
        row = cursor.fetchone()
        if row:
            return row[0]

        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO product_category (line_id, name, parent_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """, (line_id, name, parent_id, now, now))
        self.commit()
        return cursor.lastrowid

    # --- Product operations ---
    def get_product_by_name(self, name: str) -> Optional[sqlite3.Row]:
        cursor = self.execute("""
        SELECT * FROM product WHERE name = ?
        """, (name,))
        return cursor.fetchone()

    def create_product(self, line_id: int, category_id: Optional[int], name: str,
                       aliases: Optional[str], code: Optional[str], version_latest: Optional[str],
                       type_: str, status: str, summary: Optional[str],
                       family: Optional[str] = None) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO product (line_id, category_id, family, name, aliases, code, version_latest,
                            type, status, summary, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (line_id, category_id, family, name, aliases, code, version_latest,
              type_, status, summary, now, now))
        self.commit()

        # Insert into FTS
        cursor.execute("INSERT INTO product_fts (rowid, name) VALUES (?, ?)",
                       (cursor.lastrowid, name))
        self.commit()
        return cursor.lastrowid

    def update_product(self, product_id: int, **kwargs):
        """Update product fields"""
        if not kwargs:
            return
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        kwargs["updated_at"] = self.get_now()
        values = list(kwargs.values())
        values.append(product_id)
        sql = f"UPDATE product SET {set_clause} WHERE id = ?"
        self.execute(sql, values)
        self.commit()

        # Update FTS if name changed
        if "name" in kwargs:
            self.execute("UPDATE product_fts SET name = ? WHERE rowid = ?",
                         (kwargs["name"], product_id))
            self.commit()

    # --- SKU operations ---
    def create_or_update_sku(self, product_id: int, sku_code: str, model: Optional[str],
                             unit_price: Optional[float], price_base: Optional[str],
                             discount_type: Optional[str], sale_mode: Optional[str],
                             sale_status: Optional[str], notes: Optional[str],
                             service_desc: Optional[str]) -> int:
        cursor = self.execute("SELECT id FROM sku WHERE sku_code = ?", (sku_code,))
        row = cursor.fetchone()
        now = self.get_now()
        if row:
            # Update
            self.execute("""
            UPDATE sku SET product_id = ?, model = ?, unit_price = ?, price_base = ?,
                        discount_type = ?, sale_mode = ?, sale_status = ?, notes = ?,
                        service_desc = ?, updated_at = ?
            WHERE id = ?
            """, (product_id, model, unit_price, price_base, discount_type, sale_mode,
                  sale_status, notes, service_desc, now, row[0]))
            self.commit()
            return row[0]
        else:
            # Insert: 12 columns (id autoinc)
            # product_id, sku_code, model, unit_price, price_base, discount_type, 
            # sale_mode, sale_status, notes, service_desc, created_at, updated_at
            # → 11 + 2 = 13 columns? No: id autoinc, so 12 values needed. Wait:
            # Columns after id: 12 columns (see CREATE TABLE above)
            # So need 12 values
            cursor = self.execute("""
            INSERT INTO sku (
                product_id, sku_code, model, unit_price, price_base, 
                discount_type, sale_mode, sale_status, notes, 
                service_desc, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id, 
                sku_code, 
                model, 
                unit_price, 
                price_base, 
                discount_type, 
                sale_mode, 
                sale_status, 
                notes, 
                service_desc, 
                now, 
                now
            ))
            self.commit()
            return cursor.lastrowid

    # --- Doc asset operations ---
    def create_doc_asset(self, product_id: int, doc_type: str, original_path: str,
                         relative_path: Optional[str], file_name: str, version: Optional[str],
                         format_: str, md5: str) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO doc_asset (product_id, doc_type, original_path, relative_path,
                              file_name, version, format, md5, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (product_id, doc_type, original_path, relative_path, file_name,
              version, format_, md5, now, now))
        self.commit()
        return cursor.lastrowid

    def get_doc_by_md5(self, md5: str) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_asset WHERE md5 = ?", (md5,))
        return cursor.fetchone()

    # --- Doc chunk operations ---
    def create_doc_chunk(self, doc_id: int, chunk_index: int, title: Optional[str],
                         text: str, embedding: Optional[bytes]) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO doc_chunk (doc_id, chunk_index, title, text, embedding, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, chunk_index, title, text, embedding, now, now))

        chunk_id = cursor.lastrowid
        cursor.execute("INSERT INTO chunk_fts (rowid, text) VALUES (?, ?)", (chunk_id, text))
        self.commit()
        return chunk_id

    def delete_doc_chunks(self, doc_id: int):
        """Delete all chunks for a doc (for re-chunking)"""
        cursor = self.execute("SELECT id FROM doc_chunk WHERE doc_id = ?", (doc_id,))
        for row in cursor.fetchall():
            self.execute("DELETE FROM chunk_fts WHERE rowid = ?", (row[0],))
        self.execute("DELETE FROM doc_chunk WHERE doc_id = ?", (doc_id,))
        self.commit()

    # --- Query operations ---
    @staticmethod
    def _sanitize_fts_query(query: str, *, prefix: bool = False) -> str:
        """Sanitize a user query for FTS5 MATCH: strip FTS5 special chars and quote terms.

        Args:
            prefix: True 时追加 ``*`` 前缀通配。FTS5 unicode61 对中文按整串生成
                    单个 token，纯 phrase 只能整名精确命中；prefix 让"同系列前缀名"
                    （如 安全测评服务 → 安全测评服务企业版/专业版）可被召回，
                    供合同标的"近似匹配"使用。语义 chunks 搜索仍用 phrase（prefix=False）。
        """
        # FTS5 special characters that break MATCH syntax
        q = re.sub(r'["\'()\[\]{}*?:^#-]', ' ', query)
        # Collapse whitespace
        q = re.sub(r'\s+', ' ', q).strip()
        if not q:
            return '""'
        # Wrap full string as a phrase to treat it as literal tokens
        phrase = '"' + q.replace('"', ' ') + '"'
        return phrase + '*' if prefix else phrase

    def fts_search_products(self, query: str, limit: int = 20) -> List[int]:
        """FTS search products by name, return product ids.

        用 prefix 匹配召回同系列近似名（中文 unicode61 整串单 token 的对策），
        由上层 ContractMatcher 按相似度分数区分 satisfied / partial / unsatisfied。
        """
        if not self.conn:
            self.connect()
        clean = self._sanitize_fts_query(query, prefix=True)
        cursor = self.conn.execute("""
        SELECT rowid FROM product_fts WHERE name MATCH ? LIMIT ?
        """, (clean, limit))
        return [row[0] for row in cursor.fetchall()]

    def fts_search_chunks(self, query: str, limit: int = 20) -> List[int]:
        """FTS search chunks by text, return chunk ids"""
        if not self.conn:
            self.connect()
        clean = self._sanitize_fts_query(query)
        cursor = self.conn.execute("""
        SELECT rowid FROM chunk_fts WHERE text MATCH ? LIMIT ?
        """, (clean, limit))
        return [row[0] for row in cursor.fetchall()]

    def find_products_by_name(self, name: str, limit: int = 20) -> List[sqlite3.Row]:
        """Find products by exact or fuzzy name match (LIKE), returns product rows."""
        if not self.conn:
            self.connect()
        cursor = self.conn.execute("""
        SELECT * FROM product WHERE name = ? OR name LIKE ? OR aliases LIKE ?
        LIMIT ?
        """, (name, '%' + name + '%', '%' + name + '%', limit))
        return cursor.fetchall()

    def get_docs_by_product(self, product_id: int) -> List[sqlite3.Row]:
        """Get all doc_asset rows for a product."""
        if not self.conn:
            self.connect()
        cursor = self.conn.execute("""
        SELECT * FROM doc_asset WHERE product_id = ? ORDER BY doc_type
        """, (product_id,))
        return cursor.fetchall()

    def get_chunks_by_doc(self, doc_id: int, limit: int = 10) -> List[sqlite3.Row]:
        """Get first N chunks of a document."""
        if not self.conn:
            self.connect()
        cursor = self.conn.execute("""
        SELECT * FROM doc_chunk WHERE doc_id = ? ORDER BY chunk_index LIMIT ?
        """, (doc_id, limit))
        return cursor.fetchall()

    def get_product_knowledge(self, name: str, chunk_limit: int = 3) -> List[Dict]:
        """Deterministic product knowledge lookup: product -> docs -> chunks.
        Falls back to same-family products' docs when the product has no docs.
        Returns list of dicts with product/doc/chunk info."""
        products = self.find_products_by_name(name, limit=3)
        results = []
        if not products:
            # 名字没直接命中：尝试 fuzzy 前缀
            products = self.find_products_by_name(name[:max(1, len(name) - 3)], limit=3)
        for p in products:
            docs = self.get_docs_by_product(p['id'])
            if not docs and p['family']:
                # 同族回退：找同族其他有文档的产品
                fam_rows = self.execute(
                    "SELECT * FROM product WHERE family = ? ORDER BY id", (p['family'],)
                ).fetchall()
                for fr in fam_rows:
                    if fr['id'] == p['id']:
                        continue
                    docs = self.get_docs_by_product(fr['id'])
                    if docs:
                        break
            for d in docs[:2]:  # 每个产品最多取 2 个文档
                chunks = self.get_chunks_by_doc(d['id'], chunk_limit)
                for c in chunks:
                    results.append({
                        'product': dict(p),
                        'doc': dict(d),
                        'chunk': dict(c),
                        'similarity': None,
                    })
                if len(results) >= chunk_limit * 2:
                    break
            if results:
                break
        if not results:
            # FTS 关键词回退：清洗产品名后分段尝试 trigram 子串匹配
            import re as _re
            clean = _re.sub(r'[Vv][0-9.]+|（.*?）|\(.*?\)|[0-9.]+', '', name).strip()
            # 逐级截短关键词，提高命中率
            candidates = []
            if clean:
                candidates.append(clean)
                candidates.append(clean[:6])
                candidates.append(clean[:4])
            seen_docs = set()
            for kw in candidates:
                if not kw or len(kw) < 3:
                    continue
                try:
                    cursor = self.conn.execute(
                        "SELECT rowid FROM chunk_fts WHERE text MATCH ? LIMIT 6", (kw,)
                    )
                except sqlite3.OperationalError:
                    continue
                for (chunk_id,) in cursor.fetchall():
                    chunk = self.get_chunk(chunk_id)
                    if not chunk:
                        continue
                    if chunk['doc_id'] in seen_docs:
                        continue
                    seen_docs.add(chunk['doc_id'])
                    d = self.get_doc(chunk['doc_id'])
                    p_row = self.execute(
                        "SELECT * FROM product WHERE id = ?", (d['product_id'],)
                    ).fetchone()
                    results.append({
                        'product': dict(p_row) if p_row else {'name': '未知'},
                        'doc': dict(d),
                        'chunk': dict(chunk),
                        'similarity': None,
                    })
                    if len(results) >= chunk_limit * 2:
                        return results
        return results

    def get_product(self, product_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM product WHERE id = ?", (product_id,))
        return cursor.fetchone()

    def get_sku(self, sku_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM sku WHERE id = ?", (sku_id,))
        return cursor.fetchone()

    def get_chunk(self, chunk_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_chunk WHERE id = ?", (chunk_id,))
        return cursor.fetchone()

    def get_doc(self, doc_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_asset WHERE id = ?", (doc_id,))
        return cursor.fetchone()

    def list_products_by_line(self, line_id: int, status: str = None) -> List[sqlite3.Row]:
        if status:
            cursor = self.execute("""
            SELECT * FROM product WHERE line_id = ? AND status = ?
            """, (line_id, status))
        else:
            cursor = self.execute("SELECT * FROM product WHERE line_id = ?", (line_id,))
        return cursor.fetchall()

    def count_products(self) -> int:
        cursor = self.execute("SELECT COUNT(*) FROM product")
        return cursor.fetchone()[0]

    def count_skus(self) -> int:
        cursor = self.execute("SELECT COUNT(*) FROM sku")
        return cursor.fetchone()[0]

    def count_docs(self) -> int:
        cursor = self.execute("SELECT COUNT(*) FROM doc_asset")
        return cursor.fetchone()[0]

    def count_chunks(self) -> int:
        cursor = self.execute("SELECT COUNT(*) FROM doc_chunk")
        return cursor.fetchone()[0]

    def get_all_product_lines(self) -> List[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM product_line ORDER BY name")
        return cursor.fetchall()
