#!/usr/bin/env python3
"""导出 202610 确收/验收交接数据（浏览器自动化 CDP 路径）。"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bdms.core.config import get_config
from bdms.modules.integration.connectors.wecom_doc_connector import WecomDocConnector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

def main():
    _ = get_config()
    connector = WecomDocConnector()

    for doc_type in ["确收交接", "验收交接"]:
        print(f"\n=== 导出 {doc_type} ===", flush=True)
        data = connector._fetch_via_browser("202610", doc_type)
        if data:
            print(f"✅ {doc_type}: {len(data)} 行", flush=True)
            # 检查是否有 202610 数据特征
            import json
            sample = data[1] if len(data) > 1 else {}
            print(f"  样例: {json.dumps(sample, ensure_ascii=False)[:200]}", flush=True)
        else:
            print(f"❌ {doc_type}: 导出失败/空", flush=True)

if __name__ == "__main__":
    main()
