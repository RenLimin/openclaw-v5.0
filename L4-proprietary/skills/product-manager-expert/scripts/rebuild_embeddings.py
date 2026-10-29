#!/usr/bin/env python3
"""为 product_kb.doc_chunk 重建 embedding（本地 llama-server / embeddinggemma-300m）。

用途：audit_kb.py 报 "doc_chunk.embedding 全为空" 时执行全量重建。
原理：调用本地 llama.cpp llama-server 的 /v1/embeddings（OpenAI 兼容），
      向量以 float64 bytes 写入 doc_chunk.embedding（对齐 search.py np.frombuffer dtype=np.float64）。

用法：
    python3 scripts/rebuild_embeddings.py --db <db路径> [--server http://127.0.0.1:8123] [--batch 2] [--limit N]

依赖：llama-server 已在 8123 端口运行（embedding 模式）：
    llama-server -m ~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf \\
                 --embedding --port 8123 --ctx-size 2048 --host 127.0.0.1
"""
import argparse, array, json, sqlite3, sys, time, urllib.request

MAX_CHARS = 1500  # 中文约1字≈1token，1500字≈1500 token < 2048 ctx 安全

def call(server, inputs):
    req = urllib.request.Request(
        server + "/v1/embeddings",
        data=json.dumps({"input": inputs, "model": "embeddinggemma"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    data = sorted(d["data"], key=lambda x: x["index"])
    return [x["embedding"] for x in data]

def embed_one(server, text):
    """逐条嵌入，超长自动截断，最多重试2次。"""
    text = text[:MAX_CHARS]
    for attempt in range(3):
        try:
            return call(server, [text])[0]
        except Exception as e:
            if attempt == 2: raise
            time.sleep(1.5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./data/product_kb.db")
    ap.add_argument("--server", default="http://127.0.0.1:8123")
    ap.add_argument("--batch", type=int, default=2, help="并行批大小（llama-server slot 数）")
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 条（调试用）")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA journal_mode=WAL")
    rows = con.execute("SELECT id, text FROM doc_chunk WHERE embedding IS NULL ORDER BY id").fetchall()
    if args.limit: rows = rows[:args.limit]
    total = len(rows)
    print(f"待重建: {total} chunks")

    t0 = time.time(); done = 0; failed = 0
    for i in range(0, total, args.batch):
        batch_rows = rows[i:i+args.batch]
        texts = [r[1] for r in batch_rows]
        vecs = []
        try:
            # 先整批试；批内单条超长会拖垮整批 → 失败则逐条
            if len(batch_rows) == args.batch:
                vecs = call(args.server, [t[:MAX_CHARS] for t in texts])
            else:
                vecs = [embed_one(args.server, t) for t in texts]
        except Exception:
            try:
                vecs = [embed_one(args.server, t) for t in texts]
            except Exception as e:
                print(f"[{i}] 失败: {e}", file=sys.stderr)
                failed += len(batch_rows)
                continue
        for r, vec in zip(batch_rows, vecs):
            f64 = array.array("d", vec).tobytes()
            con.execute("UPDATE doc_chunk SET embedding=? WHERE id=?", (f64, r[0]))
        done += len(batch_rows)
        con.commit()
        if done % 500 < args.batch or done == total:
            el = time.time()-t0
            print(f"进度 {done}/{total} ({el:.0f}s, {done/max(el,0.1):.0f}/s)", flush=True)
    con.commit(); con.close()
    print(f"完成: {done}/{total} 失败: {failed} | 耗时 {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
