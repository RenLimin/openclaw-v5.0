#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
State Machine Engine — 可配置状态机引擎
支持定义状态、转换、守卫条件和钩子
"""

from dataclasses import dataclass, field
from typing import List, Dict, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class Transition:
    """状态转换定义"""
    event: str
    source: str | List[str]
    target: str
    guard: Optional[str] = None

@dataclass
class StateMachine:
    """状态机定义"""
    name: str
    states: List[str]
    initial: str
    transitions: List[Transition]
    guards: Dict[str, Callable[[Any], bool]] = field(default_factory=dict)
    hooks: Dict[str, List[Callable[[Any, Any], None]]] = field(default_factory=dict)

    def __post_init__(self):
        # 确保初始状态在状态列表中
        if self.initial not in self.states:
            raise ValueError(f"Initial state '{self.initial}' not in states list")

class StateMachineEngine:
    """状态机引擎，管理多个状态机实例"""

    def __init__(self):
        self._state_machines: Dict[str, StateMachine] = {}

    def register(self, sm: StateMachine) -> None:
        """注册一个状态机"""
        if sm.name in self._state_machines:
            logger.warning(f"State machine {sm.name} already registered, overwriting")
        self._state_machines[sm.name] = sm
        logger.info(f"Registered state machine: {sm.name}")

    def get_state_machine(self, name: str) -> Optional[StateMachine]:
        """获取状态机"""
        return self._state_machines.get(name)

    def trigger(self, sm_name: str, current_state: str, event: str, context: Any = None) -> Optional[str]:
        """触发一个事件，返回新状态（None表示无法转换）"""
        sm = self.get_state_machine(sm_name)
        if not sm:
            logger.error(f"State machine {sm_name} not found")
            return None

        # 找到匹配的转换
        matching_transitions = []
        for t in sm.transitions:
            if t.event != event:
                continue
            # 检查源状态匹配
            if isinstance(t.source, list):
                if current_state not in t.source:
                    continue
            else:
                if current_state != t.source:
                    continue
            matching_transitions.append(t)

        if not matching_transitions:
            logger.debug(f"No transition found for event {event} from state {current_state}")
            return None

        # 按守卫条件过滤
        valid_transitions = []
        for t in matching_transitions:
            if t.guard is None:
                valid_transitions.append(t)
            else:
                guard_func = sm.guards.get(t.guard)
                if guard_func and guard_func(context):
                    valid_transitions.append(t)
                else:
                    logger.debug(f"Guard {t.guard} failed for transition")

        if not valid_transitions:
            logger.debug(f"No valid transitions after guard check")
            return None

        # 取第一个有效转换
        transition = valid_transitions[0]
        new_state = transition.target

        # 触发钩子
        if f"{current_state}_exit" in sm.hooks:
            for hook in sm.hooks[f"{current_state}_exit"]:
                hook(context, transition)
        if f"{transition.event}_before" in sm.hooks:
            for hook in sm.hooks[f"{transition.event}_before"]:
                hook(context, transition)

        # 触发转换后钩子
        if f"{new_state}_enter" in sm.hooks:
            for hook in sm.hooks[f"{new_state}_enter"]:
                hook(context, transition)

        logger.info(f"Transition {sm.name}: {current_state} --[{event}]--> {new_state}")
        return new_state

    def add_guard(self, sm_name: str, guard_name: str, func: Callable[[Any], bool]) -> bool:
        """添加守卫函数到已注册的状态机"""
        sm = self.get_state_machine(sm_name)
        if not sm:
            logger.error(f"State machine {sm_name} not found")
            return False
        sm.guards[guard_name] = func
        return True

    def add_hook(self, sm_name: str, hook_name: str, func: Callable[[Any, Any], None]) -> bool:
        """添加钩子函数"""
        sm = self.get_state_machine(sm_name)
        if not sm:
            logger.error(f"State machine {sm_name} not found")
            return False
        if hook_name not in sm.hooks:
            sm.hooks[hook_name] = []
        sm.hooks[hook_name].append(func)
        return True
