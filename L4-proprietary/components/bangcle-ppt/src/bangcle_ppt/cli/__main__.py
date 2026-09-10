"""允许 python -m bangcle_ppt.cli 直接运行。"""

from .pptgen import main
import sys

if __name__ == "__main__":
    sys.exit(main())
