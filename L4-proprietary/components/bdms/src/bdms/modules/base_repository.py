"""BaseRepository — 仓储抽象基类。

所有模块的 Repository 实现此接口，Service 层依赖接口而非具体实现。
便于未来从 SQLite 切换到 PostgreSQL（只需新增 Repository 实现，Service 层不变）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

设计约定：
  - 所有读操作（get/list）自动过滤软删除记录，除非显式 include_deleted=True
  - 所有写操作自动填充审计字段（created_at/updated_at/created_by/updated_by）
  - 主键统一为字符串 id（UUID 或业务编码）
  - list 返回 (records, total_count) 元组，便于分页
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import datetime


# ─── 审计字段常量 ───

AUDIT_FIELDS = ["created_at", "updated_at", "created_by", "updated_by"]
SOFT_DELETE_FIELD = "deleted_at"


def now_iso() -> str:
    """返回当前时间 ISO 格式字符串（统一精度）。"""
    return datetime.now().isoformat(timespec="seconds")


class BaseRepository(ABC):
    """仓储抽象基类。

    提供统一的 CRUD 接口，自动处理：
    - 审计字段（created_at/updated_at/created_by/updated_by）
    - 软删除过滤（自动排除 deleted_at IS NOT NULL 的记录）
    - 幂等写入（子类通过 INSERT OR REPLACE 或 UPSERT 实现）
    - 分页查询（list 返回 (records, total)）

    子类必须实现：
      - table_name: str — 表名
      - _row_to_dict(row) -> dict — 行转字典（不同 DB 驱动行格式不同）
      - get(id, include_deleted) -> Optional[dict]
      - list(filters, page, page_size, include_deleted) -> tuple[list[dict], int]
      - create(data, operator) -> str
      - update(id, data, operator) -> None
      - soft_delete(id, operator) -> None
      - restore(id, operator) -> None
      - hard_delete(id) -> None
      - exists(id) -> bool
      - count(filters, include_deleted) -> int
    """

    table_name: str = ""

    # ─── 读操作 ───

    @abstractmethod
    def get(self, id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
        """获取单条记录。

        Args:
            id: 记录主键
            include_deleted: 是否包含已软删除的记录，默认 False

        Returns:
            记录字典，不存在时返回 None
        """
        ...

    @abstractmethod
    def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        include_deleted: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """列表查询（自动过滤已删除）。

        Args:
            filters: 过滤条件字典，key=字段名，value=值（精确匹配）
            page: 页码，从 1 开始
            page_size: 每页条数
            order_by: 排序字段名
            order_desc: 是否降序，默认 False（升序）
            include_deleted: 是否包含已软删除记录

        Returns:
            (记录列表, 总条数)
        """
        ...

    @abstractmethod
    def exists(self, id: str) -> bool:
        """判断记录是否存在（不含已删除）。"""
        ...

    @abstractmethod
    def count(
        self,
        filters: Optional[dict[str, Any]] = None,
        include_deleted: bool = False,
    ) -> int:
        """统计符合条件的记录数。"""
        ...

    # ─── 写操作 ───

    @abstractmethod
    def create(self, data: dict[str, Any], operator: Optional[str] = None) -> str:
        """创建记录。

        - 自动填充 created_at/updated_at = now
        - 自动填充 created_by/updated_by = operator
        - id 由 data 传入或自动生成

        Args:
            data: 业务字段字典
            operator: 操作人标识，空字符串表示系统操作

        Returns:
            新记录的 id
        """
        ...

    @abstractmethod
    def update(
        self,
        id: str,
        data: dict[str, Any],
        operator: Optional[str] = None,
    ) -> None:
        """更新记录。

        - 自动更新 updated_at = now
        - 自动更新 updated_by = operator
        - 不允许修改 created_at/created_by
        - 自动过滤已删除记录（只更新未删除的）
        """
        ...

    @abstractmethod
    def soft_delete(self, id: str, operator: Optional[str] = None) -> None:
        """软删除：设置 deleted_at = now，不物理删除。

        软删除后 get/list 默认不可见，需 include_deleted=True 才能查到。
        """
        ...

    @abstractmethod
    def restore(self, id: str, operator: Optional[str] = None) -> None:
        """恢复软删除的记录（清空 deleted_at）。"""
        ...

    @abstractmethod
    def hard_delete(self, id: str) -> None:
        """物理删除。需管理员权限，操作不可恢复。"""
        ...

    # ─── 批量操作（可选实现，子类按需覆盖）───

    def batch_create(
        self,
        items: list[dict[str, Any]],
        operator: Optional[str] = None,
    ) -> list[str]:
        """批量创建。默认逐行调用 create，子类可优化为批量 INSERT。"""
        return [self.create(item, operator) for item in items]

    def batch_update(
        self,
        items: list[dict[str, Any]],
        operator: Optional[str] = None,
    ) -> None:
        """批量更新。默认逐行调用 update，子类可优化。"""
        for item in items:
            id_ = item.pop("id", None)
            if id_:
                self.update(id_, item, operator)

    def batch_soft_delete(
        self,
        ids: list[str],
        operator: Optional[str] = None,
    ) -> None:
        """批量软删除。"""
        for id_ in ids:
            self.soft_delete(id_, operator)

    # ─── 辅助方法（供子类复用）───

    @staticmethod
    def _add_audit_fields(
        data: dict[str, Any],
        operator: Optional[str] = None,
        *,
        for_create: bool = True,
    ) -> dict[str, Any]:
        """向 data 中注入审计字段。返回新 dict，不修改原 dict。"""
        result = dict(data)
        now = now_iso()
        op = operator or ""

        if for_create:
            result["created_at"] = now
            result["created_by"] = op

        result["updated_at"] = now
        result["updated_by"] = op
        return result

    @staticmethod
    def _build_where_clause(
        filters: Optional[dict[str, Any]],
        include_deleted: bool = False,
    ) -> tuple[str, list[Any]]:
        """根据 filters 构建 WHERE 子句 + 参数列表。

        自动追加软删除过滤条件（include_deleted=False 时）。
        """
        conditions: list[str] = []
        params: list[Any] = []

        if filters:
            for key, value in filters.items():
                if value is None:
                    conditions.append(f"{key} IS NULL")
                else:
                    conditions.append(f"{key} = ?")
                    params.append(value)

        if not include_deleted:
            conditions.append(f"({SOFT_DELETE_FIELD} IS NULL OR {SOFT_DELETE_FIELD} = '')")

        if conditions:
            return "WHERE " + " AND ".join(conditions), params
        return "", params

    def batch_restore(
        self,
        ids: list[str],
        operator: Optional[str] = None,
    ) -> None:
        """批量恢复软删除的记录。"""
        for id_ in ids:
            self.restore(id_, operator)

    def batch_hard_delete(self, ids: list[str]) -> None:
        """批量物理删除。需管理员权限，操作不可恢复。"""
        for id_ in ids:
            self.hard_delete(id_)

    def get_by_field(
        self,
        field: str,
        value: Any,
        include_deleted: bool = False,
    ) -> Optional[dict[str, Any]]:
        """按唯一字段查询单条记录。

        用于 business key 查询（如 contract_no, project_no 等）。
        如果有多条匹配，返回第一条。

        Args:
            field: 字段名
            value: 字段值
            include_deleted: 是否包含已删除记录

        Returns:
            记录字典，不存在返回 None
        """
        records, _ = self.list(
            filters={field: value},
            page=1,
            page_size=1,
            include_deleted=include_deleted,
        )
        return records[0] if records else None
