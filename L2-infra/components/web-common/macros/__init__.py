"""
Web Common — L2 通用 Web UI 组件库

提供 Jinja2 宏 + CSS + JS，供 L4 业务组件复用。

用法::

    from web_common.macros import setup_web_common
    app = FastAPI()
    setup_web_common(app, template_dir="templates", static_dir="static")
"""

from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
MACROS_DIR = PKG_DIR
STATIC_DIR = PKG_DIR.parent / "static"


def get_macros_dir() -> Path:
    """返回宏模板目录路径。"""
    return MACROS_DIR


def get_static_dir() -> Path:
    """返回静态资源目录路径。"""
    return STATIC_DIR


def setup_web_common(
    app,
    template_dir: str | Path | None = None,
    static_dir: str | Path | None = None,
    static_url_path: str = "/static/web-common",
):
    """
    将 web-common 挂载到 FastAPI app 上。

    Args:
        app: FastAPI 实例
        template_dir: 业务模板目录（宏会作为可搜索路径加入 Jinja2）
        static_dir: 业务静态资源目录
        static_url_path: web-common 静态资源 URL 前缀

    Returns:
        Jinja2Templates 实例
    """
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates

    # 挂载静态资源
    static_path = get_static_dir()
    app.mount(static_url_path, StaticFiles(directory=str(static_path)), name="web-common-static")

    # 配置 Jinja2 — 宏目录 + 业务模板目录
    templates = Jinja2Templates(directory=str(MACROS_DIR))
    if template_dir:
        # 把业务模板目录加到搜索路径前面
        from jinja2 import FileSystemLoader
        dirs = [str(template_dir), str(MACROS_DIR)]
        templates.env.loader = FileSystemLoader(dirs)

    return templates
