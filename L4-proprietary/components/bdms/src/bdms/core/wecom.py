"""企微 CLI 调用模块 — 封装 wecom-cli 二进制调用。

通过 subprocess 调用 wecom-cli，自动注入配置目录。
首次调用自动执行 auth init（使用 OpenClaw 配置中的 botId/secret）。

与插件逻辑对齐：
- 二进制定位：优先插件依赖内的平台二进制
- 配置目录：<state>/wecom-cli/<safeBotId>-<sha8(botId:secret)>
- 授权方式：auth init --bot-id/--secret（非 TTY 模式走直连分支）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 二进制候选路径（按优先级排序）
_BIN_CANDIDATES = [
    # 插件依赖内的平台二进制（跳过 node shim，少一次冷启动）
    "{state_dir}/npm/projects/wecom-wecom-openclaw-plugin-18f843d908__openclaw-generation__g-8f3a4349afa261a8/node_modules/@wecom/cli-darwin-arm64/bin/wecom-cli",
    "{state_dir}/npm/projects/wecom-wecom-openclaw-plugin-18f843d908__openclaw-generation__g-8f3a4349afa261a8/node_modules/@wecom/cli-darwin-x64/bin/wecom-cli",
    "{state_dir}/npm/projects/wecom-wecom-openclaw-plugin-18f843d908__openclaw-generation__g-8f3a4349afa261a8/node_modules/@wecom/cli-linux-arm64/bin/wecom-cli",
    "{state_dir}/npm/projects/wecom-wecom-openclaw-plugin-18f843d908__openclaw-generation__g-8f3a4349afa261a8/node_modules/@wecom/cli-linux-x64/bin/wecom-cli",
]

_auth_init_done: Dict[str, bool] = {}  # key: config_dir 路径


def _state_dir() -> Path:
    """OpenClaw 状态目录。"""
    return Path(os.environ.get("OPENCLAW_STATE_DIR", Path.home() / ".openclaw"))


def _find_cli_bin() -> Optional[str]:
    """定位 wecom-cli 二进制。

    优先级：
    1. 插件依赖内的平台原生二进制（最快）
    2. 配置显式指定（bdms.core.config wecom.cli_bin_path）
    3. PATH 中的 wecom-cli
    """
    # 先看配置里有没有显式指定
    try:
        from bdms.core.config import get
        explicit = get("wecom.cli_bin_path", "")
        if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit
    except Exception:
        pass

    state = str(_state_dir())
    for candidate in _BIN_CANDIDATES:
        path = candidate.format(state_dir=state)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    # 最后试 PATH
    found = shutil.which("wecom-cli")
    return found


def _safe_bot_id(bot_id: str) -> str:
    """将 botId 转换为安全的目录名。"""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in bot_id)


def _get_config_dir(bot_id: str, secret: str) -> Path:
    """计算配置目录（与插件 wecom-cli tool 逻辑一致）。

    目录名 = <safeBotId>-<sha256(botId:secret)[:8]>
    secret 指纹编进目录名 → secret 一变目录就变 → 自动重新授权。
    """
    fp = hashlib.sha256(f"{bot_id}:{secret}".encode("utf-8")).hexdigest()[:8]
    return _state_dir() / "wecom-cli" / f"{_safe_bot_id(bot_id)}-{fp}"


def _read_openclaw_credentials() -> tuple[str, str]:
    """从 OpenClaw 配置读取 botId/secret。

    读取顺序：
    1. 环境变量 WECOM_BOT_ID / WECOM_BOT_SECRET
    2. bdms 配置（wecom.bot_id / wecom.bot_secret）
    3. openclaw.json 中的 channels.wecom 配置
    """
    bot_id = os.environ.get("WECOM_BOT_ID", "")
    secret = os.environ.get("WECOM_BOT_SECRET", "")
    if bot_id and secret:
        return bot_id, secret

    # 从 bdms 配置读
    try:
        from bdms.core.config import get
        cfg_bot_id = get("wecom.bot_id", "")
        cfg_secret = get("wecom.bot_secret", "")
        if cfg_bot_id and cfg_secret:
            return cfg_bot_id, cfg_secret
    except Exception:
        pass

    # 从 openclaw.json 读（不经过 openclaw CLI，避免 secret 被 redact）
    cfg_file = _state_dir() / "openclaw.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            channels = cfg.get("channels", {})
            wecom_cfg = channels.get("wecom", {})
            file_bot_id = wecom_cfg.get("botId", "")
            file_secret = wecom_cfg.get("secret", "")
            if file_bot_id and file_secret and not file_secret.startswith("__"):
                return file_bot_id, file_secret
        except Exception:
            pass

    return "", ""


def _ensure_auth(bin_path: str, config_dir: Path, bot_id: str, secret: str) -> bool:
    """确保 wecom-cli 已授权。首次调用自动执行 auth init。

    短路判定：credentials.enc 和 .encryption_key 都存在 → 已授权。
    原因：auth init 无幂等，每次都会打鉴权接口（45009 频率限制）。
    """
    dir_str = str(config_dir)
    if _auth_init_done.get(dir_str, False):
        return True

    # 短路：两个文件都存在则认为已授权
    cred_file = config_dir / "credentials.enc"
    key_file = config_dir / ".encryption_key"
    if cred_file.exists() and key_file.exists():
        _auth_init_done[dir_str] = True
        return True

    config_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["WECOM_CLI_CONFIG_DIR"] = str(config_dir)
    env["WECOM_CLI_LOG_LEVEL"] = "warn"

    try:
        result = subprocess.run(
            [bin_path, "auth", "init", "--bot-id", bot_id, "--secret", secret],
            capture_output=True, text=True, timeout=30,
            env=env, cwd=str(_state_dir()),
        )
        if result.returncode == 0:
            _auth_init_done[dir_str] = True
            return True

        # 解析错误信息
        try:
            err_data = json.loads(result.stdout)
            errcode = err_data.get("errcode") or err_data.get("error", {}).get("code")
            errmsg = err_data.get("errmsg") or err_data.get("error", {}).get("message", "unknown")
            logger.warning(f"wecom-cli auth init 失败: [{errcode}] {errmsg}")
        except json.JSONDecodeError:
            logger.warning(f"wecom-cli auth init 失败: {result.stderr[:200] or result.stdout[:200]}")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("wecom-cli auth init 超时")
        return False
    except Exception as e:
        logger.warning(f"wecom-cli auth init 异常: {e}")
        return False


def wecom_cli_call(args: List[str]) -> Optional[Dict[str, Any]]:
    """调用 wecom-cli 并返回 JSON 结果。

    Args:
        args: wecom-cli 子命令及参数，例如
            ["doc", "search", "--json", '{"keywords":[...]}']

    Returns:
        解析后的 JSON dict；失败或非 JSON 输出返回 None，
        原始文本存在返回 dict 的 _raw_output 字段中。
    """
    bin_path = _find_cli_bin()
    if not bin_path:
        logger.warning("未找到 wecom-cli 可执行文件")
        return None

    bot_id, secret = _read_openclaw_credentials()
    if not bot_id or not secret:
        logger.warning("无企微 botId/secret，无法调用 wecom-cli")
        return None

    config_dir = _get_config_dir(bot_id, secret)

    # 确保已授权
    if not _ensure_auth(bin_path, config_dir, bot_id, secret):
        return None

    env = os.environ.copy()
    env["WECOM_CLI_CONFIG_DIR"] = str(config_dir)
    env["WECOM_CLI_LOG_LEVEL"] = "warn"

    try:
        result = subprocess.run(
            [bin_path] + args,
            capture_output=True, text=True, timeout=60,
            env=env, cwd=str(_state_dir()),
        )
        stdout = result.stdout.strip()

        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"_raw_output": stdout}

        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"wecom-cli 调用超时: {' '.join(args[:3])}")
        return None
    except Exception as e:
        logger.warning(f"wecom-cli 调用异常: {e}")
        return None
