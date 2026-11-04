#!/usr/bin/env python3
"""端点健康探测（stdlib，零第三方依赖）。

供错误扫描器对 FailoverError 做"对症处置"：FailoverError 通常是上游模型
端点慢/不可用，而 gateway 进程本身健康。这里聚合探测 providers.yaml 中
所有 enabled 端点，单端点失败不影响其它，严格短超时。
"""
import os
import time
import urllib.request
import urllib.error

DEFAULT_TIMEOUT = 8  # urlopen 单值总超时（秒）；urllib 不支持 (connect,read) 元组

_PROVIDERS_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "providers.yaml",
)


def load_providers(path=_PROVIDERS_YAML):
    """读取 providers 配置，返回 {name: {base_url, enabled, health_check}}。

    优先用 PyYAML（运行环境已确认可用）；不可用时用一个"仅够解析本文件"
    的最小缩进解析器，避免硬依赖。
    """
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        provs = data.get("providers", {}) if isinstance(data, dict) else {}
        out = {}
        for name, cfg in provs.items():
            if isinstance(cfg, dict):
                out[name] = cfg
        return out
    except Exception:
        return _parse_providers_minimal(text)


def _parse_providers_minimal(text):
    """无 PyYAML 时的兜底解析（只识别 providers: 下两级缩进的 name + 字段）。"""
    provs = {}
    cur = None
    in_providers = False
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.startswith("providers:"):
            in_providers = True
            continue
        if not in_providers:
            continue
        if indent == 2 and line.endswith(":"):  # provider 名
            cur = line[:-1].strip()
            provs[cur] = {}
        elif indent == 4 and cur and ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().strip('"').strip("'")
            provs[cur][k.strip()] = v
    return provs


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def probe_endpoints(providers=None, timeout=DEFAULT_TIMEOUT, only_enabled=True):
    """逐个探测端点 health_check.endpoint（默认 /models）。

    返回 {name: {ok, status, latency_ms, error, base_url}}。
    每个端点独立 try/except + 严格超时；认证类失败(401/403)记 ok=False，
    网络层不可达也记 ok=False——调用方据"全挂/部分挂/全通"决策。
    """
    if providers is None:
        providers = load_providers()
    result = {}
    for name, cfg in providers.items():
        enabled = cfg.get("enabled", True)
        if only_enabled and not _truthy(enabled):
            continue
        base = str(cfg.get("base_url", "")).rstrip("/")
        hc = cfg.get("health_check") or {}
        path = "/models"
        per_timeout = timeout
        if isinstance(hc, dict):
            path = hc.get("endpoint", "/models")
            tms = hc.get("timeout_ms")
            if tms:  # providers.yaml 给的是总超时(ms)，转秒；封顶不超过调用方预算
                per_timeout = min(float(timeout), float(tms) / 1000.0)
        url = base + (path if path.startswith("/") else "/" + path)

        # reachable: TCP/TLS+HTTP 层拿到了服务器的任意响应码（含 401/403/429/404）。
        # 扫描器不带 apiKey，/models 通常回 401——这说明端点活着；FailoverError
        # timeout 对应的是网络层无响应（超时/DNS/拒绝），二者必须区分。
        entry = {"base_url": base, "url": url, "ok": False, "reachable": False,
                 "status": None, "latency_ms": None, "error": None}
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=per_timeout) as resp:
                code = resp.getcode()
                entry["status"] = code
                entry["reachable"] = True
                entry["ok"] = 200 <= code < 400
        except urllib.error.HTTPError as e:
            entry["status"] = e.code
            entry["reachable"] = True   # 服务器有响应 = 可达
            entry["ok"] = False
            entry["error"] = f"HTTP {e.code}"
        except Exception as e:  # 超时 / DNS / 连接拒绝 → 不可达
            entry["error"] = type(e).__name__
        entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
        result[name] = entry
    return result


def summarize(probe):
    """按"网络层可达性"归纳为 (all_unreachable, any_unreachable, total)。

    以 reachable（拿到任意 HTTP 响应）为准，而非 2xx——无 key 探测回 401
    仍代表端点存活。FailoverError 对症只关心端点是否在网络层失联。
    """
    total = len(probe)
    any_unreachable = any(not v["reachable"] for v in probe.values())
    all_unreachable = total > 0 and all(not v["reachable"] for v in probe.values())
    return all_unreachable, any_unreachable, total
