"""
Web API 测试 — FastAPI TestClient
至少 15 个测试用例
"""

from __future__ import annotations

import os
import sys
import tempfile
import yaml
import pytest

# 路径设置
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(os.path.dirname(_HERE), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)



# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient。"""
    from fastapi.testclient import TestClient
    from bangcle_ppt.web.main import app
    return TestClient(app)


@pytest.fixture
def sample_dsl():
    """一个简单有效的 DSL YAML 字符串。"""
    spec = {
        "title": "Web API 测试演示",
        "theme": "light",
        "slides": [
            {
                "meta": {
                    "name": "封面",
                    "page_type": "cover-light",
                    "theme": "light",
                },
                "data": {
                    "title": "Web 测试标题",
                    "subtitle": "WEB TEST",
                    "presenter": "Jerry",
                },
            },
            {
                "meta": {
                    "name": "目录",
                    "page_type": "toc-light",
                    "theme": "light",
                },
                "data": {
                    "items": [
                        {"number": "01", "title": "第一部分", "subtitle": "PART ONE"},
                        {"number": "02", "title": "第二部分", "subtitle": "PART TWO"},
                    ],
                },
            },
            {
                "meta": {
                    "name": "结束",
                    "page_type": "closing-light",
                    "theme": "light",
                },
                "data": {
                    "main_text": "谢谢观看",
                    "subtitle": "THANK YOU",
                },
            },
        ],
    }
    return yaml.dump(spec, allow_unicode=True)


@pytest.fixture
def invalid_dsl():
    """无效的 DSL。"""
    return "this is: not: valid: yaml: :::"


@pytest.fixture
def bad_page_type_dsl():
    """包含不存在 page_type 的 DSL。"""
    spec = {
        "title": "坏演示",
        "theme": "light",
        "slides": [
            {
                "meta": {"name": "坏", "page_type": "fake-template-xyz", "theme": "light"},
                "data": {},
            },
        ],
    }
    return yaml.dump(spec, allow_unicode=True)


# ============================================================
# 健康检查 & 基础路由
# ============================================================

def test_health(client):
    """测试 1: /health 健康检查。"""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_api_health(client):
    """测试 2: /api/health API 健康检查。"""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["component"] == "bangcle-ppt-web"


def test_page_index(client):
    """测试 3: 首页 HTML。"""
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "模板库" in r.text


def test_page_generator(client):
    """测试 4: 在线生成页 HTML。"""
    r = client.get("/generator")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "在线生成" in r.text


def test_page_template_detail(client):
    """测试 5: 模板详情页 HTML。"""
    r = client.get("/templates/cover-light")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "cover-light" in r.text


# ============================================================
# 模板列表 API
# ============================================================

def test_api_list_templates(client):
    """测试 6: 获取全部模板列表。"""
    r = client.get("/api/templates")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "templates" in data
    assert data["total"] >= 30  # light + dark 合计
    assert isinstance(data["templates"], list)
    # 检查结构
    t = data["templates"][0]
    assert "name" in t
    assert "theme" in t
    assert "title" in t
    assert "description" in t


def test_api_list_templates_filter_theme_light(client):
    """测试 7: 按浅色主题筛选。"""
    r = client.get("/api/templates?theme=light")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 15
    assert all(t["theme"] == "light" for t in data["templates"])


def test_api_list_templates_filter_theme_dark(client):
    """测试 8: 按深色主题筛选。"""
    r = client.get("/api/templates?theme=dark")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 10
    assert all(t["theme"] == "dark" for t in data["templates"])


def test_api_list_templates_invalid_theme(client):
    """测试 9: 无效主题参数返回 422。"""
    r = client.get("/api/templates?theme=invalid")
    assert r.status_code == 422  # FastAPI 校验失败


# ============================================================
# 模板详情 API
# ============================================================

def test_api_template_detail_cover_light(client):
    """测试 10: 获取 cover-light 详情。"""
    r = client.get("/api/templates/cover-light")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "cover-light"
    assert data["theme"] == "light"
    assert "meta" in data
    assert data["meta"]["page_type"] == "cover-light"
    assert "layout_fields" in data
    assert isinstance(data["layout_fields"], list)
    assert len(data["layout_fields"]) > 0
    assert "sample_data" in data
    assert "sample_dsl" in data


def test_api_template_detail_not_found(client):
    """测试 11: 不存在的模板返回 404。"""
    r = client.get("/api/templates/nonexistent-template-xyz")
    assert r.status_code == 404
    data = r.json()
    assert "error" in data or "detail" in data
    msg = data.get("error") or data.get("detail")
    assert "不存在" in msg


def test_api_template_detail_has_fields(client):
    """测试 12: 模板详情 layout_fields 结构正确。"""
    r = client.get("/api/templates/data-chart-light")
    assert r.status_code == 200
    data = r.json()
    fields = {f["name"]: f for f in data["layout_fields"]}
    assert "title" in fields
    # data-chart 有 kpis 等字段
    assert "chart_type" in fields or "kpis" in fields


# ============================================================
# 校验 API
# ============================================================

def test_api_validate_valid(client, sample_dsl):
    """测试 13: 校验有效 DSL。"""
    r = client.post("/api/validate", json={"dsl_yaml": sample_dsl})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert data["title"] == "Web API 测试演示"
    assert data["theme"] == "light"
    assert data["slide_count"] == 3
    assert data["errors"] == []


def test_api_validate_invalid_yaml(client):
    """测试 14: 校验格式错误的 YAML。"""
    r = client.post("/api/validate", json={"dsl_yaml": "not: valid: ::: yaml"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


def test_api_validate_empty(client):
    """测试 15: 空 DSL 返回 400。"""
    r = client.post("/api/validate", json={"dsl_yaml": ""})
    assert r.status_code == 400


def test_api_validate_bad_page_type(client, bad_page_type_dsl):
    """测试 16: 无效 page_type 校验失败。"""
    r = client.post("/api/validate", json={"dsl_yaml": bad_page_type_dsl})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


# ============================================================
# 渲染 API
# ============================================================

def test_api_render_valid(client, sample_dsl):
    """测试 17: 渲染有效 DSL 返回 PPT 文件。"""
    r = client.post("/api/render", json={
        "dsl_yaml": sample_dsl,
        "filename": "test-output.pptx",
    })
    assert r.status_code == 200
    assert "presentationml" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert "test-output.pptx" in r.headers["content-disposition"]
    # 文件大小应该合理
    assert len(r.content) > 20000  # 至少 20KB


def test_api_render_invalid_dsl(client, invalid_dsl):
    """测试 18: 无效 DSL 渲染返回 400。"""
    r = client.post("/api/render", json={"dsl_yaml": invalid_dsl})
    assert r.status_code == 400


def test_api_render_with_theme_override(client, sample_dsl):
    """测试 19: 主题覆盖参数。"""
    r = client.post("/api/render", json={
        "dsl_yaml": sample_dsl,
        "theme": "light",
    })
    assert r.status_code == 200
    assert len(r.content) > 10000


def test_api_render_bad_theme(client, sample_dsl):
    """测试 20: 无效主题参数返回 422。"""
    r = client.post("/api/render", json={
        "dsl_yaml": sample_dsl,
        "theme": "invalid",
    })
    assert r.status_code == 422


# ============================================================
# 模板预览 API
# ============================================================

def test_api_template_preview(client):
    """测试 21: 单模板预览下载。"""
    r = client.get("/api/templates/cover-light/preview")
    assert r.status_code == 200
    assert "presentationml" in r.headers["content-type"]
    assert "preview" in r.headers["content-disposition"].lower()
    assert len(r.content) > 5000


def test_api_template_preview_not_found(client):
    """测试 22: 不存在模板的预览返回 404。"""
    r = client.get("/api/templates/fake-template-xyz/preview")
    assert r.status_code == 404
