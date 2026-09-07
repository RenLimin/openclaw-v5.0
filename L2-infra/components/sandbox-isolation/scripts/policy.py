"""
沙箱隔离组件 — 权限策略检查
Copyright (c) 2026 Bangcle, Inc. All rights reserved.

策略规则：
- 白名单优先：命令/路径必须匹配白名单才能执行
- 支持通配符匹配
- 支持全局禁止的危险命令
"""
import sys
import os
import json
from typing import Dict, List, Optional, Tuple, Set, Pattern
import re

# Add workspace root to path
from pathlib import Path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from utils.utils import (
    load_json_file,
    write_json_file,
    ensure_directory
)

POLICY_DIR = "config/sandbox-policies"

# 危险命令全局黑名单
DEFAULT_DANGEROUS_COMMANDS = {
    "rm -rf /",
    ":(){ :|:& };:", # fork bomb
    "chmod 777 /",
    "mkfs",
    "fdisk",
    "dd if=/dev/zero",
    ": > /dev/sda",
    "wget | curl | sh",
    "curl | bash",
}

class SandboxPolicy:
    """沙箱权限策略检查器"""

    def __init__(self):
        self._policies: Dict[str, Dict] = {}
        self._load_policies()

    def _load_policies(self):
        """加载所有策略"""
        if not os.path.exists(POLICY_DIR):
            os.makedirs(POLICY_DIR, exist_ok=True)
            return

        for entry in os.scandir(POLICY_DIR):
            if entry.is_file() and entry.name.endswith(".json"):
                policy_name = entry.name[:-5] # remove .json
                policy = load_json_file(entry.path)
                if policy:
                    self._policies[policy_name] = policy

    def policy_exists(self, policy_name: str) -> bool:
        """检查策略是否存在"""
        return policy_name in self._policies

    def create_policy(self, policy_name: str, allowed_commands: List[str], allowed_paths: List[str], blocked_paths: List[str]) -> Tuple[bool, str]:
        """创建新策略"""
        if policy_name in self._policies:
            return False, f"Policy {policy_name} already exists"

        policy = {
            "allowed_commands": allowed_commands,
            "allowed_paths": allowed_paths,
            "blocked_paths": blocked_paths,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        }

        policy_path = os.path.join(POLICY_DIR, f"{policy_name}.json")
        write_json_file(policy_path, policy)
        self._policies[policy_name] = policy
        return True, f"Policy {policy_name} created successfully"

    def check_command(self, sandbox_id: str, command: List[str]) -> Tuple[bool, str]:
        """检查命令是否允许执行"""
        if len(command) == 0:
            return False, "Empty command"

        # 检查全局危险命令
        cmd_str = " ".join(command)
        for dangerous in DEFAULT_DANGEROUS_COMMANDS:
            if dangerous in cmd_str:
                return False, f"Command matches global dangerous pattern: {dangerous}"

        # 获取沙箱策略
        # (sandbox_id 策略名称已经在创建时记录，这里我们需要获取)
        # 简化处理：假设策略名称和沙箱ID一致，或者从沙箱信息获取
        # 实际：sandbox_id 我们只需要策略名称，所以这里简化
        policy_name = command[0] if len(command) > 0 else ""
        # TODO: 正确获取策略应该从沙箱对象获取，这里先简化
        policy = self._policies.get(policy_name)
        if not policy:
            policy_name = "default"
            policy = self._policies.get(policy_name)

        if not policy:
            return False, "No valid policy found for command check"

        return self.check_policy(policy_name, command)

    def check_policy(self, policy_name: str, command: List[str]) -> Tuple[bool, str]:
        """根据策略名称检查命令"""
        policy = self._policies.get(policy_name)
        if not policy:
            return False, f"Policy {policy_name} not found"

        cmd_base = os.path.basename(command[0])
        allowed_commands = policy.get("allowed_commands", [])

        # 命令必须在白名单中
        if cmd_base not in allowed_commands and command[0] not in allowed_commands:
            return False, f"Command {cmd_base} not in allowed list for policy {policy_name}"

        # 检查路径参数
        allowed_paths = policy.get("allowed_paths", [])
        blocked_paths = policy.get("blocked_paths", [])

        for arg in command[1:]:
            # 检查是否是路径（包含/或以 ./ 开头）
            if "/" in arg or arg.startswith("./") or arg.startswith("../"):
                # 优先检查是否在黑名单
                for blocked in blocked_paths:
                    if self._pattern_match(arg, blocked):
                        return False, f"Path {arg} matches blocked pattern {blocked}"

                # 必须匹配至少一个白名单
                if allowed_paths:
                    matched = False
                    for allowed in allowed_paths:
                        if self._pattern_match(arg, allowed):
                            matched = True
                            break
                    if not matched:
                        return False, f"Path {arg} does not match any allowed pattern for policy {policy_name}"

        return True, "OK"

    def _pattern_match(self, path: str, pattern: str) -> bool:
        """简单通配符匹配"""
        # 转换通配符为正则
        regex_pattern = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
        return re.match(regex_pattern, path) is not None

    def list_policies(self) -> List[str]:
        """列出所有策略"""
        return list(self._policies.keys())
