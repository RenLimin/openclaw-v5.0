"""审计日志封装

提供统一的审计日志记录接口，写入 fin4_audit_log 表。
覆盖主要业务操作的审计追踪。

常见 action 命名约定:
  - create_*   : 创建实体
  - update_*   : 更新实体
  - delete_*   : 删除实体
  - login      : 登录
  - logout     : 登出
  - backup     : 备份
  - restore    : 恢复
  - export     : 导出数据
  - import     : 导入数据
  - config_change: 配置变更
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
from typing import List, Dict, Optional, Any

from fin_l4.db.repositories import AuditLogRepository


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, repo: AuditLogRepository,
                 default_user: str = "system"):
        """
        Args:
            repo: AuditLogRepository 实例
            default_user: 默认用户标识（未指定 user 时使用）
        """
        self.repo = repo
        self.default_user = default_user

    # ---------- 核心记录方法 ----------

    def log(self, family_id: str, action: str,
            user: str = None,
            entity_type: str = None,
            entity_id: str = None,
            details: Dict[str, Any] = None,
            ip: str = None) -> str:
        """
        记录一条审计日志

        Args:
            family_id: 家庭 ID
            action: 操作名称（见模块文档的命名约定）
            user: 操作用户（不传用 default_user）
            entity_type: 实体类型（如 account / transaction / loan）
            entity_id: 实体 ID
            details: 操作详情（字典，会序列化为 JSON）
            ip: 操作来源 IP

        Returns:
            日志记录 ID
        """
        if not action:
            raise ValueError("Audit action cannot be empty")

        return self.repo.log(
            family_id=family_id,
            user=user or self.default_user,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip=ip,
        )

    # ---------- 便捷方法 ----------

    def log_create(self, family_id: str, entity_type: str,
                   entity_id: str, user: str = None,
                   details: Dict = None, ip: str = None) -> str:
        """记录创建操作"""
        return self.log(
            family_id=family_id,
            action=f"create_{entity_type}",
            user=user,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip=ip,
        )

    def log_update(self, family_id: str, entity_type: str,
                   entity_id: str, user: str = None,
                   details: Dict = None, ip: str = None) -> str:
        """记录更新操作"""
        return self.log(
            family_id=family_id,
            action=f"update_{entity_type}",
            user=user,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip=ip,
        )

    def log_delete(self, family_id: str, entity_type: str,
                   entity_id: str, user: str = None,
                   details: Dict = None, ip: str = None) -> str:
        """记录删除操作"""
        return self.log(
            family_id=family_id,
            action=f"delete_{entity_type}",
            user=user,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip=ip,
        )

    def log_login(self, family_id: str, user: str,
                  success: bool = True, ip: str = None) -> str:
        """记录登录事件"""
        return self.log(
            family_id=family_id,
            action="login",
            user=user,
            details={"success": success},
            ip=ip,
        )

    def log_backup(self, family_id: str, backup_file: str,
                   user: str = None, ip: str = None) -> str:
        """记录备份操作"""
        return self.log(
            family_id=family_id,
            action="backup",
            user=user,
            details={"backup_file": backup_file},
            ip=ip,
        )

    def log_restore(self, family_id: str, backup_file: str,
                    user: str = None, ip: str = None) -> str:
        """记录恢复操作"""
        return self.log(
            family_id=family_id,
            action="restore",
            user=user,
            details={"backup_file": backup_file},
            ip=ip,
        )

    # ---------- 查询 ----------

    def list_logs(self, family_id: str, limit: int = 100,
                  action: str = None,
                  entity_type: str = None) -> List[Dict]:
        """
        查询审计日志

        Args:
            family_id: 家庭 ID
            limit: 返回条数
            action: 可选，按 action 过滤
            entity_type: 可选，按实体类型过滤

        Returns:
            审计日志列表（按时间倒序）
        """
        logs = self.repo.list_by_family(family_id, limit=limit)

        # 解析 details JSON
        for log in logs:
            if log.get("details") and isinstance(log["details"], str):
                try:
                    log["details"] = json.loads(log["details"])
                except (json.JSONDecodeError, TypeError):
                    pass

        if action:
            logs = [l for l in logs if l.get("action") == action]
        if entity_type:
            logs = [l for l in logs if l.get("entity_type") == entity_type]

        return logs
