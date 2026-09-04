"""Web UI 启动脚本"""

import uvicorn
import os
import sys

# 确保 fin_l4 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fin_l4.db import init_db


def main():
    """启动 Web UI"""
    # 初始化数据库
    init_db()
    
    # 启动 uvicorn
    from fin_l4.web.main import app
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8500,
        reload=False,
    )


if __name__ == "__main__":
    main()
