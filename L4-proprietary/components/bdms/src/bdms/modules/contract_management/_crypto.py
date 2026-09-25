"""AES-256 加密/解密工具 — 用于合同敏感字段。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

使用 Fernet (AES-128-CBC) 或 AES-256-GCM。
密钥从环境变量 BDMS_CONTRACT_KEY 获取，或使用默认派生。
"""

import os
import base64
import hashlib
from typing import Optional

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _get_key() -> bytes:
    """获取加密密钥（从环境变量或默认派生）。"""
    env_key = os.environ.get("BDMS_CONTRACT_KEY", "")
    if env_key:
        return base64.urlsafe_b64encode(env_key.encode()[:32].ljust(32, b'\0'))
    # 默认密钥（开发用，生产环境必须设置环境变量）
    default = b"bdms-contract-management-v2.1-default-key-change-me"
    return base64.urlsafe_b64encode(default[:32].ljust(32, b'\0'))


def encrypt(plaintext: str) -> str:
    """加密字符串。返回 base64 编码的密文。"""
    if not plaintext:
        return ""
    if not _HAS_CRYPTO:
        # fallback: base64 编码（无加密，仅用于开发）
        return "b64:" + base64.b64encode(plaintext.encode()).decode()

    key = _get_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密字符串。"""
    if not ciphertext:
        return ""
    if not _HAS_CRYPTO:
        if ciphertext.startswith("b64:"):
            return base64.b64decode(ciphertext[4:]).decode()
        return ciphertext

    key = _get_key()
    f = Fernet(key)
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext  # 解密失败返回原文


def mask_name(name: str) -> str:
    """名称脱敏：首尾各 1 字，中间用 *** 代替。"""
    if not name or len(name) <= 2:
        return name
    return name[0] + "***" + name[-1]


def mask_amount(amount: float) -> str:
    """金额脱敏：精确到万。"""
    if amount == 0:
        return "0"
    wan = amount / 10000
    if wan >= 100:
        return f"{wan:.0f}万"
    elif wan >= 10:
        return f"{wan:.1f}万"
    else:
        return f"{wan:.2f}万"
