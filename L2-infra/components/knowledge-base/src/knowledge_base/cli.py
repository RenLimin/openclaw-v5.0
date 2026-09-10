"""Knowledge Base CLI 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Knowledge Base CLI — 通用知识库管理与检索")
    sub = ap.add_subparsers(dest="command", help="子命令")

    # add
    add_p = sub.add_parser("add", help="添加文档")
    add_p.add_argument("files", nargs="+", help="文件路径")
    add_p.add_argument("--store", default="./.kb_store", help="存储目录")

    # search
    search_p = sub.add_parser("search", help="搜索")
    search_p.add_argument("query", help="查询文本")
    search_p.add_argument("--limit", "-n", type=int, default=10, help="返回数量")
    search_p.add_argument("--mode", choices=["semantic", "keyword", "hybrid"],
                          default="hybrid", help="检索模式")
    search_p.add_argument("--store", default="./.kb_store", help="存储目录")

    # list
    list_p = sub.add_parser("list", help="列出文档")
    list_p.add_argument("--category", help="按分类过滤")
    list_p.add_argument("--tag", help="按标签过滤")
    list_p.add_argument("--limit", "-n", type=int, default=50, help="返回数量")
    list_p.add_argument("--store", default="./.kb_store", help="存储目录")

    # stats
    stats_p = sub.add_parser("stats", help="统计信息")
    stats_p.add_argument("--store", default="./.kb_store", help="存储目录")

    # rebuild
    rebuild_p = sub.add_parser("rebuild", help="重建索引")
    rebuild_p.add_argument("--store", default="./.kb_store", help="存储目录")

    # delete
    del_p = sub.add_parser("delete", help="删除文档")
    del_p.add_argument("doc_id", help="文档 ID")
    del_p.add_argument("--store", default="./.kb_store", help="存储目录")

    args = ap.parse_args()

    if not args.command:
        ap.print_help()
        return 0

    # 延迟导入，避免启动慢
    from .core import KnowledgeBase

    store = Path(args.store)

    if args.command == "add":
        kb = KnowledgeBase.load(store) if store.exists() else KnowledgeBase(storage_dir=store)
        for f in args.files:
            path = Path(f)
            if not path.exists():
                print(f"❌ 文件不存在: {f}", file=sys.stderr)
                continue
            doc_id = kb.add_file(path)
            print(f"✅ 已添加: {doc_id}  ({f})")
        kb.save()
        return 0

    if args.command == "search":
        if not store.exists():
            print("知识库为空", file=sys.stderr)
            return 1
        kb = KnowledgeBase.load(store)
        results = kb.search(args.query, limit=args.limit, mode=args.mode)
        if not results:
            print("无匹配结果")
            return 0
        print(f"搜索: {args.query}  (mode={args.mode}, 命中 {len(results)})\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r.score:.3f}] {r.title}")
            print(f"     {r.snippet}")
            print(f"     (doc: {r.chunk.doc_id})")
            print()
        return 0

    if args.command == "list":
        if not store.exists():
            print("知识库为空", file=sys.stderr)
            return 1
        kb = KnowledgeBase.load(store)
        docs = kb.list_documents(category=args.category, tag=args.tag)
        docs = docs[: args.limit]
        print(f"共 {kb.count} 篇文档，显示 {len(docs)} 篇\n")
        for d in docs:
            tags = f"  [{', '.join(d.tags)}]" if d.tags else ""
            cat = f"  ({d.category})" if d.category else ""
            print(f"  {d.doc_id}  {d.title}{cat}{tags}")
        return 0

    if args.command == "stats":
        if not store.exists():
            print("知识库为空", file=sys.stderr)
            return 1
        kb = KnowledgeBase.load(store)
        info = kb.stats()
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.command == "rebuild":
        if not store.exists():
            print("知识库为空", file=sys.stderr)
            return 1
        kb = KnowledgeBase.load(store)
        ok = kb.rebuild_index()
        if ok:
            kb.save()
            print(f"✅ 索引重建完成 ({kb.chunk_count} 个块)")
            return 0
        else:
            print("❌ 索引重建失败", file=sys.stderr)
            return 1

    if args.command == "delete":
        if not store.exists():
            print("知识库为空", file=sys.stderr)
            return 1
        kb = KnowledgeBase.load(store)
        ok = kb.delete_document(args.doc_id)
        if ok:
            kb.save()
            print(f"✅ 已删除: {args.doc_id}")
            return 0
        else:
            print(f"❌ 未找到: {args.doc_id}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
