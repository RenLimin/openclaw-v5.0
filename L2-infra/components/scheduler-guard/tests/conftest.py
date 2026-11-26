import sys
from pathlib import Path

# 让 pytest 直接 `import audit`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
