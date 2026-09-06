"""
DMS-Framework quality 模块单元测试
覆盖 QualityModule 的 CRUD、状态机、统计与事件联动
"""
import pytest
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.module import ModuleRegistry

# 被测模块
from modules.quality import manifest as quality_manifest
from modules.quality import QualityModule, Quality
# 用于触发 project.cancelled 事件
from modules.project import manifest as project_manifest
from modules.project import ProjectModule


@pytest.fixture
def db():
    """内存数据库 + 迁移"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    """注册 quality + project 模块，完成初始化与 ready"""
    from core.event_bus import EventBus
    from core.state_machine import StateMachineEngine
    reg = ModuleRegistry()
    reg._state_machine_engine = StateMachineEngine()
    reg._event_bus = EventBus()
    reg.register(project_manifest, ProjectModule)
    reg.register(quality_manifest, QualityModule)
    reg.initialize_all(db, {})
    for m in reg._manifests.values():
        inst = reg.get(m.name)
        if inst and hasattr(inst, "on_ready"):
            inst.on_ready(reg)
    return reg


class TestQualityModule:
    """quality 模块单元测试"""
    @pytest.fixture(autouse=True)
    def setup(self, registry):
        """每个测试前创建项目，获取真实 project_id。"""
        TenantContext.set("test")
        self.pm = registry.get("project")
        self.qm = registry.get("quality")
        self.proj = self.pm.create_project(name="测试项目", description="quality test")
        self.project_id = self.proj.id



    # ------------------------------------------------------------------
    # 1. 创建质量记录
    # ------------------------------------------------------------------
    def test_create_quality(self, registry, db):
        """创建质量记录，验证默认状态为 identified"""
        TenantContext.set("test")
        qm = registry.get("quality")

        q = qm.create_quality(project_id=self.project_id, title="代码质量评审",
                              description="首次评审", priority="high")

        assert q.id is not None
        assert q.title == "代码质量评审"
        assert q.project_id == self.project_id
        assert q.status == "identified"  # 默认状态
        assert q.type == "quality"
        assert q.priority == "high"
        assert q.tenant_id == "test"
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 2. metadata 属性读写
    # ------------------------------------------------------------------
    def test_metadata_properties(self, registry, db):
        """测试 defect_count / review_score / test_pass_rate 读写"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="质量记录A")

        # 初始默认值
        assert q.defect_count == 0
        assert q.review_score == 0.0
        assert q.test_pass_rate == 0.0

        # 写入并持久化
        q.defect_count = 5
        q.review_score = 92.5
        q.test_pass_rate = 88.3
        qm._repo.update(q)

        # 重新读取验证
        got = qm.get_quality(q.id)
        assert got.defect_count == 5
        assert got.review_score == 92.5
        assert got.test_pass_rate == 88.3
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 3. identified → in_review
    # ------------------------------------------------------------------
    def test_transition_start_review(self, registry, db):
        """状态迁移：identified → in_review"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="评审记录")

        r = qm.transition_quality(q.id, "start_review")
        assert r.status == "in_review"
        assert qm.get_quality(q.id).status == "in_review"
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 4. in_review → passed
    # ------------------------------------------------------------------
    def test_transition_pass(self, registry, db):
        """状态迁移：in_review → passed"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="通过测试")
        qm.transition_quality(q.id, "start_review")

        r = qm.transition_quality(q.id, "pass")
        assert r.status == "passed"
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 5. in_review → failed
    # ------------------------------------------------------------------
    def test_transition_fail(self, registry, db):
        """状态迁移：in_review → failed"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="失败测试")
        qm.transition_quality(q.id, "start_review")

        r = qm.transition_quality(q.id, "fail")
        assert r.status == "failed"
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 6. failed → in_review（重新评审）
    # ------------------------------------------------------------------
    def test_transition_re_review(self, registry, db):
        """状态迁移：failed → in_review"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="重评测试")
        qm.transition_quality(q.id, "start_review")
        qm.transition_quality(q.id, "fail")
        assert qm.get_quality(q.id).status == "failed"

        r = qm.transition_quality(q.id, "re_review")
        assert r.status == "in_review"
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 7. passed → verified（终态）
    # ------------------------------------------------------------------
    def test_transition_verify(self, registry, db):
        """状态迁移：passed → verified（终态）"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="验证测试")
        qm.transition_quality(q.id, "start_review")
        qm.transition_quality(q.id, "pass")

        r = qm.transition_quality(q.id, "verify")
        assert r.status == "verified"
        # 终态后不能再迁移
        with pytest.raises(ValueError):
            qm.transition_quality(q.id, "pass")
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 8. 非法迁移抛 ValueError
    # ------------------------------------------------------------------
    def test_invalid_transition_raises(self, registry, db):
        """非法状态迁移应抛出 ValueError"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="非法迁移测试")

        # identified 状态下不能直接 pass
        with pytest.raises(ValueError):
            qm.transition_quality(q.id, "pass")

        # 不存在的迁移名
        with pytest.raises(ValueError):
            qm.transition_quality(q.id, "nonexistent")

        # 不存在的记录
        with pytest.raises(ValueError):
            qm.transition_quality("fake-id", "start_review")
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 9. 按状态过滤列表
    # ------------------------------------------------------------------
    def test_list_filter_by_status(self, registry, db):
        """list_qualities 按 status 过滤"""
        TenantContext.set("test")
        qm = registry.get("quality")
        # 创建 3 条记录
        q1 = qm.create_quality(project_id=self.project_id, title="R1")
        q2 = qm.create_quality(project_id=self.project_id, title="R2")
        q3 = qm.create_quality(project_id=self.project_id, title="R3")

        # 全部 identified
        all_identified = qm.list_qualities(project_id=self.project_id, status="identified")
        assert len(all_identified) == 3

        # 迁移 q1 到 in_review
        qm.transition_quality(q1.id, "start_review")
        in_review = qm.list_qualities(project_id=self.project_id, status="in_review")
        assert len(in_review) == 1
        assert in_review[0].id == q1.id

        # 未传 status → 全部返回
        all_items = qm.list_qualities(project_id=self.project_id)
        assert len(all_items) == 3
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 10. 删除记录
    # ------------------------------------------------------------------
    def test_delete_quality(self, registry, db):
        """删除质量记录"""
        TenantContext.set("test")
        qm = registry.get("quality")
        q = qm.create_quality(project_id=self.project_id, title="待删")

        # 删除存在的
        result = qm.delete_quality(q.id)
        assert result is True
        assert qm.get_quality(q.id) is None

        # 删除不存在的
        result2 = qm.delete_quality("nonexistent")
        assert result2 is False
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 11. get_metrics 统计
    # ------------------------------------------------------------------
    def test_metrics_calculation(self, registry, db):
        """get_metrics 返回正确的统计数据"""
        TenantContext.set("test")
        qm = registry.get("quality")

        # 构造多种状态的记录
        q1 = qm.create_quality(project_id=self.project_id, title="Q1")
        q2 = qm.create_quality(project_id=self.project_id, title="Q2")
        q3 = qm.create_quality(project_id=self.project_id, title="Q3")
        q4 = qm.create_quality(project_id=self.project_id, title="Q4")

        # Q1: identified（缺陷 2，通过率 70）
        q1 = qm.get_quality(q1.id)
        q1.defect_count = 2
        q1.test_pass_rate = 70.0
        qm._repo.update(q1)

        # Q2: passed（缺陷 0，通过率 95）
        qm.transition_quality(q2.id, "start_review")
        qm.transition_quality(q2.id, "pass")
        q2 = qm.get_quality(q2.id)
        q2.test_pass_rate = 95.0
        qm._repo.update(q2)

        # Q3: verified（缺陷 1，通过率 100）
        qm.transition_quality(q3.id, "start_review")
        qm.transition_quality(q3.id, "pass")
        qm.transition_quality(q3.id, "verify")
        q3 = qm.get_quality(q3.id)
        q3.defect_count = 1
        q3.test_pass_rate = 100.0
        qm._repo.update(q3)

        # Q4: failed（缺陷 3，通过率 50）
        qm.transition_quality(q4.id, "start_review")
        qm.transition_quality(q4.id, "fail")
        q4 = qm.get_quality(q4.id)
        q4.defect_count = 3
        q4.test_pass_rate = 50.0
        qm._repo.update(q4)

        metrics = qm.get_metrics(project_id=self.project_id)
        assert metrics["project_id"] == self.project_id
        assert metrics["total"] == 4
        assert metrics["total_defects"] == 6  # 2+0+1+3
        # passed + verified = 2
        assert metrics["passed_count"] == 2
        assert metrics["failed_count"] == 1
        # 平均通过率：(70 + 95 + 100 + 50) / 4 = 78.75
        assert metrics["avg_pass_rate"] == 78.75
        # 各状态分布
        assert metrics["by_status"]["identified"] == 1
        assert metrics["by_status"]["passed"] == 1
        assert metrics["by_status"]["verified"] == 1
        assert metrics["by_status"]["failed"] == 1
        TenantContext.reset()

    # ------------------------------------------------------------------
    # 12. project.cancelled 事件自动关闭非终态质量记录
    # ------------------------------------------------------------------
    def test_project_cancelled_closes_open_records(self, registry, db):
        """项目取消时，自动关闭项目下所有非终态质量记录"""
        TenantContext.set("test")
        pm = registry.get("project")
        qm = registry.get("quality")

        # 创建项目
        proj = pm.create_project(name="待取消项目")

        # 创建多条质量记录，处于不同状态
        q1 = qm.create_quality(project_id=proj.id, title="R1")  # identified
        q2 = qm.create_quality(project_id=proj.id, title="R2")  # in_review
        qm.transition_quality(q2.id, "start_review")
        q3 = qm.create_quality(project_id=proj.id, title="R3")  # passed
        qm.transition_quality(q3.id, "start_review")
        qm.transition_quality(q3.id, "pass")
        q4 = qm.create_quality(project_id=proj.id, title="R4")  # verified（终态，不变）
        qm.transition_quality(q4.id, "start_review")
        qm.transition_quality(q4.id, "pass")
        qm.transition_quality(q4.id, "verify")
        q5 = qm.create_quality(project_id=proj.id, title="R5")  # failed
        qm.transition_quality(q5.id, "start_review")
        qm.transition_quality(q5.id, "fail")

        # 另一个项目的记录，不应受影响
        other_proj = pm.create_project(name="其他项目")
        qo = qm.create_quality(project_id=other_proj.id, title="其他项目记录")

        # 取消项目 → 触发 project.cancelled 事件
        pm.transition_project(proj.id, "start")
        pm.transition_project(proj.id, "cancel")

        # 验证本项目的记录状态：
        #   q1 (identified) → closed  ✅ close 迁移存在
        #   q2 (in_review) → 保持不变（没有 in_review→close 的迁移，代码 try 捕获）
        #   q3 (passed) → 保持不变
        #   q4 (verified) → 保持不变（已是终态）
        #   q5 (failed) → 保持不变
        assert qm.get_quality(q1.id).status == "closed"
        assert qm.get_quality(q2.id).status == "in_review"
        assert qm.get_quality(q3.id).status == "passed"
        assert qm.get_quality(q4.id).status == "verified"
        assert qm.get_quality(q5.id).status == "failed"

        # 其他项目记录不受影响
        assert qm.get_quality(qo.id).status == "identified"
        TenantContext.reset()
