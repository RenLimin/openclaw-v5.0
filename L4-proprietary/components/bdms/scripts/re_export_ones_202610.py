#!/usr/bin/env python3
"""重新导出 ONES 签约/POC 数据（40列履约项明细），验证列结构。

复用 9222 CDP + IAM cookie 池 + SSO 自动登录（browser_adapter 已验证链路）。
"""
import sys
import shutil
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from bdms.core.config import get_config
from bdms.modules.integration.connectors.ones_connector import OnesConnector

def main():
    _ = get_config()
    oc = OnesConnector()

    base = Path.home() / ".openclaw" / "data" / "ones_exports"

    # 备份现有 11 列文件
    for f in ["2026周报-签约项目统计.csv", "2026周报-POC&提前实施统计.csv"]:
        p = base / f
        if p.exists():
            backup = base / (f + ".bak11col")
            shutil.copy(p, backup)
            print(f"已备份: {f} → {f}.bak11col")

    # 重新导出 sign + poc
    for name in ["sign", "poc"]:
        print(f"\n=== 导出 {name} ===", flush=True)
        result = oc._export_via_browser(name, "202610")
        if result:
            out_csv = base / oc.FILTERS[name]["output_csv"]
            import pandas as pd
            df = pd.read_csv(out_csv, dtype=str, nrows=3)
            print(f"✅ {name}: 导出 {out_csv.name} ({df.shape[1]} 列)", flush=True)
            print(f"   列: {list(df.columns)[:15]}", flush=True)
            print(f"   含所属项目: {'所属项目' in df.columns}", flush=True)
        else:
            print(f"❌ {name}: 导出失败", flush=True)

if __name__ == "__main__":
    main()
