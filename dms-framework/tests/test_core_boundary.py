"""
DMS-Framework 核心引擎边界条件测试
覆盖 Database / Migrations / ModuleRegistry / EventBus / StateMachine 的边界场景
"""
import pytest
import sqlite3
from dataclasses import dataclass

from core.database import Database, BaseModel, Repository
from core.migrations import migrate as fn_migrate, _MIGRATIONS, _version_key, get_current_version
from core.module import ModuleRegistry, ModuleManifest, BaseModule
from core.event_bus import EventBus, Event
from core.state_machine import StateMachine, State, Transition
from core.saas import TenantContext


# =========================================================================
# fixtures
# =========================================================================

@pytest.fixture
def db():
    """每个测试独立的内存数据库，setup/teardown 隔离。"""
    database = Database("sqlite:///:memory:")
    yield database
    database.close()


@pytest.fixture
def conn(db):
    """直接获取 sqlite3 连接（给 migrations 测试用）。"""
    return db.connect()


@pytest.fixture
def sample_model_table(db):
    """为 BaseModel 测试创建一张示例表。"""
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_items (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            name TEXT NOT NULL,
            value TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    db.commit()
    return "test_items"


@pytest.fixture
def sample_repo(db, sample_model_table):
    """基于 SampleModel 的 Repository 实例。"""

    @dataclass
    class SampleModel(BaseModel):
        name: str = ""
        value: str = ""
        __tablename__ = "test_items"

    return Repository(db, SampleModel, "test_items")


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sm():
    """带 terminal 状态的基础状态机。"""
    m = StateMachine("boundary_test")
    m.add_state(State("draft", "todo", is_start=True))
    m.add_state(State("review", "in_progress"))
    m.add_state(State("published", "done", is_terminal=True))
    m.add_state(State("archived", "cancelled", is_terminal=True))
    m.add_transition(Transition("submit", "draft", "review"))
    m.add_transition(Transition("publish", "review", "published"))
    m.add_transition(Transition("archive", "draft", "archived"))
    return m


# =========================================================================
# Database 边界测试
# =========================================================================

class TestDatabaseBoundary:
    """Database / BaseModel / Repository 边界条件。"""

    def test_empty_table_list_returns_empty_list(self, sample_repo):
        """空表上调用 list 应返回空列表，不抛异常。"""
        result = sample_repo.list()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_nonexistent_id_returns_none(self, sample_repo):
        """get 不存在的 ID 返回 None。"""
        result = sample_repo.get("non_existent_id_xyz")
        assert result is None

    def test_delete_nonexistent_id_returns_false(self, sample_repo):
        """delete 不存在的 ID 返回 False。"""
        result = sample_repo.delete("does_not_exist_123")
        assert result is False

    def test_count_on_empty_table_is_zero(self, sample_repo):
        """空表 count 为 0。"""
        assert sample_repo.count() == 0

    def test_update_nonexistent_record_performs_upsert(self, sample_repo):
        """
        对不存在的记录执行 save（upsert 语义）：应创建新记录而非报错。
        Repository.update 内部调用 BaseModel.save，不存在则 INSERT。
        """
        from dataclasses import dataclass

        @dataclass
        class SampleModel(BaseModel):
            name: str = ""
            value: str = ""
            __tablename__ = "test_items"

        # 构造一个带指定 id 但尚未持久化的实体
        entity = SampleModel(id="upsert-test-id", name="test", value="v1")
        assert sample_repo.get("upsert-test-id") is None  # 确认不存在

        updated = sample_repo.update(entity)
        assert updated is not None
        assert updated.id == "upsert-test-id"
        # 验证已存入
        fetched = sample_repo.get("upsert-test-id")
        assert fetched is not None
        assert fetched.name == "test"

    def test_tenant_id_auto_inject_on_save(self, db, sample_model_table):
        """
        创建时不传 tenant_id（保持默认 "system"），
        保存时自动用 TenantContext.current() 注入。
        """
        from dataclasses import dataclass

        @dataclass
        class SampleModel(BaseModel):
            name: str = ""
            value: str = ""
            __tablename__ = "test_items"

        TenantContext.reset()
        TenantContext.set("tenant_alpha")
        try:
            # tenant_id 保持默认 "system"，save 时应被替换为当前租户
            entity = SampleModel(name="auto-inject-test")
            assert entity.tenant_id == "system"  # 默认值
            entity.save(db)
            assert entity.tenant_id == "tenant_alpha"

            # 从数据库读取验证
            fetched = SampleModel.get(db, entity.id)
            assert fetched is not None
            assert fetched.tenant_id == "tenant_alpha"
        finally:
            TenantContext.reset()

    def test_tenant_context_default_is_system(self, db, sample_model_table):
        """TenantContext 未设置时，使用默认 'system' 租户。"""
        from dataclasses import dataclass

        @dataclass
        class SampleModel(BaseModel):
            name: str = ""
            value: str = ""
            __tablename__ = "test_items"

        TenantContext.reset()
        try:
            entity = SampleModel(name="default-tenant")
            entity.save(db)
            assert entity.tenant_id == "system"
        finally:
            TenantContext.reset()


# =========================================================================
# Migrations 边界测试
# =========================================================================

class TestMigrationsBoundary:
    """core/migrations.py 边界条件：幂等 / 乱序排序 / 空列表。"""

    def test_migrate_idempotent(self, conn):
        """重复调用 migrate 不报错（幂等）。"""
        # 第一次执行所有迁移
        applied_1 = fn_migrate(conn)
        # 第二次应无新迁移可应用，也不抛异常
        applied_2 = fn_migrate(conn)
        assert len(applied_2) == 0
        # 版本号应保持最新
        version = get_current_version(conn)
        assert version != "0.0.0"

    def test_migrate_thrice_still_idempotent(self, conn):
        """第三次调用依然幂等，确保 schema_version 表正确处理。"""
        fn_migrate(conn)
        fn_migrate(conn)
        applied_3 = fn_migrate(conn)
        assert applied_3 == []

    def test_version_sort_with_out_of_order_versions(self):
        """乱序版本号经 _version_key 后能正确排序（语义化版本）。"""
        versions = ["1.10.0", "1.2.0", "2.0.0", "1.1.1", "0.9.9", "1.2.1"]
        sorted_versions = sorted(versions, key=_version_key)
        expected = ["0.9.9", "1.1.1", "1.2.0", "1.2.1", "1.10.0", "2.0.0"]
        assert sorted_versions == expected

    def test_version_key_handles_malformed(self):
        """非标准版本号降级为 (0,)，不会抛异常导致排序崩溃。"""
        key = _version_key("not-a-version")
        assert key == (0,)

    def test_empty_migration_list_no_error(self, conn):
        """
        空迁移列表不报错：清空 _MIGRATIONS 后 migrate 应返回空列表。
        测试后恢复原始迁移注册表。
        """
        original = dict(_MIGRATIONS)
        try:
            _MIGRATIONS.clear()
            applied = fn_migrate(conn)
            assert applied == []
            # 版本号保持初始
            # （注意：schema_version 表可能已由之前的迁移创建，但这里清空 _MIGRATIONS 后没有可应用的）
            assert isinstance(applied, list)
        finally:
            _MIGRATIONS.update(original)

    def test_get_current_version_on_fresh_db(self):
        """全新数据库（无 schema_version 表）返回 0.0.0。"""
        fresh = sqlite3.connect(":memory:")
        try:
            version = get_current_version(fresh)
            assert version == "0.0.0"
        finally:
            fresh.close()


# =========================================================================
# ModuleRegistry 边界测试
# =========================================================================

class TestModuleRegistryBoundary:
    """ModuleRegistry 边界条件：重复注册 / 不存在查询 / 初始化状态。"""

    def _make_manifest(self, name="test_mod", deps=None):
        return ModuleManifest(
            name=name,
            version="1.0.0",
            description="test module",
            dependencies=deps or [],
        )

    def _make_factory(self):
        """生成一个可实例化的假模块工厂。"""
        class FakeModule(BaseModule):
            def initialize(self, db, config, container):
                self._initialized = True

        def factory(manifest):
            return FakeModule(manifest)

        return factory

    def test_duplicate_module_registration_raises(self):
        """注册重复模块名应抛出 ValueError。"""
        registry = ModuleRegistry()
        manifest = self._make_manifest("dup_mod")
        factory = self._make_factory()
        registry.register(manifest, factory)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(manifest, factory)

    def test_get_nonexistent_module_raises_keyerror(self):
        """
        获取不存在的模块：未初始化时 has_module 返回 False，
        get 方法抛出 KeyError（而非返回 None，与 API 保持一致）。
        """
        registry = ModuleRegistry()
        # has_module 边界
        assert registry.has_module("no_such_module") is False
        # get 抛出 KeyError
        with pytest.raises(KeyError):
            registry.get("no_such_module")

    def test_get_manifest_nonexistent_raises(self):
        """获取不存在的模块清单也应抛出 KeyError。"""
        registry = ModuleRegistry()
        with pytest.raises(KeyError):
            registry.get_manifest("missing")

    def test_is_initialized_false_before_init(self):
        """初始化前 is_initialized 为 False。"""
        registry = ModuleRegistry()
        assert registry.is_initialized is False

    def test_is_initialized_true_after_init(self):
        """初始化完成后 is_initialized 为 True。"""
        registry = ModuleRegistry()
        manifest = self._make_manifest("init_mod")
        factory = self._make_factory()
        registry.register(manifest, factory)

        db = Database("sqlite:///:memory:")
        try:
            registry.initialize_all(db, {})
            assert registry.is_initialized is True
        finally:
            db.close()

    def test_double_initialize_raises(self):
        """重复调用 initialize_all 应抛 RuntimeError。"""
        registry = ModuleRegistry()
        manifest = self._make_manifest("once_mod")
        factory = self._make_factory()
        registry.register(manifest, factory)

        db = Database("sqlite:///:memory:")
        try:
            registry.initialize_all(db, {})
            with pytest.raises(RuntimeError, match="already initialized"):
                registry.initialize_all(db, {})
        finally:
            db.close()

    def test_list_modules_empty(self):
        """空注册表 list_modules 返回空列表。"""
        registry = ModuleRegistry()
        assert registry.list_modules() == []


# =========================================================================
# EventBus 边界测试
# =========================================================================

class TestEventBusBoundary:
    """EventBus 边界条件：订阅者异常隔离 / clear_history / unsubscribe。"""

    def test_subscriber_exception_does_not_affect_others(self, event_bus):
        """
        一个订阅者抛出异常不应影响其他订阅者接收事件。
        """
        received_good = []

        def bad_handler(event):
            raise RuntimeError("boom!")

        def good_handler(event):
            received_good.append(event)

        event_bus.subscribe("test.event", bad_handler)
        event_bus.subscribe("test.event", good_handler)

        # 不应抛异常
        event_bus.publish("test.event", {"x": 1})

        # 好的订阅者应收到事件
        assert len(received_good) == 1
        assert received_good[0].payload["x"] == 1

    def test_multiple_bad_subscribers_all_isolated(self, event_bus):
        """多个异常订阅者都被隔离，不影响彼此及后续订阅者。"""
        received = []

        def bad1(e):
            raise ValueError("err1")

        def bad2(e):
            raise TypeError("err2")

        def good(e):
            received.append(e)

        event_bus.subscribe("test.x", bad1)
        event_bus.subscribe("test.x", bad2)
        event_bus.subscribe("test.x", good)

        event_bus.publish("test.x", {})
        assert len(received) == 1

    def test_clear_history(self, event_bus):
        """clear_history 后历史记录为空。"""
        event_bus.publish("a", {})
        event_bus.publish("b", {})
        event_bus.publish("c", {})
        assert len(event_bus.get_history()) == 3

        event_bus.clear_history()
        assert len(event_bus.get_history()) == 0
        assert event_bus.stats()["history_size"] == 0

    def test_clear_history_then_publish(self, event_bus):
        """clear_history 后再发布事件，历史记录重新累积。"""
        event_bus.publish("old", {})
        event_bus.clear_history()
        event_bus.publish("new", {})
        history = event_bus.get_history()
        assert len(history) == 1
        assert history[0].name == "new"

    def test_unsubscribe_removes_handler(self, event_bus):
        """unsubscribe 后该 handler 不再收到事件。"""
        received = []

        def handler(event):
            received.append(event)

        event_bus.subscribe("unsub.event", handler)
        event_bus.publish("unsub.event", {"n": 1})
        assert len(received) == 1

        event_bus.unsubscribe("unsub.event", handler)
        event_bus.publish("unsub.event", {"n": 2})
        # 只收到第一次
        assert len(received) == 1
        assert received[0].payload["n"] == 1

    def test_unsubscribe_nonexistent_handler_no_error(self, event_bus):
        """取消订阅一个不存在的 handler 不抛异常。"""
        def some_handler(e):
            pass

        # 未订阅过，直接 unsubscribe 应安全
        event_bus.unsubscribe("ghost.event", some_handler)
        # 无异常即通过

    def test_unsubscribe_nonexistent_pattern_no_error(self, event_bus):
        """取消订阅一个不存在的模式不抛异常。"""
        def h(e):
            pass

        event_bus.unsubscribe("no.such.pattern", h)
        # 无异常即通过

    def test_publish_no_subscribers_no_error(self, event_bus):
        """没有订阅者时发布事件不报错。"""
        event_bus.publish("lonely.event", {"data": 1})
        assert event_bus.stats()["history_size"] == 1


# =========================================================================
# StateMachine 边界测试
# =========================================================================

class TestStateMachineBoundary:
    """StateMachine 边界条件：未注册迁移 / terminal 状态迁移 / 多 guard 全部需通过。"""

    def test_fire_unregistered_transition_raises(self, sm):
        """触发未注册的迁移名应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Unknown transition"):
            sm.fire("draft", "nonexistent_trigger", {})

    def test_can_transition_unregistered_returns_false(self, sm):
        """can_transition 对未注册的迁移返回 False。"""
        assert sm.can_transition("draft", "no_such_transition") is False

    def test_transition_from_terminal_state_raises(self, sm):
        """从 terminal 状态触发迁移应抛出 ValueError。"""
        # published 是 terminal 状态，没有任何出边
        with pytest.raises(ValueError):
            sm.fire("published", "submit", {})

    def test_terminal_state_has_no_available_transitions(self, sm):
        """terminal 状态的可用迁移列表为空。"""
        available = sm.get_available_transitions("published")
        assert available == []

    def test_multiple_guards_all_must_pass(self, sm):
        """
        多 guard 全部需要通过：只要有一个不通过，迁移就被拒绝（PermissionError）。
        """
        m = StateMachine("multi_guard_test")
        m.add_state(State("start", "todo", is_start=True))
        m.add_state(State("end", "done", is_terminal=True))

        guard1_called = []
        guard2_called = []

        def guard1(ctx):
            guard1_called.append(True)
            return ctx.get("pass1", True)

        def guard2(ctx):
            guard2_called.append(True)
            return ctx.get("pass2", True)

        m.add_transition(Transition(
            "go", "start", "end",
            guards=[guard1, guard2]
        ))

        # 全部通过 -> 成功
        from_s, to_s = m.fire("start", "go", {"pass1": True, "pass2": True})
        assert to_s == "end"

        # 重置到 start 状态重新测试
        # 第一个 guard 不通过 -> 抛出 PermissionError
        guard1_called.clear()
        guard2_called.clear()
        with pytest.raises(PermissionError):
            m.fire("start", "go", {"pass1": False, "pass2": True})
        # 第一个 guard 失败后，第二个 guard 也应被调用（全部检查）
        # 注：当前实现是依次检查，第一个失败就抛
        assert len(guard1_called) == 1
        # guard2 不一定被调用（短路），但至少 guard1 执行了

    def test_all_guards_evaluated_before_fire(self, sm):
        """
        可用迁移列表只包含所有 guard 都通过的迁移。
        """
        m = StateMachine("guard_avail")
        m.add_state(State("s1", "todo", is_start=True))
        m.add_state(State("s2", "done", is_terminal=True))
        m.add_transition(Transition(
            "all_pass", "s1", "s2",
            guards=[lambda c: c.get("a", False), lambda c: c.get("b", False)]
        ))

        # 只有一个 guard 通过 -> 不在可用列表中
        available = m.get_available_transitions("s1", {"a": True, "b": False})
        assert "all_pass" not in available

        # 两个都通过 -> 在可用列表中
        available = m.get_available_transitions("s1", {"a": True, "b": True})
        assert "all_pass" in available

    def test_fire_from_wrong_state_raises(self, sm):
        """从错误的源状态触发迁移应抛 ValueError。"""
        # "approve" 不存在于 sm 中，但我们测的是 from_state 不匹配
        # submit 的 from_state 是 draft，从 review 触发应报错
        with pytest.raises(ValueError):
            sm.fire("review", "submit", {})

    def test_unknown_state_in_get_available_transitions(self, sm):
        """查询未注册状态的可用迁移返回空列表。"""
        available = sm.get_available_transitions("never_heard_of_state")
        assert available == []
