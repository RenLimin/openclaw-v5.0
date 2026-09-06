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
    "multimodal": ["图片","图像","image","picture","photo","截图","看图","读图",
                   "视频","video","帧","frame","画面",
                   "识别","ocr","OCR","文字识别",
                   "描述图片","描述图","图里有","这张图","这张照片",
                   "视觉","vision","多模态","multimodal"],
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
    # 检查消息中是否包含图片/视频附件(多模态输入检测)
    has_media = False
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") in ("image_url", "image", "video", "video_url"):
                        has_media = True
                        break
                    # 检查 base64 或 data URL 形式的图片
                    if part.get("type") == "text" and "data:image" in str(part.get("text", "")):
                        has_media = True
                        break
        if has_media:
            break

    msg_lower = last_user_msg.lower()
    
    # 有媒体附件时,优先判定为 multimodal
    if has_media:
        return "multimodal"
    
    for task_type in ["multimodal", "coding", "reasoning", "research"]:
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
    required_input_types = config.get("requires_input_types", [])
    for model_ref in fallback_chain:
        model = models.get(model_ref)
        if not model or model.get("status") != "active":
            continue
        # 能力匹配检查: 模型必须支持任务需要的输入类型
        model_input_types = set(model.get("input_types", ["text"]))
        if any(t not in model_input_types for t in required_input_types):
            continue
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

# ─── Embedding 速率限制（模块级全局）───
_EMBEDDING_PROVIDER = "coding-plan"
_EMBEDDING_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
_EMBEDDING_MAX_BATCH = 10  # 火山 API 单批上限
_EMBEDDING_MIN_INTERVAL = 2.0  # 全局最小请求间隔(秒)
_embedding_last_request_time = [0.0]
_embedding_lock = asyncio.Lock()

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
            if content_length > 0:
                try:
                    body = await asyncio.wait_for(
                        reader.readexactly(content_length), timeout=30.0
                    )
                except (asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                    logger.error(f"读取 body 失败: {e} (expected {content_length} bytes)")
                    await self._send_error(400, f"Body read error: {e}", writer)
                    return
            else:
                body = b""

            if path in ("/v1/chat/completions", "/chat/completions") and method == "POST":
                await self._handle_chat(body, writer)
            elif path in ("/v1/embeddings", "/embeddings") and method == "POST":
                await self._handle_embeddings(body, writer)
            elif path in ("/v1/models", "/models") and method == "GET":
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

    async def _handle_embeddings(self, body: bytes, writer):
        """处理 embedding 请求 — 分片转发到火山 coding-plan。"""
        global _embedding_last_request_time
        self.request_count += 1
        try:
            request = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Embedding JSON decode failed: {e}")
            await self._send_error(400, "Invalid JSON", writer)
            return

        inputs = request.get("input", [])
        if not inputs:
            await self._send_error(400, "Empty input", writer)
            return

        model = request.get("model", "doubao-embedding-vision-251215")
        logger.info(f"Embedding request: {len(inputs)} inputs, model={model}")

        # 获取 API key
        api_key = get_api_key(_EMBEDDING_PROVIDER)
        if not api_key:
            await self._send_error(500, "Cannot get coding-plan API key", writer)
            return

        # 分片处理（火山限 10 条/批）
        all_embeddings = []
        total_usage = {"prompt_tokens": 0, "total_tokens": 0}
        try:
            for batch_start in range(0, len(inputs), _EMBEDDING_MAX_BATCH):
                batch = inputs[batch_start:batch_start + _EMBEDDING_MAX_BATCH]
                payload = json.dumps({"model": model, "input": batch})

                # 全局速率限制：确保请求间隔 >= EMBEDDING_MIN_INTERVAL
                async with _embedding_lock:
                    import time as _time
                    now = _time.monotonic()
                    elapsed = now - _embedding_last_request_time[0]
                    wait = _EMBEDDING_MIN_INTERVAL - elapsed
                    if wait > 0:
                        await asyncio.sleep(wait)
                    _embedding_last_request_time[0] = _time.monotonic()

                req = urllib.request.Request(
                    f"{_EMBEDDING_BASE_URL}/embeddings",
                    data=payload.encode(),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                response = urllib.request.urlopen(req, timeout=60)
                result = json.loads(response.read())

                if "data" in result:
                    for item in result["data"]:
                        all_embeddings.append(item)
                    usage = result.get("usage", {})
                    total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    total_usage["total_tokens"] += usage.get("total_tokens", 0)
                else:
                    logger.error(f"Embedding batch {batch_start} error: {result}")
                    await self._send_error(502, f"Provider error: {result.get('error', {}).get('message', 'unknown')}", writer)
                    return

                logger.debug(f"Batch {batch_start}-{batch_start + len(batch) - 1} OK")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Embedding provider error: {e.code} {error_body[:200]}")
            await self._send_error(e.code, error_body[:500], writer)
            return
        except Exception as e:
            logger.error(f"Embedding forwarding failed: {e}")
            await self._send_error(500, str(e)[:200], writer)
            return

        # 构造 OpenAI-compatible 响应
        response_data = {
            "object": "list",
            "data": [
                {"object": "embedding", "embedding": item["embedding"], "index": idx}
                for idx, item in enumerate(all_embeddings)
            ],
            "model": model,
            "usage": total_usage,
        }
        resp_body = json.dumps(response_data).encode()
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(resp_body)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(header.encode() + resp_body)
        await writer.drain()
        logger.info(f"Embedding response: {len(all_embeddings)} vectors, {total_usage['total_tokens']} tokens")

    async def _handle_chat(self, body: bytes, writer):
        self.request_count += 1
        logger.debug(f"RAW body first 300 bytes: {body[:300]}")
        try:
            request = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed: {e}. Body length={len(body)}, first 200: {body[:200]}")
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
