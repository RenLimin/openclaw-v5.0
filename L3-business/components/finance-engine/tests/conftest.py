"""finance-engine 测试共享配置"""

import sys
from pathlib import Path

# 将 L3-business/components/ 加入 sys.path
# finance_engine -> finance-engine 符号链接已存在
PARENT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PARENT_DIR))
