# -*- coding: utf-8 -*-
"""CLI Framework 测试。"""

import pytest
from unittest.mock import MagicMock, patch
from cli import CLIFramework, CommandDef


class TestCLIFramework:
    """CLIFramework 核心功能测试。"""

    def setup_method(self):
        self.cli = CLIFramework(prog="test-dms")

    def test_register_command(self):
        """注册命令后应能通过名称获取。"""
        handler = MagicMock()
        cmd = CommandDef(name="create", handler=handler, description="创建项目")
        self.cli.register_command(cmd)
        assert "create" in self.cli._commands

    def test_register_overwrites_duplicate(self):
        """重复注册同名命令应覆盖。"""
        h1, h2 = MagicMock(), MagicMock()
        self.cli.register_command(CommandDef(name="cmd", handler=h1, description="v1"))
        self.cli.register_command(CommandDef(name="cmd", handler=h2, description="v2"))
        assert self.cli._commands["cmd"].handler == h2

    def test_run_no_args_returns_0(self):
        """无参数调用应打印帮助并返回 0。"""
        result = self.cli.run([])
        assert result == 0

    def test_run_unknown_command_raises_system_exit(self):
        """未知命令应触发 argparse sys.exit(2)。"""
        with pytest.raises(SystemExit) as exc_info:
            self.cli.run(["nonexistent"])
        assert exc_info.value.code == 2

    def test_run_known_command(self):
        """已知命令应被正确调用并返回处理结果。"""
        handler = MagicMock(return_value=0)
        self.cli.register_command(CommandDef(
            name="mytest", handler=handler, description="测试命令"
        ))
        result = self.cli.run(["mytest"])
        assert result == 0
        # handler 在 setup 阶段被调用一次（add_argument 等），run 阶段再调用一次
        assert handler.call_count >= 1
