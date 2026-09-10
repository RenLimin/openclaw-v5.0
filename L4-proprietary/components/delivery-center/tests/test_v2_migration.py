"""
BDMS v2 迁移工具测试

覆盖：全量迁移、字段映射、数据校验、dry-run、回滚
"""

import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest
import pandas as pd

# 路径设置
BASE_DIR = Path(__file__).resolve().parent.parent
V2_DIR = BASE_DIR / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "scripts"))

from migrate_v1_to_v2 import (
    migrate_full, import_data, rollback_import, validate_migration,
    V1_SIGN_COLUMN_MAP, DATA_TYPE_FILENAME
)
from db import init_db, get_connection, get_import_log


@pytest.fixture
def temp_dirs(tmp_path):
    """临时目录：输出目录 + 备份目录"""
    output_dir = tmp_path / "ones_exports"
    output_dir.mkdir()
    # 重写 ONES_DATA_DIR 和 BACKUP_DIR 指向临时目录
    import migrate_v1_to_v2 as mig
    original_ones = mig.ONES_DATA_DIR
    original_backup = mig.BACKUP_DIR
    mig.ONES_DATA_DIR = output_dir
    mig.BACKUP_DIR = tmp_path / "backups"
    mig.BACKUP_DIR.mkdir()
    yield output_dir
    mig.ONES_DATA_DIR = original_ones
    mig.BACKUP_DIR = original_backup


@pytest.fixture
def v1_db(tmp_path):
    """创建一个模拟的 v1 数据库"""
    db_path = tmp_path / "bdms_v1_test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # OA 合同台账（5 条）
    cursor.execute("""
        CREATE TABLE oa_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            htbh TEXT UNIQUE,
            合同名称 TEXT,
            客户名称 TEXT,
            签约金额 REAL,
            责任销售 TEXT,
            责任销售部门 TEXT,
            签约销售 TEXT,
            签约销售团队 TEXT,
            创建日期 DATE,
            申请日期 DATE,
            服务开始日期 DATE,
            服务结束日期 DATE,
            直签或代理 TEXT,
            合同分类 TEXT,
            归档状态 TEXT
        )
    """)
    for i in range(5):
        cursor.execute("""
            INSERT INTO oa_contracts (htbh, 合同名称, 客户名称, 签约金额, 责任销售, 责任销售部门,
                签约销售, 签约销售团队, 创建日期, 申请日期, 服务开始日期, 服务结束日期,
                直签或代理, 合同分类, 归档状态)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"HT2026{i:03d}",
            f"测试合同{i}",
            f"客户{i}",
            100000.0 + i * 10000,
            f"销售{i}",
            "测试部门",
            f"销售{i}",
            "测试团队",
            "2026-01-01",
            "2026-01-05",
            "2026-02-01",
            "2026-12-31",
            "直签",
            "技术服务",
            "已归档",
        ))

    # ONES 项目（3 条，关联前 3 个合同）
    cursor.execute("""
        CREATE TABLE ones_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT UNIQUE,
            项目名称 TEXT,
            合同编号 TEXT,
            客户名称 TEXT,
            项目经理 TEXT,
            部门 TEXT,
            项目状态 TEXT,
            立项日期 DATE,
            预估结项日期 DATE,
            实际结项日期 DATE
        )
    """)
    for i in range(3):
        cursor.execute("""
            INSERT INTO ones_projects (project_id, 项目名称, 合同编号, 客户名称,
                项目经理, 部门, 项目状态, 立项日期, 预估结项日期, 实际结项日期)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"PRJ{i:03d}",
            f"测试项目{i}",
            f"HT2026{i:03d}",
            f"客户{i}",
            f"PM{i}",
            "交付一部",
            "进行中",
            "2026-02-01",
            "2026-06-30",
            None,
        ))

    # 确收凭证（4 条）
    cursor.execute("""
        CREATE TABLE revenue_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id TEXT,
            bi_id TEXT,
            合同编号 TEXT,
            合同名称 TEXT,
            客户名称 TEXT,
            销售部门 TEXT,
            项目经理 TEXT,
            交接日期 DATE,
            财务 TEXT,
            是否接收 TEXT
        )
    """)
    for i in range(4):
        cursor.execute("""
            INSERT INTO revenue_vouchers (voucher_id, bi_id, 合同编号, 合同名称,
                客户名称, 销售部门, 项目经理, 交接日期, 财务, 是否接收)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"REV{i:03d}",
            f"BI{i:03d}",
            f"HT2026{i:03d}",
            f"测试合同{i}",
            f"客户{i}",
            "测试部门",
            f"PM{i}",
            "2026-06-30",
            "财务A",
            "是",
        ))

    # 验收凭证（3 条）
    cursor.execute("""
        CREATE TABLE acceptance_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id TEXT,
            bi_id TEXT,
            合同编号 TEXT,
            合同名称 TEXT,
            客户名称 TEXT,
            项目经理 TEXT,
            验收单编号 TEXT,
            交接日期 DATE,
            验收方式 TEXT,
            全部或部分 TEXT,
            财务 TEXT,
            财务是否接收 TEXT
        )
    """)
    for i in range(3):
        cursor.execute("""
            INSERT INTO acceptance_vouchers (voucher_id, bi_id, 合同编号, 合同名称,
                客户名称, 项目经理, 验收单编号, 交接日期, 验收方式, 全部或部分, 财务, 财务是否接收)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"ACC{i:03d}",
            f"BI{i:03d}",
            f"HT2026{i:03d}",
            f"测试合同{i}",
            f"客户{i}",
            f"PM{i}",
            f"YS{i:03d}",
            "2026-06-30",
            "现场验收",
            "全部",
            "财务A",
            "是",
        ))

    # 工时数据（2 条）
    cursor.execute("""
        CREATE TABLE workhours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            工作项 TEXT,
            总工时 REAL,
            迁移工时 REAL,
            剩余工时 REAL,
            月份 TEXT
        )
    """)
    for i in range(2):
        cursor.execute("""
            INSERT INTO workhours (工作项, 总工时, 迁移工时, 剩余工时, 月份)
            VALUES (?, ?, ?, ?, ?)
        """, (
            f"项目{i}",
            100.0 + i * 50,
            50.0 + i * 25,
            50.0 + i * 25,
            "202606",
        ))

    # report_history
    cursor.execute("""
        CREATE TABLE report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT UNIQUE,
            report_type TEXT,
            file_path TEXT
        )
    """)

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def meta_db(tmp_path):
    """临时元数据库"""
    db_path = tmp_path / "bdms_v2_meta.db"
    init_db(db_path)

    # 重写 db 模块中的 DB_PATH
    import db
    original = db.DB_PATH
    db.DB_PATH = db_path

    # 也重写 migrate_v1_to_v2 中导入的函数
    import migrate_v1_to_v2 as mig
    # 给 create_import_log 打补丁
    original_create = mig.create_import_log
    original_get = mig.get_import_log

    def patched_create(*args, **kwargs):
        kwargs["db_path"] = db_path
        return original_create(*args, **kwargs)

    def patched_get(*args, **kwargs):
        kwargs["db_path"] = db_path
        return original_get(*args, **kwargs)

    mig.create_import_log = patched_create
    mig.get_import_log = patched_get

    yield db_path

    db.DB_PATH = original
    mig.create_import_log = original_create
    mig.get_import_log = original_get


# ============================================================
# 测试用例
# ============================================================

def test_full_migration_success(v1_db, temp_dirs, meta_db):
    """测试 1：全量迁移成功，行数正确"""
    result = migrate_full(
        v1_db_path=v1_db,
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )

    assert result["status"] == "success"
    assert result["month"] == "202606"
    assert result["total_rows"] > 0

    # 签约：5 条合同
    assert result["details"]["sign"]["v1_rows"] == 5
    assert result["details"]["sign"]["v2_rows"] == 5

    # 确收：4 条
    assert result["details"]["revenue"]["v1_rows"] == 4
    assert result["details"]["revenue"]["v2_rows"] == 4

    # 验收：3 条
    assert result["details"]["acceptance"]["v1_rows"] == 3
    assert result["details"]["acceptance"]["v2_rows"] == 3

    # 工时：2 条
    assert result["details"]["workhours"]["v1_rows"] == 2
    assert result["details"]["workhours"]["v2_rows"] == 2

    # 验证文件存在
    sign_file = temp_dirs / DATA_TYPE_FILENAME["sign"].format(month="202606")
    assert sign_file.exists()
    df = pd.read_csv(sign_file)
    assert len(df) == 5


def test_field_mapping_correct(v1_db, temp_dirs, meta_db):
    """测试 2：字段映射正确，核心列存在且值对应"""
    migrate_full(
        v1_db_path=v1_db,
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )

    # 检查签约 CSV 的列名映射
    sign_file = temp_dirs / DATA_TYPE_FILENAME["sign"].format(month="202606")
    df = pd.read_csv(sign_file, dtype=str)

    # v2 列名应该存在
    expected_cols = ["合同编号", "合同名称", "客户名称", "签约金额", "责任销售", "销售部门"]
    for col in expected_cols:
        assert col in df.columns, f"缺少列: {col}"

    # 第一行数据验证
    row0 = df.iloc[0]
    assert row0["合同编号"] == "HT2026000"
    assert row0["合同名称"] == "测试合同0"
    assert row0["客户名称"] == "客户0"
    assert float(row0["签约金额"]) == 100000.0

    # 确收交接列映射
    rev_file = temp_dirs / DATA_TYPE_FILENAME["revenue"].format(month="202606")
    df_rev = pd.read_csv(rev_file, dtype=str)
    assert "合同编号" in df_rev.columns
    assert "是否接收" in df_rev.columns
    assert df_rev.iloc[0]["是否接收"] == "是"


def test_dry_run_no_write(v1_db, temp_dirs, meta_db):
    """测试 3：dry-run 模式不写入文件"""
    # 确保目录是空的
    assert len(list(temp_dirs.glob("*.csv"))) == 0

    result = migrate_full(
        v1_db_path=v1_db,
        month="202606",
        dry_run=True,
        output_dir=temp_dirs,
    )

    assert result["status"] == "dry_run"
    # dry-run 不应该产生文件
    csv_files = list(temp_dirs.glob("*.csv"))
    assert len(csv_files) == 0, f"dry-run 不应写入文件，但发现: {csv_files}"


def test_rollback_import(v1_db, temp_dirs, meta_db):
    """测试 4：回滚功能 — 导入后可恢复到之前的状态"""
    # 第一次迁移，产生初始文件
    migrate_full(
        v1_db_path=v1_db,
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )

    sign_file = temp_dirs / DATA_TYPE_FILENAME["sign"].format(month="202606")
    original_content = sign_file.read_text()

    # 准备一个不同的 Excel 文件（1 行数据）
    excel_path = temp_dirs.parent / "new_data.xlsx"
    df_new = pd.DataFrame([{
        "合同编号": "HTNEW001",
        "合同名称": "新合同",
        "客户名称": "新客户",
        "签约金额": 999999,
    }])
    df_new.to_excel(excel_path, index=False)

    # 增量导入（会覆盖原文件）
    import_result = import_data(
        source_path=excel_path,
        data_type="sign",
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )
    assert import_result["status"] == "success"

    # 确认文件已被覆盖（内容变了）
    df_after = pd.read_csv(sign_file)
    assert len(df_after) == 1
    assert df_after.iloc[0]["合同编号"] == "HTNEW001"

    # 获取最新的导入记录 ID
    conn = get_connection(meta_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM import_logs WHERE data_type = 'sign' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    import_id = row["id"]

    # 执行回滚
    rollback_result = rollback_import(
        import_id=import_id,
        output_dir=temp_dirs,
    )

    assert rollback_result["status"] == "success"

    # 验证文件内容已恢复
    rolled_back_content = sign_file.read_text()
    assert rolled_back_content == original_content, "回滚后文件内容应与原始一致"


def test_validate_migration(v1_db, temp_dirs, meta_db):
    """测试 5：数据校验 — 迁移前后行数、金额一致"""
    # 先迁移
    migrate_full(
        v1_db_path=v1_db,
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )

    # 运行校验
    validation = validate_migration(
        v1_db_path=v1_db,
        month="202606",
        output_dir=temp_dirs,
    )

    assert validation["all_pass"] == True, f"校验应该全部通过，结果: {validation}"

    # 检查签约金额一致
    sign_check = validation["checks"]["sign"]
    assert sign_check["row_count_pass"] == True
    assert sign_check["amount_pass"] == True
    assert sign_check["non_null_pass"] == True

    # 确收行数一致
    assert validation["checks"]["revenue"]["row_count_pass"] == True

    # 验收行数一致
    assert validation["checks"]["acceptance"]["row_count_pass"] == True


def test_import_excel_file(temp_dirs, meta_db):
    """测试 6：从 Excel 文件导入数据"""
    # 准备 Excel 数据
    excel_path = temp_dirs.parent / "test_revenue.xlsx"
    df = pd.DataFrame([
        {"凭证编号": "REV001", "合同编号": "HT001", "合同名称": "合同A", "客户名称": "客户A",
         "销售部门": "部门1", "项目经理": "PM1", "交接日期": "2026-06-30",
         "财务": "财务A", "是否接收": "是"},
        {"凭证编号": "REV002", "合同编号": "HT002", "合同名称": "合同B", "客户名称": "客户B",
         "销售部门": "部门2", "项目经理": "PM2", "交接日期": "2026-06-30",
         "财务": "财务B", "是否接收": "否"},
    ])
    df.to_excel(excel_path, index=False)

    # 导入
    result = import_data(
        source_path=excel_path,
        data_type="revenue",
        month="202606",
        dry_run=False,
        output_dir=temp_dirs,
    )

    assert result["status"] == "success"
    assert result["rows"] == 2
    assert result["data_type"] == "revenue"

    # 验证文件
    out_file = temp_dirs / DATA_TYPE_FILENAME["revenue"].format(month="202606")
    assert out_file.exists()
    df_out = pd.read_csv(out_file)
    assert len(df_out) == 2
    assert df_out.iloc[0]["合同编号"] == "HT001"


def test_import_invalid_file(temp_dirs, meta_db):
    """测试 7：导入不存在的文件应抛错"""
    with pytest.raises(FileNotFoundError):
        import_data(
            source_path=Path("/nonexistent/file.xlsx"),
            data_type="sign",
            month="202606",
            output_dir=temp_dirs,
        )


def test_import_invalid_type(temp_dirs, meta_db):
    """测试 8：不支持的数据类型应抛错"""
    # 先创建一个文件
    csv_path = temp_dirs / "test.csv"
    csv_path.write_text("col1,col2\na,b\n")

    with pytest.raises(ValueError, match="不支持的数据类型"):
        import_data(
            source_path=csv_path,
            data_type="invalid_type",
            month="202606",
            output_dir=temp_dirs,
        )
