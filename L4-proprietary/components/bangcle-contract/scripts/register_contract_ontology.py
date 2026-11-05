"""contractctl ontology 装配脚本 — L4 bangcle-contract → L2 运营本体（幂等）。

薄封装：装配逻辑集中在 contract_review.ontology_bridge.assemble.assemble()。

用法：
    python3 scripts/register_contract_ontology.py \
        [--db <contract.db>] [--ai-kb <ai_kb.db>] [--register HT-2026-001:100000]
"""
from __future__ import annotations

import argparse
import os
import sys

# ---------------------------------------------------------------
# sys.path 注入（L4 组件根；包内 assemble 自带 L2/L3 路径引导）
# ---------------------------------------------------------------

def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))          # .../scripts
    comp = os.path.dirname(here)                               # .../bangcle-contract
    if comp not in sys.path:
        sys.path.insert(0, comp)


_ensure_paths()


def main() -> None:
    from contract_review.ontology_bridge.assemble import assemble

    parser = argparse.ArgumentParser(
        prog="register-contract-ontology",
        description="L4 bangcle-contract → L2 运营本体装配（幂等）",
    )
    parser.add_argument("--db", default=None, help="L4 contract 库路径（默认组件 data/）")
    parser.add_argument("--ai-kb", default=None, help="L2 ai_kb 库路径（默认与 db 同目录 ai_kb.db）")
    parser.add_argument("--register", default=None,
                        help="登记示例合同（逗号分隔 NO:AMOUNT，如 HT-2026-001:100000）")
    args = parser.parse_args()

    out = assemble(args.db, args.ai_kb, args.register)
    print("contract DB :", out["db_path"])
    print("ai_kb DB    :", out["ai_kb_path"])
    print("domain_id   :", out["domain_id"])
    for f in out["functions"]:
        print(f"  fn  {f}")
    for a in out["actions"]:
        print(f"  act {a}")
    print(f"bindings validated: {len(out['bindings'])} action types")
    for c in out["registered_contracts"]:
        print(f"  reg {c['contract_no']} -> identity {c['identity_id']} "
              f"(canonical={c['canonical_key']}, created={c['created']})")


if __name__ == "__main__":
    main()
