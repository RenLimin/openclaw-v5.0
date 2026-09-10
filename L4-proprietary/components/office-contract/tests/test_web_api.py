"""
合同审批 Web API 测试 — FastAPI TestClient
覆盖所有 API 端点的核心场景。
"""

import os
import sys
import tempfile
import shutil
import pytest

# 路径设置
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_WEB_DIR)
if _MODULE_DIR not in sys.path:
    sys.path.insert(0, _MODULE_DIR)

# 在 import 前覆盖配置
import config


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def test_env():
    """临时数据库 + 输出目录"""
    test_db = os.path.join(tempfile.gettempdir(), "test_contract_web.db")
    test_output_dir = os.path.join(tempfile.gettempdir(), "test_contract_web_outputs")

    orig_db = config.DB_PATH
    orig_output = config.OUTPUT_DIR
    config.DB_PATH = test_db
    config.OUTPUT_DIR = test_output_dir

    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
    os.makedirs(test_output_dir, exist_ok=True)

    yield {"db_path": test_db, "output_dir": test_output_dir}

    config.DB_PATH = orig_db
    config.OUTPUT_DIR = orig_output
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)


@pytest.fixture(scope="module")
def client(test_env):
    """FastAPI TestClient（确保 DB 已初始化）"""
    from services import init_db
    from fastapi.testclient import TestClient
    from web.main import app
    init_db()
    return TestClient(app)


@pytest.fixture(scope="module")
def sample_contracts(client):
    """创建几个不同级别的测试合同，模块级复用"""
    contracts = {}

    resp = client.post("/api/contracts", json={
        "title": "Web API 测试合同-L1",
        "party_b": "测试客户甲",
        "amount": 50000,
        "contract_type": "tech_service",
    })
    assert resp.status_code == 201
    contracts["l1"] = resp.json()["id"]

    resp = client.post("/api/contracts", json={
        "title": "Web API 测试合同-L3",
        "party_b": "测试客户乙",
        "amount": 800000,
        "contract_type": "sow",
    })
    assert resp.status_code == 201
    contracts["l3"] = resp.json()["id"]

    resp = client.post("/api/contracts", json={
        "title": "Web API 驳回测试",
        "party_b": "驳回测试客户",
        "amount": 200000,
    })
    assert resp.status_code == 201
    contracts["reject"] = resp.json()["id"]

    return contracts


# ============================================================
# 健康检查
# ============================================================

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_api_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ============================================================
# 合同创建
# ============================================================

class TestCreateContract:
    def test_create_ok(self, client):
        resp = client.post("/api/contracts", json={
            "title": "新建合同测试",
            "party_b": "客户有限公司",
            "amount": 100000,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] > 0
        assert "approval_level" in data

    def test_create_missing_title(self, client):
        resp = client.post("/api/contracts", json={
            "party_b": "客户",
            "amount": 10000,
        })
        assert resp.status_code == 422  # Pydantic 校验失败

    def test_create_zero_amount(self, client):
        resp = client.post("/api/contracts", json={
            "title": "零金额合同",
            "party_b": "客户",
            "amount": 0,
        })
        assert resp.status_code == 422


# ============================================================
# 合同列表
# ============================================================

class TestListContracts:
    def test_list_default(self, client, sample_contracts):
        resp = client.get("/api/contracts")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 3

    def test_list_pagination(self, client):
        resp = client.get("/api/contracts?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    def test_list_filter_status(self, client):
        resp = client.get("/api/contracts?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "draft"


# ============================================================
# 合同详情
# ============================================================

class TestGetContract:
    def test_get_ok(self, client, sample_contracts):
        cid = sample_contracts["l1"]
        resp = client.get(f"/api/contracts/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "contract" in data
        assert "approval_level" in data
        assert data["contract"]["id"] == cid

    def test_get_not_found(self, client):
        resp = client.get("/api/contracts/999999")
        assert resp.status_code == 404

    def test_contains_approval_info(self, client, sample_contracts):
        cid = sample_contracts["l3"]
        resp = client.get(f"/api/contracts/{cid}")
        data = resp.json()
        assert data["approval_level"] == 3
        assert len(data["approval_roles"]) == 3
        assert "sla_days" in data


# ============================================================
# 提交审批
# ============================================================

class TestSubmitApproval:
    def test_submit_ok(self, client, sample_contracts):
        cid = sample_contracts["l1"]
        resp = client.post(f"/api/contracts/{cid}/submit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "review1"

    def test_submit_already_submitted(self, client, sample_contracts):
        """已提交的合同再次提交应失败"""
        cid = sample_contracts["l1"]
        resp = client.post(f"/api/contracts/{cid}/submit")
        assert resp.status_code == 400  # ValueError → 400


# ============================================================
# 审批通过 / 驳回
# ============================================================

class TestApproval:
    def test_approve_l1(self, client, sample_contracts):
        cid = sample_contracts["l1"]
        resp = client.post(f"/api/contracts/{cid}/approve", json={
            "approver_name": "张经理",
            "approver_role": "销售经理",
            "comment": "同意",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["to_status"] == "approved"

    def test_approve_missing_role(self, client, sample_contracts):
        cid = sample_contracts["l3"]
        resp = client.post(f"/api/contracts/{cid}/approve", json={
            "approver_name": "某人",
        })
        assert resp.status_code == 422

    def test_reject_flow(self, client, sample_contracts):
        cid = sample_contracts["reject"]
        # 先提交
        client.post(f"/api/contracts/{cid}/submit")
        # 再驳回
        resp = client.post(f"/api/contracts/{cid}/reject", json={
            "approver_name": "王经理",
            "approver_role": "销售经理",
            "comment": "信息不完整",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rejected_at_level"] == 1
        # 验证状态回退
        detail = client.get(f"/api/contracts/{cid}").json()
        assert detail["contract"]["status"] == "draft"


# ============================================================
# 风险扫描
# ============================================================

class TestRiskScan:
    def test_risk_scan_l1(self, client, sample_contracts):
        cid = sample_contracts["l1"]
        resp = client.get(f"/api/contracts/{cid}/risk-scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_risk" in data
        assert "findings" in data
        assert len(data["findings"]) > 0
        assert "summary" in data


# ============================================================
# 审批历史
# ============================================================

class TestHistory:
    def test_history_exists(self, client, sample_contracts):
        cid = sample_contracts["l1"]
        resp = client.get(f"/api/contracts/{cid}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "approvals" in data
        assert "audit_logs" in data
        assert len(data["audit_logs"]) > 0

    def test_history_not_found(self, client):
        resp = client.get("/api/contracts/999999/history")
        assert resp.status_code == 404


# ============================================================
# 统计数据
# ============================================================

class TestStats:
    def test_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "draft_count" in data
        assert "approved_count" in data
        assert "approval_rate" in data


# ============================================================
# 页面路由
# ============================================================

class TestPages:
    def test_dashboard_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "仪表盘" in resp.text or "dashboard" in resp.text.lower()

    def test_contract_list_page(self, client):
        resp = client.get("/contracts")
        assert resp.status_code == 200
        assert "合同" in resp.text

    def test_contract_detail_page(self, client, sample_contracts):
        resp = client.get(f"/contracts/{sample_contracts['l1']}")
        assert resp.status_code == 200

    def test_new_contract_page(self, client):
        # /new 路由在 /contracts/new 之前定义，避免和 {contract_id} 冲突
        resp = client.get("/new")
        assert resp.status_code == 200

    def test_error_page(self, client):
        """访问不存在的页面应该走错误处理"""
        resp = client.get("/nonexistent-page")
        # FastAPI 默认 404 是 JSON，我们的异常处理只覆盖已知路径
        assert resp.status_code == 404
