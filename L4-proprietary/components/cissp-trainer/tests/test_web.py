"""
CISSP Trainer Web API 测试
使用 FastAPI TestClient + 临时数据库
"""

from __future__ import annotations

import sys
import os
import pytest
from pathlib import Path

# 路径设置
_COMP_DIR = Path(__file__).resolve().parents[1]
_SRC_DIR = _COMP_DIR / "src"
_WEB_DIR = _COMP_DIR / "web"
for _p in [str(_SRC_DIR), str(_COMP_DIR), str(_WEB_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from cissp_trainer.database import init_db
from cissp_trainer.importer import import_questions
from cissp_trainer.learning_path import init_preset_paths
from cissp_trainer.knowledge_graph import add_edge

from web.main import app
from web.api import router as api_router


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def test_db(tmp_path):
    """创建临时测试数据库，注入到 web.api"""
    db_path = tmp_path / "test_web.db"
    engine = init_db(db_path=db_path, drop_first=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    # 导入测试题
    session = SessionLocal()
    sample_qs = [
        # 域1
        {
            "id": "w-test-d1-001", "domain": 1, "difficulty": 2, "question_type": "single",
            "stem": "CIA 三元组是什么？",
            "options": {"A": "机密性完整性可用性", "B": "保密性真实性", "C": "可靠性", "D": "可审计性"},
            "correct_answer": "A", "explanation": "CIA = Confidentiality, Integrity, Availability",
            "tags": ["CIA三元组", "安全基础"], "source": "test"
        },
        {
            "id": "w-test-d1-002", "domain": 1, "difficulty": 3, "question_type": "single",
            "stem": "外包属于哪种风险处置？",
            "options": {"A": "规避", "B": "转移", "C": "缓解", "D": "接受"},
            "correct_answer": "B", "explanation": "外包将风险转移给第三方",
            "tags": ["风险管理", "风险处置"], "source": "test"
        },
        {
            "id": "w-test-d1-003", "domain": 1, "difficulty": 1, "question_type": "truefalse",
            "stem": "安全策略由 IT 部门批准。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "B", "explanation": "安全策略由高层管理批准",
            "tags": ["安全策略", "治理"], "source": "test"
        },
        # 域2
        {
            "id": "w-test-d2-001", "domain": 2, "difficulty": 2, "question_type": "single",
            "stem": "数据分类的目的？",
            "options": {"A": "合规", "B": "确定价值分配保护", "C": "省钱", "D": "检索"},
            "correct_answer": "B", "explanation": "按价值分级保护",
            "tags": ["数据分类", "资产管理"], "source": "test"
        },
        {
            "id": "w-test-d2-002", "domain": 2, "difficulty": 4, "question_type": "single",
            "stem": "SSD 最有效的销毁方式？",
            "options": {"A": "格式化", "B": "覆写", "C": "物理粉碎", "D": "删分区"},
            "correct_answer": "C", "explanation": "SSD 磨损均衡导致覆写不可靠",
            "tags": ["数据销毁", "SSD"], "source": "test"
        },
        # 域3
        {
            "id": "w-test-d3-001", "domain": 3, "difficulty": 3, "question_type": "single",
            "stem": "Bell-LaPadula 保护什么？",
            "options": {"A": "完整性", "B": "可用性", "C": "机密性", "D": "不可否认"},
            "correct_answer": "C", "explanation": "Bell-LaPadula 是机密性模型",
            "tags": ["安全模型", "Bell-LaPadula"], "source": "test"
        },
        {
            "id": "w-test-d3-002", "domain": 3, "difficulty": 3, "question_type": "single",
            "stem": "Biba 模型保护什么？",
            "options": {"A": "机密性", "B": "完整性", "C": "可用性", "D": "审计"},
            "correct_answer": "B", "explanation": "Biba 是完整性模型",
            "tags": ["安全模型", "Biba"], "source": "test"
        },
        # 域4
        {
            "id": "w-test-d4-001", "domain": 4, "difficulty": 3, "question_type": "single",
            "stem": "SYN 洪水攻击利用什么？",
            "options": {"A": "ICMP", "B": "TCP三次握手", "C": "UDP", "D": "DNS"},
            "correct_answer": "B", "explanation": "利用 TCP 三次握手漏洞",
            "tags": ["网络攻击", "SYN洪水"], "source": "test"
        },
        # 域5-8 各1题
        {
            "id": "w-test-d5-001", "domain": 5, "difficulty": 2, "question_type": "single",
            "stem": "RBAC 适合什么场景？",
            "options": {"A": "研究环境", "B": "职责明确的大型组织", "C": "军事", "D": "临时团队"},
            "correct_answer": "B", "explanation": "RBAC 基于角色",
            "tags": ["RBAC", "访问控制"], "source": "test"
        },
        {
            "id": "w-test-d6-001", "domain": 6, "difficulty": 3, "question_type": "single",
            "stem": "漏洞评估与渗透测试的区别？",
            "options": {"A": "工具vs手动", "B": "识别vs验证利用", "C": "内部vs外包", "D": "没区别"},
            "correct_answer": "B", "explanation": "漏洞评估只识别",
            "tags": ["漏洞评估", "渗透测试"], "source": "test"
        },
        {
            "id": "w-test-d7-001", "domain": 7, "difficulty": 2, "question_type": "single",
            "stem": "SIEM 的主要功能？",
            "options": {"A": "防入侵", "B": "集中收集关联分析日志", "C": "加密流量", "D": "身份管理"},
            "correct_answer": "B", "explanation": "SIEM 是安全信息与事件管理",
            "tags": ["SIEM", "安全运营"], "source": "test"
        },
        {
            "id": "w-test-d8-001", "domain": 8, "difficulty": 3, "question_type": "single",
            "stem": "SQL 注入最有效的防御？",
            "options": {"A": "过滤单引号", "B": "存储过程", "C": "参数化查询", "D": "限权限"},
            "correct_answer": "C", "explanation": "参数化查询将结构与数据分离",
            "tags": ["SQL注入", "安全编码"], "source": "test"
        },
    ]
    result = import_questions(session, sample_qs, source="test")
    assert result["added"] == 12

    # 初始化预设学习路径
    init_preset_paths(session)

    # 添加知识图谱边
    add_edge(session, "安全基础", "CIA三元组", 1, "prerequisite", 1.0)
    add_edge(session, "CIA三元组", "风险管理", 1, "prerequisite", 0.8)
    add_edge(session, "风险管理", "风险处置", 1, "part_of", 1.0)
    add_edge(session, "安全模型", "Bell-LaPadula", 3, "part_of", 1.0)
    add_edge(session, "安全模型", "Biba", 3, "related", 0.9)

    session.commit()
    session.close()

    # Monkey-patch: 让 web.api 使用这个临时 DB
    import cissp_trainer.database as db_module
    orig_engine = db_module._engine
    orig_session = db_module._SessionLocal

    db_module._engine = engine
    db_module._SessionLocal = SessionLocal
    db_module.DEFAULT_DB_PATH = db_path

    yield db_path

    # 恢复
    db_module._engine = orig_engine
    db_module._SessionLocal = orig_session
    engine.dispose()


@pytest.fixture
def client(test_db):
    """返回 TestClient"""
    with TestClient(app) as c:
        yield c


# ============================================================
# 1. Health & Basics
# ============================================================

class TestHealth:
    def test_health_endpoint(self, client):
        """健康检查接口"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_api_health_endpoint(self, client):
        """API 健康检查"""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["domains"] == 8

    def test_page_dashboard(self, client):
        """仪表盘页面可访问"""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "CISSP" in resp.text

    def test_page_questions(self, client):
        """题库页面可访问"""
        resp = client.get("/questions")
        assert resp.status_code == 200

    def test_page_exam_list(self, client):
        """模考列表页可访问"""
        resp = client.get("/exam")
        assert resp.status_code == 200

    def test_page_learning_path(self, client):
        """学习路径页可访问"""
        resp = client.get("/learning-path")
        assert resp.status_code == 200

    def test_page_knowledge_graph(self, client):
        """知识图谱页可访问"""
        resp = client.get("/knowledge-graph")
        assert resp.status_code == 200


# ============================================================
# 2. 题库 API
# ============================================================

class TestQuestionAPI:
    def test_list_questions_default(self, client):
        """默认列出题目"""
        resp = client.get("/api/questions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 12
        assert len(data["items"]) == 12
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_questions_pagination(self, client):
        """分页"""
        resp = client.get("/api/questions?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 12
        assert len(data["items"]) == 5
        assert data["total_pages"] == 3

    def test_list_questions_filter_domain(self, client):
        """按领域筛选"""
        resp = client.get("/api/questions?domain=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        for item in data["items"]:
            assert item["domain"] == 1

    def test_list_questions_filter_difficulty(self, client):
        """按难度筛选"""
        resp = client.get("/api/questions?difficulty=3")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["difficulty"] == 3

    def test_list_questions_keyword(self, client):
        """关键词搜索"""
        resp = client.get("/api/questions?keyword=CIA")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_get_question_detail(self, client):
        """题目详情"""
        resp = client.get("/api/questions/1")
        assert resp.status_code == 200
        data = resp.json()
        assert "stem" in data
        assert "options" in data
        assert "correct_answer" in data

    def test_get_question_not_found(self, client):
        """题目不存在"""
        resp = client.get("/api/questions/9999")
        assert resp.status_code == 404

    def test_pick_questions_random(self, client):
        """随机抽题"""
        resp = client.get("/api/questions/random/pick?count=5&mode=random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5
        assert len(data["questions"]) == 5

    def test_pick_questions_by_domain(self, client):
        """按领域抽题"""
        resp = client.get("/api/questions/random/pick?count=2&domain=1&mode=random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        for q in data["questions"]:
            assert q["domain"] == 1

    def test_answer_question_correct(self, client):
        """答题 - 正确"""
        resp = client.post("/api/questions/answer", json={
            "question_id": 1,
            "user_answer": "A",
            "time_spent_sec": 10
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_correct"] is True
        assert data["correct_answer"] == "A"

    def test_answer_question_wrong(self, client):
        """答题 - 错误"""
        resp = client.post("/api/questions/answer", json={
            "question_id": 1,
            "user_answer": "B",
            "time_spent_sec": 5
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_correct"] is False

    def test_answer_question_invalid(self, client):
        """答题 - 题目不存在"""
        resp = client.post("/api/questions/answer", json={
            "question_id": 9999,
            "user_answer": "A"
        })
        assert resp.status_code == 400


# ============================================================
# 3. 学习进度 API
# ============================================================

class TestStatsAPI:
    def test_overall_stats(self, client):
        """总体统计"""
        # 先答几题产生记录
        client.post("/api/questions/answer", json={"question_id": 1, "user_answer": "A"})
        client.post("/api/questions/answer", json={"question_id": 2, "user_answer": "B"})

        resp = client.get("/api/stats/overall")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_questions"] == 12
        assert data["total_study_records"] == 2
        assert data["total_correct"] == 2
        assert "overall_accuracy" in data
        assert "today_studied" in data
        assert "due_review_count" in data
        assert "total_knowledge_points" in data

    def test_domain_stats(self, client):
        """各领域统计"""
        resp = client.get("/api/stats/domains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 8
        for d in data:
            assert "domain" in d
            assert "domain_name" in d
            assert "question_count" in d
            assert "accuracy" in d

    def test_weak_kps(self, client):
        """薄弱知识点"""
        # 先答几题产生掌握度数据
        for qid in [1, 2, 3, 4, 5]:
            client.post("/api/questions/answer", json={"question_id": qid, "user_answer": "A"})

        resp = client.get("/api/stats/weak-kps?top_n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # 因为 review_count < 2 可能返回空，但状态码必须 200

    def test_progress_curve(self, client):
        """学习进度曲线"""
        resp = client.get("/api/stats/progress-curve?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7
        for d in data:
            assert "date" in d
            assert "total" in d
            assert "correct" in d
            assert "accuracy" in d


# ============================================================
# 4. 模考 API
# ============================================================

class TestExamAPI:
    def test_create_exam(self, client):
        """创建考试"""
        resp = client.post("/api/exams", json={
            "title": "测试考试",
            "question_count": 5,
            "duration_minutes": 30,
            "difficulty_min": 1,
            "difficulty_max": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_questions"] == 5
        assert "exam_id" in data

    def test_create_exam_domain_filter(self, client):
        """创建考试 - 指定领域"""
        resp = client.post("/api/exams", json={
            "title": "域1专项",
            "question_count": 3,
            "duration_minutes": 10,
            "domain_filter": [1],
            "difficulty_min": 1,
            "difficulty_max": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_questions"] == 3

    def test_start_exam(self, client):
        """开始考试"""
        # 创建
        create_resp = client.post("/api/exams", json={
            "title": "测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        exam_id = create_resp.json()["exam_id"]

        # 开始
        resp = client.post(f"/api/exams/{exam_id}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "in_progress"

    def test_get_current_question(self, client):
        """获取当前题目"""
        create_resp = client.post("/api/exams", json={
            "title": "测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        exam_id = create_resp.json()["exam_id"]
        client.post(f"/api/exams/{exam_id}/start")

        resp = client.get(f"/api/exams/{exam_id}/current")
        assert resp.status_code == 200
        data = resp.json()
        assert "index" in data
        assert "stem" in data
        assert "options" in data
        assert data["index"] == 1

    def test_answer_and_submit(self, client):
        """答题 + 交卷完整流程"""
        create_resp = client.post("/api/exams", json={
            "title": "完整流程测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        exam_id = create_resp.json()["exam_id"]
        client.post(f"/api/exams/{exam_id}/start")

        # 答 3 题
        for i in range(3):
            current = client.get(f"/api/exams/{exam_id}/current").json()
            qid = current["question_id"]
            # 获取正确答案
            q_detail = client.get(f"/api/questions/{qid}").json()
            correct = q_detail["correct_answer"]
            resp = client.post(f"/api/exams/{exam_id}/answer", json={
                "user_answer": correct,
                "time_spent_sec": 5
            })
            assert resp.status_code == 200

        # 交卷
        submit_resp = client.post(f"/api/exams/{exam_id}/submit")
        assert submit_resp.status_code == 200
        result = submit_resp.json()
        assert result["success"] is True
        assert "score" in result
        assert "passed" in result
        assert result["total_questions"] == 3
        assert "domain_scores" in result

    def test_exam_history(self, client):
        """考试历史"""
        # 创建并完成一场考试
        cr = client.post("/api/exams", json={
            "title": "历史测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        eid = cr.json()["exam_id"]
        client.post(f"/api/exams/{eid}/start")
        for i in range(3):
            cur = client.get(f"/api/exams/{eid}/current").json()
            qd = client.get(f"/api/questions/{cur['question_id']}").json()
            client.post(f"/api/exams/{eid}/answer", json={"user_answer": qd["correct_answer"], "time_spent_sec": 1})
        client.post(f"/api/exams/{eid}/submit")

        resp = client.get("/api/exams/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_exam_result(self, client):
        """考试结果详情"""
        cr = client.post("/api/exams", json={
            "title": "结果测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        eid = cr.json()["exam_id"]
        client.post(f"/api/exams/{eid}/start")
        for i in range(3):
            cur = client.get(f"/api/exams/{eid}/current").json()
            qd = client.get(f"/api/questions/{cur['question_id']}").json()
            client.post(f"/api/exams/{eid}/answer", json={"user_answer": qd["correct_answer"], "time_spent_sec": 1})
        client.post(f"/api/exams/{eid}/submit")

        resp = client.get(f"/api/exams/{eid}/result")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "wrong_questions" in data
        assert "domain_scores" in data

    def test_score_curve(self, client):
        """成绩曲线"""
        resp = client.get("/api/exams/score-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_pause_resume(self, client):
        """暂停/继续考试"""
        cr = client.post("/api/exams", json={
            "title": "暂停测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        eid = cr.json()["exam_id"]
        client.post(f"/api/exams/{eid}/start")

        # 暂停
        pause_resp = client.post(f"/api/exams/{eid}/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["status"] == "paused"

        # 继续
        resume_resp = client.post(f"/api/exams/{eid}/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json()["status"] == "in_progress"

    def test_goto_question(self, client):
        """跳转题目"""
        cr = client.post("/api/exams", json={
            "title": "跳转测试", "question_count": 3, "duration_minutes": 10,
            "difficulty_min": 1, "difficulty_max": 5,
        })
        eid = cr.json()["exam_id"]
        client.post(f"/api/exams/{eid}/start")

        resp = client.post(f"/api/exams/{eid}/goto?index=2")
        assert resp.status_code == 200
        assert resp.json()["current_index"] == 2


# ============================================================
# 5. 知识图谱 API
# ============================================================

class TestKnowledgeGraphAPI:
    def test_build_domain_graph(self, client):
        """构建领域图谱"""
        resp = client.get("/api/kg/domains/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == 1
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0

    def test_prerequisites(self, client):
        """查询前置依赖"""
        resp = client.get("/api/kg/prerequisites?kp_name=CIA三元组&domain=1&depth=3")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # CIA三元组有前置"安全基础"
        names = [p["name"] for p in data]
        assert "安全基础" in names

    def test_successors(self, client):
        """查询后继"""
        resp = client.get("/api/kg/successors?kp_name=安全基础&domain=1&depth=2")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [p["name"] for p in data]
        assert "CIA三元组" in names

    def test_suggest_next(self, client):
        """推荐下一步学习"""
        resp = client.get("/api/kg/suggest-next?kp_name=安全基础&domain=1&top_n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_weak_propagation(self, client):
        """薄弱点传播分析"""
        resp = client.get("/api/kg/weak-propagation?kp_name=安全基础&domain=1&max_depth=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "source_kp" in data
        assert "total_affected" in data
        assert isinstance(data["affected_kps"], list)


# ============================================================
# 6. 学习路径 API
# ============================================================

class TestLearningPathAPI:
    def test_list_paths(self, client):
        """列出所有路径"""
        resp = client.get("/api/paths")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # beginner/advanced/sprint
        slugs = [p["slug"] for p in data]
        assert "beginner" in slugs
        assert "advanced" in slugs
        assert "sprint" in slugs

    def test_recommend_path(self, client):
        """推荐路径"""
        resp = client.get("/api/paths/recommend")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_slug" in data
        assert "reason" in data
        assert "user_stats" in data

    def test_start_path(self, client):
        """开始学习路径"""
        resp = client.post("/api/paths/start", json={"slug": "beginner"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "path" in data
        assert "progress" in data

    def test_start_duplicate_path(self, client):
        """重复开始同一路径"""
        client.post("/api/paths/start", json={"slug": "beginner"})
        resp = client.post("/api/paths/start", json={"slug": "beginner"})
        # 应返回错误（已在进行中）
        assert resp.status_code == 400

    def test_current_path(self, client):
        """当前路径状态"""
        client.post("/api/paths/start", json={"slug": "beginner"})
        resp = client.get("/api/paths/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_path"] is True
        assert "path" in data
        assert "progress" in data

    def test_daily_plan(self, client):
        """每日学习计划"""
        client.post("/api/paths/start", json={"slug": "beginner"})
        resp = client.get("/api/paths/daily-plan")
        assert resp.status_code == 200
        data = resp.json()
        assert "has_path" in data
        assert data["has_path"] is True
        assert "daily_question_target" in data
        assert "recommended_mode" in data

    def test_adjust_path(self, client):
        """动态调整路径"""
        client.post("/api/paths/start", json={"slug": "beginner"})
        resp = client.post("/api/paths/adjust")
        assert resp.status_code == 200
        data = resp.json()
        assert "adjusted" in data
        # 可能因数据不足未调整，但结构必须正确
