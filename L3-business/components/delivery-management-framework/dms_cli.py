#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DMF CLI — 交付管理框架统一 CLI 入口
"""

import sys
import argparse
from .registry import ModuleRegistry
from .state_machine import StateMachineEngine
from .raci import RACIEngine
from .event_bus import EventBus
from .cli import CLIFramework

# 创建单例框架实例
registry = ModuleRegistry()
state_machine = StateMachineEngine()
raci_engine = RACIEngine()
event_bus = EventBus()

def main():
    """CLI 主入口"""
    cli = CLIFramework(prog="dms")
    # 这里可以由各个模块自动注册命令，现在先给出基础入口
    cli.run(sys.argv[1:])

if __name__ == "__main__":
    sys.exit(main())
