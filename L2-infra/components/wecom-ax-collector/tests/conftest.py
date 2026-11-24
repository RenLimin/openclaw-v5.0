"""企微 AX 采集组件测试配置。"""
import sys
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = COMP_DIR / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

for p in (str(SCRIPTS_DIR), str(COMP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
