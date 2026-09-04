"""安全模块

功能:
- 加密工具 (encryption): PBKDF2 密钥派生 + AES-256-GCM
- 备份恢复 (backup): SQLite 备份 + AES 加密
- 审计日志 (audit): 审计日志封装

设计原则:
- 纯 Python 库，依赖 cryptography
- 不注册 OpenClaw 工具
- 密钥不从代码中硬编码，由调用方（用户密码 / 主密钥）派生
- 与 OpenClaw 端口 18789 无冲突（L4 端口 8500）
"""

from fin_l4.security.encryption import (
    derive_key,
    encrypt_data,
    decrypt_data,
    encrypt_string,
    decrypt_string,
    EncryptionError,
)
from fin_l4.security.backup import BackupManager
from fin_l4.security.audit import AuditLogger

__all__ = [
    "derive_key",
    "encrypt_data",
    "decrypt_data",
    "encrypt_string",
    "decrypt_string",
    "EncryptionError",
    "BackupManager",
    "AuditLogger",
]
