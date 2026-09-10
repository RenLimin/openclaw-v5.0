"""
知识图谱模块测试
"""

import pytest
from cissp_trainer.knowledge_graph import (
    add_edge, remove_edge, get_prerequisites, get_successors,
    get_related, suggest_next_kps, analyze_weak_propagation,
    build_domain_graph, to_mermaid, to_text_tree, mastery_heatmap,
    import_preset_graph,
)
from cissp_trainer.models import KnowledgePoint, KnowledgeEdge


class TestEdgeManagement:
    """边管理测试"""

    def test_add_prerequisite_edge(self, db_session):
        """可以添加前置依赖边"""
        edge = add_edge(db_session, "A", "B", domain=1, edge_type="prerequisite")
        assert edge is not None
        assert edge.edge_type == "prerequisite"

        # 验证知识点被创建
        src = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        tgt = db_session.query(KnowledgePoint).filter_by(name="B", domain=1).first()
        assert src is not None
        assert tgt is not None

    def test_add_duplicate_edge(self, db_session):
        """重复添加边不会重复创建"""
        add_edge(db_session, "A", "B", domain=1)
        add_edge(db_session, "A", "B", domain=1)

        edges = db_session.query(KnowledgeEdge).all()
        assert len(edges) == 1

    def test_add_related_edge(self, db_session):
        """可以添加相关边"""
        edge = add_edge(db_session, "A", "B", domain=1, edge_type="related")
        assert edge.edge_type == "related"

    def test_remove_edge(self, db_session):
        """可以删除边"""
        add_edge(db_session, "A", "B", domain=1)
        result = remove_edge(db_session, "A", "B", domain=1)
        assert result is True
        assert db_session.query(KnowledgeEdge).count() == 0

    def test_remove_nonexistent_edge(self, db_session):
        """删除不存在的边返回 False"""
        result = remove_edge(db_session, "X", "Y", domain=1)
        assert result is False


class TestPrerequisiteQueries:
    """前置/后继查询测试"""

    def setup_chain(self, session):
        """建立 A → B → C → D 的前置链"""
        add_edge(session, "A", "B", 1)   # A 是 B 的前置
        add_edge(session, "B", "C", 1)   # B 是 C 的前置
        add_edge(session, "C", "D", 1)   # C 是 D 的前置

    def test_get_prerequisites_depth1(self, db_session):
        """查询直接前置（深度 1）"""
        self.setup_chain(db_session)
        prereqs = get_prerequisites(db_session, "D", domain=1, depth=1)
        assert len(prereqs) == 1
        assert prereqs[0]["name"] == "C"

    def test_get_prerequisites_depth3(self, db_session):
        """查询所有前置（深度 3）"""
        self.setup_chain(db_session)
        prereqs = get_prerequisites(db_session, "D", domain=1, depth=3)
        names = {p["name"] for p in prereqs}
        assert "A" in names
        assert "B" in names
        assert "C" in names
        assert len(prereqs) == 3

    def test_get_successors(self, db_session):
        """查询后继知识点"""
        self.setup_chain(db_session)
        succ = get_successors(db_session, "A", domain=1, depth=3)
        names = {s["name"] for s in succ}
        assert "B" in names
        assert "C" in names
        assert "D" in names

    def test_get_prerequisites_nonexistent(self, db_session):
        """查询不存在的知识点返回空"""
        result = get_prerequisites(db_session, "不存在的点", domain=1)
        assert result == []

    def test_get_related(self, db_session):
        """查询相关知识点"""
        add_edge(db_session, "A", "B", 1, edge_type="related")
        add_edge(db_session, "A", "C", 1, edge_type="related")
        related = get_related(db_session, "A", domain=1)
        names = {r["name"] for r in related}
        assert "B" in names
        assert "C" in names


class TestLearningSuggestions:
    """学习建议测试"""

    def test_suggest_next_when_prereqs_mastered(self, db_session):
        """前置掌握后，推荐后继"""
        # A → B → C
        add_edge(db_session, "A", "B", 1)
        add_edge(db_session, "B", "C", 1)

        # 设置 A 掌握度很高
        kp_a = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        kp_a.mastery_level = 0.9
        kp_a.review_count = 5

        # 设置 B 掌握度低
        kp_b = db_session.query(KnowledgePoint).filter_by(name="B", domain=1).first()
        kp_b.mastery_level = 0.2
        kp_b.review_count = 2

        db_session.flush()

        # 学完 A，推荐学 B
        suggestions = suggest_next_kps(db_session, "A", domain=1)
        assert len(suggestions) > 0
        names = {s["name"] for s in suggestions}
        assert "B" in names

    def test_suggest_next_when_not_mastered(self, db_session):
        """前置未掌握时，不推荐后继"""
        add_edge(db_session, "A", "B", 1)

        # A 掌握度低
        kp_a = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        kp_a.mastery_level = 0.3
        kp_a.review_count = 5

        kp_b = db_session.query(KnowledgePoint).filter_by(name="B", domain=1).first()
        kp_b.mastery_level = 0.1

        db_session.flush()

        suggestions = suggest_next_kps(db_session, "A", domain=1)
        # B 的前置只有 A，但 A 没掌握到 0.7，所以不会推荐
        assert len(suggestions) == 0


class TestWeakPropagation:
    """薄弱点传播分析测试"""

    def test_propagation_chain(self, db_session):
        """链式传播：A 弱 → B、C、D 都受影响"""
        # A → B → C → D
        add_edge(db_session, "A", "B", 1)
        add_edge(db_session, "B", "C", 1)
        add_edge(db_session, "C", "D", 1)

        # A 掌握度很低
        kp_a = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        kp_a.mastery_level = 0.1
        db_session.flush()

        result = analyze_weak_propagation(db_session, "A", domain=1)
        assert result.total_affected == 3  # B, C, D
        names = {k["name"] for k in result.affected_kps}
        assert "B" in names
        assert "C" in names
        assert "D" in names

    def test_propagation_distance_decay(self, db_session):
        """距离越远影响越小"""
        add_edge(db_session, "A", "B", 1, weight=1.0)
        add_edge(db_session, "B", "C", 1, weight=1.0)

        kp_a = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        kp_a.mastery_level = 0.0
        db_session.flush()

        result = analyze_weak_propagation(db_session, "A", domain=1)
        kp_map = {k["name"]: k for k in result.affected_kps}

        # B 的影响应该大于 C
        assert kp_map["B"]["impact"] > kp_map["C"]["impact"]

    def test_propagation_no_successors(self, db_session):
        """没有后继的点传播结果为空"""
        add_edge(db_session, "A", "B", 1)  # B 是后继
        # A 是起点，B 没有后继
        kp_b = db_session.query(KnowledgePoint).filter_by(name="B", domain=1).first()
        kp_b.mastery_level = 0.2
        db_session.flush()

        result = analyze_weak_propagation(db_session, "B", domain=1)
        assert result.total_affected == 0


class TestGraphVisualization:
    """图谱可视化测试"""

    def test_build_domain_graph(self, db_session):
        """构建领域图谱"""
        add_edge(db_session, "A", "B", 1)
        add_edge(db_session, "B", "C", 1)
        add_edge(db_session, "A", "C", 1, edge_type="related")

        graph = build_domain_graph(db_session, 1)
        assert graph["domain"] == 1
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 3

    def test_to_mermaid(self, db_session):
        """生成 Mermaid 格式"""
        add_edge(db_session, "A", "B", 1)
        mermaid = to_mermaid(db_session, 1)
        assert "flowchart" in mermaid
        assert "classDef" in mermaid

    def test_to_text_tree(self, db_session):
        """生成文本树"""
        add_edge(db_session, "A", "B", 1)
        tree = to_text_tree(db_session, 1)
        assert isinstance(tree, str)
        assert "A" in tree or "B" in tree

    def test_mastery_heatmap(self, db_session):
        """生成热力图"""
        add_edge(db_session, "A", "B", 1)
        heatmap = mastery_heatmap(db_session)
        assert "热力图" in heatmap
        assert "域1" in heatmap


class TestImportPresetGraph:
    """批量导入测试"""

    def test_import_preset_graph(self, db_session):
        """可以批量导入预设图谱"""
        preset = [
            {
                "domain": 1,
                "edges": [
                    {"source": "A", "target": "B", "type": "prerequisite"},
                    {"source": "B", "target": "C", "type": "prerequisite"},
                    {"source": "A", "target": "C", "type": "related", "weight": 0.7},
                ]
            },
            {
                "domain": 2,
                "edges": [
                    {"source": "X", "target": "Y", "type": "prerequisite"},
                ]
            }
        ]
        result = import_preset_graph(db_session, preset)
        assert result["added"] == 4
        assert result["errors"] == []

    def test_import_invalid_domain(self, db_session):
        """无效领域会报错但不中断"""
        preset = [
            {"domain": 99, "edges": [{"source": "A", "target": "B"}]}
        ]
        result = import_preset_graph(db_session, preset)
        assert len(result["errors"]) > 0
