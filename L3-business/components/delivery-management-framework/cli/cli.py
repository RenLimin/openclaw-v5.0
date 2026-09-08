#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Framework — 统一 CLI 框架
模块自动注册命令，统一入口
"""

from dataclasses import dataclass
from typing import Dict, Callable, List, Optional
import argparse
import sys
import logging

logger = logging.getLogger(__name__)

@dataclass
class CommandDef:
    """CLI 命令定义"""
    name: str
    handler: Callable
    description: str

class CLIFramework:
    """CLI 框架，管理模块命令"""

    def __init__(self, prog: str = "dms"):
        self.prog = prog
        self._commands: Dict[str, CommandDef] = {}

    def register_command(self, cmd: CommandDef) -> None:
        """注册一个命令"""
        if cmd.name in self._commands:
            logger.warning(f"Command {cmd.name} already registered, overwriting")
        self._commands[cmd.name] = cmd
        logger.debug(f"Registered command: {cmd.name}")

    def run(self, args: Optional[List[str]] = None) -> int:
        """运行 CLI，解析参数并调用处理函数"""
        if args is None:
            args = sys.argv[1:]

        if not args:
            self.print_help()
            return 0

        parser = argparse.ArgumentParser(prog=self.prog)
        subparsers = parser.add_subparsers(dest="command", required=True)

        for cmd in self._commands.values():
            subparser = subparsers.add_parser(cmd.name, help=cmd.description)
            # handler 负责添加自己的参数
            cmd.handler(subparser)

        parsed = parser.parse_args(args)
        command = parsed.command
        if command not in self._commands:
            print(f"Error: Unknown command '{command}'")
            self.print_help()
            return 1

        handler = self._commands[command].handler
        return handler(parsed)

    def print_help(self) -> None:
        """打印帮助信息"""
        print(f"{self.prog} — 交付管理框架 CLI")
        print()
        print("可用命令:")
        max_len = max(len(cmd.name) for cmd in self._commands.values()) if self._commands else 0
        for cmd in sorted(self._commands.values(), key=lambda x: x.name):
            print(f"  {cmd.name.ljust(max_len)} — {cmd.description}")
        print()
        print("用法:")
        print(f"  {self.prog} <module> <command> [options]")
