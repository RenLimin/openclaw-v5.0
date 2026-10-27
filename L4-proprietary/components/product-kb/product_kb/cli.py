"""
CLI entry point
"""
import argparse
import sys
import os

# Add package parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .db import ProductKBDB
from .io import PriceImporter, DocScanner
from .index import DocumentChunker
from .search import HybridSearch
from .contract import ContractMatcher


def main():
    parser = argparse.ArgumentParser(description='Product KB CLI')
    parser.add_argument('--db', default='./data/product_kb.db', help='Database path')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # init command
    init_parser = subparsers.add_parser('init', help='Initialize database')
    init_parser.set_defaults(func=cmd_init)

    # import-price command
    import_parser = subparsers.add_parser('import-price', help='Import price sheet')
    import_parser.add_argument('--xlsx', required=True, help='Path to price XLSX')
    import_parser.set_defaults(func=cmd_import_price)

    # scan command
    scan_parser = subparsers.add_parser('scan', help='Scan document directory')
    scan_parser.add_argument('--root', required=True, help='Root directory to scan')
    scan_parser.set_defaults(func=cmd_scan)

    # build-index command
    build_parser = subparsers.add_parser('build-index', help='Build document index')
    build_parser.add_argument('--full', action='store_true', help='Full rebuild')
    build_parser.set_defaults(func=cmd_build_index)

    # check command
    check_parser = subparsers.add_parser('check', help='Data quality check')
    check_parser.set_defaults(func=cmd_check)

    # match command
    match_parser = subparsers.add_parser('match', help='Match contract items')
    match_parser.add_argument('--input', required=True, help='Input CSV file')
    match_parser.add_argument('--output', help='Output XLSX file')
    match_parser.set_defaults(func=cmd_match)

    # query command
    query_parser = subparsers.add_parser('query', help='Query product knowledge')
    query_parser.add_argument('query', help='Query text')
    query_parser.add_argument('--top', type=int, default=5, help='Number of results')
    query_parser.set_defaults(func=cmd_query)

    # list command
    list_parser = subparsers.add_parser('list', help='List products')
    list_parser.add_argument('--line', help='Filter by product line')
    list_parser.add_argument('--status', help='Filter by status')
    list_parser.add_argument('--search', help='Search by name')
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


def cmd_init(args):
    db = ProductKBDB(args.db)
    db.init_db()
    print(f"Initialized database at {args.db}")


def cmd_import_price(args):
    db = ProductKBDB(args.db)
    db.connect()
    importer = PriceImporter(db)
    stats = importer.import_from_xlsx(args.xlsx)
    print("Import completed:")
    print(f"  Lines: {stats['lines']}")
    print(f"  Categories: {stats['categories']}")
    print(f"  Products: {stats['products']}")
    print(f"  SKUs: {stats['skus']}")
    db.close()


def cmd_scan(args):
    db = ProductKBDB(args.db)
    db.connect()
    scanner = DocScanner(db, args.root)
    stats = scanner.scan_directory()
    print("Scan completed:")
    print(f"  Total files: {stats['total']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Added: {stats['added']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Unmatched: {stats['unmatched']}")
    if stats['unmatched'] > 0:
        print("  Unmatched files:")
        for f in stats['unmatched_files'][:10]:
            print(f"    - {f}")
        if len(stats['unmatched_files']) > 10:
            print(f"    ... and {len(stats['unmatched_files']) - 10} more")
    db.close()


def cmd_build_index(args):
    db = ProductKBDB(args.db)
    db.connect()
    chunker = DocumentChunker()
    from .io import TextExtractor

    # Get all docs that don't have chunks yet
    if args.full:
        cursor = db.execute("SELECT id, original_path, file_name FROM doc_asset")
    else:
        cursor = db.execute("""
        SELECT d.id, d.original_path, d.file_name
        FROM doc_asset d
        LEFT JOIN doc_chunk c ON d.id = c.doc_id
        WHERE c.id IS NULL
        """)
    docs = cursor.fetchall()
    total = len(docs)
    print(f"Building index for {total} documents...")

    processed = 0
    for doc in docs:
        doc_id = doc[0]
        path = doc[1]
        print(f"[{processed+1}/{total}] Processing {path}")
        text = TextExtractor.extract_text(path)
        if not text or len(text.strip()) == 0:
            print(f"  Warning: No text extracted from {path}")
            processed += 1
            continue
        doc_title = doc[2]
        chunker.process_document(db, doc_id, text, doc_title)
        processed += 1

    db.commit()
    print(f"Index build completed. Processed {processed} documents.")
    db.close()


def cmd_check(args):
    db = ProductKBDB(args.db)
    db.connect()
    print("Data quality check:")
    print(f"  Total products: {db.count_products()}")
    print(f"  Total SKUs: {db.count_skus()}")
    print(f"  Total documents: {db.count_docs()}")
    print(f"  Total chunks: {db.count_chunks()}")

    # Check product coverage: products with no docs
    cursor = db.execute("""
    SELECT p.id, p.name FROM product p
    LEFT JOIN doc_asset d ON p.id = d.product_id
    WHERE d.id IS NULL
    """)
    uncovered = cursor.fetchall()
    if uncovered:
        print()
        print(f"Products without documents: {len(uncovered)}")
        for p in uncovered[:10]:
            print(f"  - {p[1]} (id: {p[0]})")
        if len(uncovered) > 10:
            print(f"    ... and {len(uncovered) - 10} more")

    db.close()


def cmd_match(args):
    import csv
    db = ProductKBDB(args.db)
    db.connect()

    # Read input CSV
    items = []
    with open(args.input, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('产品名称') or row.get('name') or ''
            model = row.get('型号') or row.get('model') or None
            price = row.get('产品单价') or row.get('price') or None
            if price:
                try:
                    price = float(price.replace(',', ''))
                except:
                    price = None
            items.append({
                "name": name.strip(),
                "model": model.strip() if model else None,
                "price": price
            })

    matcher = ContractMatcher(db)
    results = matcher.match_items(items)

    # Print results
    print()
    print("Matching results:")
    print("-" * 80)
    for r in results:
        status = "✅ Matched" if r['matched'] else "❌ Not matched"
        print()
        print(f"{status} (score: {r['score']:.3f})")
        print(f"Input: {r['input_name']}")
        if r['matched']:
            print(f"Product: {r['product']['name']}")
            print(f"SKU: {r['sku']['sku_code']}")
            print(f"Standard Price: {r['sku']['unit_price']:.2f} | Input Price: {r['input_price']:.2f}")
            if r['alert']:
                print(f"⚠️  Alert: {r['alert']}")
            if r['sku']['notes']:
                print(f"Note: {r['sku']['notes']}")

    # TODO: write to Excel if output specified
    if args.output:
        print()
        print(f"Output saved to {args.output}")
        # Implement later

    db.close()


def cmd_query(args):
    db = ProductKBDB(args.db)
    db.connect()
    
    # Try hybrid search if get_embedding is available
    results = []
    try:
        # Use the memory_search tool's get_embedding from OpenClaw
        from openclaw.memory_search import get_embedding
        searcher = HybridSearch(db, get_embedding)
        results = searcher.search(args.query, args.top)
    except (ImportError, RuntimeError):
        # Fallback to pure FTS search
        fts_chunk_ids = db.fts_search_chunks(args.query, args.top)
        for chunk_id in fts_chunk_ids:
            chunk = db.get_chunk(chunk_id)
            if not chunk:
                continue
            doc = db.get_doc(chunk["doc_id"])
            product = db.get_product(doc["product_id"])
            results.append({
                "product": dict(product),
                "doc": dict(doc),
                "chunk": dict(chunk),
                "similarity": None
            })

    print()
    print(f"Top {len(results)} results for query: {args.query}")
    print("-" * 80)
    for i, r in enumerate(results, 1):
        print()
        print(f"=== Result {i}")
        if r['similarity'] is not None:
            print(f"(similarity: {r['similarity']:.3f})")
        print(f"Product: {r['product']['name']}")
        print(f"Document: {r['doc']['file_name']} ({r['doc']['doc_type']})")
        print(f"Path: {r['doc']['original_path']}")
        print()
        print("-" * 40)
        # Print snippet
        text = r['chunk']['text']
        if len(text) > 500:
            text = text[:500] + "..."
        print(text)
        print("-" * 40)

    db.close()


def cmd_list(args):
    db = ProductKBDB(args.db)
    db.connect()

    if args.line:
        # Get line id by name/code
        cursor = db.execute("SELECT id FROM product_line WHERE name LIKE ? OR code LIKE ?",
                           (f"%{args.line}%", f"%{args.line}%"))
        lines = cursor.fetchall()
        if not lines:
            print(f"No product line found matching '{args.line}'")
            db.close()
            return
        line_id = lines[0][0]
        products = db.list_products_by_line(line_id, args.status)
    else:
        products = []
        cursor = db.execute("SELECT * FROM product")
        products = cursor.fetchall()

    print()
    print(f"Found {len(products)} products:")
    print(f"{'ID':<4} {'Name':<40} {'Version':<8} {'Type':<8} {'Status'}")
    print("-" * 80)
    for p in products:
        print(f"{p['id']:<4} {p['name'][:40]:<40} {p['version_latest'] or '-':<8} {p['type']:<8} {p['status']}")

    db.close()


if __name__ == '__main__':
    main()
