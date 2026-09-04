"""Web UI 启动脚本 — 配置化版本

支持环境变量:
  FIN4_HOST   监听地址 (默认 127.0.0.1)
  FIN4_PORT   端口     (默认 8500)
  FIN4_DB_DIR 数据目录 (默认 ~/.fin-l4)
  也可在项目根目录放 .env 文件

用法:
  python3 fin_l4/run_web.py
  FIN4_HOST=0.0.0.0 FIN4_PORT=8500 FIN4_DB_DIR=/data/fin4 python3 fin_l4/run_web.py
"""

import uvicorn
import os
import sys

# 确保 fin_l4 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fin_l4.db import init_db
from fin_l4.config import get_settings


def main():
    """启动 Web UI"""
    settings = get_settings()

    # 初始化数据库
    init_db(settings.db_path)

    print(f"[FIN-L4] 启动于 http://{settings.host}:{settings.port}")
    print(f"[FIN-L4] 数据库: {settings.db_path}")
    print(f"[FIN-L4] 家庭ID: {settings.family_id}")

    # 启动 uvicorn
    from fin_l4.web.main import app
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
