"""视觉回归服务前置探测守卫的 hermetic 单测（E-01）。

锁定 `VisualTestBase.ensure_http_service_available` 三态语义：
- 目标 HTTP 端口拒绝连接（预览服务未启动）→ pytest.skip，而不是把
  ERR_CONNECTION_REFUSED 误报成视觉回归失败；
- 端口在监听（即使返回错误状态码）→ 不 skip，交由真实浏览器/像素校验暴露；
- file:// URL → 不做 TCP 探测（本地文件无需服务）。

不启动浏览器、不依赖网络与登录态，全部本地自举。
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import sys
from pathlib import Path

import pytest

_VISUAL_DIR = Path(__file__).resolve().parent
if str(_VISUAL_DIR) not in sys.path:
    sys.path.insert(0, str(_VISUAL_DIR))

from base import VisualTestBase  # noqa: E402


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_closed_connection_is_skipped():
    port = _free_port()  # 绑定后立即释放，保证无监听
    url = f"http://127.0.0.1:{port}/"
    with pytest.raises(pytest.skip.Exception) as excinfo:
        VisualTestBase.ensure_http_service_available(url)
    message = str(excinfo.value)
    assert "预览服务未启动" in message
    assert f"127.0.0.1:{port}" in message


def test_listening_port_is_not_skipped():
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler)
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 服务在监听（即使页面返回 404）也不应被前置守卫 skip
        VisualTestBase.ensure_http_service_available(f"http://127.0.0.1:{port}/")
    finally:
        server.shutdown()
        server.server_close()


def test_file_url_bypasses_probe():
    # file:// 无主机/端口，直接返回，不应触发任何网络或 skip
    VisualTestBase.ensure_http_service_available("file:///tmp/whatever.html")
