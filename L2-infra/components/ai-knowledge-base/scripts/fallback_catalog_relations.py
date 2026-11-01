import sys
import sqlite3
sys.path.insert(0, '..')
from ai_kb.db import AIKB

def main():
    db_path = 'instances/bangcle-products/data/bangcle-products.db'
    kb = AIKB(db_path)
    conn = kb.conn

    # 找出所有0关联的产品实体
    zero_catalog = conn.execute('''
    SELECT e.id, e.name, e.collection_id FROM entity e
    LEFT JOIN kb_relation kr ON kr.subject_type = 'entity'
      AND kr.subject_id = e.id AND kr.relation_type = 'documents'
    WHERE e.entity_type IN ('product','service')
    GROUP BY e.id, e.name
    HAVING COUNT(kr.id) = 0
    ''').fetchall()
    print(f'需要兜底关联的目录实体数: {len(zero_catalog)}')

    linked = 0
    total_docs = 0

    for row in zero_catalog:
        eid, name, col_id = row
        # 获取同类别下所有文档
        if not col_id:
            continue
        same_col_docs = conn.execute('''
            SELECT da.id FROM doc_asset da
            INNER JOIN kb_relation kr ON kr.subject_id = da.entity_id
            WHERE kr.relation_type = 'documents'
              AND EXISTS (
                  SELECT 1 FROM entity e2
                  WHERE e2.id = kr.subject_id AND e2.collection_id = ?
              )
              AND da.entity_id != ?
            LIMIT 10
        ''', (col_id, eid)).fetchall()
        n = len(same_col_docs)
        if n == 0:
            # 去上层集合找文档
            col = conn.execute('SELECT parent_id FROM collection WHERE id = ?', (col_id,)).fetchone()
            if col and col[0]:
                same_col_docs = conn.execute('''
                    SELECT da.id FROM doc_asset da
                    INNER JOIN kb_relation kr ON kr.subject_id = da.entity_id
                    WHERE kr.relation_type = 'documents'
                      AND EXISTS (
                          SELECT 1 FROM entity e2
                          WHERE e2.id = kr.subject_id AND e2.collection_id = ?
                      )
                      AND da.entity_id != ?
                    LIMIT 10
                ''', (col[0], eid)).fetchall()
                n = len(same_col_docs)
        # 建立关联
        for doc_row in same_col_docs:
            doc_id = doc_row[0]
            # 检查是否已有关系
            exist = conn.execute('''
                SELECT id FROM kb_relation WHERE subject_type='entity' AND subject_id=?
                AND relation_type='documents' AND object_type='doc_asset' AND object_id=?
            ''', (eid, doc_id)).fetchone()
            if not exist:
                meta = '{"source":"catalog_fallback","note":"zero original docs, fallback to category docs"}'
                conn.execute('''
                INSERT INTO kb_relation (subject_type, subject_id, relation_type, object_type, object_id, metadata, created_at)
                VALUES ('entity', ?, 'documents', 'doc_asset', ?, ?, '2026-10-19')
                ''', (eid, doc_id, meta))
                linked += 1
                total_docs += 1

    conn.commit()
    print(f'✅ 完成：新增 {linked} 个兜底关联（关联 {total_docs} 文档）')

    # 重新统计
    print('\n=== 清洗后统计 ===')
    result = {}
    cursor = conn.execute('''
    SELECT e.id, e.name, COUNT(kr.id) as cnt
    FROM entity e
    LEFT JOIN kb_relation kr ON kr.subject_type = 'entity'
      AND kr.subject_id = e.id AND kr.relation_type = 'documents'
    WHERE e.entity_type IN ('product','service')
    GROUP BY e.id, e.name
    ''')
    for row in cursor:
        cnt = row[2]
        if cnt == 0:
            result['0关联'] = result.get('0关联', 0) + 1
        elif cnt <= 3:
            result['1-3关联'] = result.get('1-3关联', 0) + 1
        else:
            result['>3关联'] = result.get('>3关联', 0) + 1

    for key in ['0关联', '1-3关联', '>3关联']:
        if key in result:
            print(f'  {key}: {result[key]} entities')

if __name__ == "__main__":
    main()
