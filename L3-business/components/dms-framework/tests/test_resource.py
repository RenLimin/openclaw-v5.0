"""
DMS-Framework resource 模块单元测试
覆盖 Resource 模型、状态机迁移、CRUD、过滤、统计视图、事件联动
"""
import pytest
import tempfile
import os
import sys
sys.path.insert(0, '.')

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.module import ModuleRegistry
from core.event_bus import EventBus

from modules.project import manifest as project_manifest
from modules.project import ProjectModule, _factory as project_factory
from modules.resource import manifest as resource_manifest
from modules.resource import ResourceModule, Resource, _factory as resource_factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """临时 SQLite 数据库 + 迁移"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    """注册 project + resource 模块，附带事件总线"""
    reg = ModuleRegistry()
    reg._event_bus = EventBus()
    reg.register(project_manifest, project_factory)
    reg.register(resource_manifest, resource_factory)
    reg.initialize_all(db, {})
    return reg


@pytest.fixture
def setup_project(registry):
    """创建一个测试项目，返回 (project_module, resource_module, project_id)"""
    TenantContext.set("test_tenant")
    pm = registry.get("project")
    rm = registry.get("resource")
    proj = pm.create_project(name="资源测试项目")
    yield pm, rm, proj.id
    TenantContext.reset()


# ---------------------------------------------------------------------------
# TestResourceModule
# ---------------------------------------------------------------------------

class TestResourceModule:
    """resource 模块单元测试集"""

    # 1. 创建资源
    def test_create(self, setup_project):
        """创建资源：验证默认状态为 requested，类型为 resource"""
        _, rm, pid = setup_project
        r = rm.create_resource(project_id=pid, title="服务器资源",
                               description="10台云服务器")
        assert r.id is not None
        assert r.title == "服务器资源"
        assert r.project_id == pid
        assert r.status == "requested"  # 默认起始状态
        assert r.type == "resource"
        assert r.tenant_id == "test_tenant"

        # 通过 get_resource 回读校验持久化
        got = rm.get_resource(r.id)
        assert got is not None
        assert got.title == "服务器资源"
        assert got.status == "requested"

    # 2. metadata 字段读写
    def test_metadata(self, setup_project):
        """metadata 字段：resource_type/capacity/allocated/cost_per_unit 读写持久化"""
        _, rm, pid = setup_project
        r = rm.create_resource(project_id=pid, title="CPU资源")

        # 写入 metadata（通过属性 setter）
        r.resource_type = "cpu"
        r.capacity = 100.0
        r.allocated = 40.0
        r.cost_per_unit = 2.5
        rm._repo.update(r)

        # 回读校验
        got = rm.get_resource(r.id)
        assert got.resource_type == "cpu"
        assert got.capacity == 100.0
        assert got.allocated == 40.0
        assert got.cost_per_unit == 2.5

    # 3. requested → allocated 迁移
    def test_transition_allocate(self, setup_project):
        """状态迁移：requested → allocated，验证 resource.allocated 事件"""
        _, rm, pid = setup_project
        bus = rm._container._event_bus
        before = len(bus._history)

        r = rm.create_resource(project_id=pid, title="存储资源")
        assert r.status == "requested"

        r2 = rm.transition_resource(r.id, "allocate")
        assert r2.status == "allocated"

        # 回读确认持久化
        got = rm.get_resource(r.id)
        assert got.status == "allocated"

        # 验证事件发布：resource.status_changed + resource.allocated
        events = [e.name for e in bus._history[before:]]
        assert "resource.created" in events
        assert "resource.status_changed" in events
        assert "resource.allocated" in events

    # 4. allocated → released 迁移（终态）
    def test_transition_release(self, setup_project):
        """状态迁移：allocated → released（终态），验证 resource.released 事件"""
        _, rm, pid = setup_project
        bus = rm._container._event_bus
        before = len(bus._history)

        r = rm.create_resource(project_id=pid, title="带宽资源")
        rm.transition_resource(r.id, "allocate")
        assert rm.get_resource(r.id).status == "allocated"

        r2 = rm.transition_resource(r.id, "release")
        assert r2.status == "released"

        # released 是终态
        got = rm.get_resource(r.id)
        assert got.status == "released"

        # 验证 resource.released 事件
        events = [e.name for e in bus._history[before:]]
        assert "resource.released" in events

    # 5. allocated → reallocated → allocated
    def test_transition_reallocate(self, setup_project):
        """重新分配：allocated → reallocated → allocated 循环"""
        _, rm, pid = setup_project
        r = rm.create_resource(project_id=pid, title="GPU资源")

        # 首次分配
        r = rm.transition_resource(r.id, "allocate")
        assert r.status == "allocated"

        # 重新分配
        r = rm.transition_resource(r.id, "reallocate")
        assert r.status == "reallocated"

        # 确认分配
        r = rm.transition_resource(r.id, "confirm")
        assert r.status == "allocated"

        # 可以再次 reallocate → confirm
        r = rm.transition_resource(r.id, "reallocate")
        assert r.status == "reallocated"
        r = rm.transition_resource(r.id, "confirm")
        assert r.status == "allocated"

    # 6. 非法迁移抛 ValueError
    def test_invalid_transition(self, setup_project):
        """非法状态迁移抛出 ValueError"""
        _, rm, pid = setup_project
        r = rm.create_resource(project_id=pid, title="测试资源")

        # requested 不能直接 release
        with pytest.raises(ValueError):
            rm.transition_resource(r.id, "release")

        # requested 不能直接 reallocate
        with pytest.raises(ValueError):
            rm.transition_resource(r.id, "reallocate")

        # 不存在的迁移名
        with pytest.raises(ValueError):
            rm.transition_resource(r.id, "foo_bar")

        # 不存在的资源 ID
        with pytest.raises(ValueError):
            rm.transition_resource("non-existent-id", "allocate")

        # 终态 released 之后不能再迁移
        rm.transition_resource(r.id, "allocate")
        rm.transition_resource(r.id, "release")
        with pytest.raises(ValueError):
            rm.transition_resource(r.id, "allocate")

    # 7. 列表过滤：按状态 / 按项目
    def test_list_filter(self, setup_project):
        """列表过滤：按状态和项目过滤资源"""
        _, rm, pid = setup_project

        # 创建 3 个资源，分别处于不同状态
        r1 = rm.create_resource(project_id=pid, title="资源A")  # requested
        r2 = rm.create_resource(project_id=pid, title="资源B")  # → allocated
        r3 = rm.create_resource(project_id=pid, title="资源C")  # → cancelled
        rm.transition_resource(r2.id, "allocate")
        rm.transition_resource(r3.id, "cancel")

        # 全量列表
        all_items = rm.list_resources(project_id=pid)
        assert len(all_items) == 3

        # 按状态过滤
        requested = rm.list_resources(project_id=pid, status="requested")
        assert len(requested) == 1
        assert requested[0].id == r1.id

        allocated = rm.list_resources(project_id=pid, status="allocated")
        assert len(allocated) == 1
        assert allocated[0].id == r2.id

        cancelled = rm.list_resources(project_id=pid, status="cancelled")
        assert len(cancelled) == 1
        assert cancelled[0].id == r3.id

        # 跨项目隔离：另一个项目看不到这些资源
        pm = rm._container.get("project")
        proj2 = pm.create_project(name="另一个项目")
        other = rm.list_resources(project_id=proj2.id)
        assert len(other) == 0

    # 8. 删除资源
    def test_delete(self, setup_project):
        """删除资源：存在返回 True，不存在返回 False"""
        _, rm, pid = setup_project
        r = rm.create_resource(project_id=pid, title="待删资源")
        assert rm.get_resource(r.id) is not None

        result = rm.delete_resource(r.id)
        assert result is True
        assert rm.get_resource(r.id) is None

        # 重复删除返回 False
        result2 = rm.delete_resource(r.id)
        assert result2 is False

        # 不存在的 ID 返回 False
        assert rm.delete_resource("no-such-id") is False

    # 9. 资源分配概览
    def test_allocation_overview(self, setup_project):
        """allocation_overview：统计视图 — 数量、容量、利用率、成本"""
        _, rm, pid = setup_project

        # 资源 1：CPU，容量 100，已分配 50，单价 2
        r1 = rm.create_resource(project_id=pid, title="CPU池")
        r1.resource_type = "cpu"
        r1.capacity = 100.0
        r1.allocated = 50.0
        r1.cost_per_unit = 2.0
        rm._repo.update(r1)
        rm.transition_resource(r1.id, "allocate")

        # 资源 2：内存，容量 200，已分配 30，单价 1
        r2 = rm.create_resource(project_id=pid, title="内存池")
        r2.resource_type = "memory"
        r2.capacity = 200.0
        r2.allocated = 30.0
        r2.cost_per_unit = 1.0
        rm._repo.update(r2)
        # 保持 requested 状态

        ov = rm.allocation_overview(pid)
        assert ov["project_id"] == pid
        assert ov["total"] == 2
        # 状态分布
        assert ov["by_status"]["allocated"] == 1
        assert ov["by_status"]["requested"] == 1
        # 总容量 = 100 + 200
        assert ov["total_capacity"] == 300.0
        # 总分配 = 50 + 30
        assert ov["total_allocated"] == 80.0
        # 利用率 = 80 / 300 * 100 ≈ 26.67
        assert ov["utilization_rate"] == pytest.approx(26.67, 0.01)
        # 预估成本 = 50*2 + 30*1 = 130
        assert ov["estimated_cost"] == 130.0

    # 10. project.cancelled 事件触发资源释放
    def test_project_cancelled_releases(self, setup_project):
        """项目取消事件联动：project.cancelled → 释放已分配资源"""
        pm, rm, pid = setup_project

        # 创建 3 个资源：2 个 allocated，1 个 requested
        r1 = rm.create_resource(project_id=pid, title="资源-已分配1")
        r2 = rm.create_resource(project_id=pid, title="资源-已分配2")
        r3 = rm.create_resource(project_id=pid, title="资源-待分配")
        rm.transition_resource(r1.id, "allocate")
        rm.transition_resource(r2.id, "allocate")

        assert rm.get_resource(r1.id).status == "allocated"
        assert rm.get_resource(r2.id).status == "allocated"
        assert rm.get_resource(r3.id).status == "requested"

        # 触发项目取消（发布 project.cancelled 事件）
        pm.transition_project(pid, "start")  # 先进入 in_progress
        pm.transition_project(pid, "cancel")

        # 验证：已分配资源被自动释放
        assert rm.get_resource(r1.id).status == "released"
        assert rm.get_resource(r2.id).status == "released"
        # 非 allocated 状态的资源保持不变
        assert rm.get_resource(r3.id).status == "requested"
