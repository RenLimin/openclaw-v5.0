#!/usr/bin/env python3
"""
DMS-Framework 统一命令行入口（Phase 2 模块系统版）

通过 ModuleRegistry 加载所有模块，按拓扑排序初始化，
从模块 manifest 聚合 CLI 命令，执行时注入模块实例到 context。

用法: python dms.py <module> <command> [options]
"""
from __future__ import annotations

import sys
import os
import argparse
import logging
from typing import Any

# 确保本目录在 import 路径首位
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("dms")


# ===========================================================================
# FrameworkRegistry — 带状态机引擎 + 事件总线的模块注册中心
# ===========================================================================

class FrameworkRegistry:
    """ModuleRegistry 的功能扩展封装，附加状态机引擎和事件总线。

    模块通过 container._state_machine_engine 注册状态机，
    通过 container._event_bus 发布/订阅事件。

    实际的注册/查询/生命周期逻辑委托给内部 ModuleRegistry 实例。
    """

    def __init__(self) -> None:
        from core.module import ModuleRegistry
        self._registry = ModuleRegistry()
        self._state_machine_engine: Any = None
        self._event_bus: Any = None

    # -- 委托到 ModuleRegistry --------------------------------------------

    def register(self, manifest: Any, factory: Any) -> None:
        self._registry.register(manifest, factory)

    def get(self, name: str) -> Any:
        return self._registry.get(name)

    def get_manifest(self, name: str) -> Any:
        return self._registry.get_manifest(name)

    def list_modules(self) -> list[Any]:
        return self._registry.list_modules()

    def has_module(self, name: str) -> bool:
        return self._registry.has_module(name)

    def resolve_dependencies(self) -> list[str]:
        return self._registry.resolve_dependencies()

    def initialize_all(self, db: Any, config: dict[str, Any]) -> None:
        # 把 self 作为 container 传入，这样模块可以访问 _state_machine_engine 和 _event_bus
        order = self._registry.resolve_dependencies()

        # Phase 1: initialize
        for name in order:
            manifest = self._registry._manifests[name]
            factory = self._registry._factories[name]
            instance = factory(manifest)
            instance.initialize(db, config.get(name, {}), self)
            instance._initialized = True
            self._registry._instances[name] = instance

        # Phase 2: on_ready
        for name in order:
            self._registry._instances[name].on_ready(self)

        self._registry._initialized = True

    @property
    def is_initialized(self) -> bool:
        return self._registry._initialized


# ===========================================================================
# 模块注册与初始化
# ===========================================================================

def build_registry() -> FrameworkRegistry:
    """创建 FrameworkRegistry 并注册所有业务模块。"""
    from core.state_machine import StateMachineEngine
    from core.event_bus import EventBus

    from modules.project import manifest as project_manifest, _factory as project_factory
    from modules.milestone import manifest as milestone_manifest, _factory as milestone_factory
    from modules.deliverable import manifest as deliverable_manifest, _factory as deliverable_factory
    from modules.risk import manifest as risk_manifest, _factory as risk_factory
    from modules.raci import manifest as raci_manifest, _factory as raci_factory
    from modules.quality import manifest as quality_manifest, _factory as quality_factory
    from modules.resource import manifest as resource_manifest, _factory as resource_factory
    from modules.budget import manifest as budget_manifest, _factory as budget_factory
    from modules.communication import manifest as communication_manifest, _factory as communication_factory
    from modules.contract import manifest as contract_manifest, _factory as contract_factory
    from modules.sla import manifest as sla_manifest, _factory as sla_factory
    from modules.task import manifest as task_manifest, _factory as task_factory
    from modules.issue import manifest as issue_manifest, _factory as issue_factory
    from modules.decision import manifest as decision_manifest, _factory as decision_factory

    from core.workflow_scheme import WorkflowSchemeEngine

    registry = FrameworkRegistry()
    registry._state_machine_engine = StateMachineEngine()
    registry._event_bus = EventBus()
    registry._workflow_engine = WorkflowSchemeEngine()

    registry.register(project_manifest, project_factory)
    registry.register(milestone_manifest, milestone_factory)
    registry.register(deliverable_manifest, deliverable_factory)
    registry.register(risk_manifest, risk_factory)
    registry.register(raci_manifest, raci_factory)
    registry.register(quality_manifest, quality_factory)
    registry.register(resource_manifest, resource_factory)
    registry.register(budget_manifest, budget_factory)
    registry.register(communication_manifest, communication_factory)
    registry.register(contract_manifest, contract_factory)
    registry.register(sla_manifest, sla_factory)
    registry.register(task_manifest, task_factory)
    registry.register(issue_manifest, issue_factory)
    registry.register(decision_manifest, decision_factory)

    return registry


def ensure_initialized(registry: FrameworkRegistry, db: Any, config: dict[str, Any]) -> None:
    """确保模块已初始化（惰性初始化，幂等）。"""
    if not registry.is_initialized:
        registry.initialize_all(db, config)


# ===========================================================================
# CLI 构建
# ===========================================================================

def _parse_command_name(name: str) -> tuple[str, str]:
    """将 "project create" 解析为 (module_name, subcommand)。"""
    parts = name.split(None, 1)
    if len(parts) != 2:
        raise ValueError(f"无效的命令名格式: {name!r} (期望 'module command')")
    return parts[0], parts[1]


def _add_arg_kwargs(subparser: Any, arg_def: dict[str, Any]) -> None:
    """根据 CommandDef.arguments 中的定义，向子解析器添加参数。

    支持的键: flags (list) / name (str) 二选一，其余作为 add_argument 的 kwargs。
    """
    kwargs = {k: v for k, v in arg_def.items() if k not in ("flags", "name")}
    if "flags" in arg_def:
        subparser.add_argument(*arg_def["flags"], **kwargs)
    elif "name" in arg_def:
        subparser.add_argument(arg_def["name"], **kwargs)
    else:
        raise ValueError(f"参数定义必须包含 'flags' 或 'name': {arg_def}")


def build_parser(registry: FrameworkRegistry) -> argparse.ArgumentParser:
    """根据已注册模块的 manifest.commands 构建 argparse。"""
    parser = argparse.ArgumentParser(
        prog="dms",
        description="DMS-Framework: L3 通用交付管理框架"
    )
    parser.add_argument("--db", default="delivery.db", help="数据库路径")
    parser.add_argument("--tenant", default="system", help="租户 ID")
    parser.add_argument(
        "--format", choices=["table", "json", "csv"],
        default="table", help="输出格式"
    )

    subparsers = parser.add_subparsers(dest="_top_level", help="功能模块")

    # ── 全局命令（非模块命令） ──

    # init
    subparsers.add_parser("init", help="初始化框架 + 数据库")

    # module
    module_parser = subparsers.add_parser("module", help="模块管理")
    module_sub = module_parser.add_subparsers(dest="_action")
    module_sub.add_parser("list", help="列出已注册模块")

    # schema
    schema_parser = subparsers.add_parser("schema", help="Schema 版本控制")
    schema_sub = schema_parser.add_subparsers(dest="_action")
    schema_sub.add_parser("diff", help="查看待执行迁移")
    schema_sub.add_parser("migrate", help="执行迁移")

    # event
    event_parser = subparsers.add_parser("event", help="事件总线")
    event_sub = event_parser.add_subparsers(dest="_action")
    event_sub.add_parser("stats", help="查看事件总线统计")

    # workflow
    workflow_parser = subparsers.add_parser("workflow", help="Work flow scheme management")
    workflow_sub = workflow_parser.add_subparsers(dest="_action")
    workflow_sub.add_parser("list", help="List all schemes")
    set_p = workflow_sub.add_parser("set", help="Switch scheme")
    set_p.add_argument("--name", required=True, help="scheme name")
    res_p = workflow_sub.add_parser("resolve", help="Resolve entity type mapping")
    res_p.add_argument("--entity-type", required=True, help="entity type")
    res_p.add_argument("--project-id", help="project id (optional)")

    # ── 从 manifest 聚合模块命令 ──
    # 按模块名分组：module_name -> list[CommandDef]
    module_commands: dict[str, list[Any]] = {}
    for manifest in registry.list_modules():
        for cmd in manifest.commands:
            mod_name, _sub = _parse_command_name(cmd.name)
            module_commands.setdefault(mod_name, []).append(cmd)

    for mod_name, commands in sorted(module_commands.items()):
        mod_parser = subparsers.add_parser(
            mod_name,
            help=registry.get_manifest(mod_name).description or mod_name,
        )
        mod_sub = mod_parser.add_subparsers(dest="_action")
        mod_sub.required = True

        for cmd in commands:
            _mod, sub_name = _parse_command_name(cmd.name)
            cmd_parser = mod_sub.add_parser(sub_name, help=cmd.help)
            # 把 handler 和所属模块名存起来，用于分发
            cmd_parser.set_defaults(
                _handler=cmd.handler,
                _module_name=mod_name,
                _command_name=cmd.name,
            )
            for arg_def in cmd.arguments:
                _add_arg_kwargs(cmd_parser, arg_def)

    return parser


# ===========================================================================
# 命令分发
# ===========================================================================

def dispatch(args: argparse.Namespace, registry: FrameworkRegistry,
             db: Any, config: dict[str, Any]) -> None:
    """根据解析结果分发命令。"""
    top = args._top_level

    if top is None:
        # 没给子命令
        return

    # ── 全局命令 ──
    if top == "init":
        _cmd_init(db, args)
        return

    if top == "module":
        _cmd_module(registry, db, args)
        return

    if top == "schema":
        _cmd_schema(db, args)
        return

    if top == "event":
        _cmd_event(registry, db, args, config)
        return

    if top == "workflow":
        _cmd_workflow(registry, db, args, config)
        return

    # ── 模块命令 ──
    if registry.has_module(top):
        # 确保模块已初始化
        ensure_initialized(registry, db, config)

        handler = getattr(args, "_handler", None)
        module_name = getattr(args, "_module_name", None)
        if not handler or not module_name:
            print(f"❌ 模块 '{top}' 下的命令未找到 handler")
            return

        try:
            module_instance = registry.get(module_name)
        except KeyError:
            print(f"❌ 模块未注册或未初始化: {module_name}")
            return

        ctx = {
            "module": module_instance,
            "container": registry,
        }

        try:
            handler(args, ctx)
        except Exception as e:
            logger.exception("命令执行异常")
            print(f"❌ 命令执行失败: {e}")
        return

    print(f"❌ 未知命令: {top}")


# ===========================================================================
# 全局命令实现
# ===========================================================================

def _cmd_init(db: Any, args: argparse.Namespace) -> None:
    """初始化框架 + 数据库。"""
    from core.migrations import migrate
    conn = db.connect()
    applied = migrate(conn)
    if applied:
        print(f"✅ 数据库初始化完成，已应用迁移: {', '.join(applied)}")
    else:
        print("✅ 数据库已是最新版本")
    print(f"   数据库: {args.db}")
    print(f"   租户: {args.tenant}")


def _cmd_module(registry: FrameworkRegistry, db: Any, args: argparse.Namespace) -> None:
    if args._action == "list":
        modules = registry.list_modules()
        if not modules:
            print("暂无已注册模块")
            return
        print(f"{'模块':<15} {'版本':<10} {'描述'}")
        print("-" * 70)
        for m in modules:
            print(f"{m.name:<15} {m.version:<10} {m.description}")


def _cmd_schema(db: Any, args: argparse.Namespace) -> None:
    from core.migrations import migrate, diff
    conn = db.connect()
    if args._action == "diff":
        pending = diff(conn)
        if pending:
            print(f"待执行迁移: {', '.join(pending)}")
        else:
            print("✅ 无待执行迁移")
    elif args._action == "migrate":
        applied = migrate(conn)
        if applied:
            print(f"✅ 已应用迁移: {', '.join(applied)}")
        else:
            print("✅ 已是最新版本")


def _cmd_event(registry: FrameworkRegistry, db: Any,
               args: argparse.Namespace, config: dict[str, Any]) -> None:
    """事件总线命令（触发模块初始化以收集订阅）。"""
    # 初始化模块以注册订阅
    ensure_initialized(registry, db, config)

    if args._action == "stats":
        bus = registry._event_bus
        if not bus:
            print("❌ 事件总线未初始化")
            return
        stats = bus.stats()
        print("📊 事件总线统计")
        print(f"   订阅模式数: {stats['patterns']}")
        print(f"   订阅者总数: {stats['subscribers']}")
        print(f"   历史事件数: {stats['history_size']}")




def _cmd_workflow(registry, db, args, config):
    """workflow command: manage work flow schemes"""
    engine = getattr(registry, '_workflow_engine', None)
    if not engine:
        print("WorkflowSchemeEngine not initialized")
        return
    action = getattr(args, '_action', None)
    if action == "list":
        active = engine.get_active()
        print(f"Active scheme: {active}")
        for s in engine.list_schemes():
            marker = " <-- current" if s.name == active else ""
            print(f"  {s.name:15s} {s.description}{marker}")
            for et, mn in s.mappings.items():
                print(f"    {et:20s} -> {mn}")
    elif action == "set":
        try:
            engine.set_active(args.name)
            print(f"Switched to: {args.name}")
        except KeyError as e:
            print(f"Error: {e}")
    elif action == "resolve":
        try:
            mn = engine.get_machine_name(args.entity_type, getattr(args, "project_id", None))
            print(f"  {args.entity_type} -> {mn}")
        except KeyError as e:
            print(f"Error: {e}")
    else:
        print("Actions: list / set / resolve")
# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    from core.database import Database
    from core.saas import TenantContext

    # 先构建 registry（仅注册，不初始化）
    registry = build_registry()

    # 构建 parser（用 manifest 中的命令定义）
    parser = build_parser(registry)
    args = parser.parse_args()

    if not args._top_level:
        parser.print_help()
        return

    # 设置租户上下文
    TenantContext.set(args.tenant)

    # 数据库连接
    db = Database(f"sqlite:///{args.db}")

    # 配置（预留，按模块名传空 dict 即可）
    config: dict[str, Any] = {}

    # 分发
    dispatch(args, registry, db, config)


if __name__ == "__main__":
    main()

def _cmd_workflow_list(args, ctx):
    engine = ctx["registry"]._workflow_engine
    active = engine.get_active()
    print(f"当前激活方案: {active}")
    print()
    for s in engine.list_schemes():
        marker = " ← 当前" if s.name == active else ""
        print(f"  {s.name:15s} {s.description}{marker}")
        for et, mn in s.mappings.items():
            print(f"    {et:20s} → {mn}")

def _cmd_workflow_set(args, ctx):
    engine = ctx["registry"]._workflow_engine
    try:
        engine.set_active(args.name)
        print(f"✅ 已切换至方案: {args.name}")
    except KeyError as e:
        print(f"❌ {e}")

def _cmd_workflow_resolve(args, ctx):
    engine = ctx["registry"]._workflow_engine
    try:
        mn = engine.get_machine_name(args.entity_type, getattr(args, "project_id", None))
        print(f"  {args.entity_type} → {mn}")
    except KeyError as e:
        print(f"❌ {e}")


