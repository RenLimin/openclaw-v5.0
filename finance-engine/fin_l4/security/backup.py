"""备份与恢复 — SQLite 备份 + AES 加密

功能:
- 对 SQLite 数据库文件进行在线备份（使用 SQLite backup API）
- 备份文件使用 AES-256-GCM 加密存储
- 支持按保留策略自动清理旧备份
- 支持从备份文件恢复

备份文件格式:
  [4 bytes magic] = "L4BK"
  [2 bytes header_len]
  [header_len bytes JSON header (plaintext)]
  [encrypted blob (AES-256-GCM)]

JSON header 包含元数据（同时作为 AES-GCM 的 associated_data 参与完整性校验）:
  - db_path: 源数据库路径
  - size: 原始文件大小
  - created_at: 创建时间戳 (YYYYMMDD_HHMMSS)
  - version: 备份格式版本
"""

import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from fin_l4.security.encryption import (
    encrypt_data,
    decrypt_data,
    EncryptionError,
)


# 备份文件魔数
_MAGIC = b"L4BK"
_FORMAT_VERSION = 1


class BackupManager:
    """SQLite 数据库备份管理器"""

    def __init__(self, db_path: str, backup_dir: str,
                 retention_count: int = 10,
                 password: str = None):
        """
        Args:
            db_path: 源数据库文件路径
            backup_dir: 备份目录
            retention_count: 保留备份数量（超过自动删除最旧的）
            password: 加密密码（None 表示不加密，不推荐）
        """
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.retention_count = retention_count
        self.password = password

    # ---------- 备份 ----------

    def create_backup(self, password: str = None) -> str:
        """
        创建数据库备份

        Args:
            password: 加密密码（不传则使用初始化时的 password）

        Returns:
            备份文件路径
        """
        pwd = password or self.password
        if pwd is None:
            raise ValueError("Backup encryption password is required")

        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"fin_l4_backup_{timestamp}.db.enc"

        # 第一步: 生成临时明文备份
        tmp_path = self.backup_dir / f".tmp_backup_{timestamp}.db"
        try:
            self._sqlite_backup(str(tmp_path))

            # 第二步: 读取明文
            with open(tmp_path, "rb") as f:
                plain_data = f.read()

            # 构造 header（元数据）
            header = {
                "version": _FORMAT_VERSION,
                "db_path": self.db_path,
                "size": len(plain_data),
                "created_at": timestamp,
            }
            header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")

            # header 作为 associated_data（不加密但参与完整性校验）
            encrypted = encrypt_data(plain_data, pwd,
                                     associated_data=header_bytes)

            # 写入文件: magic(4) + header_len(2) + header + encrypted_blob
            with open(backup_file, "wb") as f:
                f.write(_MAGIC)
                f.write(len(header_bytes).to_bytes(2, "big"))
                f.write(header_bytes)
                f.write(encrypted)

        finally:
            # 清理临时文件
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        # 第三步: 按保留策略清理
        self._apply_retention()

        return str(backup_file)

    def _sqlite_backup(self, target_path: str):
        """使用 SQLite backup API 进行在线备份"""
        src_conn = sqlite3.connect(self.db_path)
        dst_conn = sqlite3.connect(target_path)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
            src_conn.close()

    # ---------- 恢复 ----------

    def restore_backup(self, backup_file: str,
                       target_db_path: str = None,
                       password: str = None) -> str:
        """
        从备份恢复数据库

        Args:
            backup_file: 备份文件路径
            target_db_path: 恢复到的目标路径（不传则覆盖源库，需谨慎）
            password: 解密密码

        Returns:
            恢复后的数据库路径

        Warning:
            如果 target_db_path 为 None，将覆盖源数据库。
            建议先备份当前数据库再恢复。
        """
        pwd = password or self.password
        if pwd is None:
            raise ValueError("Decryption password is required")

        target = target_db_path or self.db_path

        # 读取并解析文件
        with open(backup_file, "rb") as f:
            data = f.read()

        # 解包 header
        if len(data) < 6:
            raise EncryptionError("Backup file too short (invalid header)")

        magic = data[:4]
        if magic != _MAGIC:
            raise EncryptionError(
                f"Invalid backup file: bad magic '{magic.decode('latin-1')}'"
            )

        header_len = int.from_bytes(data[4:6], "big")
        if len(data) < 6 + header_len:
            raise EncryptionError("Backup file header truncated")

        header_bytes = data[6:6 + header_len]
        encrypted = data[6 + header_len:]

        # 解析 header
        try:
            header = json.loads(header_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise EncryptionError(f"Invalid backup header: {e}")

        if header.get("version") != _FORMAT_VERSION:
            raise EncryptionError(
                f"Unsupported backup format version: {header.get('version')}"
            )

        # 解密（header 作为 associated_data）
        try:
            plain_data = decrypt_data(encrypted, pwd,
                                      associated_data=header_bytes)
        except EncryptionError:
            raise

        # 验证大小
        if len(plain_data) != header.get("size", -1):
            raise EncryptionError(
                f"Size mismatch: expected {header['size']}, got {len(plain_data)}"
            )

        # 写入目标路径
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 先写临时文件再替换，确保原子性
        tmp_path = target_path.with_suffix(".tmp_restore")
        try:
            with open(tmp_path, "wb") as f:
                f.write(plain_data)

            # 验证数据库完整性
            self._verify_db(str(tmp_path))

            # 替换目标文件
            if target_path.exists():
                # 保留旧文件为 .bak
                old_bak = target_path.with_suffix(".bak_before_restore")
                if old_bak.exists():
                    old_bak.unlink()
                target_path.rename(old_bak)

            tmp_path.rename(target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return str(target_path)

    def _verify_db(self, db_path: str):
        """验证数据库完整性"""
        conn = sqlite3.connect(db_path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                raise EncryptionError(
                    f"Database integrity check failed: {result[0]}"
                )
        finally:
            conn.close()

    # ---------- 备份列表 ----------

    def list_backups(self) -> List[Dict]:
        """
        列出所有备份文件（按时间倒序）

        Returns:
            [
                {"path": "...", "size": 12345, "created_at": "2026-09-04 10:00:00"},
                ...
            ]
        """
        backups = []
        for f in self.backup_dir.glob("fin_l4_backup_*.db.enc"):
            stat = f.stat()
            # 从文件名解析时间
            try:
                name = f.stem.replace("fin_l4_backup_", "").replace(".db", "")
                dt = datetime.strptime(name, "%Y%m%d_%H%M%S")
            except ValueError:
                dt = datetime.fromtimestamp(stat.st_mtime)

            backups.append({
                "path": str(f),
                "size": stat.st_size,
                "created_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": dt,
            })

        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    def latest_backup(self) -> Optional[Dict]:
        """获取最新的备份"""
        backups = self.list_backups()
        return backups[0] if backups else None

    # ---------- 清理 ----------

    def _apply_retention(self):
        """应用保留策略，删除超出数量的最旧备份"""
        backups = self.list_backups()
        if len(backups) <= self.retention_count:
            return

        to_delete = backups[self.retention_count:]
        for b in to_delete:
            try:
                os.unlink(b["path"])
            except OSError:
                pass

    def prune_old(self, keep_count: int = None) -> int:
        """
        手动清理旧备份

        Args:
            keep_count: 保留数量（不传则使用 retention_count）

        Returns:
            删除的备份数量
        """
        if keep_count is None:
            keep_count = self.retention_count

        backups = self.list_backups()
        if len(backups) <= keep_count:
            return 0

        to_delete = backups[keep_count:]
        deleted = 0
        for b in to_delete:
            try:
                os.unlink(b["path"])
                deleted += 1
            except OSError:
                pass
        return deleted
