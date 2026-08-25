#!/usr/bin/env python3
"""model-scheduling 代理服务 — 接收请求,路由到最优 provider。

启动: python3 proxy.py [--host 127.0.0.1] [--port 3000]
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from config_watcher import ConfigWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(SCRIPT_DIR.parent / "logs" / "model-scheduling.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("model-scheduling.proxy")

watcher = ConfigWatcher(str(SCRIPT_DIR.parent / "config"))

# ─── 任务分类 ───
TASK_KEYWORDS = {
    "coding": ["代码","code","函数","function","class","debug","调试","重构","refactor",
               "修复","fix","bug","编程","git","commit","review","python","javascript",
               "typescript","java","sql","api","接口","测试","test","deploy","写一个","实现"],
    "reasoning": ["推理","reasoning","架构","architecture","设计","design","方案","solution",
                  "策略","strategy","决策","decision","深度","deep","复杂","complex","评估","evaluate",
                  "分析","analyze","比较","compare"],
    "research": ["搜索","search","研究","research","总结","summarize","文档","document",
                 "网络","web","最新","latest","新闻","news","查找","find","查一下"],
}

def classify_task(messages: list[dict]) -> str:
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_user_msg = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        last_user_msg += part.get("text", "")
            break
    msg_lower = last_user_msg.lower()
    for task_type in ["coding", "reasoning", "research"]:
        for kw in TASK_KEYWORDS[task_type]:
            if kw in msg_lower:
                return task_type
    return "chat"

# ─── 模型选择 ───
def select_model(task_type: str) -> dict | None:
    routing = watcher.get("routing.yaml")
    models_config = watcher.get("models.yaml")
    task_routing = routing.get("task_routing", {})
    config = task_routing.get(task_type, task_routing.get("chat", {}))
    fallback_chain = config.get("fallback_chain", [])
    models = {m["id"]: m for m in models_config.get("models", [])}
    for model_ref in fallback_chain:
        model = models.get(model_ref)
        if model and model.get("status") == "active":
            return model
    for model in sorted(models.values(), key=lambda m: m.get("priority", 99)):
        if model.get("status") == "active":
            return model
    return None

# ─── API Key 获取 ───
def get_api_key(provider_id: str) -> str:
    # 1. 从 ~/.zshenv 加载环境变量
    zshenv = Path.home() / ".zshenv"
    if zshenv.exists():
        for line in zshenv.read_text().splitlines():
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                _, _, kv = line.partition("export ")
                key, _, val = kv.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and key not in os.environ:
                    os.environ[key] = val

    env_keys = {
        "coding-plan": ["ARK_API_KEY", "VOLCENGINE_API_KEY", "CODING_PLAN_API_KEY"],
        "longcat": ["LONGCAT_API_KEY", "LONGCAT_KEY"],
    }
    for env_key in env_keys.get(provider_id, []):
        val = os.environ.get(env_key, "")
        if val:
            return val

    # 2. 尝试 auth-profiles.json
    auth_file = Path.home() / ".openclaw" / "auth-profiles.json"
    if auth_file.exists():
        try:
            auth_data = json.loads(auth_file.read_text())
            for pid, pconf in auth_data.get("profiles", {}).items():
                if pid.startswith(provider_id):
                    key = pconf.get("apiKey", "")
                    if key:
                        return key
        except Exception:
            pass

    logger.error(f"无法获取 {provider_id} API key")
    return ""

# ─── HTTP 服务 ───
class ProxyHandler:
    def __init__(self):
        self.request_count = 0
        self.error_count = 0

    async def handle_request(self, reader, writer):
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            parts = request_line.decode().strip().split(" ")
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]

            headers = {}
            while True:
                line = await reader.readline()
                if line == b"\r\n" or not line:
                    break
                if b":" in line:
                    key, _, val = line.decode().partition(":")
                    headers[key.strip().lower()] = val.strip()

            content_length = int(headers.get("content-length", 0))
            body = await reader.read(content_length) if content_length > 0 else b""

            if path == "/v1/chat/completions" and method == "POST":
                await self._handle_chat(body, writer)
            elif path == "/v1/models" and method == "GET":
                await self._handle_models(writer)
            elif path == "/health" and method == "GET":
                await self._handle_health(writer)
            else:
                await self._send_error(404, "Not Found", writer)

        except Exception as e:
            logger.error(f"请求处理失败: {e}")
            self.error_count += 1
            try:
                await self._send_error(500, str(e)[:200], writer)
            except Exception:
                pass
        finally:
            writer.close()

    async def _handle_chat(self, body: bytes, writer):
        self.request_count += 1
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            await self._send_error(400, "Invalid JSON", writer)
            return

        messages = request.get("messages", [])
        stream = request.get("stream", False)
        task_type = classify_task(messages)
        model = select_model(task_type)

        if not model:
            await self._send_error(503, "No available model", writer)
            return

        logger.info(f"任务: {task_type} → 模型: {model['id']}")

        providers = watcher.get("providers.yaml")
        provider_conf = providers.get("providers", {}).get(model["provider"], {})
        if not provider_conf or not provider_conf.get("enabled", False):
            await self._send_error(503, f"Provider {model['provider']} unavailable", writer)
            return

        await self._forward(request, model, provider_conf, writer, stream)

    async def _forward(self, request, model, provider_conf, writer, stream):
        base_url = provider_conf.get("base_url", "").rstrip("/")
        api_key = get_api_key(model["provider"])

        if not api_key:
            await self._send_error(500, f"Cannot get API key for {model['provider']}", writer)
            return

        url = f"{base_url}/chat/completions"
        payload = {**request, "model": model["model_id"]}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )

        try:
            if stream:
                response = urllib.request.urlopen(req, timeout=120)
                await self._stream_response(response, writer, model)
            else:
                response = urllib.request.urlopen(req, timeout=120)
                resp_body = response.read()
                await self._send_response(200, resp_body, writer, model)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Provider API 错误: {e.code} {error_body[:200]}")
            await self._send_error(e.code, error_body[:500], writer)
        except Exception as e:
            logger.error(f"转发失败: {e}")
            await self._send_error(500, str(e)[:200], writer)

    async def _stream_response(self, response, writer, model):
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "X-Model-Scheduling: " + model["id"] + "\r\n"
            "Connection: keep-alive\r\n\r\n"
        )
        writer.write(header.encode())
        await writer.drain()
        try:
            for line in response:
                if line:
                    writer.write(line)
                    await writer.drain()
        except Exception as e:
            logger.error(f"流式传输中断: {e}")

    async def _send_response(self, status, body, writer, model=None):
        try:
            response_data = json.loads(body)
            if model:
                response_data["model_scheduling"] = {"selected_model": model["id"], "provider": model.get("provider")}
            body = json.dumps(response_data).encode()
        except Exception:
            pass
        header = f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        writer.write(header.encode() + body)
        await writer.drain()

    async def _handle_models(self, writer):
        models_config = watcher.get("models.yaml")
        models = [{"id": m["id"], "object": "model", "owned_by": m.get("provider", "unknown")}
                  for m in models_config.get("models", []) if m.get("status") == "active"]
        body = json.dumps({"data": models, "object": "list"}).encode()
        header = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        writer.write(header.encode() + body)
        await writer.drain()

    async def _handle_health(self, writer):
        body = json.dumps({"status": "ok", "requests": self.request_count, "errors": self.error_count}).encode()
        header = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        writer.write(header.encode() + body)
        await writer.drain()

    async def _send_error(self, status, message, writer):
        body = json.dumps({"error": {"message": message, "type": "proxy_error"}}).encode()
        header = f"HTTP/1.1 {status} Error\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        writer.write(header.encode() + body)
        await writer.drain()


async def main():
    parser = argparse.ArgumentParser(description="model-scheduling 代理服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    watcher.start()

    async def handle_client(reader, writer):
        await ProxyHandler().handle_request(reader, writer)

    server = await asyncio.start_server(handle_client, args.host, args.port)
    addr = server.sockets[0].getsockname()
    logger.info(f"代理服务已启动: {addr[0]}:{addr[1]}")
    print(f"✅ 代理服务已启动: {addr[0]}:{addr[1]}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
