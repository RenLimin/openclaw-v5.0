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
from pathlib import Path

MODEL = sys.argv[1]
NTOK = int(sys.argv[2])

# 容错加载 openclaw.json：损坏时优雅降级
_cfg_path = Path.home() / ".openclaw" / "openclaw.json"
try:
    d = json.loads(_cfg_path.read_text())
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"❌ 无法加载 openclaw.json: {e}", file=sys.stderr)
    print("   尝试从 .bak 恢复最新配置...", file=sys.stderr)
    import glob
    baks = sorted(glob.glob(str(_cfg_path) + ".bak*"), reverse=True)
    if baks:
        try:
            d = json.loads(Path(baks[0]).read_text())
            print(f"   已使用备份: {baks[0]}", file=sys.stderr)
        except Exception:
            print("❌ 备份也不可用，中止", file=sys.stderr)
            sys.exit(1)
    else:
        print("❌ 无备份可用，中止", file=sys.stderr)
        sys.exit(1)

pr = d.get("models", {}).get("providers", {}).get("coding-plan")
if not pr:
    print("❌ 未找到 coding-plan provider 配置", file=sys.stderr)
    sys.exit(1)
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
