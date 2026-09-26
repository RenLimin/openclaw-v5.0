"""BDMS Schema 验证脚本 — 一键验证所有表/字段/索引是否存在。

用法：
    python3 src/bdms/core/verify_schema.py          # 验证默认 DB
    python3 src/bdms/core/verify_schema.py --db path/to/bdms.db
    python3 src/bdms/core/verify_schema.py --quiet  # 只输出摘要

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional

# 确保能 import bdms
_SRC = Path(__file__).resolve().parent.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bdms.core.paths import DB_PATH


# ─── 预期表定义（MVP + Full 全部）───
# 格式: { 表名: { "columns": [列名...], "indexes": [索引名...] } }
# columns 只验证存在性，不验证类型（SQLite 灵活，类型是建议的）

EXPECTED_TABLES: dict[str, dict[str, list[str]]] = {
    # === v1.0 核心表 ===
    "job": {
        "columns": ["id", "module", "month", "mode", "status", "progress",
                    "message", "output_path", "started_at", "finished_at",
                    "created_at"],
        "indexes": ["idx_job_module_month"],
    },
    "report_month": {
        "columns": ["id", "module", "month", "source_path", "generated_at",
                    "row_counts"],
        "indexes": [],
    },
    "md_reference": {
        "columns": ["id", "data_type", "code", "label", "extra",
                    "sort_order", "enabled", "updated_at"],
        "indexes": ["idx_md_ref_type"],
    },
    "sys_settings": {
        "columns": ["key", "value", "description", "updated_at"],
        "indexes": [],
    },
    "import_log": {
        "columns": ["id", "module", "month", "source_type", "source_path",
                    "data_type", "row_count", "status", "message",
                    "created_at"],
        "indexes": [],
    },
    # === 交付月报（v1.0）===
    "dr_sheet_row": {
        "columns": ["month", "sheet", "row_index", "data"],
        "indexes": [],
    },
    "dr_sheet_meta": {
        "columns": ["month", "sheet", "columns", "row_count"],
        "indexes": [],
    },
    # === 确收（v1.0）===
    "rr_sheet_row": {
        "columns": ["period", "sheet", "row_index", "contract_no",
                    "category", "archive_month", "perf_id", "data"],
        "indexes": [],
    },
    "rr_sheet_meta": {
        "columns": ["period", "sheet", "columns", "row_count"],
        "indexes": [],
    },
    # === v2.1 合同管理 ===
    "cr_contracts": {
        "columns": ["id", "contract_no", "title", "contract_type", "party_a",
                    "party_b", "amount", "currency", "effective_date",
                    "expiry_date", "status", "approval_level", "signed_date",
                    "archive_date",
                    "created_by", "updated_by", "created_at", "updated_at",
                    "deleted_at"],
        "indexes": ["idx_cr_status", "idx_cr_deleted"],
    },
    "cr_contract_documents": {
        "columns": ["id", "contract_id", "version", "file_path", "file_hash",
                    "watermark", "created_by", "created_at"],
        "indexes": [],
    },
    "cr_contract_clauses": {
        "columns": ["id", "contract_id", "clause_type", "clause_title",
                    "clause_content", "sort_order", "created_at",
                    "deleted_at"],
        "indexes": [],
    },
    "cr_risk_scan_results": {
        "columns": ["id", "contract_id", "scan_batch", "risk_category",
                    "risk_level", "issue_summary", "suggestion", "status",
                    "created_at", "deleted_at"],
        "indexes": ["idx_cr_risk_level"],
    },
    "cr_approval_log": {
        "columns": ["id", "contract_id", "from_status", "to_status",
                    "action", "approver_name", "approver_role", "comment",
                    "created_at"],
        "indexes": [],
    },
    "cr_audit_trail": {
        "columns": ["id", "contract_id", "operation", "field_name",
                    "old_value", "new_value", "operator", "created_at"],
        "indexes": [],
    },
    "cr_templates": {
        "columns": ["id", "template_code", "template_name", "contract_type",
                    "file_path", "version", "is_default", "enabled",
                    "created_at", "updated_at", "deleted_at"],
        "indexes": [],
    },
    "cr_clause_library": {
        "columns": ["id", "clause_code", "clause_name", "clause_type",
                    "content", "risk_level", "applicable_contract_types",
                    "created_at", "updated_at", "deleted_at"],
        "indexes": [],
    },
    # === v2.1 项目管理 ===
    "pm_projects": {
        "columns": ["id", "project_no", "project_name", "contract_id",
                    "project_type", "dept", "pm", "status", "start_date",
                    "end_date", "budget",
                    "created_by", "updated_by", "created_at", "updated_at",
                    "deleted_at"],
        "indexes": ["idx_pm_status", "idx_pm_pm", "idx_pm_deleted"],
    },
    "pm_phases": {
        "columns": ["id", "project_id", "phase_name", "phase_order",
                    "status", "planned_start", "planned_end",
                    "actual_start", "actual_end", "created_at"],
        "indexes": [],
    },
    "pm_team_members": {
        "columns": ["id", "project_id", "member_name", "role",
                    "allocation", "start_date", "end_date", "created_at"],
        "indexes": [],
    },
    "pm_milestones": {
        "columns": ["id", "project_id", "milestone_name", "planned_date",
                    "actual_date", "status", "created_at"],
        "indexes": [],
    },
    "pm_delivery_reports": {
        "columns": ["id", "project_id", "report_type", "title", "content",
                    "status", "submitted_at", "reviewed_at", "created_at"],
        "indexes": [],
    },
    # === v2.1 成本管理 ===
    "ct_timesheets": {
        "columns": ["id", "project_id", "employee_name", "work_date",
                    "hours", "work_type", "description", "status",
                    "approver", "approved_at", "created_at", "deleted_at"],
        "indexes": ["idx_ct_ts_project", "idx_ct_ts_deleted"],
    },
    "ct_staff_rates": {
        "columns": ["id", "role", "level", "rate_per_hour",
                    "effective_date", "created_at", "deleted_at"],
        "indexes": [],
    },
    "ct_device_usage": {
        "columns": ["id", "project_id", "device_name", "start_date",
                    "end_date", "cost_per_day", "total_cost", "status",
                    "created_at"],
        "indexes": [],
    },
    "ct_travel_costs": {
        "columns": ["id", "project_id", "employee_name", "travel_date",
                    "cost_type", "amount", "description", "status",
                    "created_at"],
        "indexes": [],
    },
    # === v2.1 风险管理 ===
    "rk_risks": {
        "columns": ["id", "risk_no", "project_id", "risk_type", "risk_level",
                    "title", "description", "impact", "likelihood",
                    "reporter", "status", "owner", "due_date", "closed_at",
                    "created_at", "updated_at", "deleted_at"],
        "indexes": ["idx_rk_project", "idx_rk_status", "idx_rk_deleted"],
    },
    "rk_risk_history": {
        "columns": ["id", "risk_id", "action", "operator", "detail",
                    "created_at"],
        "indexes": [],
    },
    "rk_risk_actions": {
        "columns": ["id", "risk_id", "action_type", "description",
                    "owner", "due_date", "completed_at", "created_at"],
        "indexes": [],
    },
    # === v2.1 售后管理（Full）===
    "as_tickets": {
        "columns": ["id", "ticket_no", "title", "ticket_type", "priority",
                    "status", "project_id", "customer_name", "contact_person",
                    "contact_phone", "product_id", "product_version",
                    "assignee", "sla_level", "sla_response_hours",
                    "sla_resolve_hours", "first_response_at", "resolved_at",
                    "closed_at", "satisfaction_score",
                    "created_by", "updated_by", "created_at", "updated_at",
                    "deleted_at"],
        "indexes": ["idx_as_status", "idx_as_project",
                    "idx_as_assignee", "idx_as_deleted"],
    },
    "as_ticket_history": {
        "columns": ["id", "ticket_id", "action", "operator", "detail",
                    "created_at"],
        "indexes": [],
    },
    "as_warranty_contracts": {
        "columns": ["id", "project_id", "warranty_start", "warranty_end",
                    "service_level", "remaining_tickets", "status",
                    "created_at"],
        "indexes": [],
    },
    "as_sla_snapshots": {
        "columns": ["id", "snapshot_date", "sla_level", "total_tickets",
                    "on_time_response", "on_time_resolve",
                    "response_breach_rate", "resolve_breach_rate",
                    "avg_response_hours", "avg_resolve_hours",
                    "created_at"],
        "indexes": [],
    },
    # === v2.1 变更管理（Full）===
    "ch_change_requests": {
        "columns": ["id", "project_id", "change_type", "title",
                    "description", "reason", "proposed_changes", "status",
                    "impact_delivery_days", "impact_cost_delta",
                    "impact_revenue_delta", "submitted_by", "submitted_at",
                    "approved_by", "approved_at", "executed_at",
                    "created_at", "updated_at", "deleted_at"],
        "indexes": ["idx_ch_project", "idx_ch_status", "idx_ch_deleted"],
    },
    # === v2.1 数据集成 ===
    "int_staging": {
        "columns": ["id", "connector_name", "batch_id", "source_id",
                    "status", "source_data", "normalized_data",
                    "target_module", "target_table", "error_msg",
                    "retry_count", "created_at", "processed_at"],
        "indexes": ["idx_int_staging_lookup", "idx_int_staging_target"],
    },
    "int_sync_log": {
        "columns": ["id", "connector_name", "batch_id", "mode", "status",
                    "total_fetched", "new_count", "updated_count",
                    "unchanged_count", "error_count", "params",
                    "started_at", "completed_at", "error_msg"],
        "indexes": ["idx_int_sync_log_connector"],
    },
    # === v2.1 知识库（Full）===
    "kb_item": {
        "columns": ["id", "kb_id", "knowledge_type", "title", "content",
                    "summary", "product_code", "service_level",
                    "applicable_version", "status", "current_version",
                    "published_version", "author", "last_editor",
                    "reviewer", "review_comment", "view_count",
                    "reference_count", "helpful_count", "metadata",
                    "created_at", "updated_at", "published_at",
                    "archived_at", "deleted_at"],
        "indexes": ["idx_kb_item_type", "idx_kb_item_status",
                    "idx_kb_item_product", "idx_kb_item_deleted"],
    },
    "kb_version": {
        "columns": ["id", "kb_id", "version", "title", "content",
                    "summary", "product_code", "metadata", "status",
                    "change_note", "publisher", "created_at",
                    "published_at"],
        "indexes": ["idx_kb_version_kb_id"],
    },
    "kb_tag": {
        "columns": ["id", "tag_name", "tag_category", "usage_count",
                    "created_at"],
        "indexes": [],
    },
    "kb_item_tag": {
        "columns": ["id", "kb_id", "tag_id", "created_at"],
        "indexes": ["idx_kb_item_tag_kb", "idx_kb_item_tag_tag"],
    },
    "kb_item_embedding": {
        "columns": ["id", "kb_id", "version", "title_embedding",
                    "content_embedding", "combined_embedding",
                    "model_version", "dim", "created_at", "updated_at"],
        "indexes": ["idx_kb_embed_kb_id"],
    },
    "kb_review_log": {
        "columns": ["id", "kb_id", "version", "action", "operator",
                    "comment", "created_at"],
        "indexes": [],
    },
    "kb_relation": {
        "columns": ["id", "from_kb_id", "to_kb_id", "relation_type",
                    "created_at"],
        "indexes": ["idx_kb_rel_from", "idx_kb_rel_to"],
    },
    "kb_fts": {
        "columns": ["kb_id", "title", "summary", "content", "tags",
                    "product_name"],
        "indexes": [],
    },
    # === v2.1 看板 ===
    "dash_snapshot": {
        "columns": ["id", "metric_key", "period", "dimension",
                    "dim_value", "value", "source_module", "computed_at"],
        "indexes": ["idx_dash_snapshot_lookup"],
    },
    "dash_user_config": {
        "columns": ["id", "user_id", "view_id", "view_name", "config",
                    "is_default", "created_at", "updated_at"],
        "indexes": ["idx_dash_user_config_user"],
    },
    # === v2.1 领域事件（Full）===
    "outbox_events": {
        "columns": ["id", "event_type", "aggregate_type", "aggregate_id",
                    "payload", "created_at", "published_at", "status"],
        "indexes": ["idx_outbox_status", "idx_outbox_created"],
    },
}

# MVP 表清单（MVP 验证时只查这些）
MVP_TABLES = [
    "job", "report_month", "md_reference", "sys_settings", "import_log",
    "dr_sheet_row", "dr_sheet_meta",
    "rr_sheet_row", "rr_sheet_meta",
    "cr_contracts", "cr_contract_documents", "cr_contract_clauses",
    "cr_risk_scan_results", "cr_approval_log", "cr_audit_trail",
    "cr_templates", "cr_clause_library",
    "pm_projects", "pm_phases", "pm_team_members", "pm_milestones",
    "pm_delivery_reports",
    "ct_timesheets", "ct_staff_rates", "ct_device_usage", "ct_travel_costs",
    "rk_risks", "rk_risk_history", "rk_risk_actions",
    "int_staging", "int_sync_log",
    "dash_snapshot", "dash_user_config",
]


def get_all_tables(conn: sqlite3.Connection) -> set[str]:
    """获取 DB 中所有表名（包括虚拟表）。"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {r[0] for r in rows}


def get_all_indexes(conn: sqlite3.Connection) -> set[str]:
    """获取所有索引名。"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    return {r[0] for r in rows}


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """获取表的所有列名。"""
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return {r[1] for r in rows}


def verify(
    db_path: Path,
    mvp_only: bool = False,
    quiet: bool = False,
) -> tuple[bool, dict]:
    """验证 schema。

    Returns:
        (是否全部通过, 详细结果 dict)
    """
    conn = sqlite3.connect(str(db_path))
    try:
        actual_tables = get_all_tables(conn)
        actual_indexes = get_all_indexes(conn)

        expected = EXPECTED_TABLES
        if mvp_only:
            expected = {k: v for k, v in expected.items() if k in MVP_TABLES}

        missing_tables: list[str] = []
        extra_tables: list[str] = []
        missing_columns: dict[str, list[str]] = {}
        missing_indexes: dict[str, list[str]] = {}
        passed_tables: list[str] = []

        for table, spec in expected.items():
            if table not in actual_tables:
                missing_tables.append(table)
                continue

            # 检查列
            cols = get_table_columns(conn, table)
            exp_cols = set(spec["columns"])
            missing = exp_cols - cols
            if missing:
                missing_columns[table] = sorted(missing)

            # 检查索引
            exp_indexes = set(spec["indexes"])
            miss_idx = exp_indexes - actual_indexes
            if miss_idx:
                missing_indexes[table] = sorted(miss_idx)

            if not missing and not miss_idx:
                passed_tables.append(table)

        # 多余的表（实际有但预期没有）
        all_expected_names = set(expected.keys())
        extra = actual_tables - all_expected_names - {"sqlite_sequence"}
        if extra:
            extra_tables = sorted(extra)

        all_passed = (
            not missing_tables
            and not missing_columns
            and not missing_indexes
        )

        result = {
            "passed": all_passed,
            "total_expected": len(expected),
            "passed_tables": len(passed_tables),
            "missing_tables": sorted(missing_tables),
            "missing_columns": missing_columns,
            "missing_indexes": missing_indexes,
            "extra_tables": extra_tables,
        }

        if not quiet:
            _print_result(result, mvp_only=mvp_only)

        return all_passed, result
    finally:
        conn.close()


def _print_result(result: dict, mvp_only: bool = False) -> None:
    """打印验证结果。"""
    scope = "MVP" if mvp_only else "Full"
    print(f"BDMS Schema Verification ({scope} scope)")
    print("=" * 50)
    print(f"预期表数: {result['total_expected']}")
    print(f"通过表数: {result['passed_tables']}")
    print()

    if result["missing_tables"]:
        print(f"❌ 缺少 {len(result['missing_tables'])} 张表:")
        for t in result["missing_tables"]:
            print(f"   - {t}")
        print()

    if result["missing_columns"]:
        print(f"❌ {len(result['missing_columns'])} 张表缺列:")
        for t, cols in result["missing_columns"].items():
            print(f"   - {t}: {', '.join(cols)}")
        print()

    if result["missing_indexes"]:
        print(f"⚠️  {len(result['missing_indexes'])} 张表缺索引:")
        for t, idxs in result["missing_indexes"].items():
            print(f"   - {t}: {', '.join(idxs)}")
        print()

    if result["extra_tables"]:
        print(f"ℹ️  额外表（不在预期中）: {len(result['extra_tables'])} 张")
        for t in result["extra_tables"]:
            print(f"   - {t}")
        print()

    if result["passed"]:
        print("✅ ALL PASSED")
    else:
        print("❌ FAILED — 见上方详情")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BDMS Schema 验证")
    parser.add_argument("--db", type=str, default=None,
                        help="数据库路径，默认使用配置路径")
    parser.add_argument("--mvp", action="store_true",
                        help="只验证 MVP 范围的表")
    parser.add_argument("--quiet", action="store_true",
                        help="静默模式，只输出通过/失败")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    passed, _ = verify(db_path, mvp_only=args.mvp, quiet=args.quiet)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
