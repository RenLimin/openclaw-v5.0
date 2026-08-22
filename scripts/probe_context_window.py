#!/usr/bin/env python3
"""探测 provider 端点上某模型的真实输入 token 上限（二分探边界）。

背景与方法论: docs/knowledge-base/by-category/project-experience/correct/
              EXP-20260822-004-context-window-empirical-probe.md

用法:
    python3 scripts/probe_context_window.py <model-id> <approx-token-count> [provider]

示例:
    python3 scripts/probe_context_window.py glm-5.3 10          # 健全性检查
    python3 scripts/probe_context_window.py glm-5.3 1048550     # 探边界
    python3 scripts/probe_context_window.py minimax-m3 1046000

要点:
    - "hello " * N ≈ N tokens，可直接用 N 定位边界
    - max_tokens=4 只探输入侧，避免 input+output 混淆边界
    - 400 + "context window exceeded" = 真边界
    - 429 AccountRateLimitExceeded = 频率限制，等 60~75s 重试
    - 大请求耗时 30s~2min，建议后台跑
"""

import json, os, sys, urllib.request, urllib.error

MODEL = sys.argv[1]
NTOK = int(sys.argv[2])

d = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
pr = d["models"]["providers"]["coding-plan"]
KEY = pr.get("apiKey") or pr.get("api_key")
BASE = pr["baseUrl"].rstrip("/")

# "hello " ≈ 1 token for most BPE tokenizers
filler = "hello " * NTOK
body = {
    "model": MODEL,
    "messages": [{"role": "user", "content": filler + "\n\nReply with only: OK"}],
    "max_tokens": 4,
    "temperature": 0,
}
req = urllib.request.Request(
    f"{BASE}/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    u = resp.get("usage", {})
    print(f"OK   model={MODEL} req_tok~{NTOK} prompt_tokens={u.get('prompt_tokens')} total={u.get('total_tokens')}")
except urllib.error.HTTPError as e:
    raw = e.read().decode()[:600]
    print(f"FAIL model={MODEL} req_tok~{NTOK} http={e.code}")
    print(f"     {raw}")
except Exception as e:
    print(f"ERR  model={MODEL} req_tok~{NTOK} {type(e).__name__}: {e}")
