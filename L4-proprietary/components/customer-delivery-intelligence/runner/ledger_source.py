"""读取 OA 台账（既有自动化产出的原始文件），按客户筛行 —— 权威事实源。"""
from __future__ import annotations
from pathlib import Path
import pandas as pd, warnings
warnings.filterwarnings("ignore")

DEFAULT_LEDGER = Path.home()/".openclaw/data/oa_exports/contract_ledger_202610.xlsx"


def load_customer_rows(customer: str, ledger: Path | None = None) -> list[dict]:
    df = pd.read_excel(ledger or DEFAULT_LEDGER)
    keys = ["客户名称", "最终用户名称"]
    pat = customer.replace("股份有限公司", "").replace("有限公司", "")[:4]  # 如"中国建设银"
    mask = pd.Series(False, index=df.index)
    for k in keys:
        if k in df.columns:
            mask |= df[k].astype(str).str.contains(pat, na=False)
    rows = df[mask].to_dict(orient="records")
    # 规整 NaN -> None
    clean = []
    for r in rows:
        clean.append({k: (None if (v is None or (isinstance(v, float) and v != v)) else v)
                      for k, v in r.items()})
    return clean
