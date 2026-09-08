#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 通用交付管理框架（DMS-Framework）
入口模块
"""

from .registry import ModuleRegistry, ModuleManifest
from .state_machine import StateMachineEngine, StateMachine, Transition
from .raci import RACIEngine, Capability, RoleTemplate, Assignment
from .event_bus import EventBus
from .cli import CLIFramework, CommandDef
from .models import BaseModel
from .repo import BaseRepository

__all__ = [
    "ModuleRegistry",
    "ModuleManifest",
    "StateMachineEngine",
    "StateMachine",
    "Transition",
    "RACIEngine",
    "Capability",
    "RoleTemplate",
    "Assignment",
    "EventBus",
    "CLIFramework",
    "CommandDef",
    "BaseModel",
    "BaseRepository",
]
