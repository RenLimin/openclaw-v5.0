#!/usr/bin/env python3
"""model-scheduling 代理服务 — 接收请求,路由到最优 provider。

启动: python3 proxy.py [--host 127.0.0.1] [--port 3000]
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import aiohttp

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

# ─── Provider 健康状态 ───
def _get_provider_health(provider_id: str) -> str:
    """从 usage.json 获取 provider 健康状态(大小写不敏感)。

    TTL 自动降级:
    - unreachable 状态超过 HEALTH_TTL_SECONDS(1小时) → 自动降级为 unknown
      让请求去实际试探，避免永久跳过某个 provider
    - exhausted / healthy 不受 TTL 影响
    """
    import time as _time
    usage_data = watcher.get("usage.json") if hasattr(watcher, "get") else {}
    providers = usage_data.get("providers", {})
    now = _time.time()
    for pid, pdata in providers.items():
        if pid.lower() == provider_id.lower():
            health = pdata.get("health", {})
            status = health.get("status", "")
            last_checked = health.get("last_checked", "")
            # exhausted(余额不足) → degraded(路由排到末尾)
            if status == "exhausted":
                return "degraded"
            # unreachable TTL 自动降级
            if status == "unreachable" and last_checked:
                try:
                    from datetime import datetime, timezone
                    checked_time = datetime.fromisoformat(last_checked)
                    if checked_time.tzinfo is None:
                        checked_time = checked_time.replace(tzinfo=timezone.utc)
                    age_seconds = now - checked_time.timestamp()
                    if age_seconds > 3600:  # 1 hour TTL
                        logger.info(f"Provider {provider_id} unreachable 已超 1h TTL，自动降级为 unknown")
                        return "unknown"
                except (ValueError, TypeError):
                    pass
            return status
    return ""

# ─── 模型选择(返回 chain 列表) ───
def estimate_tokens(request: dict) -> int:
    """粗估请求 token 数（中文 ~1.5 字/token，英文 ~4 字符/token）。"""
    try:
        n = 0
        for msg in request.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        t = item.get("text", "")
                        n += len(t) * (1.5 if any('\u4e00' <= ch <= '\u9fff' for ch in t) else 0.25)
                        # 图片按 ~1.5k tokens 估
                        if item.get("type") in ("image_url", "image"):
                            n += 1500
            elif isinstance(content, str):
                n += len(content) * (1.5 if any('\u4e00' <= ch <= '\u9fff' for ch in content) else 0.25)
        return int(n)
    except Exception:
        return 0


def build_fallback_chain(task_type: str, est_tokens: int = 0) -> list[dict]:
    """根据任务类型构建 fallback 模型链,过滤不可用项。

    est_tokens > 0 时,过滤掉 context_window < est_tokens 的模型(上下文感知路由)。
    """
    routing = watcher.get("routing.yaml")
    models_config = watcher.get("models.yaml")
    providers_config = watcher.get("providers.yaml")
    task_routing = routing.get("task_routing", {})
    config = task_routing.get(task_type, task_routing.get("chat", {}))
    fallback_chain_refs = config.get("fallback_chain", [])
    models = {m["id"]: m for m in models_config.get("models", [])}
    provider_confs = providers_config.get("providers", {})
    # 建立大小写不敏感的 provider 查找映射
    provider_confs_lower = {k.lower(): v for k, v in provider_confs.items()}
    required_input_types = config.get("requires_input_types", [])

    chain = []
    # 大上下文兜底: 估算超过 200k 时,确保链里有 longCat(1M ctx) 兜底
    # 背景: 2026-09-28 事故 — 234k 请求估算在 doubao 阈值下,真实编码超限,
    #       chat 链无 longCat,全链失败 → 503。任何链都应有大 ctx 兜底。
    if est_tokens > 200000:
        LONGCAT_ID = "longCat/LongCat-2.0"
        if LONGCAT_ID not in fallback_chain_refs:
            fallback_chain_refs = fallback_chain_refs + [LONGCAT_ID]
            logger.info(f"大上下文({est_tokens} tokens): 链末尾追加 longCat 兜底")
    for model_ref in fallback_chain_refs:
        model = models.get(model_ref)
        if not model or model.get("status") != "active":
            continue
        # provider 必须启用(大小写不敏感)
        provider_id = model.get("provider", "")
        pconf = provider_confs_lower.get(provider_id.lower(), {})
        if not pconf.get("enabled", False):
            continue
        # provider 健康状态 unreachable → 跳过(exhausted 不跳过,放进去让请求时触发 fallback)
        health = _get_provider_health(provider_id)
        if health == "unreachable":
            continue
        # 能力匹配检查
        model_input_types = set(model.get("input_types", ["text"]))
        if any(t not in model_input_types for t in required_input_types):
            continue
        # 上下文感知: 估算 token 超过模型窗口 → 跳过(避免 400 exceed max tokens)
        if est_tokens > 0:
            ctx = model.get("context_window", 262144)
            if est_tokens > ctx * 0.9:  # 留 10% 余量给输出
                continue
        # degraded(余额不足) → 标记,后续排到链末尾
        if health == "degraded":
            chain.append({"model": model, "_degraded": True})
        else:
            chain.append({"model": model, "_degraded": False})
    # 排序: healthy 在前, degraded 在后(保持各自原有顺序)
    chain.sort(key=lambda x: x.get("_degraded", False))
    result = [x["model"] for x in chain]

    # 修复(2026-09-28): ctx 过滤后链空 → 放宽重建(不过滤 ctx)
    # 背景: 1.05M tokens 会话把 longCat(1M) 也过滤掉 → 空链 → 503。
    # 宁可让最大的模型硬试(可能被 provider 截断),不可直接 503。
    if not result and est_tokens > 0:
        logger.warning(f"ctx 过滤后链空({est_tokens} tokens), 放宽 ctx 过滤重建链")
        result = build_fallback_chain(task_type, 0)
        # 大 ctx 优先: 按 context_window 降序
        result.sort(key=lambda m: -m.get("context_window", 0))
        # longCat(1M) 不在链里 → 强制追加为兜底(它是全系统唯一 1M ctx 模型)
        LONGCAT_ID = "longCat/LongCat-2.0"
        all_ids = [m["id"] for m in result]
        if LONGCAT_ID not in all_ids:
            models_config = watcher.get("models.yaml")
            for m in models_config.get("models", []):
                if m["id"] == LONGCAT_ID and m.get("status") == "active":
                    result.insert(0, m)  # 1M ctx 最大,放最前
                    break
    return result

def select_model(task_type: str) -> dict | None:
    """兼容旧接口: 返回 chain 第一个模型。"""
    chain = build_fallback_chain(task_type)
    if chain:
        return chain[0]
    # 兜底: 所有 active 模型按 priority（稳定排序: priority → id）
    models_config = watcher.get("models.yaml")
    models = {m["id"]: m for m in models_config.get("models", [])}
    for model in sorted(models.values(), key=lambda m: (m.get("priority", 99), m.get("id", ""))):
        if model.get("status") == "active":
            return model
    return None

# ─── API Key 获取 ───
def get_api_key(provider_id: str) -> str:
    """获取 provider API key。

    优先级:
    1. 环境变量(LaunchAgent 启动时已 source ~/.zshenv)
    2. auth-profiles.json(OpenClaw 认证配置)
    3. openclaw.json provider 配置(SecretRef 除外)

    注意: 不直接读取 ~/.zshenv,因为 LaunchAgent 已保证环境变量注入。
    """
    env_keys = {
        "coding-plan": ["ARK_API_KEY", "VOLCENGINE_API_KEY", "CODING_PLAN_API_KEY"],
        "longcat": ["LONGCAT_API_KEY", "LONGCAT_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
    }
    # 1. 环境变量(LaunchAgent source ~/.zshenv 后可用)
    # 大小写不敏感查找(provider 可能是 longCat/longcat/LONGCAT)
    matched_keys = []
    for k, v in env_keys.items():
        if k.lower() == provider_id.lower():
            matched_keys = v
            break
    for env_key in matched_keys:
        val = os.environ.get(env_key, "")
        if val:
            return val

    # 2. auth-profiles.json
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

    # 3. openclaw.json(非 SecretRef)
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            ocfg = json.loads(config_path.read_text())
            providers = ocfg.get("models", {}).get("providers", {})
            pconf = providers.get(provider_id, {})
            key = pconf.get("apiKey", "")
            if isinstance(key, str) and key and not key.startswith("secretref-"):
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
        # provider 连续失败计数（运行时健康反馈，零额外网络请求）
        self._provider_fail_streak: dict[str, int] = {}
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=10)
        )

    def _mark_provider_failure(self, provider_id: str, status_code: int):
        """运行时失败反馈：连续 3 次网络/5xx 失败 → 标记 unreachable（写入 usage.json）。
        与 402(exhausted) 同通道，复用 TTL 自愈机制（1h 后自动降级 unknown 重新试探）。
        仅处理网络类错误(502/504)，不处理 4xx(鉴权/参数)和限流(429)。
        """
        if status_code not in (502, 504):
            return
        import time as _time
        usage_path = Path(__file__).parent.parent / "config" / "usage.json"
        try:
            streak = self._provider_fail_streak.get(provider_id, 0) + 1
            self._provider_fail_streak[provider_id] = streak
            if streak >= 3:
                usage = json.loads(usage_path.read_text())
                providers = usage.setdefault("providers", {})
                for pid, pdata in providers.items():
                    if pid.lower() == provider_id.lower():
                        pdata.setdefault("health", {})["status"] = "unreachable"
                        pdata["health"]["last_checked"] = _time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                        pdata["health"]["detail"] = f"连续 {streak} 次网络失败自动标记"
                usage_path.write_text(json.dumps(usage, indent=2, ensure_ascii=False))
                logger.warning(f"Provider {provider_id} 连续 {streak} 次网络失败 → 标记 unreachable（1h TTL 自愈）")
                self._provider_fail_streak[provider_id] = 0
        except Exception as e:
            logger.warning(f"标记 provider 失败状态异常: {e}")

    def _mark_provider_success(self, provider_id: str):
        """成功后重置失败计数。"""
        if provider_id in self._provider_fail_streak:
            del self._provider_fail_streak[provider_id]


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

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                url = f"{_EMBEDDING_BASE_URL}/embeddings"
                async with self.session.post(url, headers=headers, data=payload.encode()) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Embedding batch {batch_start} error: {resp.status} {error_text[:200]}")
                        await self._send_error(resp.status, error_text[:500], writer)
                        return
                    result = await resp.json()

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

        # P1 修复: 用户手动指定模型时优先使用(不覆盖)
        user_model = request.get("model", "")
        providers_config = watcher.get("providers.yaml")
        if user_model and user_model not in ("coding-plan/auto", "auto", "model-scheduling/auto"):
            # 手动指定了具体模型 → 直接用，不走自动路由
            models_config = watcher.get("models.yaml")
            model_map = {m["id"]: m for m in models_config.get("models", [])}
            target = model_map.get(user_model)
            if target:
                provider_id = target.get("provider", "")
                provider_conf = providers_config.get("providers", {}).get(provider_id, {})
                logger.info(f"手动路由: {user_model} (provider: {provider_id})")
                success, status_code, result = await self._forward_once(request, target, provider_conf, stream, writer)
                if success:
                    return
                logger.warning(f"手动模型 {user_model} 失败({status_code})，回退到自动路由")

        # 自动路由(上下文感知: 大请求自动路由到大 ctx 模型)
        est = estimate_tokens(request)
        if est > 200000:
            logger.info(f"大上下文请求: 估算 ~{est} tokens, 启用上下文感知路由")
        chain = build_fallback_chain(task_type, est)
        if not chain:
            await self._send_error(503, "No available model", writer)
            return
        fallback_path = []
        last_error = None
        last_status = 500

        for idx, model in enumerate(chain):
            provider_id = model.get("provider", "")
            provider_conf = providers_config.get("providers", {}).get(provider_id, {})
            
            if idx == 0:
                logger.info(f"任务: {task_type} → 模型: {model['id']} (provider: {provider_id})")
            else:
                logger.warning(f"Fallback #{idx}: 切换到 {model['id']} (provider: {provider_id}) [前一个失败: {last_status}]")
                fallback_path.append(model["id"])
            
            success, status_code, result = await self._forward_once(request, model, provider_conf, stream, writer)
            
            if success:
                self._mark_provider_success(provider_id)
                if fallback_path:
                    logger.info(f"Fallback 成功: 最终模型 {model['id']}, 路径: {' → '.join(fallback_path)}")
                return
            
            last_status = status_code
            last_error = result
            # 运行时健康反馈：连续网络失败 → 标记 unreachable（TTL 自愈）
            self._mark_provider_failure(provider_id, status_code)
            # 402(余额不足) → 标记 provider exhausted,后续路由排到末尾
            if status_code == 402:
                try:
                    import json as _json, time as _time
                    usage_path = Path(__file__).parent.parent / "config" / "usage.json"
                    if usage_path.exists():
                        usage = _json.loads(usage_path.read_text())
                        providers = usage.setdefault("providers", {})
                        for pid, pdata in providers.items():
                            if pid.lower() == provider_id.lower():
                                pdata.setdefault("health", {})["status"] = "exhausted"
                                pdata["health"]["last_checked"] = _time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                        usage_path.write_text(_json.dumps(usage, indent=2, ensure_ascii=False))
                        logger.info(f"Provider {provider_id} 余额不足(402), 标记 exhausted")
                except Exception as e:
                    logger.warning(f"标记 exhausted 失败: {e}")
            # 4xx 中只有 401/403 不可重试(鉴权问题,换 provider 也没用)
            # 402(余额不足)、429(限流)、404(模型不存在) → 继续 fallback
            if status_code in (401, 403):
                break
        
        # 所有模型都失败 — 返回聚合诊断而非最后一个错误(避免 Gateway 误判 billing)
        self.error_count += 1
        if est > 200000:
            await self._send_error(413, f"Request context (~{est} tokens) exceeds all available models. Tip: compact the session or switch to a large-context model (longCat/LongCat-2.0).", writer)
            return
        await self._send_error(last_status, str(last_error)[:500], writer)

    async def _forward_once(self, request, model, provider_conf, stream, writer):
        base_url = provider_conf.get("base_url", "").rstrip("/")
        api_key = get_api_key(model["provider"])

        if not api_key:
            await self._send_error(500, f"Cannot get API key for {model['provider']}", writer)
            return

        url = f"{base_url}/chat/completions"
        # 消息格式转换: OpenClaw content 数组 → provider 期望格式
        messages = request.get("messages", [])
        normalized = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                normalized.append({**msg, "content": "\n".join(text_parts) if text_parts else ""})
            else:
                normalized.append(msg)
        payload = {**request, "model": model["model_id"], "messages": normalized}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=120)
            if stream:
                async with self.session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Provider API 错误 (stream): {model['id']} {response.status} {error_text[:200]}")
                        return False, response.status, error_text
                    await self._stream_response(response, writer, model)
                    return True, 200, ""
            else:
                async with self.session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Provider API 错误: {model['id']} {response.status} {error_text[:200]}")
                        return False, response.status, error_text
                    resp_body = await response.read()
                    await self._send_response(200, resp_body, writer, model)
                    return True, 200, resp_body
        except aiohttp.ClientError as e:
            logger.error(f"转发失败 (network): {model['id']} {type(e).__name__}: {e}")
            return False, 502, f"Network error: {type(e).__name__}: {str(e)[:150]}"
        except asyncio.TimeoutError:
            logger.error(f"转发超时: {model['id']}")
            return False, 504, "Timeout"

    async def _stream_response(self, response: aiohttp.ClientResponse, writer, model):
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
            async for line in response.content:
                if line:
                    writer.write(line)
                    await writer.drain()
        except Exception as e:
            logger.error(f"流式传输中断: {e}")

    async def _send_response(self, status: int, body: bytes, writer, model=None):
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

    async def _send_error(self, status: int, message: str, writer):
        body = json.dumps({"error": {"message": message, "type": "proxy_error"}}).encode()
        header = f"HTTP/1.1 {status} Error\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        writer.write(header.encode() + body)
        await writer.drain()


async def startup_probe():
    """启动时探活 — 并发检测所有 provider 的 DNS + TCP + /models 端点。
    结果写入 usage.json，标记 healthy / degraded / unreachable。
    全部不可用则标记 degraded（带病上线，路由层会跳过）。
    """
    import socket
    from datetime import datetime, timezone

    logger.info("启动探活: 检测所有 provider 健康状态...")
    providers_config = watcher.get("providers.yaml")
    providers = providers_config.get("providers", {})
    if not providers:
        logger.warning("无 provider 配置，跳过探活")
        return

    # 加载现有 usage.json
    usage_path = Path(__file__).parent.parent / "config" / "usage.json"
    if usage_path.exists():
        usage = json.loads(usage_path.read_text())
    else:
        usage = {}
    usage.setdefault("providers", {})

    async def probe_one(provider_id: str, pconf: dict):
        base_url = pconf.get("base_url", "")
        if not base_url:
            return provider_id, "unreachable", "无 base_url"
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 1. DNS 解析
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, port))
        except socket.gaierror as e:
            return provider_id, "unreachable", f"DNS 解析失败: {e}"
        except Exception as e:
            return provider_id, "unreachable", f"DNS 异常: {e}"

        # 2. TCP 连接
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
        except asyncio.TimeoutError:
            return provider_id, "unreachable", "TCP 连接超时"
        except ConnectionRefusedError:
            return provider_id, "unreachable", "TCP 连接拒绝"
        except Exception as e:
            return provider_id, "unreachable", f"TCP 异常: {e}"

        # 3. /models 端点
        api_key = get_api_key(provider_id)
        if not api_key:
            return provider_id, "degraded", "API key 未配置（TCP 可达但无法认证）"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with session.get(f"{base_url}/models", headers=headers) as resp:
                    if resp.status == 200:
                        return provider_id, "healthy", f"healthy ({resp.status})"
                    elif resp.status in (401, 403):
                        return provider_id, "degraded", f"认证失败 ({resp.status})"
                    else:
                        return provider_id, "degraded", f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return provider_id, "degraded", "/models 超时（TCP 可达）"
        except aiohttp.ClientError as e:
            return provider_id, "degraded", f"/models 错误: {type(e).__name__}"
        except Exception as e:
            return provider_id, "degraded", f"/models 异常: {e}"

    # 并发探活
    tasks = [probe_one(pid, pconf) for pid, pconf in providers.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    now = datetime.now(timezone.utc).isoformat()
    healthy_count = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"探活异常: {result}")
            continue
        pid, status, detail = result
        usage["providers"].setdefault(pid, {})
        usage["providers"][pid]["health"] = {
            "status": status,
            "last_checked": now,
            "detail": detail
        }
        if status == "healthy":
            healthy_count += 1
        logger.info(f"  {pid}: {status} — {detail}")

    usage_path.write_text(json.dumps(usage, indent=2, ensure_ascii=False))
    total = len(results)
    logger.info(f"探活完成: {healthy_count}/{total} healthy")
    if healthy_count == 0:
        logger.critical("⚠️ 所有 provider 不可用！proxy 将以 degraded 模式启动")


async def main():
    parser = argparse.ArgumentParser(description="model-scheduling 代理服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--skip-probe", action="store_true", help="跳过启动探活")
    args = parser.parse_args()

    watcher.start()

    # 启动探活（除非显式跳过）
    if not args.skip_probe:
        await startup_probe()

    handler = ProxyHandler()

    server = await asyncio.start_server(
        handler.handle_request, 
        args.host, 
        args.port
    )
    addr = server.sockets[0].getsockname()
    logger.info(f"代理服务已启动: {addr[0]}:{addr[1]}")
    print(f"✅ 代理服务已启动: {addr[0]}:{addr[1]}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
