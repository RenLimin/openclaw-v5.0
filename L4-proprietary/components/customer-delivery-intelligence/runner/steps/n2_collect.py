"""N2 取数编排：原始数据必须直接来自 OA/ONES（数据来源铁律）。

两条路径，数据同源：
1. reuse（默认，快）：复用「既有浏览器自动化已产出并落盘」的原始文件
   （OA 销售台账 XLSX + ONES 签约项目 CSV）。做存在性/大小校验，直接登记。
2. live：现场驱动既有自动化重新导出（数分钟，--live 或 reuse 缺文件时）。
绝不重写浏览器自动化；只调用 delivery-center 既有 collector。
"""
from __future__ import annotations
import os
from pathlib import Path
from ..state import now_iso
from .. import existing_collectors as ex

ONES_FETCH = ex.fetch_ones_filter
OA_FETCH = ex.fetch_oa_contract_ledger

# 既有自动化的标准落盘位置（直接来自 OA/ONES）
EXISTING_OA_LEDGER = Path.home()/".openclaw/data/oa_exports/contract_ledger_202610.xlsx"
EXISTING_ONES_SIGN = Path.home()/".openclaw/data/ones_exports/2026周报-签约项目统计.csv"


def set_fetchers(ones=None, oa=None):
    global ONES_FETCH, OA_FETCH
    if ones is not None: ONES_FETCH = ones
    if oa is not None: OA_FETCH = oa


def _existing_files():
    out = []
    for p, typ in ((EXISTING_ONES_SIGN, "csv"), (EXISTING_OA_LEDGER, "xlsx")):
        if p.exists() and p.stat().st_size > 0:
            out.append({"path": p, "type": typ, "source": ("ones" if typ=="csv" else "oa"),
                        "size": p.stat().st_size})
    return out


def run(state: dict) -> dict:
    inp = state["input_norm"]
    month = inp["period"]["end"][:7].replace("-", "")
    reuse = inp.get("scope", {}).get("liveExport") is not True  # 默认复用

    files_meta: list[dict] = []
    proof: dict = {}
    errors: list[str] = []

    have = _existing_files()
    sources = {f["source"] for f in have}

    if reuse and {"ones", "oa"} <= sources:
        # 快路径：既有自动化原始产出
        for f in have:
            files_meta.append({"uri": f["path"].resolve().as_uri(), "type": f["type"],
                               "source": f["source"], "size": f["size"]})
            proof[f["source"]] = {"file": str(f["path"]), "size": f["size"], "reused": True}
    else:
        # live：调用既有自动化重新导出
        raw_dir = Path("storage/raw")/state["task_id"]; raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            ones_csv = ONES_FETCH("2026周报-签约项目统计")
            if ones_csv and os.path.exists(ones_csv):
                files_meta.append({"uri": Path(ones_csv).resolve().as_uri(), "type": "csv",
                                   "source": "ones", "size": os.path.getsize(ones_csv)})
                proof["ones"] = {"file": ones_csv}
            else:
                errors.append("ones: no file")
        except Exception as e:
            errors.append(f"ones: {e!r}")
        try:
            oa = OA_FETCH(month, export_dir=str(raw_dir), headless=True)
            if oa and oa.get("file"):
                files_meta.append({"uri": Path(oa["file"]).resolve().as_uri(), "type": "xlsx",
                                   "source": "oa", "size": oa.get("size")})
                proof["oa"] = {"file": oa["file"]}
            else:
                errors.append("oa: no file")
        except Exception as e:
            errors.append(f"oa: {e!r}")

    state["raw"] = {"ones": proof.get("ones", {}), "oa": proof.get("oa", {}),
                    "fetchedAt": now_iso()}
    state["file_manifest"] = files_meta
    state["completeness"] = proof
    if errors:
        state["errors"].extend(errors)
        state["_event"] = "fail"
    else:
        state["_event"] = "pass"
    return state
