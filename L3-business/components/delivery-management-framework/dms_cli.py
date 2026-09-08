#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DMF CLI — 交付管理框架统一 CLI 入口
"""

import sys
import argparse
from L3-business.components.delivery-management-framework.registry import ModuleRegistry
from L3-business.components.delivery-management-framework.state_machine import StateMachineEngine
from L3-business.components.delivery-management-framework.raci import RACIEngine
from L3-business.components.delivery-management-framework.event_bus import EventBus
from L3-business.components.delivery-management-framework.cli import CLIFramework

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
