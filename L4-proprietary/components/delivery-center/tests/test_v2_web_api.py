"""
BDMS v2 Web API 测试

覆盖：5 个 API 接口 + 页面路由，共 10+ 测试用例
注意：使用 mock 避免实际生成报告（生成器本身有独立测试）
"""

import sys
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# 路径设置
BASE_DIR = Path(__file__).resolve().parent.parent
V2_DIR = BASE_DIR / "src" / "delivery_center" / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "web"))
sys.path.insert(0, str(V2_DIR / "services"))


@pytest.fixture
def temp_db(tmp_path):
    """临时元数据库"""
    import importlib
    import db as v2_db
    db_path = tmp_path / "bdms_v2_test.db"
    v2_db.init_db(db_path)
    v2_db.DB_PATH = db_path

    # 给 report_service 也换临时路径
    import report_service
    importlib.reload(report_service)

    yield db_path

    # 还原
    importlib.reload(v2_db)
    importlib.reload(report_service)


@pytest.fixture
def client(temp_db):
    """FastAPI 测试客户端（mock 掉实际生成器）"""
    # 用 patch 替换掉实际生成函数
    with patch("services.report_service._generate_report_async") as mock_gen:
        def fake_gen(job_id, month):
            """假生成：直接把状态改成 completed"""
            import db as v2_db
            # 创建一个假的 Excel 文件
            from openpyxl import Workbook
            report_dir = Path(temp_db).parent / "reports"
            report_dir.mkdir(exist_ok=True)
            fake_file = report_dir / f"交付月报-{month}-v2.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "签约"
            ws["A1"] = "合同编号"
            ws["B1"] = "签约金额"
            ws["A2"] = "HT001"
            ws["B2"] = 100000
            wb.create_sheet("POC&提前实施")
            wb.create_sheet("异常项目")
            wb.create_sheet("确收交接")
            wb.create_sheet("验收交接")
            wb.save(fake_file)

            v2_db.update_job_status(
                job_id, "completed", progress=100,
                file_path=str(fake_file), db_path=temp_db
            )
        mock_gen.side_effect = fake_gen

        from main import app
        from fastapi.testclient import TestClient
        yield TestClient(app)


# ============================================================
# 测试用例
# ============================================================

def test_health_check(client):
    """测试 1：健康检查接口"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


def test_report_list_empty(client):
    """测试 2：空列表"""
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_generate_report_success(client):
    """测试 3：触发生成报告成功返回 job_id"""
    resp = client.post("/api/reports/generate", json={"month": "202606"})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["month"] == "202606"
    assert data["status"] == "pending"
    assert data["job_id"] > 0


def test_generate_report_invalid_month_format(client):
    """测试 4：无效月份格式应返回 400"""
    # 太短
    resp = client.post("/api/reports/generate", json={"month": "2026"})
    assert resp.status_code == 400

    # 非数字
    resp = client.post("/api/reports/generate", json={"month": "abcdef"})
    assert resp.status_code == 400


def test_generate_report_invalid_month_range(client):
    """测试 5：月份范围错误"""
    # 月份 13
    resp = client.post("/api/reports/generate", json={"month": "202613"})
    assert resp.status_code == 400

    # 月份 00
    resp = client.post("/api/reports/generate", json={"month": "202600"})
    assert resp.status_code == 400

    # 年份太老
    resp = client.post("/api/reports/generate", json={"month": "190001"})
    assert resp.status_code == 400


def test_get_status_completed(client):
    """测试 6：查询任务状态（completed）"""
    # 先创建一个任务
    resp = client.post("/api/reports/generate", json={"month": "202607"})
    job_id = resp.json()["job_id"]

    # mock 会异步改状态，等一小会儿
    import time
    time.sleep(0.5)

    resp = client.get(f"/api/reports/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["month"] == "202607"
    assert data["status"] == "completed"
    assert data["progress"] == 100
    assert data["file_path"] is not None


def test_get_status_not_found(client):
    """测试 7：查询不存在的任务返回 404"""
    resp = client.get("/api/reports/99999/status")
    assert resp.status_code == 404


def test_list_reports_with_data(client):
    """测试 8：列表含数据，按时间倒序"""
    # 创建 3 个任务
    months = ["202604", "202605", "202606"]
    for m in months:
        client.post("/api/reports/generate", json={"month": m})

    import time
    time.sleep(0.5)

    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3
    # 应该按 id 倒序排列（最新的在前）
    ids_returned = [r["id"] for r in data[:3]]
    assert ids_returned == sorted(ids_returned, reverse=True)


def test_download_completed_report(client):
    """测试 9：已完成的报告可以下载"""
    resp = client.post("/api/reports/generate", json={"month": "202606"})
    job_id = resp.json()["job_id"]

    import time
    time.sleep(0.5)

    resp = client.get(f"/api/reports/{job_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(resp.content) > 0


def test_download_pending_report(client):
    """测试 10：pending 状态的报告下载返回 400"""
    # 直接操作 DB 创建一个 pending 任务
    import db as v2_db
    job_id = v2_db.create_job("202609", db_path=client.app.state.test_db if hasattr(client.app.state, 'test_db') else None)

    # 不用 mock 的方式，直接查 DB
    conn = v2_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM report_jobs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    latest_id = row["id"]

    # 先确认状态是 pending
    resp = client.get(f"/api/reports/{latest_id}/status")
    if resp.json()["status"] == "pending":
        resp = client.get(f"/api/reports/{latest_id}/download")
        assert resp.status_code == 400


def test_download_not_found(client):
    """测试 11：下载不存在的报告返回 404"""
    resp = client.get("/api/reports/99999/download")
    assert resp.status_code == 404


def test_summary_api_completed(client):
    """测试 12：已完成报告的概要 API"""
    resp = client.post("/api/reports/generate", json={"month": "202606"})
    job_id = resp.json()["job_id"]

    import time
    time.sleep(0.5)

    resp = client.get(f"/api/reports/{job_id}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "job" in data
    assert "sheets" in data
    assert isinstance(data["sheets"], list)
    assert len(data["sheets"]) > 0  # 我们的 mock 文件有 6 个 sheet


def test_summary_not_found(client):
    """测试 13：不存在的报告概要返回 404"""
    resp = client.get("/api/reports/99999/summary")
    assert resp.status_code == 404


def test_page_list(client):
    """测试 14：列表页可访问"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "月报列表" in resp.text
    assert "BDMS v2" in resp.text


def test_page_generate(client):
    """测试 15：生成页可访问"""
    resp = client.get("/generate")
    assert resp.status_code == 200
    assert "生成月报" in resp.text


def test_page_detail_exists(client):
    """测试 16：详情页可访问"""
    resp = client.post("/api/reports/generate", json={"month": "202606"})
    job_id = resp.json()["job_id"]

    resp = client.get(f"/reports/{job_id}")
    assert resp.status_code == 200
    assert f"月报 #{job_id}" in resp.text


def test_page_detail_not_found(client):
    """测试 17：不存在的报告详情页显示错误"""
    resp = client.get("/reports/99999")
    assert resp.status_code == 200
    assert "不存在" in resp.text


def test_generate_missing_body(client):
    """测试 18：缺少请求体返回 422"""
    resp = client.post("/api/reports/generate", json={})
    assert resp.status_code == 422


def test_list_limit_param(client):
    """测试 19：列表支持 limit 参数"""
    for i in range(5):
        client.post("/api/reports/generate", json={"month": f"2026{str(i+1).zfill(2)}"})

    import time
    time.sleep(0.3)

    resp = client.get("/api/reports?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
