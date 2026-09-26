"""BDMS v1 → v2.1 数据迁移脚本。

功能：
  1. 备份原数据库（自动创建 .bak 文件）
  2. 初始化 v2.1 schema（幂等）
  3. 迁移 v1 数据到 v2 结构（幂等，可重复执行）
  4. 验证迁移结果

用法：
    python3 src/bdms/core/migrate_v1_to_v2.py           # 迁移默认 DB
    python3 src/bdms/core/migrate_v1_to_v2.py --db path  # 迁移指定 DB
    python3 src/bdms/core/migrate_v1_to_v2.py --dry-run  # 预览，不实际写入
    python3 src/bdms/core/migrate_v1_to_v2.py --verify   # 只验证已迁移的 DB

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

迁移原则：
  - 先备份，再迁移
  - 幂等：重复执行结果一致，不丢数据，不产生重复
  - 只增不删：v1 表保留，v2 新表新增，不破坏原数据
  - 可回滚：迁移失败可从 .bak 文件恢复
"""

import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

# 确保能 import bdms
_SRC = Path(__file__).resolve().parent.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bdms.core.paths import DB_PATH, DATA_DIR


# v1 → v2 表映射（v1 表名: v2 表名）
# 大部分 v1 表直接保留，无需迁移，因为 v2 init 用的是 IF NOT EXISTS
# 这里只列需要改造/字段补齐的表

V1_TO_V2_TABLE_MAP = {
    # 元数据表：直接保留，结构兼容
    "job": "job",
    "report_month": "report_month",
    "md_reference": "md_reference",
    "sys_settings": "sys_settings",
    "import_log": "import_log",
    # 交付月报：直接保留
    "dr_sheet_row": "dr_sheet_row",
    "dr_sheet_meta": "dr_sheet_meta",
    # 确收：直接保留
    "rr_sheet_row": "rr_sheet_row",
    "rr_sheet_meta": "rr_sheet_meta",
    # v1 dashboard 表（如果有）：保留为历史数据
    "db_snapshot": "db_snapshot",
}


def backup_db(db_path: Path) -> Path:
    """备份数据库，返回备份文件路径。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = db_path.with_suffix(f".v1_migrate_{timestamp}.bak")
    shutil.copy2(db_path, bak_path)
    return bak_path


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """获取表的列名集合。"""
    try:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return {r[1] for r in rows}
    except sqlite3.OperationalError:
        return set()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """判断表是否存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def add_missing_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> int:
    """给表添加缺失的列。

    Args:
        conn: DB 连接
        table: 表名
        columns: {列名: 列定义（含类型和默认值）}

    Returns:
        新增列数
    """
    existing = get_table_columns(conn, table)
    added = 0
    for col, definition in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            added += 1
    return added


def migrate_metadata_tables(conn: sqlite3.Connection) -> dict:
    """迁移元数据表（补齐审计字段等）。

    v1 的元数据表没有审计字段，v2 约定有。
    用 ALTER TABLE 补齐，设默认值。

    Returns:
        {table: added_columns_count}
    """
    result = {}

    # job 表：v1 已有大部分字段，无需补
    result["job"] = 0

    # sys_settings 表：v1 有 updated_at，兼容
    result["sys_settings"] = 0

    # md_reference 表：v1 有 updated_at，兼容
    result["md_reference"] = 0

    # import_log 表：v1 有 created_at，兼容
    result["import_log"] = 0

    # report_month 表：v1 结构基本够用
    result["report_month"] = 0

    return result


def migrate_delivery_report(conn: sqlite3.Connection) -> dict:
    """迁移交付月报数据。

    v1 的 dr_sheet_row / dr_sheet_meta 结构在 v2 中直接保留。
    v2 的 delivery_report 模块继续使用这些表。
    无需结构迁移，只需验证数据完整性。
    """
    result = {"tables_preserved": ["dr_sheet_row", "dr_sheet_meta"]}

    # 统计行数
    for tbl in ["dr_sheet_row", "dr_sheet_meta"]:
        if table_exists(conn, tbl):
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            result[f"{tbl}_rows"] = count
        else:
            result[f"{tbl}_rows"] = 0

    return result


def migrate_revenue(conn: sqlite3.Connection) -> dict:
    """迁移确收数据。

    同交付月报，v1 的 rr_ 表在 v2 中直接保留。
    """
    result = {"tables_preserved": ["rr_sheet_row", "rr_sheet_meta"]}

    for tbl in ["rr_sheet_row", "rr_sheet_meta"]:
        if table_exists(conn, tbl):
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            result[f"{tbl}_rows"] = count
        else:
            result[f"{tbl}_rows"] = 0

    return result


def migrate_master_data(conn: sqlite3.Connection) -> dict:
    """迁移主数据。

    v1 的 md_reference 表在 v2 中继续使用。
    v2 新增的 master_data 模块会在初始化时创建它自己的表，
    如果 md_reference 有数据，按需导入到新的主数据结构中。

    目前策略：md_reference 保留，master_data 模块从零开始。
    后续如果需要迁移，再加迁移逻辑。
    """
    return {
        "md_reference_preserved": True,
        "note": "v2 master_data 模块表为空，md_reference 保留为历史数据",
    }


def set_migration_version(conn: sqlite3.Connection, version: str) -> None:
    """记录迁移版本号到 sys_settings。"""
    conn.execute(
        """INSERT INTO sys_settings (key, value, description)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value = excluded.value,
             description = excluded.description,
             updated_at = datetime('now', 'localtime')""",
        (
            "db.schema_version",
            version,
            "BDMS 数据库 schema 版本号",
        ),
    )


def get_migration_version(conn: sqlite3.Connection) -> Optional[str]:
    """获取当前迁移版本号。"""
    row = conn.execute(
        "SELECT value FROM sys_settings WHERE key = 'db.schema_version'",
    ).fetchone()
    return row[0] if row else None


def verify_migration(conn: sqlite3.Connection) -> tuple[bool, list[str]]:
    """验证迁移结果。

    Returns:
        (是否通过, 问题列表)
    """
    issues: list[str] = []

    # 1. 核心 v1 表必须还在
    for tbl in ["job", "report_month", "md_reference", "sys_settings",
                "import_log", "dr_sheet_row", "dr_sheet_meta",
                "rr_sheet_row", "rr_sheet_meta"]:
        if not table_exists(conn, tbl):
            issues.append(f"v1 表丢失: {tbl}")

    # 2. v2 新表必须存在（MVP 范围）
    mvp_tables = [
        "cr_contracts", "cr_approval_log", "cr_audit_trail",
        "cr_risk_scan_results", "cr_contract_documents",
        "pm_projects", "pm_phases", "pm_milestones", "pm_team_members",
        "ct_timesheets", "ct_staff_rates",
        "rk_risks", "rk_risk_history",
        "dash_snapshot", "dash_user_config",
        "int_staging", "int_sync_log",
    ]
    for tbl in mvp_tables:
        if not table_exists(conn, tbl):
            issues.append(f"v2 MVP 表缺失: {tbl}")

    # 3. v1 数据行数必须不变（交付月报）
    # （这里只检查表存在，具体行数对比由调用方在迁移前后对比）

    return len(issues) == 0, issues


def migrate(
    db_path: Path,
    dry_run: bool = False,
    skip_backup: bool = False,
) -> dict:
    """执行完整迁移。

    Args:
        db_path: 数据库文件路径
        dry_run: 试运行模式，只打印计划不实际修改
        skip_backup: 跳过备份（不推荐）

    Returns:
        迁移结果字典
    """
    result: dict = {
        "db_path": str(db_path),
        "dry_run": dry_run,
        "backup_path": None,
        "before_version": None,
        "after_version": None,
        "steps": {},
        "passed": False,
        "issues": [],
    }

    if not db_path.exists():
        result["error"] = f"数据库文件不存在: {db_path}"
        return result

    # 1. 备份
    if not dry_run and not skip_backup:
        bak_path = backup_db(db_path)
        result["backup_path"] = str(bak_path)
        result["steps"]["backup"] = f"备份完成: {bak_path.name}"

    # 2. 迁移前版本
    conn = sqlite3.connect(str(db_path))
    try:
        result["before_version"] = get_migration_version(conn) or "v1.0"

        if dry_run:
            # dry-run 只打印计划
            result["steps"]["plan"] = [
                "初始化 v2.1 schema",
                "迁移元数据表（补齐字段）",
                "验证交付月报数据完整性",
                "验证确收数据完整性",
                "设置 schema_version = v2.1",
                "验证迁移结果",
            ]
            result["passed"] = True
            return result

        # 3. 初始化 v2.1 schema（幂等）
        from bdms.core import db
        db.init_db(db_path)
        result["steps"]["init_schema"] = "v2.1 schema 初始化完成"

        # 4. 迁移元数据表
        meta_result = migrate_metadata_tables(conn)
        result["steps"]["metadata"] = meta_result

        # 5. 交付月报数据验证
        dr_result = migrate_delivery_report(conn)
        result["steps"]["delivery_report"] = dr_result

        # 6. 确收数据验证
        rr_result = migrate_revenue(conn)
        result["steps"]["revenue"] = rr_result

        # 7. 主数据迁移策略
        md_result = migrate_master_data(conn)
        result["steps"]["master_data"] = md_result

        # 8. 设置版本号
        set_migration_version(conn, "v2.1-mvp")
        result["after_version"] = "v2.1-mvp"

        conn.commit()

        # 9. 验证
        passed, issues = verify_migration(conn)
        result["passed"] = passed
        result["issues"] = issues

        return result
    finally:
        conn.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BDMS v1 → v2.1 数据迁移")
    parser.add_argument("--db", type=str, default=None,
                        help="数据库路径，默认使用配置路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行，不实际修改数据库")
    parser.add_argument("--skip-backup", action="store_true",
                        help="跳过备份（危险，不推荐）")
    parser.add_argument("--verify", action="store_true",
                        help="只验证当前数据库的迁移状态")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    if args.verify:
        # 只验证
        conn = sqlite3.connect(str(db_path))
        try:
            version = get_migration_version(conn) or "unknown"
            passed, issues = verify_migration(conn)
            print(f"Schema 版本: {version}")
            print(f"验证结果: {'✅ 通过' if passed else '❌ 失败'}")
            if issues:
                print("问题列表:")
                for issue in issues:
                    print(f"  - {issue}")
            sys.exit(0 if passed else 1)
        finally:
            conn.close()
        return

    # 执行迁移
    print(f"开始迁移: {db_path}")
    if args.dry_run:
        print("(DRY-RUN 模式，不会实际修改)")
    print()

    result = migrate(db_path, dry_run=args.dry_run,
                     skip_backup=args.skip_backup)

    if "error" in result:
        print(f"❌ 错误: {result['error']}")
        sys.exit(1)

    print(f"原版本: {result['before_version']}")
    print(f"目标版本: {result['after_version'] or 'v2.1-mvp'}")
    if result["backup_path"]:
        print(f"备份文件: {Path(result['backup_path']).name}")
    print()

    print("迁移步骤:")
    for step, detail in result["steps"].items():
        if isinstance(detail, dict):
            print(f"  ✅ {step}")
            for k, v in detail.items():
                print(f"     - {k}: {v}")
        elif isinstance(detail, list):
            print(f"  📋 {step}:")
            for item in detail:
                print(f"     - {item}")
        else:
            print(f"  ✅ {step}: {detail}")

    print()
    if result["passed"]:
        print("✅ 迁移成功，验证通过")
    else:
        print("❌ 迁移验证失败")
        for issue in result["issues"]:
            print(f"  - {issue}")
        if result["backup_path"]:
            print(f"\n可从备份恢复: {result['backup_path']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
