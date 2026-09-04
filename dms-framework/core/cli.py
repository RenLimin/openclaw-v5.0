"""
core/cli.py — CLI 框架
统一命令行入口：dms <module> <command> [options]
基于 argparse，支持模块动态注册命令。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .module import ModuleRegistry


# ---------------------------------------------------------------------------
# CLI 命令定义
# ---------------------------------------------------------------------------

@dataclass
class CLICommand:
    """CLI 命令定义。"""

    module: str
    name: str
    handler: Callable[..., None]
    help: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.module}.{self.name}"


# ---------------------------------------------------------------------------
# CLIFramework — CLI 框架
# ---------------------------------------------------------------------------

class CLIFramework:
    """统一 CLI 框架：dms <module> <command> [options]

    设计原则：
    - 两级命令：模块 + 子命令
    - 模块通过 ModuleRegistry 自动发现命令
    - 内置全局命令（init, module list, schema 等）不依赖模块
    - 支持从 sys.argv 或传入 args 执行

    用法:
        cli = CLIFramework(registry)
        cli.register_builtins()
        cli.execute()  # 使用 sys.argv[1:]
    """

    def __init__(self, registry: ModuleRegistry, prog: str = "dms") -> None:
        self._registry = registry
        self._prog = prog
        self._commands: dict[str, CLICommand] = {}  # "module.command" -> CLICommand
        self._parser: argparse.ArgumentParser | None = None
        self._context: dict[str, Any] = {}

    # -- 命令注册 ----------------------------------------------------------

    def register_command(
        self,
        module: str,
        command: str,
        handler: Callable[..., None],
        help_text: str = "",
        arguments: list[dict[str, Any]] | None = None,
    ) -> None:
        """注册一个命令。

        arguments 中每一项是 argparse.add_argument 的参数字典，
        必须包含 "flags" (list) 或 "name" (str)。
        """
        key = f"{module}.{command}"
        if key in self._commands:
            raise ValueError(f"Command '{key}' already registered")
        self._commands[key] = CLICommand(
            module=module,
            name=command,
            handler=handler,
            help=help_text,
            arguments=arguments or [],
        )

    def register_module_commands(self) -> None:
        """从已注册的模块中自动发现并注册命令。"""
        for manifest in self._registry.list_modules():
            for cmd_def in manifest.commands:
                self.register_command(
                    module=manifest.name,
                    command=cmd_def.name,
                    handler=cmd_def.handler,
                    help_text=cmd_def.help,
                    arguments=cmd_def.arguments,
                )

    # -- 内置命令 ----------------------------------------------------------

    def register_builtins(self) -> None:
        """注册框架内置命令。"""

        # dms init
        self.register_command(
            module="system",
            command="init",
            handler=self._cmd_init,
            help_text="初始化框架 + 数据库",
            arguments=[
                {"flags": ["--db-url"], "default": "sqlite:///delivery.db", "help": "数据库 URL"},
                {"flags": ["--tenant"], "default": "system", "help": "初始租户 ID"},
            ],
        )

        # dms module list
        self.register_command(
            module="module",
            command="list",
            handler=self._cmd_module_list,
            help_text="列出所有已注册模块",
        )

        # dms schema diff
        self.register_command(
            module="schema",
            command="diff",
            handler=self._cmd_schema_diff,
            help_text="显示待应用的 schema 变更",
            arguments=[
                {"flags": ["--db-url"], "default": "sqlite:///delivery.db", "help": "数据库 URL"},
            ],
        )

        # dms schema migrate
        self.register_command(
            module="schema",
            command="migrate",
            handler=self._cmd_schema_migrate,
            help_text="应用数据库迁移",
            arguments=[
                {"flags": ["--db-url"], "default": "sqlite:///delivery.db", "help": "数据库 URL"},
                {"flags": ["--target"], "default": "latest", "help": "目标版本"},
            ],
        )

        # dms tenant migrate
        self.register_command(
            module="tenant",
            command="migrate",
            handler=self._cmd_tenant_migrate,
            help_text="迁移指定租户的数据",
            arguments=[
                {"name": "tenant_id", "help": "租户 ID"},
                {"flags": ["--target"], "default": "latest", "help": "目标版本"},
                {"flags": ["--db-url"], "default": "sqlite:///delivery.db", "help": "数据库 URL"},
            ],
        )

    # -- 执行 --------------------------------------------------------------

    def build_parser(self) -> argparse.ArgumentParser:
        """构建 argparse parser。每次调用重新构建（命令可能动态变化）。"""
        parser = argparse.ArgumentParser(
            prog=self._prog,
            description="DMS Framework CLI - 交付管理框架命令行工具",
        )
        subparsers = parser.add_subparsers(dest="module", help="模块名")

        # 按模块分组
        by_module: dict[str, list[CLICommand]] = {}
        for cmd in self._commands.values():
            by_module.setdefault(cmd.module, []).append(cmd)

        for module_name, cmds in sorted(by_module.items()):
            module_parser = subparsers.add_parser(module_name, help=f"{module_name} 模块命令")
            cmd_sub = module_parser.add_subparsers(dest="command", help="子命令")
            for cmd in sorted(cmds, key=lambda c: c.name):
                p = cmd_sub.add_parser(cmd.name, help=cmd.help)
                for arg in cmd.arguments:
                    kwargs = {k: v for k, v in arg.items() if k not in ("flags", "name")}
                    if "flags" in arg:
                        p.add_argument(*arg["flags"], **kwargs)
                    elif "name" in arg:
                        p.add_argument(arg["name"], **kwargs)
                p.set_defaults(_handler=cmd.handler, _cmd_key=cmd.full_name)

        self._parser = parser
        return parser

    def execute(self, args: list[str] | None = None) -> int:
        """解析并执行命令。返回退出码。"""
        if args is None:
            args = sys.argv[1:]

        parser = self.build_parser()
        parsed = parser.parse_args(args)

        if not parsed.module or not parsed.command:
            parser.print_help()
            return 1

        handler = getattr(parsed, "_handler", None)
        if handler is None:
            print(f"Error: No handler for command '{parsed.module} {parsed.command}'", file=sys.stderr)
            return 1

        try:
            handler(parsed, self._context)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    def get_help(self) -> str:
        """返回帮助文本。"""
        parser = self.build_parser()
        return parser.format_help()

    # -- 上下文 ------------------------------------------------------------

    def set_context(self, key: str, value: Any) -> None:
        self._context[key] = value

    def get_context(self, key: str) -> Any:
        return self._context.get(key)

    # -- 内置命令实现 ------------------------------------------------------

    def _cmd_init(self, args: argparse.Namespace, context: dict[str, Any]) -> None:
        """dms init — 初始化框架和数据库。"""
        from .database import Database, MigrationManager

        db = Database(args.db_url)
        db.connect()
        mm = MigrationManager()

        # 收集所有模块的迁移
        if self._registry.is_initialized:
            pass  # 已初始化，直接用

        print(f"✓ Framework initialized with DB: {args.db_url}")
        print(f"✓ Tenant: {args.tenant}")
        print(f"✓ Modules: {len(self._registry.list_modules())} registered")

    def _cmd_module_list(self, args: argparse.Namespace, context: dict[str, Any]) -> None:
        """dms module list — 列出模块。"""
        modules = self._registry.list_modules()
        if not modules:
            print("(no modules registered)")
            return
        print(f"{'Name':<25} {'Version':<12} {'Description'}")
        print("-" * 70)
        for m in sorted(modules, key=lambda x: x.name):
            print(f"{m.name:<25} {m.version:<12} {m.description}")

    def _cmd_schema_diff(self, args: argparse.Namespace, context: dict[str, Any]) -> None:
        """dms schema diff — 显示待迁移。"""
        from .database import Database, MigrationManager

        db = Database(args.db_url)
        mm = MigrationManager()
        pending = mm.diff(db)
        if not pending:
            print("Database is up to date.")
        else:
            print("Pending migrations:")
            for p in pending:
                print(f"  {p}")

    def _cmd_schema_migrate(self, args: argparse.Namespace, context: dict[str, Any]) -> None:
        """dms schema migrate — 执行迁移。"""
        from .database import Database, MigrationManager

        db = Database(args.db_url)
        mm = MigrationManager()
        current = mm.get_current_version(db)
        print(f"Current version: {current}")
        mm.migrate(db, target=args.target)
        new_version = mm.get_current_version(db)
        print(f"Migrated to: {new_version}")

    def _cmd_tenant_migrate(self, args: argparse.Namespace, context: dict[str, Any]) -> None:
        """dms tenant migrate <id> — 租户级迁移。"""
        from .database import Database, MigrationManager
        from .saas import TenantContext

        db = Database(args.db_url)
        mm = MigrationManager()

        with TenantContext.scope(args.tenant_id):
            db.set_tenant_context(args.tenant_id)
            current = mm.get_current_version(db)
            print(f"Tenant {args.tenant_id} — current: {current}")
            mm.migrate(db, target=args.target)
            new = mm.get_current_version(db)
            print(f"Tenant {args.tenant_id} — migrated to: {new}")
