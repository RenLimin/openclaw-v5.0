"""加密工具 — PBKDF2 密钥派生 + AES-256-GCM

使用 cryptography 库实现:
- PBKDF2-HMAC-SHA256 密钥派生（600,000 轮迭代，符合 OWASP 推荐）
- AES-256-GCM 认证加密（提供机密性 + 完整性）
- 每个消息独立 salt + nonce，输出格式: version || salt_len || salt || nonce || ciphertext || tag

输出格式 (二进制):
  [1 byte version]
  [2 bytes salt length]
  [salt bytes]
  [12 bytes nonce]
  [ciphertext bytes]
  [16 bytes GCM tag]

注意:
- 密钥从不硬编码，由用户密码 / 主密钥通过 PBKDF2 派生
- 不存储密码，只存 salt（用于派生密钥时的盐值；密码由用户保管）
"""

import os
import base64
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag


# ---------- 常量 ----------

# 协议版本号（便于未来升级）
_VERSION = 1

# AES-256 密钥长度
_KEY_LEN = 32  # 256 bits

# GCM nonce 长度（推荐 12 字节）
_NONCE_LEN = 12

# GCM tag 长度
_TAG_LEN = 16

# PBKDF2 迭代次数（OWASP 2023 推荐 SHA-256 ≥ 600,000）
_PBKDF2_ITERATIONS = 600_000

# 默认 salt 长度
_DEFAULT_SALT_LEN = 16


class EncryptionError(Exception):
    """加密/解密相关错误"""
    pass


# ---------- 密钥派生 ----------

def derive_key(password: str, salt: bytes,
               iterations: int = _PBKDF2_ITERATIONS,
               key_len: int = _KEY_LEN) -> bytes:
    """
    使用 PBKDF2-HMAC-SHA256 从密码派生密钥

    Args:
        password: 用户密码（字符串）
        salt: 盐值（字节，每个用户/每条记录应唯一）
        iterations: 迭代次数
        key_len: 密钥长度（字节）

    Returns:
        派生密钥（字节）
    """
    if not password:
        raise EncryptionError("Password cannot be empty")
    if not salt or len(salt) < 8:
        raise EncryptionError("Salt must be at least 8 bytes")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=key_len,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def generate_salt(length: int = _DEFAULT_SALT_LEN) -> bytes:
    """生成随机盐值"""
    return os.urandom(length)


# ---------- 核心加解密 ----------

def encrypt_data(plaintext: bytes, password: str,
                 salt: Optional[bytes] = None,
                 associated_data: Optional[bytes] = None) -> bytes:
    """
    加密二进制数据

    Args:
        plaintext: 明文（字节）
        password: 用户密码
        salt: 盐值（不提供则随机生成）
        associated_data: 附加认证数据（不加密但参与认证）

    Returns:
        加密后的二进制包（version || salt_len || salt || nonce || ciphertext || tag）
    """
    if salt is None:
        salt = generate_salt()

    # 派生密钥
    key = derive_key(password, salt)

    # 生成随机 nonce
    nonce = os.urandom(_NONCE_LEN)

    # AES-GCM 加密
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data)

    # ciphertext_with_tag 最后 16 字节是 tag
    ciphertext = ciphertext_with_tag[:-_TAG_LEN]
    tag = ciphertext_with_tag[-_TAG_LEN:]

    # 打包: version(1) + salt_len(2) + salt + nonce(12) + ciphertext + tag(16)
    salt_len = len(salt)
    return (
        bytes([_VERSION])
        + salt_len.to_bytes(2, "big")
        + salt
        + nonce
        + ciphertext
        + tag
    )


def decrypt_data(blob: bytes, password: str,
                 associated_data: Optional[bytes] = None) -> bytes:
    """
    解密二进制数据

    Args:
        blob: 加密后的二进制包
        password: 用户密码
        associated_data: 附加认证数据（必须与加密时一致）

    Returns:
        明文（字节）

    Raises:
        EncryptionError: 解密失败（密码错误 / 数据损坏）
    """
    if not blob or len(blob) < 1 + 2 + 8 + _NONCE_LEN + _TAG_LEN:
        raise EncryptionError("Invalid encrypted data: too short")

    # 解包
    offset = 0
    version = blob[offset]
    offset += 1
    if version != _VERSION:
        raise EncryptionError(f"Unsupported encryption version: {version}")

    salt_len = int.from_bytes(blob[offset:offset + 2], "big")
    offset += 2
    if salt_len < 8 or salt_len > 1024:
        raise EncryptionError(f"Invalid salt length: {salt_len}")

    salt = blob[offset:offset + salt_len]
    offset += salt_len

    nonce = blob[offset:offset + _NONCE_LEN]
    offset += _NONCE_LEN

    # 剩余部分: ciphertext + tag
    remaining = blob[offset:]
    if len(remaining) < _TAG_LEN:
        raise EncryptionError("Invalid encrypted data: missing tag")

    ciphertext = remaining[:-_TAG_LEN]
    tag = remaining[-_TAG_LEN:]

    # 派生密钥
    try:
        key = derive_key(password, salt)
    except EncryptionError:
        raise

    # AES-GCM 解密
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, associated_data)
    except InvalidTag:
        raise EncryptionError(
            "Decryption failed: wrong password or data corrupted"
        )

    return plaintext


# ---------- 字符串便捷方法 ----------

def encrypt_string(plaintext: str, password: str,
                   associated_data: Optional[bytes] = None) -> str:
    """
    加密字符串，返回 Base64 编码的密文

    Args:
        plaintext: 明文字符串
        password: 用户密码
        associated_data: 附加认证数据

    Returns:
        Base64 编码的密文字符串
    """
    blob = encrypt_data(plaintext.encode("utf-8"), password,
                        associated_data=associated_data)
    return base64.b64encode(blob).decode("ascii")


def decrypt_string(ciphertext_b64: str, password: str,
                   associated_data: Optional[bytes] = None) -> str:
    """
    解密 Base64 编码的密文，返回明文字符串

    Args:
        ciphertext_b64: Base64 编码的密文
        password: 用户密码
        associated_data: 附加认证数据

    Returns:
        明文字符串

    Raises:
        EncryptionError: 解密失败
    """
    try:
        blob = base64.b64decode(ciphertext_b64)
    except (ValueError, base64.binascii.Error) as e:
        raise EncryptionError(f"Invalid base64 data: {e}")

    plaintext_bytes = decrypt_data(blob, password,
                                   associated_data=associated_data)
    return plaintext_bytes.decode("utf-8")
