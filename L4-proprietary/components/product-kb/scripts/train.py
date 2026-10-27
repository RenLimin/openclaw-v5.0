#!/usr/bin/env python3
"""
Product Expert Training Script
- Random product questioning
- KB reference comparison
- Progress tracking
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from product_kb.search import HybridSearch
from product_kb.db import ProductKBDB

DB_PATH = "./data/product_kb.db"
PROGRESS_PATH = "./docs/training/training_progress.md"


class ProductTrainer:
    def __init__(self, db_path=DB_PATH):
        self.db = ProductKBDB(db_path)
        self.db.connect()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            pass

    def get_random_product(self):
        """Get a random active product for training"""
        cursor = self.db.execute("SELECT id, name FROM product WHERE status = '正常销售' OR status = 'active'")
        products = cursor.fetchall()
        if not products:
            cursor = self.db.execute("SELECT id, name FROM product")
            products = cursor.fetchall()
        if not products:
            return None
        return random.choice(products)

    def search_kb(self, query, top_k=3):
        """Search KB; deterministic product->docs->chunks lookup first, FTS fallback"""
        results = self.db.get_product_knowledge(query, chunk_limit=top_k)
        if results:
            return results
        try:
            searcher = HybridSearch(self.db)
            return searcher.search(query, top_k)
        except (RuntimeError, TypeError):
            fts_ids = self.db.fts_search_chunks(query, top_k)
            results = []
            for cid in fts_ids:
                chunk = self.db.get_chunk(cid)
                if not chunk:
                    continue
                doc = self.db.get_doc(chunk["doc_id"])
                product = self.db.get_product(doc["product_id"])
                results.append({
                    "product": dict(product),
                    "doc": dict(doc),
                    "chunk": dict(chunk),
                    "similarity": None,
                })
            return results

    def save_progress(self, question, answer, correct, notes=""):
        """Save one training record"""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "CORRECT" if correct else "INCORRECT"
        with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
            f.write("\n## " + now + "\n")
            f.write("**Q**: " + question + "\n")
            f.write("**A**: " + answer.replace("\n", " ") + "\n")
            f.write("**Result**: " + status + "\n")
            if notes:
                f.write("**Notes**: " + notes.replace("\n", " ") + "\n")

    def start_training_session(self, count=10):
        """Run an interactive training session"""
        print("=== Training session: " + str(count) + " questions ===")
        correct_count = 0
        for i in range(count):
            product = self.get_random_product()
            if not product:
                print("No products found in database.")
                break
            print()
            print("Q" + str(i + 1) + "/" + str(count) + ": 请介绍产品「" + product["name"] + "」")
            print("输入你的回答（多行以 EOF 结尾），或直接回车跳过:")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "EOF":
                    break
                lines.append(line)
            answer = "\n".join(lines).strip()
            if not answer:
                print("Skipped.")
                continue

            print()
            print("=== 知识库参考 ===")
            results = self.search_kb(product["name"], 3)
            if not results:
                print("(no KB reference found)")
            for j, r in enumerate(results, 1):
                sim = r["similarity"]
                sim_str = "%.3f" % sim if sim is not None else "n/a"
                print("[" + str(j) + "] similarity=" + sim_str + " | " + str(r["product"]["name"]))
                text = r["chunk"]["text"].replace("\n", " ")
                if len(text) > 200:
                    text = text[:200] + "..."
                print("    " + text)

            verdict = input("你的回答正确吗？(y/n): ").strip().lower()
            correct = verdict in ("y", "yes")
            if correct:
                correct_count += 1
            notes = input("笔记（可选）: ").strip()
            self.save_progress(product["name"], answer, correct, notes)
            print("=" * 60)

        print()
        print("Session done. Correct: " + str(correct_count) + "/" + str(count))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Product Expert Training")
    parser.add_argument("--count", type=int, default=10, help="Number of questions per session")
    parser.add_argument("--init", action="store_true", help="Initialize progress file")
    args = parser.parse_args()

    if args.init:
        if os.path.exists(PROGRESS_PATH):
            print("Progress file already exists at " + PROGRESS_PATH)
        else:
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                f.write("# Bangcle 产品专家训练进度记录\n\n")
            print("Initialized progress file at " + PROGRESS_PATH)
        return

    trainer = ProductTrainer()
    trainer.start_training_session(args.count)


if __name__ == "__main__":
    main()
