"""模块 Base 层 — 跨模块复用基类与工具。

提供 5 个基类 + 2 个 Mixin + 统一异常体系：
  - BaseEngine: 计算引擎契约（compute / persist / load / has_data）
  - BaseService: 幂等编排（auto / read / regenerate 三模式 + job 钩子）
  - BaseExporter: Excel 导出骨架（统一样式常量 + 列映射）
  - BaseImporter: 数据导入骨架（校验 / 幂等 / 重试 / 错误日志）
  - BaseRepository: 仓储抽象接口（见 base_repository.py）
  - AuditMixin: 审计字段注入（created_at/updated_at/created_by/updated_by）
  - SoftDeleteMixin: 软删除字段（deleted_at）

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

设计原则：
  - 引擎层纯函数，无副作用
  - Service 层编排，负责事务 + job 记录
  - 导入导出层幂等，可重复执行
  - 所有基类 type hints 完整，便于 IDE 提示和静态检查
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any
from datetime import datetime
from time import sleep

from bdms.core import db as _db
from bdms.core.paths import DATA_DIR


# ─── 统一异常体系 ───


class BDMSBaseError(Exception):
    """BDMS 异常基类。"""

    code: str = "BDMS_BASE_ERROR"

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(BDMSBaseError):
    """资源未找到。"""
    code = "NOT_FOUND"


class ValidationError(BDMSBaseError):
    """数据校验失败。"""
    code = "VALIDATION_ERROR"


class StateTransitionError(BDMSBaseError):
    """状态转换非法。"""
    code = "STATE_TRANSITION_ERROR"


class ImportError_(BDMSBaseError):
    """数据导入失败。"""
    code = "IMPORT_ERROR"


class ExportError(BDMSBaseError):
    """数据导出失败。"""
    code = "EXPORT_ERROR"


# ─── 常量 ───

MODE_AUTO = "auto"
MODE_READ = "read"
MODE_REGENERATE = "regenerate"
VALID_MODES = {MODE_AUTO, MODE_READ, MODE_REGENERATE}

AUDIT_FIELDS = ["created_at", "updated_at", "created_by", "updated_by"]
SOFT_DELETE_FIELD = "deleted_at"


def now_iso() -> str:
    """返回当前时间 ISO 格式字符串（秒级精度，全系统统一）。"""
    return datetime.now().isoformat(timespec="seconds")


# ─── AuditMixin（类级 Mixin，供 models / repositories 继承）───


class AuditMixin:
    """审计字段 Mixin。

    为任意数据对象注入 4 个审计字段：
      - created_at: 创建时间（ISO 格式）
      - updated_at: 最后更新时间
      - created_by: 创建人（空字符串表示系统）
      - updated_by: 最后更新人

    使用方式：
      class MyModel(AuditMixin):
          def __init__(self, **kwargs):
              super().__init__(**kwargs)
              self._init_audit_fields()
    """

    def _init_audit_fields(self, operator: Optional[str] = None) -> None:
        """初始化审计字段（创建新记录时调用）。"""
        now = now_iso()
        op = operator or ""
        self.created_at: str = now
        self.updated_at: str = now
        self.created_by: str = op
        self.updated_by: str = op

    def _touch_audit_fields(self, operator: Optional[str] = None) -> None:
        """更新审计字段（修改记录时调用）。"""
        self.updated_at = now_iso()
        self.updated_by = operator or ""


class SoftDeleteMixin:
    """软删除 Mixin。

    提供 deleted_at 字段及相关判断方法。
    None 或空字符串表示未删除。
    """

    def _init_soft_delete(self) -> None:
        """初始化软删除字段（未删除状态）。"""
        self.deleted_at: Optional[str] = None

    @property
    def is_deleted(self) -> bool:
        """是否已软删除。"""
        return bool(self.deleted_at)

    def soft_delete(self, operator: Optional[str] = None) -> None:
        """执行软删除。"""
        self.deleted_at = now_iso()
        if hasattr(self, "_touch_audit_fields"):
            self._touch_audit_fields(operator)

    def restore(self, operator: Optional[str] = None) -> None:
        """恢复软删除。"""
        self.deleted_at = None
        if hasattr(self, "_touch_audit_fields"):
            self._touch_audit_fields(operator)


# ─── 审计字段 SQL 工具（供手写 SQL 时使用）───


def audit_insert_sql(table: str, fields: list[str]) -> tuple[str, list[Any]]:
    """生成带审计字段的 INSERT SQL。

    Returns:
        (sql_statement, values_list) — values 前 4 位是审计字段值
    """
    all_fields = AUDIT_FIELDS + fields
    placeholders = ",".join(["?"] * len(all_fields))
    sql = f"INSERT INTO {table} ({','.join(all_fields)}) VALUES ({placeholders})"
    now = now_iso()
    sql_values = [now, now, "", ""]
    return sql, sql_values


def audit_update_sql(table: str, fields: list[str]) -> tuple[str, list[Any]]:
    """生成带审计字段的 UPDATE SQL。

    Returns:
        (sql_statement, values_list) — values 末尾是 id
    """
    set_clause = ", ".join([f"{f} = ?" for f in fields])
    set_clause += ", updated_at = ?, updated_by = ?"
    sql = f"UPDATE {table} SET {set_clause} WHERE id = ?"
    return sql


# ─── BaseEngine 契约 ───


class BaseEngine(ABC):
    """计算引擎抽象基类。

    所有业务计算引擎继承此类，统一接口契约。

    设计约定（必须遵守）：
      - compute() 是纯函数 → 不写 DB、不发请求、无副作用
      - persist() 只负责落盘 → 不做计算
      - load() 返回与 compute() 同构的数据结构 → 上层无感知数据来源
      - has_data() 快速判断是否已有数据 → O(1) 查询，不加载全量

    子类必须实现：
      - compute(month) -> dict
      - persist(month, data, overwrite) -> dict[str, int]
      - load(month) -> dict
      - has_data(month) -> bool
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """初始化引擎。

        Args:
            db_path: 数据库文件路径，默认使用 DATA_DIR/bdms.db
        """
        self.db_path: Path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    @abstractmethod
    def compute(self, month: str) -> dict[str, Any]:
        """计算某月数据。纯函数，无副作用。

        Args:
            month: 月份，格式 'YYYY-MM'

        Returns:
            计算结果字典，键为 sheet/table 名，值为数据列表或 DataFrame
        """
        ...

    @abstractmethod
    def persist(
        self,
        month: str,
        data: dict[str, Any],
        overwrite: bool = True,
    ) -> dict[str, int]:
        """将计算结果落盘到 DB。

        Args:
            month: 月份
            data: compute() 返回的同构字典
            overwrite: 是否覆盖已有数据

        Returns:
            {sheet_name: row_count} 各表写入行数
        """
        ...

    @abstractmethod
    def load(self, month: str) -> dict[str, Any]:
        """从 DB 读取某月数据。

        Args:
            month: 月份

        Returns:
            与 compute() 同构的结果字典
        """
        ...

    @abstractmethod
    def has_data(self, month: str) -> bool:
        """DB 中是否已有该月数据。

        实现要求：O(1) 查询，不加载全量数据。
        """
        ...

    # ─── 可选实现 ───

    def import_source(
        self,
        month: str,
        source_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """导入源数据到中间表（可选实现）。

        对于有外部数据源的模块（如确收分析、交付月报），
        此方法负责解析源文件并写入中间/原始数据表。
        默认抛 NotImplementedError。

        Args:
            month: 月份，格式 YYYY-MM
            source_path: 源文件路径

        Returns:
            {
                "month": str,
                "source_path": str,
                "sheet_counts": {sheet: row_count},
                "total_rows": int,
            }

        Raises:
            NotImplementedError: 模块不支持源数据导入
            ImportError_: 导入失败
        """
        raise NotImplementedError(
            f"{type(self).__name__} 未实现 import_source"
        )

    def summary_counts(self, month: str) -> dict[str, Any]:
        """获取某月数据汇总计数（可选实现）。

        返回各维度的统计汇总，用于列表页快速展示。
        默认返回空 dict，子类可覆盖。

        Args:
            month: 月份

        Returns:
            汇总字典，结构由各模块定义
        """
        return {}

    def check_sources(self, month: str) -> dict[str, Any]:
        """检查某月的数据源是否齐备。默认返回空 dict。

        子类可覆盖以返回各数据源的状态（存在性、行数、更新时间等）。
        """
        return {}

    def sources_available(self, month: str) -> bool:
        """数据源是否可用。默认返回 True。

        子类可覆盖以实现"数据源缺失时提前报错"的逻辑。
        """
        return True

    def validate_compute_input(self, month: str) -> None:
        """校验 compute 的输入参数。

        Raises:
            ValidationError: 月份格式不正确
        """
        if not month or len(month) != 7 or month[4] != "-":
            raise ValidationError(f"月份格式错误: {month}，应为 YYYY-MM")

    def validate_import_input(
        self,
        month: str,
        source_path: Optional[Path] = None,
    ) -> None:
        """校验导入输入参数。

        Args:
            month: 月份
            source_path: 源文件路径

        Raises:
            ValidationError: 参数校验失败
        """
        if not month or len(month) != 7 or month[4] != "-":
            raise ValidationError(f"月份格式错误: {month}，应为 YYYY-MM")
        if source_path is not None:
            p = Path(source_path)
            if not p.exists() or not p.is_file():
                raise ValidationError(f"源文件不存在或不可读: {source_path}")
            if p.stat().st_size == 0:
                raise ValidationError(f"源文件为空: {source_path}")

    def get_reference_data(self, data_type: str) -> list[dict[str, Any]]:
        """获取参考数据（可选实现）。

        从 md_reference 表读取指定类型的参考数据。
        默认返回空列表，子类可覆盖。

        Args:
            data_type: 数据类型编码

        Returns:
            参考数据记录列表
        """
        return []

    def upsert_reference_data(
        self,
        data_type: str,
        code: str,
        label: str,
        extra: Optional[str] = None,
    ) -> None:
        """更新或插入参考数据（可选实现）。

        默认抛 NotImplementedError，子类可覆盖。
        """
        raise NotImplementedError(
            f"{type(self).__name__} 未实现 upsert_reference_data"
        )

    # ─── 通用 CRUD Helper（单表引擎用）───

    # 子类设置这两个属性即可使用 _insert/_update/_get_by_id 等 helper
    table_name: str = ""
    soft_delete: bool = True
    id_column: str = "id"

    def _get_conn(self):
        """获取数据库连接（每次新建，用完需手动关闭）。"""
        return _db.get_connection(self.db_path)

    def _get_by_id(self, id: Any) -> Optional[dict[str, Any]]:
        """按 ID 获取单条记录（自动软删除过滤）。"""
        if not self.table_name:
            raise NotImplementedError("子类必须设置 table_name")
        conn = self._get_conn()
        try:
            where = [f"{self.id_column} = ?"]
            params: list[Any] = [id]
            if self.soft_delete:
                where.append("(deleted_at IS NULL OR deleted_at = '')")
            sql = f"SELECT * FROM {self.table_name} WHERE {" AND ".join(where)}"
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _get_by_id_or_raise(self, id: Any) -> dict[str, Any]:
        """按 ID 获取记录，不存在则抛 NotFoundError。"""
        record = self._get_by_id(id)
        if not record:
            raise NotFoundError(
                f"{self.table_name} id={id} not found"
            )
        return record

    def _insert(self, data: dict[str, Any]) -> int:
        """插入一条记录，返回新 ID。

        自动处理审计字段（created_at/updated_at/created_by/updated_by）。
        """
        if not self.table_name:
            raise NotImplementedError("子类必须设置 table_name")
        conn = self._get_conn()
        try:
            # 注入审计字段
            now = now_iso()
            full_data = dict(data)
            if "created_at" not in full_data:
                full_data["created_at"] = now
            if "updated_at" not in full_data:
                full_data["updated_at"] = now

            columns = ", ".join(full_data.keys())
            placeholders = ", ".join(["?"] * len(full_data))
            values = list(full_data.values())

            sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
            cur = conn.execute(sql, values)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _update(self, id: Any, data: dict[str, Any]) -> None:
        """按 ID 更新记录。

        自动更新 updated_at 字段。禁止改 id / created_at / created_by。
        """
        if not self.table_name:
            raise NotImplementedError("子类必须设置 table_name")
        conn = self._get_conn()
        try:
            # 去掉不允许更新的字段
            update_data = dict(data)
            for key in (self.id_column, "created_at", "created_by"):
                update_data.pop(key, None)

            # 自动更新 updated_at
            update_data["updated_at"] = now_iso()

            set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
            values = list(update_data.values()) + [id]

            sql = f"UPDATE {self.table_name} SET {set_clause} WHERE {self.id_column} = ?"
            conn.execute(sql, values)
            conn.commit()
        finally:
            conn.close()

    def _soft_delete(self, id: Any, operator: str = "") -> None:
        """软删除：设置 deleted_at = now。

        只有 soft_delete=True 的表才支持。
        """
        if not self.soft_delete:
            raise NotImplementedError(f"{self.table_name} 不支持软删除")
        conn = self._get_conn()
        try:
            now = now_iso()
            conn.execute(
                f"UPDATE {self.table_name} SET deleted_at = ?, updated_at = ?, updated_by = ? "
                f"WHERE {self.id_column} = ?",
                (now, now, operator, id),
            )
            conn.commit()
        finally:
            conn.close()

    def _restore(self, id: Any, operator: str = "") -> None:
        """恢复软删除的记录。"""
        if not self.soft_delete:
            raise NotImplementedError(f"{self.table_name} 不支持软删除")
        conn = self._get_conn()
        try:
            now = now_iso()
            conn.execute(
                f"UPDATE {self.table_name} SET deleted_at = NULL, updated_at = ?, updated_by = ? "
                f"WHERE {self.id_column} = ?",
                (now, operator, id),
            )
            conn.commit()
        finally:
            conn.close()


# ─── BaseService ───


class BaseService:
    """幂等编排服务基类。

    子类通过组合使用本类的 generate 骨架，统一处理：
      - 三模式幂等（auto / read / regenerate）
      - job 记录与状态跟踪
      - 错误记录与重试标记

    子类必须设置：
      - module_name: str — 模块名（用于 job 注册和日志）
      - engine: BaseEngine — 计算引擎实例

    使用方式（组合而非继承）：
      class MyService:
          def __init__(self):
              self.engine = MyEngine()
              self._base = BaseService(module_name="my_module", engine=self.engine)

          def generate(self, month, mode=MODE_AUTO):
              return self._base.generate(month, mode)
    """

    module_name: str = ""
    engine: Optional[BaseEngine] = None
    _meta_db_path: Optional[Path] = None

    def __init__(
        self,
        module_name: Optional[str] = None,
        engine: Optional[BaseEngine] = None,
        meta_db_path: Optional[Path] = None,
    ) -> None:
        """初始化服务。

        支持两种模式：
        1. 继承模式：子类在 __init__ 中设置 self.module_name 和 self.engine，然后 super().__init__()
           （注意：必须在 super().__init__() 之前设置好 self.engine，否则 meta_db_path 取默认值）
        2. 组合模式：实例化时传入 module_name 和 engine

        Args:
            module_name: 模块标识，用于 job 注册
            engine: 计算引擎实例
            meta_db_path: 元数据 DB 路径，默认与 engine.db_path 一致
        """
        # 构造参数优先，其次实例属性（子类先赋值了的），最后类属性
        if module_name:
            self.module_name = module_name
        if engine is not None:
            self.engine = engine
        if meta_db_path:
            self._meta_db_path = Path(meta_db_path)

    def _ensure_ready(self) -> None:
        """延迟校验：确保 module_name 和 engine 已设置。

        在 generate/has_data/list_months 等公共方法入口调用。
        继承模式下，子类在 __init__ 中赋值后才调 super()，但顺序可能反。
        用延迟校验兼容各种初始化顺序。
        """
        if not self.module_name:
            raise ValueError(
                f"{type(self).__name__} 必须设置 module_name"
            )
        if self.engine is None:
            raise ValueError(
                f"{type(self).__name__} 必须设置 engine"
            )

    @property
    def meta_db_path(self) -> Path:
        """元数据 DB 路径，延迟取值。"""
        if self._meta_db_path:
            return self._meta_db_path
        if self.engine:
            return self.engine.db_path
        from bdms.core.paths import DATA_DIR
        return DATA_DIR / "bdms.db"

    def generate(self, month: str, mode: str = MODE_AUTO) -> dict[str, Any]:
        """幂等生成/读取数据。

        Args:
            month: 月份，格式 YYYY-MM
            mode: auto / read / regenerate

        Returns:
            {
                "month": str,
                "mode": str,
                "action": "read" | "generated",
                "sheets": dict[str, int],
                "job_id": int,
                "total_rows": int,
            }

        Raises:
            ValueError: 模式无效或 read 模式无数据
            Exception: 计算过程中的异常（会先记录 job 失败状态再抛出）
        """
        self._ensure_ready()
        if mode not in VALID_MODES:
            raise ValueError(f"未知模式: {mode}，有效模式: {VALID_MODES}")

        # 创建 job 记录
        conn = _db.get_connection(self.meta_db_path)
        try:
            job_id = _db.create_job(conn, self.module_name, month, mode)
            conn.commit()
        finally:
            conn.close()

        try:
            has_data = self.engine.has_data(month)

            if mode == MODE_READ:
                if not has_data:
                    raise ValueError(
                        f"{self.module_name} {month} 无数据可读，"
                        f"请先用 auto/regenerate 模式生成"
                    )
                action = "read"
            elif mode == MODE_REGENERATE:
                action = "generated"
            else:  # auto
                action = "read" if has_data else "generated"

            if action == "read":
                data = self._load_existing(month)
                counts = self._count_rows(data)
            else:
                computed = self.engine.compute(month)
                counts = self.engine.persist(
                    month, computed,
                    overwrite=(mode == MODE_REGENERATE or has_data),
                )

            total = sum(
                v for v in counts.values()
                if isinstance(v, (int, float))
            )
            self._finish_job(
                job_id, "done", 100,
                message=f"{action}: {total} 行",
            )
            return {
                "month": month,
                "mode": mode,
                "action": action,
                "sheets": counts,
                "job_id": job_id,
                "total_rows": total,
            }
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    def _load_existing(self, month: str) -> dict[str, Any]:
        """读取已有数据。子类可覆盖以自定义 read 行为。"""
        return self.engine.load(month)

    @staticmethod
    def _count_rows(data: dict[str, Any]) -> dict[str, int]:
        """统计各 sheet/table 的行数。"""
        counts: dict[str, int] = {}
        for k, v in data.items():
            if hasattr(v, "__len__"):
                counts[k] = len(v)
            else:
                counts[k] = 0
        return counts

    def _finish_job(
        self,
        job_id: int,
        status: str,
        progress: int,
        message: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> None:
        """更新 job 状态。"""
        conn = _db.get_connection(self.meta_db_path)
        try:
            _db.update_job_status(conn, job_id, status, progress, message, output_path)
            conn.commit()
        finally:
            conn.close()

    def has_data(self, month: str) -> bool:
        """检查某月是否已有数据。"""
        self._ensure_ready()
        return self.engine.has_data(month)

    def list_months(self) -> list[dict[str, Any]]:
        """列出所有有数据的月份（按时间倒序）。"""
        self._ensure_ready()
        conn = _db.get_connection(self.meta_db_path)
        try:
            return _db.list_months(conn, self.module_name)
        finally:
            conn.close()

    def export(
        self,
        month: str,
        out_path: Optional[Path] = None,
    ) -> Path:
        """导出数据到 Excel（可选实现）。

        默认使用 self.exporter（如果已设置），否则抛 NotImplementedError。
        子类可覆盖或设置 self._exporter 属性。

        Args:
            month: 月份
            out_path: 输出路径，默认自动生成

        Returns:
            导出文件路径

        Raises:
            ExportError: 导出失败
            NotImplementedError: 模块不支持导出
        """
        exporter = getattr(self, "_exporter", None)
        if exporter is None:
            raise NotImplementedError(
                f"{type(self).__name__} 未配置 exporter，请设置 self._exporter"
            )
        return exporter.export(month, out_path)


# ─── BaseExporter ───


class BaseExporter(ABC):
    """Excel 导出骨架。

    统一样式常量 + sheet 顺序管理 + 文件输出路径处理。

    子类必须实现：
      - module_name: str — 模块名
      - sheet_order: list[str] — 导出 sheet 顺序
      - _write_all_sheets(wb, month, conn) — 写各 sheet 内容
    """

    module_name: str = ""
    sheet_order: list[str] = []

    # ─── 统一样式常量（子类直接引用）───

    HEADER_FILL = "305496"      # 深蓝背景
    HEADER_FONT_COLOR = "FFFFFF"  # 白色字体
    HEADER_FONT_BOLD = True
    HEADER_FONT_SIZE = 11
    BODY_FONT_SIZE = 10
    BORDER_STYLE = "thin"
    BORDER_COLOR = "B4B4B4"
    NUMBER_FORMAT_INT = "#,##0"
    NUMBER_FORMAT_FLOAT = "#,##0.00"
    NUMBER_FORMAT_PERCENT = "0.00%"
    NUMBER_FORMAT_DATE = "YYYY-MM-DD"
    ROW_HEIGHT_HEADER = 28
    ROW_HEIGHT_BODY = 20

    def __init__(self, db_path: Optional[Path] = None):
        """初始化导出器。

        Args:
            db_path: 数据库路径，默认 DATA_DIR/bdms.db
        """
        self.db_path: Path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    def export(self, month: str, out_path: Optional[Path] = None) -> Path:
        """导出 Excel 文件。

        Args:
            month: 月份
            out_path: 输出路径，默认自动生成到 OUTPUT_DIR

        Returns:
            导出文件路径

        Raises:
            ExportError: 导出过程中发生错误
        """
        try:
            from openpyxl import Workbook
            from bdms.core.paths import output_path

            conn = _db.get_connection(self.db_path)
            try:
                wb = Workbook()
                # 删除默认 sheet
                if wb.active:
                    wb.remove(wb.active)
                self._write_all_sheets(wb, month, conn)
            finally:
                conn.close()

            if out_path:
                target = Path(out_path)
            else:
                target = output_path(f"{self.module_name}_{month}.xlsx")

            target.parent.mkdir(parents=True, exist_ok=True)
            wb.save(target)
            return target
        except Exception as e:
            raise ExportError(f"导出失败: {e}", details={"month": month}) from e

    @abstractmethod
    def _write_all_sheets(self, wb: Any, month: str, conn: Any) -> None:
        """写所有 sheet 内容。子类实现。

        Args:
            wb: openpyxl Workbook 实例
            month: 月份
            conn: 数据库连接
        """
        ...

    # ─── 样式辅助方法（子类复用）───

    @staticmethod
    def apply_header_style(cell: Any) -> None:
        """给单元格应用表头样式。"""
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

        cell.font = Font(
            name="微软雅黑",
            size=BaseExporter.HEADER_FONT_SIZE,
            bold=BaseExporter.HEADER_FONT_BOLD,
            color=BaseExporter.HEADER_FONT_COLOR,
        )
        cell.fill = PatternFill(
            start_color=BaseExporter.HEADER_FILL,
            end_color=BaseExporter.HEADER_FILL,
            fill_type="solid",
        )
        thin = Side(border_style=BaseExporter.BORDER_STYLE,
                    color=BaseExporter.BORDER_COLOR)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    @staticmethod
    def apply_body_style(cell: Any, number_format: Optional[str] = None) -> None:
        """给单元格应用正文样式。"""
        from openpyxl.styles import Font, Border, Side, Alignment

        cell.font = Font(name="微软雅黑", size=BaseExporter.BODY_FONT_SIZE)
        thin = Side(border_style=BaseExporter.BORDER_STYLE,
                    color=BaseExporter.BORDER_COLOR)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        if number_format:
            cell.number_format = number_format


# ─── BaseImporter ───


class BaseImporter(ABC):
    """数据导入器共享骨架。

    统一处理：数据校验、幂等导入、错误日志、重试机制。

    子类必须实现：
      - source_type: str — 导入来源类型标识
      - _parse_source(source_path) -> dict — 解析源文件
      - _validate_parsed(data) -> tuple[bool, list[str]] — 校验，返回(是否通过, 错误列表)
      - _persist_data(month, data) -> dict — 幂等落盘
    """

    source_type: str = ""
    module_name: str = ""
    max_retries: int = 3
    retry_delay: float = 1.0  # 秒

    def __init__(self, db_path: Optional[Path] = None):
        """初始化导入器。

        Args:
            db_path: 数据库路径，默认 DATA_DIR/bdms.db
        """
        self.db_path: Path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    def import_all(
        self,
        source_path: Path,
        month: str,
        retries: Optional[int] = None,
    ) -> dict[str, Any]:
        """完整导入流程：parse → validate → persist → register。

        带重试机制，persist 阶段失败时自动重试。

        Args:
            source_path: 源文件路径
            month: 月份
            retries: 重试次数，默认使用 self.max_retries

        Returns:
            {
                "month": str,
                "source_type": str,
                "source_path": str,
                "sheets": dict[str, int],
                "total_rows": int,
                "retries": int,
            }

        Raises:
            ImportError_: 导入失败（已重试 max_retries 次后）
        """
        max_try = retries if retries is not None else self.max_retries

        # 1. 校验源文件
        if not self.validate_source(source_path):
            raise ImportError_(f"源文件不可读: {source_path}")

        # 2. 解析（只做一次，解析失败不重试）
        try:
            data = self._parse_source(source_path)
        except Exception as e:
            raise ImportError_(f"解析源文件失败: {e}", details={
                "source_path": str(source_path),
                "source_type": self.source_type,
            }) from e

        # 3. 校验（只做一次）
        is_valid, errors = self._validate_parsed(data)
        if not is_valid:
            raise ImportError_("数据校验失败", details={
                "errors": errors,
                "source_path": str(source_path),
            })

        # 4. 落盘（带重试）
        last_error: Optional[Exception] = None
        for attempt in range(max_try):
            try:
                counts = self._persist_data(month, data)
                total = sum(
                    v for v in counts.values()
                    if isinstance(v, (int, float))
                )

                # 5. 注册到元数据
                conn = _db.get_connection(self.db_path)
                try:
                    _db.register_month(conn, self.module_name, month, counts)
                    _db.log_import(
                        conn, self.module_name, month, self.source_type,
                        str(source_path), "done", total,
                    )
                    conn.commit()
                finally:
                    conn.close()

                return {
                    "month": month,
                    "source_type": self.source_type,
                    "source_path": str(source_path),
                    "sheets": counts,
                    "total_rows": total,
                    "retries": attempt,
                }
            except Exception as e:
                last_error = e
                if attempt < max_try - 1:
                    sleep(self.retry_delay * (2 ** attempt))  # 指数退避
                    continue

        # 所有重试都失败
        conn = _db.get_connection(self.db_path)
        try:
            _db.log_import(
                conn, self.module_name, month, self.source_type,
                str(source_path), "failed", 0,
            )
            conn.commit()
        finally:
            conn.close()

        raise ImportError_(
            f"导入失败（已重试 {max_try} 次）: {last_error}",
            details={"source_path": str(source_path), "month": month},
        ) from last_error

    def validate_source(self, source_path: Path) -> bool:
        """校验源文件是否可读。子类可覆盖。"""
        p = Path(source_path)
        return p.exists() and p.is_file() and p.stat().st_size > 0

    @abstractmethod
    def _parse_source(self, source_path: Path) -> dict[str, Any]:
        """解析源文件。返回结构化数据字典。

        Raises:
            Exception: 解析失败时抛出任意异常，import_all 会捕获并包装
        """
        ...

    @abstractmethod
    def _validate_parsed(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """校验解析后的数据。

        Returns:
            (是否通过, 错误信息列表)
        """
        ...

    @abstractmethod
    def _persist_data(self, month: str, data: dict[str, Any]) -> dict[str, int]:
        """幂等落盘。

        实现要求：重复执行结果一致，不产生重复数据。

        Returns:
            {table_name: row_count} 各表写入行数
        """
        ...


# ─── BaseValidator ───


class BaseValidator(ABC):
    """数据校验器基类。

    统一校验模式：逐行校验 → 批量校验 → 结果落盘 → 人工校正。
    DR（交付月报）和 RR（确收分析）模块复用此模式。

    子类必须实现：
      - validate_row(row, row_index) -> list[dict]
      - validate_batch(rows, month, sheet) -> dict
      - persist_validation_results(month, results) -> int

    可选实现：
      - apply_manual_correction(month, corrections) -> dict
      - list_pending(month) -> list[dict]
      - auto_fill_suggestions(month) -> list[dict]
    """

    module_name: str = ""
    validation_table: str = ""  # 校验结果表名（如 rr_import_validation）

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """初始化校验器。

        Args:
            db_path: 数据库路径，默认 DATA_DIR/bdms.db
        """
        self.db_path: Path = Path(db_path) if db_path else (DATA_DIR / "bdms.db")

    @abstractmethod
    def validate_row(
        self,
        sheet: str,
        row: dict[str, Any],
        row_index: int,
    ) -> list[dict[str, Any]]:
        """校验单行数据。

        Args:
            sheet: Sheet 名称
            row: 行数据字典
            row_index: 行序号

        Returns:
            校验错误列表，每项为：
            {
                "rule_code": str,
                "severity": "ERROR" | "WARNING",
                "message": str,
                "column_name": Optional[str],
                "original_value": Optional[str],
            }
            无错误返回空列表。
        """
        ...

    @abstractmethod
    def validate_batch(
        self,
        sheet: str,
        rows: list[dict[str, Any]],
        month: str,
    ) -> dict[str, Any]:
        """批量校验。

        Args:
            sheet: Sheet 名称
            rows: 数据行列表
            month: 月份

        Returns:
            {
                "month": str,
                "sheet": str,
                "total_rows": int,
                "error_count": int,
                "warning_count": int,
                "results": list[dict],  # 完整校验结果
            }
        """
        ...

    @abstractmethod
    def persist_validation_results(
        self,
        month: str,
        results: dict[str, Any],
    ) -> int:
        """将校验结果写入校验表。

        Args:
            month: 月份
            results: validate_batch 返回的结果字典

        Returns:
            写入的记录数
        """
        ...

    # ─── 可选实现 ───

    def apply_manual_correction(
        self,
        month: str,
        corrections: list[dict[str, Any]],
        operator: str = "",
    ) -> dict[str, Any]:
        """应用人工校正。

        Args:
            month: 月份
            corrections: 校正列表，每项含 id + corrected_value
            operator: 操作人

        Returns:
            {"updated": int, "month": str}
        """
        raise NotImplementedError(
            f"{type(self).__name__} 未实现 apply_manual_correction"
        )

    def list_pending(
        self,
        month: str,
        severity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """列出待处理的校验问题。

        Args:
            month: 月份
            severity: 按严重程度过滤（ERROR/WARNING），None 表示全部

        Returns:
            待处理问题列表
        """
        raise NotImplementedError(
            f"{type(self).__name__} 未实现 list_pending"
        )

    def auto_fill_suggestions(
        self,
        month: str,
    ) -> list[dict[str, Any]]:
        """自动填充建议。

        基于历史数据和规则，为存疑数据提供建议值。

        Args:
            month: 月份

        Returns:
            建议列表，每项含 id + suggested_value + confidence
        """
        return []

    # ─── 辅助方法 ───

    def _get_conn(self):
        """获取数据库连接。"""
        return _db.get_connection(self.db_path)

    @staticmethod
    def _make_error(
        rule_code: str,
        severity: str,
        message: str,
        column_name: Optional[str] = None,
        original_value: Optional[str] = None,
    ) -> dict[str, Any]:
        """构造标准错误字典。"""
        return {
            "rule_code": rule_code,
            "severity": severity,
            "message": message,
            "column_name": column_name,
            "original_value": original_value,
        }
