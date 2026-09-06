"""外部系统链接管理 CRUD

管理银行、券商、基金公司等外部系统的链接信息。
链接信息（名称、类型、URL、用户名提示）存储在 fin4_integrations 表。

注意: 不存储密码等敏感凭证。敏感凭证由 security.encryption 模块单独管理。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import List, Optional, Dict
from fin_l4.db.repositories import IntegrationRepository


# 支持的链接类型
VALID_LINK_TYPES = {"bank", "broker", "fund", "other"}


class LinkManager:
    """外部系统链接管理器"""

    def __init__(self, repo: IntegrationRepository):
        self.repo = repo

    # ---------- 创建 ----------

    def create_link(self, family_id: str, name: str, link_type: str,
                    url: str, username_hint: str = None,
                    note: str = None) -> str:
        """
        创建一个外部系统链接

        Args:
            family_id: 家庭 ID
            name: 链接名称（如 "招商银行"）
            link_type: 类型: bank / broker / fund / other
            url: 官网或登录页 URL
            username_hint: 用户名提示（不存密码）
            note: 备注

        Returns:
            新建链接的 ID

        Raises:
            ValueError: link_type 不合法
        """
        if link_type not in VALID_LINK_TYPES:
            raise ValueError(
                f"Invalid link_type '{link_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_LINK_TYPES))}"
            )
        if not name or not name.strip():
            raise ValueError("Link name cannot be empty")
        if not url or not url.strip():
            raise ValueError("Link URL cannot be empty")

        return self.repo.create(
            family_id=family_id,
            name=name.strip(),
            link_type=link_type,
            url=url.strip(),
            username_hint=username_hint.strip() if username_hint else None,
            note=note.strip() if note else None,
        )

    # ---------- 查询 ----------

    def list_links(self, family_id: str,
                   link_type: str = None) -> List[Dict]:
        """
        列出家庭下的所有外部系统链接

        Args:
            family_id: 家庭 ID
            link_type: 可选，按类型过滤

        Returns:
            链接列表（按类型排序）
        """
        links = self.repo.list_by_family(family_id)
        if link_type:
            links = [l for l in links if l["link_type"] == link_type]
        return links

    def list_by_type(self, family_id: str) -> Dict[str, List[Dict]]:
        """
        按类型分组返回链接

        Returns:
            {
                "bank": [...],
                "broker": [...],
                "fund": [...],
                "other": [...],
            }
        """
        links = self.repo.list_by_family(family_id)
        result = {t: [] for t in VALID_LINK_TYPES}
        for link in links:
            lt = link.get("link_type", "other")
            if lt not in result:
                lt = "other"
            result[lt].append(link)
        return result

    def get_link(self, link_id: str) -> Optional[Dict]:
        """获取单个链接详情"""
        row = self.repo.conn.execute(
            f"SELECT * FROM {self.repo.table} WHERE id = ?",
            (link_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    # ---------- 更新 ----------

    def update_link(self, link_id: str, **kwargs) -> bool:
        """
        更新链接信息

        可更新字段: name, link_type, url, username_hint, note
        """
        allowed = {"name", "link_type", "url", "username_hint", "note"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return False

        if "link_type" in updates and updates["link_type"] not in VALID_LINK_TYPES:
            raise ValueError(
                f"Invalid link_type '{updates['link_type']}'. "
                f"Must be one of: {', '.join(sorted(VALID_LINK_TYPES))}"
            )

        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [link_id]

        self.repo.conn.execute(
            f"UPDATE {self.repo.table} SET {sets} WHERE id = ?",
            values
        )
        self.repo.conn.commit()

        return self.repo.conn.total_changes > 0

    # ---------- 删除 ----------

    def delete_link(self, link_id: str) -> bool:
        """
        删除链接

        Returns:
            是否成功删除
        """
        before = self.repo.conn.total_changes
        self.repo.delete(link_id)
        return self.repo.conn.total_changes > before

    # ---------- 统计 ----------

    def count_by_type(self, family_id: str) -> Dict[str, int]:
        """统计各类型链接数量"""
        grouped = self.list_by_type(family_id)
        return {k: len(v) for k, v in grouped.items()}
