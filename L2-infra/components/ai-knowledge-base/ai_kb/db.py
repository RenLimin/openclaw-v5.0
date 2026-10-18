"""
Generic Database operations for Enterprise AI Knowledge Base
L2 infrastructure component, generic for any domain KB
"""
import sqlite3
import re
import datetime
from typing import Optional, List, Dict, Any, Tuple


class AIKB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        # check_same_thread=False: FastAPI async endpoints may run on
        # different threads than the connection creator (event loop vs threadpool)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def init_db(self):
        """Initialize database tables for generic AI KB"""
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()

        # Domain: 顶级域 (产品、合同、文档等不同知识库实例)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS domain (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """)

        # Collection: 域内分类 (产品线、合同分类、文档分类)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (domain_id) REFERENCES domain (id),
            FOREIGN KEY (parent_id) REFERENCES collection (id)
        )
        """)

        # Entity: 实体 (产品、合同、文档)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER NOT NULL,
            collection_id INTEGER,
            entity_type TEXT NOT NULL,
            family TEXT,
            name TEXT NOT NULL,
            aliases TEXT,
            code TEXT UNIQUE,
            version_latest TEXT,
            status TEXT,
            summary TEXT,
            metadata TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (domain_id) REFERENCES domain (id),
            FOREIGN KEY (collection_id) REFERENCES collection (id)
        )
        """)

        # Attribute: 结构化属性 (SKU、价格等，通用键值对存储)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_attr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            attr_key TEXT NOT NULL,
            attr_value TEXT,
            attr_type TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (entity_id) REFERENCES entity (id)
        )
        """)

        # Document asset: 文档资产，关联到实体
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doc_asset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            doc_type TEXT NOT NULL,
            original_path TEXT NOT NULL,
            relative_path TEXT,
            file_name TEXT NOT NULL,
            version TEXT,
            format TEXT NOT NULL,
            md5 TEXT,
            permissions TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (entity_id) REFERENCES entity (id)
        )
        """)

        # Document chunk: 文档切片，存储文本+向量
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doc_chunk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            title TEXT,
            text TEXT NOT NULL,
            embedding BLOB,
            permissions TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (doc_id) REFERENCES doc_asset (id)
        )
        """)

        # Knowledge relation: 知识图谱关系，任意实体间关联
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_relation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id INTEGER NOT NULL,
            metadata TEXT,
            permissions TEXT,
            created_at DATETIME
        )
        """)

        # Knowledge feedback: 用户对查询/答案的有效性反馈
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT NOT NULL,
            answer_text TEXT,
            feedback_type TEXT NOT NULL, -- useful / not_useful / incorrect
            feedback_comment TEXT,
            entity_id INTEGER, -- 关联到相关实体 (可选)
            doc_id INTEGER, -- 关联到相关文档 (可选)
            chunk_id INTEGER, -- 关联到相关切片 (可选)
            user_id TEXT, -- 反馈人 (可选)
            created_at DATETIME NOT NULL,
            FOREIGN KEY (entity_id) REFERENCES entity (id),
            FOREIGN KEY (doc_id) REFERENCES doc_asset (id),
            FOREIGN KEY (chunk_id) REFERENCES doc_chunk (id)
        )
        """)

        # Migration version: track database schema version
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_migration (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at DATETIME NOT NULL
        )
        """)

        # Audit log: all operations are logged
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            user_id TEXT,
            operation_type TEXT NOT NULL,
            object_type TEXT,
            object_id INTEGER,
            request_id TEXT,
            risk_level TEXT,
            rule_triggered TEXT,
            action_taken TEXT NOT NULL,
            details TEXT,
            created_at DATETIME NOT NULL
        )
        """)

        # Template: reusable template for new KB instances
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            author TEXT,
            category TEXT,
            config_yaml TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)

        # FTS indexes
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5(name, aliases);
        """)
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

    # --- Domain operations ---
    def get_or_create_domain(self, name: str, code: str, description: str = None) -> int:
        cursor = self.execute("SELECT id FROM domain WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            return row[0]

        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO domain (name, code, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """, (name, code, description, now, now))
        self.commit()
        return cursor.lastrowid

    # --- Collection operations ---
    def get_or_create_collection(self, domain_id: int, name: str, parent_id: int = None) -> int:
        cursor = self.execute("""
        SELECT id FROM collection WHERE domain_id = ? AND name = ?
        """, (domain_id, name))
        row = cursor.fetchone()
        if row:
            return row[0]

        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO collection (domain_id, name, parent_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """, (domain_id, name, parent_id, now, now))
        self.commit()
        return cursor.lastrowid

    # --- Entity operations ---
    def get_entity_by_name(self, domain_id: int, name: str) -> Optional[sqlite3.Row]:
        cursor = self.execute("""
        SELECT * FROM entity WHERE domain_id = ? AND name = ?
        """, (domain_id, name))
        return cursor.fetchone()

    def create_entity(self, domain_id: int, collection_id: Optional[int], entity_type: str,
                      family: Optional[str], name: str, aliases: Optional[str], code: Optional[str],
                      version_latest: Optional[str], status: Optional[str], summary: Optional[str],
                      metadata: Optional[str] = None) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO entity (domain_id, collection_id, entity_type, family, name, aliases, code,
                            version_latest, status, summary, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (domain_id, collection_id, entity_type, family, name, aliases, code,
              version_latest, status, summary, metadata, now, now))
        self.commit()

        # Insert into FTS
        cursor.execute("INSERT INTO entity_fts (rowid, name, aliases) VALUES (?, ?, ?)",
                       (cursor.lastrowid, name, aliases or ""))
        self.commit()
        return cursor.lastrowid

    def update_entity(self, entity_id: int, **kwargs):
        if not kwargs:
            return
        kwargs["updated_at"] = self.get_now()
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(entity_id)
        sql = f"UPDATE entity SET {set_clause} WHERE id = ?"
        self.execute(sql, values)
        self.commit()

        # Update FTS if name/aliases changed
        if "name" in kwargs or "aliases" in kwargs:
            name = kwargs.get("name", "")
            aliases = kwargs.get("aliases", "")
            self.execute("UPDATE entity_fts SET name = ?, aliases = ? WHERE rowid = ?",
                         (name, aliases or "", entity_id))
            self.commit()

    # --- Entity attribute operations ---
    def set_entity_attr(self, entity_id: int, attr_key: str, attr_value: str, attr_type: str = "text"):
        """Set or update entity attribute"""
        cursor = self.execute("""
        SELECT id FROM entity_attr WHERE entity_id = ? AND attr_key = ?
        """, (entity_id, attr_key))
        row = cursor.fetchone()
        now = self.get_now()
        if row:
            self.execute("""
            UPDATE entity_attr SET attr_value = ?, attr_type = ?, updated_at = ?
            WHERE id = ?
            """, (attr_value, attr_type, now, row[0]))
        else:
            self.execute("""
            INSERT INTO entity_attr (entity_id, attr_key, attr_value, attr_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (entity_id, attr_key, attr_value, attr_type, now, now))
        self.commit()

    def get_entity_attrs(self, entity_id: int) -> List[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM entity_attr WHERE entity_id = ?", (entity_id,))
        return cursor.fetchall()

    # --- Doc asset operations ---
    def create_doc_asset(self, entity_id: int, doc_type: str, original_path: str,
                         relative_path: Optional[str], file_name: str, version: Optional[str],
                         format_: str, md5: str, permissions: Optional[str] = None) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO doc_asset (entity_id, doc_type, original_path, relative_path,
                              file_name, version, format, md5, permissions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_id, doc_type, original_path, relative_path, file_name,
              version, format_, md5, permissions, now, now))
        self.commit()
        return cursor.lastrowid

    def get_doc_by_md5(self, md5: str) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_asset WHERE md5 = ?", (md5,))
        return cursor.fetchone()

    # --- Doc chunk operations ---
    def create_doc_chunk(self, doc_id: int, chunk_index: int, title: Optional[str],
                         text: str, embedding: Optional[bytes], permissions: Optional[str] = None) -> int:
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO doc_chunk (doc_id, chunk_index, title, text, embedding, permissions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, chunk_index, title, text, embedding, permissions, now, now))

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

    # --- Feedback operations ---
    def add_feedback(self, query_text: str, feedback_type: str, answer_text: str = None,
                     feedback_comment: str = None, entity_id: int = None, doc_id: int = None,
                     chunk_id: int = None, user_id: str = None) -> int:
        """Add user feedback for a query/answer"""
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO kb_feedback (query_text, answer_text, feedback_type, feedback_comment,
                               entity_id, doc_id, chunk_id, user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (query_text, answer_text, feedback_type, feedback_comment,
              entity_id, doc_id, chunk_id, user_id, now))
        self.commit()
        return cursor.lastrowid

    def get_feedback_stats_for_entity(self, entity_id: int) -> Dict[str, int]:
        """Get feedback statistics for an entity"""
        cursor = self.execute("""
        SELECT feedback_type, COUNT(*) FROM kb_feedback WHERE entity_id = ? GROUP BY feedback_type
        """, (entity_id,))
        stats = {}
        for row in cursor.fetchall():
            stats[row[0]] = row[1]
        return stats

    def get_feedback_stats_for_doc(self, doc_id: int) -> Dict[str, int]:
        """Get feedback statistics for a document"""
        cursor = self.execute("""
        SELECT feedback_type, COUNT(*) FROM kb_feedback WHERE doc_id = ? GROUP BY feedback_type
        """, (doc_id,))
        stats = {}
        for row in cursor.fetchall():
            stats[row[0]] = row[1]
        return stats

    def list_low_score_knowledge(self, domain_id: int, threshold: int = 1) -> List[sqlite3.Row]:
        """List entities that have more than threshold negative feedback"""
        cursor = self.execute("""
        SELECT e.id, e.name, e.domain_id, 
               COUNT(CASE WHEN f.feedback_type IN ('not_useful', 'incorrect') THEN 1 END) as negative_count,
               COUNT(*) as total_count
        FROM entity e
        LEFT JOIN kb_feedback f ON e.id = f.entity_id
        WHERE e.domain_id = ?
        GROUP BY e.id
        HAVING negative_count >= ?
        ORDER BY negative_count DESC
        """, (domain_id, threshold))
        return cursor.fetchall()

    # --- Helper sanitize for FTS ---
    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Sanitize a user query for FTS5 MATCH: strip special chars and quote terms."""
        q = re.sub(r'["\'()\[\]{}*?:^#-]', ' ', query)
        q = re.sub(r'\s+', ' ', q).strip()
        if not q:
            return '""'
        return '"' + q.replace('"', ' ') + '"'

    # --- Query operations ---
    def fts_search_entities(self, domain_id: int, query: str, limit: int = 20, include_expired: bool = False) -> List[int]:
        """FTS search entities by name/aliases, return entity ids"""
        clean = self._sanitize_fts_query(query)
        # Join with domain filter to get only current domain results.
        # Note: FTS5 MATCH cannot be used inside a subquery (rowid IN (...)),
        # so we use a JOIN instead.
        extra_where = "" if include_expired else "AND (e.status IS NULL OR e.status != 'expired')"
        sql = f"""
        SELECT e.id FROM entity_fts f
        JOIN entity e ON e.id = f.rowid
        WHERE (f.name MATCH ? OR f.aliases MATCH ?)
        AND e.domain_id = ? {extra_where}
        LIMIT ?
        """
        try:
            cursor = self.conn.execute(sql, (clean, clean, domain_id, limit))
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Fallback: try name-only match (some FTS5 setups reject OR on MATCH)
            sql2 = f"""
            SELECT e.id FROM entity_fts f
            JOIN entity e ON e.id = f.rowid
            WHERE f.name MATCH ?
            AND e.domain_id = ? {extra_where}
            LIMIT ?
            """
            try:
                cursor = self.conn.execute(sql2, (clean, domain_id, limit))
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                return []

    def fts_search_chunks(self, query: str, limit: int = 20) -> List[int]:
        """FTS search chunks by text, return chunk ids"""
        clean = self._sanitize_fts_query(query)
        cursor = self.conn.execute("""
        SELECT rowid FROM chunk_fts WHERE text MATCH ? LIMIT ?
        """, (clean, limit))
        return [row[0] for row in cursor.fetchall()]

    def find_entities_by_name(self, domain_id: int, name: str, limit: int = 20, include_expired: bool = False) -> List[sqlite3.Row]:
        """Find entities by exact or fuzzy name match, returns entity rows."""
        extra_where = "" if include_expired else "AND (status IS NULL OR status != 'expired')"
        sql = f"""
        SELECT * FROM entity
        WHERE domain_id = ? AND (name = ? OR name LIKE ? OR aliases LIKE ?) {extra_where}
        LIMIT ?
        """
        cursor = self.conn.execute(sql, (domain_id, name, '%' + name + '%', '%' + name + '%', limit))
        return cursor.fetchall()

    def get_docs_by_entity(self, entity_id: int) -> List[sqlite3.Row]:
        """Get all doc_asset rows for an entity."""
        cursor = self.conn.execute("""
        SELECT * FROM doc_asset WHERE entity_id = ? ORDER BY doc_type
        """, (entity_id,))
        return cursor.fetchall()

    def get_chunks_by_doc(self, doc_id: int, limit: int = 10) -> List[sqlite3.Row]:
        """Get first N chunks of a document."""
        cursor = self.conn.execute("""
        SELECT * FROM doc_chunk WHERE doc_id = ? ORDER BY chunk_index LIMIT ?
        """, (doc_id, limit))
        return cursor.fetchall()

    def get_docs_by_relation(self, entity_id: int, relation_type: str = "documents") -> List[sqlite3.Row]:
        """Get doc_asset rows linked to an entity via kb_relation (catalog links)."""
        cursor = self.conn.execute("""
        SELECT da.* FROM kb_relation kr
        INNER JOIN doc_asset da ON kr.object_id = da.id
        WHERE kr.subject_type = 'entity' AND kr.subject_id = ?
          AND kr.relation_type = ? AND kr.object_type = 'doc_asset'
        ORDER BY da.file_name
        """, (entity_id, relation_type))
        return cursor.fetchall()

    def get_entity_knowledge(self, domain_id: int, name: str, chunk_limit: int = 3, include_expired: bool = False) -> List[Dict]:
        """Deterministic knowledge lookup: entity → docs → chunks.
        Falls back to same-family entities' docs when the entity has no docs.
        Returns list of dicts with entity/doc/chunk info."""
        entities = self.find_entities_by_name(domain_id, name, limit=3, include_expired=include_expired)
        results = []
        if not entities:
            # 名字没直接命中：尝试 fuzzy 前缀
            entities = self.find_entities_by_name(domain_id, name[:max(1, len(name) - 3)], limit=3, include_expired=include_expired)
        for ent in entities:
            docs = self.get_docs_by_entity(ent['id'])
            if not docs and ent['family']:
                # 同族回退：找同族其他有文档的实体
                fam_rows = self.execute(
                    "SELECT * FROM entity WHERE domain_id = ? AND family = ? ORDER BY id", (domain_id, ent['family'])
                ).fetchall()
                for fr in fam_rows:
                    if fr['id'] == ent['id']:
                        continue
                    # Skip expired in fallback
                    if not include_expired and fr['status'] == 'expired':
                        continue
                    docs = self.get_docs_by_entity(fr['id'])
                    if docs:
                        break
            for d in docs[:2]:  # 每个实体最多取 2 个文档
                chunks = self.get_chunks_by_doc(d['id'], chunk_limit)
                for c in chunks:
                    results.append({
                        'entity': dict(ent),
                        'doc': dict(d),
                        'chunk': dict(c),
                        'similarity': None,
                    })
                if len(results) >= chunk_limit * 2:
                    break
            if results:
                break
        if not results:
            # FTS 关键词回退：清洗名称后分段尝试匹配
            import re as _re
            clean = _re.sub(r'[Vv][0-9.]+|（.*?）|\(.*?\)|[0-9.]+', '', name).strip()
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
                    if d is None:
                        continue
                    ent_row = self.get_entity(d['entity_id'])
                    if ent_row is None:
                        continue
                    # Skip expired entities in FTS fallback
                    if not include_expired and ent_row['status'] == 'expired':
                        continue
                    results.append({
                        'entity': dict(ent_row) if ent_row else {'name': '未知'},
                        'doc': dict(d),
                        'chunk': dict(chunk),
                        'similarity': None,
                    })
                    if len(results) >= chunk_limit * 2:
                        return results
        return results

    def get_entity(self, entity_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM entity WHERE id = ?", (entity_id,))
        return cursor.fetchone()

    def get_chunk(self, chunk_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_chunk WHERE id = ?", (chunk_id,))
        return cursor.fetchone()

    def get_doc(self, doc_id: int) -> Optional[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM doc_asset WHERE id = ?", (doc_id,))
        return cursor.fetchone()

    def list_entities_by_collection(self, collection_id: int, status: str = None) -> List[sqlite3.Row]:
        if status:
            cursor = self.execute("""
            SELECT * FROM entity WHERE collection_id = ? AND status = ?
            """, (collection_id, status))
        else:
            cursor = self.execute("""
            SELECT * FROM entity WHERE collection_id = ? AND (status IS NULL OR status != 'expired')
            """, (collection_id,))
        return cursor.fetchall()

    def count_entities(self, domain_id: int = None, include_expired: bool = False) -> int:
        if include_expired:
            if domain_id:
                cursor = self.execute("SELECT COUNT(*) FROM entity WHERE domain_id = ?", (domain_id,))
            else:
                cursor = self.execute("SELECT COUNT(*) FROM entity")
        else:
            if domain_id:
                cursor = self.execute("""
                SELECT COUNT(*) FROM entity WHERE domain_id = ? AND (status IS NULL OR status != 'expired')
                """, (domain_id,))
            else:
                cursor = self.execute("""
                SELECT COUNT(*) FROM entity WHERE status IS NULL OR status != 'expired'
                """)
        return cursor.fetchone()[0]

    def count_docs(self, domain_id: int = None) -> int:
        if domain_id:
            cursor = self.execute("""
            SELECT COUNT(*) FROM doc_asset da
            JOIN entity e ON da.entity_id = e.id WHERE e.domain_id = ? AND (e.status IS NULL OR e.status != 'expired')
            """, (domain_id,))
        else:
            cursor = self.execute("""
            SELECT COUNT(*) FROM doc_asset da
            JOIN entity e ON da.entity_id = e.id WHERE (e.status IS NULL OR e.status != 'expired')
            """)
        return cursor.fetchone()[0]

    def count_chunks(self, domain_id: int = None) -> int:
        if domain_id:
            cursor = self.execute("""
            SELECT COUNT(*) FROM doc_chunk dc
            JOIN doc_asset da ON dc.doc_id = da.id
            JOIN entity e ON da.entity_id = e.id WHERE e.domain_id = ? AND (e.status IS NULL OR e.status != 'expired')
            """, (domain_id,))
        else:
            cursor = self.execute("""
            SELECT COUNT(*) FROM doc_chunk dc
            JOIN doc_asset da ON dc.doc_id = da.id
            JOIN entity e ON da.entity_id = e.id WHERE (e.status IS NULL OR e.status != 'expired')
            """)
        return cursor.fetchone()[0]

    def get_all_domains(self) -> List[sqlite3.Row]:
        cursor = self.execute("SELECT * FROM domain ORDER BY name")
        return cursor.fetchall()

    # --- Migration ---
    def get_current_migration_version(self) -> int:
        """Get the highest applied migration version"""
        if not self.conn:
            self.connect()
        cursor = self.execute("SELECT MAX(version) FROM kb_migration")
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def apply_migration(self, version: int, name: str):
        """Record that a migration has been applied"""
        now = self.get_now()
        self.execute("INSERT INTO kb_migration (version, name, applied_at) VALUES (?, ?, ?)",
                     (version, name, now))
        self.commit()

    # --- Audit log ---
    def add_audit_log(self, operation_type: str, user_id: str = None,
                     object_type: str = None, object_id: int = None,
                     request_id: str = None, risk_level: str = None,
                     rule_triggered: str = None, action_taken: str = None,
                     details: str = None) -> int:
        """Add an audit log entry"""
        now = self.get_now()
        cursor = self.execute("""
        INSERT INTO kb_audit_log (
            timestamp, user_id, operation_type, object_type, object_id,
            request_id, risk_level, rule_triggered, action_taken, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, user_id, operation_type, object_type, object_id,
              request_id, risk_level, rule_triggered, action_taken, details, now))
        self.commit()
        return cursor.lastrowid

    # --- Template storage ---
    def save_template(self, template_id: str, name: str, version: str,
                      description: str, author: str, category: str,
                      config_yaml: str) -> int:
        """Save or update a template"""
        now = self.get_now()
        cursor = self.execute("SELECT id FROM kb_template WHERE template_id = ?", (template_id,))
        row = cursor.fetchone()
        if row:
            self.execute("""
            UPDATE kb_template
            SET name = ?, version = ?, description = ?, author = ?, category = ?,
                config_yaml = ?, updated_at = ?
            WHERE id = ?
            """, (name, version, description, author, category, config_yaml, now, row[0]))
            self.commit()
            return row[0]
        else:
            cursor = self.execute("""
            INSERT INTO kb_template (template_id, name, version, description, author, category,
                                     config_yaml, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (template_id, name, version, description, author, category, config_yaml, now, now))
            self.commit()
            return cursor.lastrowid

