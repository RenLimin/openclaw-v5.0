#!/usr/bin/env python3
"""
DMS-Framework HTTP API 入口

基于 FastAPI，自动从模块注册生成 REST 端点。
支持 JWT Bearer Token + X-API-Key 双模式认证。

用法:
    python dms_api.py                  # 默认 127.0.0.1:8000
    python dms_api.py --host 0.0.0.0 --port 8080
    uvicorn dms_api:app --reload
"""
from __future__ import annotations

import argparse
import os
import sys

# 确保本目录在 import 路径首位
sys.path.insert(0, os.path.dirname(__file__))


def create_app(db_url: str | None = None, config: dict | None = None):
    """创建 FastAPI 应用（供 uvicorn 使用）。"""
    from core.database import Database
    from core.api import create_app as _create_fastapi_app
    from core.config import get_config
    from dms import build_registry

    cfg = get_config()
    actual_db_url = db_url or cfg.db_url
    registry = build_registry()
    db = Database(actual_db_url)
    app = _create_fastapi_app(registry, db, config)
    return app


# 全局 app 实例（供 uvicorn 直接引用）
app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(prog="dms-api", description="DMS Framework HTTP API Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")
    parser.add_argument("--db", default="delivery.db", help="数据库路径")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("❌ uvicorn 未安装。请运行: pip install uvicorn")
        sys.exit(1)

    print(f"🚀 DMS Framework API starting...")
    print(f"   URL: http://{args.host}:{args.port}")
    print(f"   Docs: http://{args.host}:{args.port}/docs")
    print(f"   DB: {args.db}")

    uvicorn.run(
        "dms_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
