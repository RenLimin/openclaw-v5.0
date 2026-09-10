#!/usr/bin/env python3
"""
BDMS v1 → v2 数据迁移工具

功能：
1. full: 全量迁移 v1 SQLite → v2 CSV 数据目录
2. import: 从 Excel/CSV 导入数据到 v2
3. rollback: 回滚指定导入记录
4. 支持 dry-run 模式
"""

import sys
import argparse
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
import pandas as pd

# 模块路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from db import (
    init_db, create_import_log, get_import_log,
    DB_PATH as META_DB_PATH
)

# v2 数据目录（与 delivery_report_generator.py 中 ONES_DIR 一致）
ONES_DATA_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
BACKUP_DIR = Path.home() / ".openclaw" / "data" / "bdms_migration_backups"

# ============================================================
# v1 → v2 字段映射
# ============================================================

# 签约项目统计：v1 oa_contracts + ones_projects → v2 签约 CSV 列
V1_SIGN_COLUMN_MAP = {
    # v1 字段: v2 列名
    "htbh": "合同编号",
    "合同名称": "合同名称",
    "客户名称": "客户名称",
    "签约金额": "签约金额",
    "责任销售": "责任销售",
    "责任销售部门": "销售部门",
    "签约销售": "签约销售",
    "签约销售团队": "销售团队",
    "创建日期": "创建日期",
    "申请日期": "申请日期",
    "服务开始日期": "合同起始日期",
    "服务结束日期": "合同结束日期",
    "直签或代理": "直签或代理",
    "合同分类": "合同分类",
    "归档状态": "归档状态",
}

# ones_projects 补充映射
V1_PROJECT_COLUMN_MAP = {
    "project_id": "项目编号",
    "项目名称": "项目名称",
    "合同编号": "合同编号",
    "项目经理": "项目经理",
    "部门": "项目部门",
    "项目状态": "项目状态",
    "立项日期": "立项日期",
    "预估结项日期": "预估结项日期",
    "实际结项日期": "实际结项日期",
}

# 确收凭证 → 确收交接 CSV
V1_REVENUE_COLUMN_MAP = {
    "voucher_id": "凭证编号",
    "合同编号": "合同编号",
    "合同名称": "合同名称",
    "客户名称": "客户名称",
    "销售部门": "销售部门",
    "项目经理": "项目经理",
    "交接日期": "交接日期",
    "财务": "财务",
    "是否接收": "是否接收",
}

# 验收凭证 → 验收交接 CSV
V1_ACCEPTANCE_COLUMN_MAP = {
    "voucher_id": "凭证编号",
    "合同编号": "合同编号",
    "合同名称": "合同名称",
    "客户名称": "客户名称",
    "项目经理": "项目经理",
    "验收单编号": "验收单编号",
    "交接日期": "交接日期",
    "验收方式": "验收方式",
    "全部或部分": "全部或部分验收",
    "财务": "财务",
    "财务是否接收": "财务是否接收",
}

# 工时 → 工时明细
V1_WORKHOUR_COLUMN_MAP = {
    "工作项": "工作项",
    "总工时": "总工时",
    "迁移工时": "迁移工时",
    "剩余工时": "剩余工时",
    "月份": "月份",
}

# v2 已知的必填列（缺失则留空）
V2_SIGN_REQUIRED_COLS = [
    "合同编号", "合同名称", "客户名称", "签约金额",
    "项目经理", "项目名称", "项目状态", "销售部门",
]

# ============================================================
# 数据类型 → 输出文件名
# ============================================================
DATA_TYPE_FILENAME = {
    "sign": "{month}周报-签约项目统计.csv",
    "poc": "{month}周报-POC&提前实施统计.csv",
    "exception": "{month}-签约项目异常处置.csv",
    "revenue": "{month}确收凭证交接-确收.csv",
    "acceptance": "{month}确收凭证交接-验收.csv",
    "workhours": "workhours-{month}.csv",
}

DATA_TYPE_LABEL = {
    "sign": "签约项目统计",
    "poc": "POC&提前实施统计",
    "exception": "异常项目处置",
    "revenue": "确收交接",
    "acceptance": "验收交接",
    "workhours": "工时数据",
}


# ============================================================
# 辅助函数
# ============================================================

def _safe_read_v1_table(v1_conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    """从 v1 数据库读取表为 DataFrame"""
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", v1_conn)
    except Exception:
        return pd.DataFrame()


def _apply_column_map(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """应用字段映射，只保留映射后的列"""
    result = pd.DataFrame()
    for src_col, dst_col in col_map.items():
        if src_col in df.columns:
            result[dst_col] = df[src_col]
    return result


def _ensure_output_dir():
    """确保输出目录存在"""
    ONES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _backup_file(file_path: Path, month: str, data_type: str) -> Optional[str]:
    """备份现有文件，返回备份路径"""
    if not file_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{month}_{data_type}_{timestamp}.csv.bak"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(file_path, backup_path)
    return str(backup_path)


def _safe_decimal_sum(series: pd.Series) -> Decimal:
    """安全求和（用 Decimal 避免浮点误差）"""
    total = Decimal("0")
    for val in series.dropna():
        try:
            total += Decimal(str(val))
        except (InvalidOperation, ValueError):
            continue
    return total


# ============================================================
# 全量迁移：v1 SQLite → v2 CSV
# ============================================================

def migrate_full(v1_db_path: Path, month: str, dry_run: bool = False,
                 output_dir: Path = None) -> dict:
    """全量迁移 v1 → v2

    返回迁移结果摘要 dict
    """
    out_dir = output_dir or ONES_DATA_DIR
    _ensure_output_dir()

    if not v1_db_path.exists():
        raise FileNotFoundError(f"v1 数据库不存在: {v1_db_path}")

    # 连接 v1 数据库
    v1_conn = sqlite3.connect(str(v1_db_path))
    v1_conn.row_factory = sqlite3.Row

    results = {}
    total_rows = 0

    # --- 1. 签约项目（oa_contracts + ones_projects 关联） ---
    print("\n📋 [1/5] 迁移签约项目数据...")
    df_oa = _safe_read_v1_table(v1_conn, "oa_contracts")
    df_proj = _safe_read_v1_table(v1_conn, "ones_projects")

    df_sign = pd.DataFrame()
    if not df_oa.empty:
        df_sign = _apply_column_map(df_oa, V1_SIGN_COLUMN_MAP)
    if not df_proj.empty and not df_sign.empty:
        # 按合同编号关联项目信息
        df_proj_mapped = _apply_column_map(df_proj, V1_PROJECT_COLUMN_MAP)
        if "合同编号" in df_sign.columns and "合同编号" in df_proj_mapped.columns:
            df_sign = df_sign.merge(
                df_proj_mapped, on="合同编号", how="left",
                suffixes=("", "_proj")
            )
            # 去重同名列（保留左表）
            for col in df_proj_mapped.columns:
                if col + "_proj" in df_sign.columns and col in df_sign.columns:
                    df_sign[col] = df_sign[col].fillna(df_sign[col + "_proj"])
                    df_sign.drop(columns=[col + "_proj"], inplace=True)

    sign_count = len(df_sign)
    results["sign"] = {
        "v1_rows": len(df_oa),
        "v2_rows": sign_count,
        "columns": list(df_sign.columns) if not df_sign.empty else [],
        "amount_total_v1": str(_safe_decimal_sum(df_oa["签约金额"])) if "签约金额" in df_oa.columns else "0",
        "amount_total_v2": str(_safe_decimal_sum(df_sign["签约金额"])) if "签约金额" in df_sign.columns else "0",
    }
    total_rows += sign_count
    print(f"  ✅ 签约: v1 {len(df_oa)} 行 → v2 {sign_count} 行")

    # --- 2. 确收交接 ---
    print("\n📋 [2/5] 迁移确收凭证数据...")
    df_rev = _safe_read_v1_table(v1_conn, "revenue_vouchers")
    df_rev_mapped = _apply_column_map(df_rev, V1_REVENUE_COLUMN_MAP) if not df_rev.empty else pd.DataFrame()
    results["revenue"] = {
        "v1_rows": len(df_rev),
        "v2_rows": len(df_rev_mapped),
        "columns": list(df_rev_mapped.columns) if not df_rev_mapped.empty else [],
    }
    total_rows += len(df_rev_mapped)
    print(f"  ✅ 确收: v1 {len(df_rev)} 行 → v2 {len(df_rev_mapped)} 行")

    # --- 3. 验收交接 ---
    print("\n📋 [3/5] 迁移验收凭证数据...")
    df_acc = _safe_read_v1_table(v1_conn, "acceptance_vouchers")
    df_acc_mapped = _apply_column_map(df_acc, V1_ACCEPTANCE_COLUMN_MAP) if not df_acc.empty else pd.DataFrame()
    results["acceptance"] = {
        "v1_rows": len(df_acc),
        "v2_rows": len(df_acc_mapped),
        "columns": list(df_acc_mapped.columns) if not df_acc_mapped.empty else [],
    }
    total_rows += len(df_acc_mapped)
    print(f"  ✅ 验收: v1 {len(df_acc)} 行 → v2 {len(df_acc_mapped)} 行")

    # --- 4. 工时数据 ---
    print("\n📋 [4/5] 迁移工时数据...")
    df_wh = _safe_read_v1_table(v1_conn, "workhours")
    df_wh_mapped = _apply_column_map(df_wh, V1_WORKHOUR_COLUMN_MAP) if not df_wh.empty else pd.DataFrame()
    results["workhours"] = {
        "v1_rows": len(df_wh),
        "v2_rows": len(df_wh_mapped),
        "columns": list(df_wh_mapped.columns) if not df_wh_mapped.empty else [],
        "hours_total_v1": str(_safe_decimal_sum(df_wh["总工时"])) if "总工时" in df_wh.columns else "0",
        "hours_total_v2": str(_safe_decimal_sum(df_wh_mapped["总工时"])) if "总工时" in df_wh_mapped.columns else "0",
    }
    total_rows += len(df_wh_mapped)
    print(f"  ✅ 工时: v1 {len(df_wh)} 行 → v2 {len(df_wh_mapped)} 行")

    # --- 5. 写入文件（非 dry-run） ---
    print(f"\n{'=' * 50}")
    if dry_run:
        print("🔍 DRY-RUN 模式：不写入文件")
        status = "dry_run"
    else:
        print("💾 写入 v2 数据目录...")
        status = "success"

        data_map = {
            "sign": df_sign,
            "revenue": df_rev_mapped,
            "acceptance": df_acc_mapped,
            "workhours": df_wh_mapped,
        }

        backup_paths = {}
        try:
            for dtype, df in data_map.items():
                if df.empty:
                    continue
                fname = DATA_TYPE_FILENAME[dtype].format(month=month)
                out_path = out_dir / fname
                # 确收/验收 CSV 在 v2 中是从 REF_BASE_DIR 读的
                # 迁移时统一写到 ones_exports 目录，生成时配置路径即可
                backup = _backup_file(out_path, month, dtype)
                if backup:
                    backup_paths[dtype] = backup
                # 写 CSV（UTF-8 with BOM 兼容 Excel）
                df.to_csv(out_path, index=False, encoding="utf-8-sig")
                print(f"  ✅ {DATA_TYPE_LABEL[dtype]} → {fname}")

            # 记录导入日志
            for dtype, df in data_map.items():
                if df.empty:
                    continue
                create_import_log(
                    source_type="v1_sqlite",
                    source_path=str(v1_db_path),
                    data_type=dtype,
                    status=status,
                    rows_imported=len(df),
                    month=month,
                    backup_path=backup_paths.get(dtype),
                )
        except Exception as e:
            print(f"❌ 写入失败: {e}")
            # 回滚：恢复备份
            for dtype, backup in backup_paths.items():
                fname = DATA_TYPE_FILENAME[dtype].format(month=month)
                out_path = out_dir / fname
                if backup and Path(backup).exists():
                    shutil.copy2(backup, out_path)
                    print(f"  ↩️  已回滚 {dtype}")
            status = "failed"
            raise

    v1_conn.close()

    summary = {
        "month": month,
        "total_rows": total_rows,
        "status": status,
        "details": results,
        "output_dir": str(out_dir),
    }

    print(f"\n📊 迁移完成：{total_rows} 行数据，状态: {status}")
    return summary


# ============================================================
# 增量导入：Excel/CSV → v2
# ============================================================

def import_data(source_path: Path, data_type: str, month: str,
                dry_run: bool = False, output_dir: Path = None) -> dict:
    """从 Excel 或 CSV 导入数据到 v2 数据目录"""
    out_dir = output_dir or ONES_DATA_DIR
    _ensure_output_dir()

    if not source_path.exists():
        raise FileNotFoundError(f"源文件不存在: {source_path}")

    if data_type not in DATA_TYPE_FILENAME:
        raise ValueError(f"不支持的数据类型: {data_type}，可选: {list(DATA_TYPE_FILENAME.keys())}")

    # 读取源文件
    suffix = source_path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(source_path, dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(source_path, dtype=str, encoding="utf-8-sig")
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 .xlsx / .xls / .csv")

    row_count = len(df)
    col_count = len(df.columns)

    print(f"📥 读取 {source_path.name}: {row_count} 行 × {col_count} 列")
    print(f"   列名: {list(df.columns)[:10]}...")

    if dry_run:
        print("🔍 DRY-RUN 模式：不写入文件")
        status = "dry_run"
    else:
        fname = DATA_TYPE_FILENAME[data_type].format(month=month)
        out_path = out_dir / fname
        backup = _backup_file(out_path, month, data_type)

        try:
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            status = "success"
            print(f"💾 已写入: {out_path}")

            create_import_log(
                source_type="excel" if suffix in (".xlsx", ".xls") else "csv",
                source_path=str(source_path),
                data_type=data_type,
                status=status,
                rows_imported=row_count,
                month=month,
                backup_path=backup,
            )
        except Exception as e:
            print(f"❌ 写入失败: {e}")
            if backup and Path(backup).exists():
                shutil.copy2(backup, out_path)
                print(f"  ↩️  已回滚")
            status = "failed"
            raise

    return {
        "data_type": data_type,
        "month": month,
        "rows": row_count,
        "columns": col_count,
        "status": status,
        "output_file": DATA_TYPE_FILENAME[data_type].format(month=month),
    }


# ============================================================
# 回滚
# ============================================================

def rollback_import(import_id: int, output_dir: Path = None) -> dict:
    """根据导入记录 ID 回滚"""
    out_dir = output_dir or ONES_DATA_DIR
    log = get_import_log(import_id)
    if not log:
        raise ValueError(f"导入记录不存在: {import_id}")

    if not log["backup_path"]:
        return {"status": "skipped", "reason": "无备份文件，无法回滚"}

    backup_path = Path(log["backup_path"])
    if not backup_path.exists():
        return {"status": "failed", "reason": f"备份文件不存在: {backup_path}"}

    fname = DATA_TYPE_FILENAME[log["data_type"]].format(month=log["month"] or "")
    target_path = out_dir / fname

    # 恢复备份
    shutil.copy2(backup_path, target_path)

    # 更新日志状态
    from db import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE import_logs SET status = 'rolled_back' WHERE id = ?",
        (import_id,)
    )
    conn.commit()
    conn.close()

    print(f"↩️  已回滚: {fname} (从 {backup_path.name} 恢复)")
    return {
        "status": "success",
        "import_id": import_id,
        "restored_file": str(target_path),
        "backup_file": str(backup_path),
    }


# ============================================================
# 校验
# ============================================================

def validate_migration(v1_db_path: Path, month: str, output_dir: Path = None) -> dict:
    """校验迁移结果：行数、金额等"""
    out_dir = output_dir or ONES_DATA_DIR

    if not v1_db_path.exists():
        raise FileNotFoundError(f"v1 数据库不存在: {v1_db_path}")

    v1_conn = sqlite3.connect(str(v1_db_path))

    checks = {}
    all_pass = True

    # 签约项目
    sign_file = out_dir / DATA_TYPE_FILENAME["sign"].format(month=month)
    if sign_file.exists():
        df_v2 = pd.read_csv(sign_file, dtype=str)
        df_v1 = _safe_read_v1_table(v1_conn, "oa_contracts")

        row_pass = len(df_v1) == len(df_v2)
        v1_amount = _safe_decimal_sum(df_v1["签约金额"]) if "签约金额" in df_v1.columns else Decimal("0")
        v2_amount = _safe_decimal_sum(df_v2["签约金额"]) if "签约金额" in df_v2.columns else Decimal("0")
        amount_diff = abs(v1_amount - v2_amount)
        amount_pass = amount_diff < Decimal("0.01")

        # 非空率
        non_null_rate = df_v2["合同编号"].notna().sum() / len(df_v2) if len(df_v2) > 0 else 0
        non_null_pass = non_null_rate >= 0.95

        checks["sign"] = {
            "row_count_v1": len(df_v1),
            "row_count_v2": len(df_v2),
            "row_count_pass": row_pass,
            "amount_v1": str(v1_amount),
            "amount_v2": str(v2_amount),
            "amount_diff": str(amount_diff),
            "amount_pass": amount_pass,
            "contract_no_non_null_rate": f"{non_null_rate:.2%}",
            "non_null_pass": non_null_pass,
            "pass": row_pass and amount_pass and non_null_pass,
        }
        if not checks["sign"]["pass"]:
            all_pass = False

    # 确收
    rev_file = out_dir / DATA_TYPE_FILENAME["revenue"].format(month=month)
    if rev_file.exists():
        df_v2 = pd.read_csv(rev_file, dtype=str)
        df_v1 = _safe_read_v1_table(v1_conn, "revenue_vouchers")
        row_pass = len(df_v1) == len(df_v2)
        checks["revenue"] = {
            "row_count_v1": len(df_v1),
            "row_count_v2": len(df_v2),
            "row_count_pass": row_pass,
            "pass": row_pass,
        }
        if not row_pass:
            all_pass = False

    # 验收
    acc_file = out_dir / DATA_TYPE_FILENAME["acceptance"].format(month=month)
    if acc_file.exists():
        df_v2 = pd.read_csv(acc_file, dtype=str)
        df_v1 = _safe_read_v1_table(v1_conn, "acceptance_vouchers")
        row_pass = len(df_v1) == len(df_v2)
        checks["acceptance"] = {
            "row_count_v1": len(df_v1),
            "row_count_v2": len(df_v2),
            "row_count_pass": row_pass,
            "pass": row_pass,
        }
        if not row_pass:
            all_pass = False

    v1_conn.close()

    return {
        "month": month,
        "all_pass": all_pass,
        "checks": checks,
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="BDMS v1 → v2 数据迁移工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # full
    p_full = subparsers.add_parser("full", help="全量迁移 v1 → v2")
    p_full.add_argument("--v1-db", required=True, help="v1 SQLite 数据库路径")
    p_full.add_argument("--month", required=True, help="报告月份 YYYYMM")
    p_full.add_argument("--output-dir", help="v2 数据输出目录")
    p_full.add_argument("--dry-run", action="store_true", help="只预览不写入")
    p_full.add_argument("--validate", action="store_true", help="迁移后自动校验")

    # import
    p_import = subparsers.add_parser("import", help="从 Excel/CSV 导入")
    p_import.add_argument("--source", required=True, help="源文件路径")
    p_import.add_argument("--type", required=True, dest="data_type",
                          choices=list(DATA_TYPE_FILENAME.keys()),
                          help="数据类型")
    p_import.add_argument("--month", required=True, help="报告月份 YYYYMM")
    p_import.add_argument("--output-dir", help="v2 数据输出目录")
    p_import.add_argument("--dry-run", action="store_true", help="只预览不写入")

    # rollback
    p_rollback = subparsers.add_parser("rollback", help="回滚指定导入")
    p_rollback.add_argument("--import-id", type=int, required=True, help="导入记录 ID")
    p_rollback.add_argument("--output-dir", help="v2 数据目录")

    # validate
    p_validate = subparsers.add_parser("validate", help="校验迁移结果")
    p_validate.add_argument("--v1-db", required=True, help="v1 SQLite 数据库路径")
    p_validate.add_argument("--month", required=True, help="报告月份 YYYYMM")
    p_validate.add_argument("--output-dir", help="v2 数据目录")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 初始化元数据库
    init_db()

    if args.command == "full":
        result = migrate_full(
            v1_db_path=Path(args.v1_db),
            month=args.month,
            dry_run=args.dry_run,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        if args.validate and not args.dry_run:
            print("\n" + "=" * 50)
            print("🔍 运行迁移校验...")
            v = validate_migration(
                v1_db_path=Path(args.v1_db),
                month=args.month,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
            print(f"校验结果: {'✅ 全部通过' if v['all_pass'] else '❌ 存在不通过项'}")
            for name, check in v["checks"].items():
                status = "✅" if check["pass"] else "❌"
                print(f"  {status} {name}: v1 {check.get('row_count_v1', '-')} / v2 {check.get('row_count_v2', '-')}")

    elif args.command == "import":
        result = import_data(
            source_path=Path(args.source),
            data_type=args.data_type,
            month=args.month,
            dry_run=args.dry_run,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )

    elif args.command == "rollback":
        result = rollback_import(
            import_id=args.import_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )

    elif args.command == "validate":
        result = validate_migration(
            v1_db_path=Path(args.v1_db),
            month=args.month,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )


if __name__ == "__main__":
    main()
