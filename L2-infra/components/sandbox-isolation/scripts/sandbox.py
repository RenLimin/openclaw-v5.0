"""
沙箱隔离组件 — 沙箱生命周期管理器
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import sys
import os
import json
import time
import tempfile
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict

# Add workspace root and L1-runtime to path
from pathlib import Path
# sandbox.py: L2-infra/components/sandbox-isolation/scripts/sandbox.py
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
L1_RUNTIME = WORKSPACE_ROOT / "L1-runtime"
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(L1_RUNTIME))

import importlib
openclaw_adapter_module = importlib.import_module('adapters.openclaw.openclaw.adapter')
openclaw_adapter = openclaw_adapter_module.adapter

from utils.utils import (
    get_current_datetime,
    ensure_directory,
    read_file,
    write_json_file,
    load_json_file
)

from dataclasses import dataclass

@dataclass
class SandboxInfo:
    """沙箱信息"""
    sandbox_id: str
    status: str
    workdir: str
    created_at: str
    policy_name: str

SANDBOX_ROOT = "sandboxes"

@dataclass
class Sandbox:
    """沙箱数据结构"""
    sandbox_id: str
    status: str  # created | running | exited | stopped | destroyed
    workdir: str
    policy_name: str
    created_at: str
    started_at: Optional[str] = None
    exited_at: Optional[str] = None
    command: Optional[List[str]] = None
    exit_code: Optional[int] = None
    mounts: List[Dict[str, Any]] = None
    env: Dict[str, str] = None

    def to_dict(self):
        return asdict(self)

class SandboxManager:
    """沙箱生命周期管理器"""

    def __init__(self):
        self._sandboxes: Dict[str, Sandbox] = {}
        self._load_sandboxes()

    def _get_sandbox_state_path(self, sandbox_id: str) -> str:
        return os.path.join(SANDBOX_ROOT, sandbox_id, "state.json")

    def _load_sandboxes(self):
        """从磁盘加载已存在的沙箱"""
        if not os.path.exists(SANDBOX_ROOT):
            ensure_directory(SANDBOX_ROOT)
            return

        for entry in os.scandir(SANDBOX_ROOT):
            if entry.is_dir():
                state_path = self._get_sandbox_state_path(entry.name)
                if os.path.exists(state_path):
                    data = load_json_file(state_path)
                    if data:
                        sandbox = Sandbox(**data)
                        self._sandboxes[sandbox.sandbox_id] = sandbox

    def _save_sandbox(self, sandbox: Sandbox):
        """保存沙箱状态到磁盘"""
        sandbox_dir = os.path.join(SANDBOX_ROOT, sandbox.sandbox_id)
        ensure_directory(sandbox_dir)
        state_path = self._get_sandbox_state_path(sandbox.sandbox_id)
        write_json_file(state_path, sandbox.to_dict())

    def create(
        self,
        policy_name: str,
        workdir: Optional[str] = None,
        mounts: Optional[List[Dict[str, str]]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """创建新沙箱"""
        # 生成沙箱ID
        sandbox_id = f"sandbox-{int(time.time())}"

        # 如果未指定工作目录，创建临时目录
        if not workdir:
            temp_root = os.path.join(SANDBOX_ROOT, sandbox_id, "workdir")
            ensure_directory(temp_root)
            workdir = temp_root
        else:
            # 确保工作目录存在
            if not os.path.exists(workdir):
                ok = ensure_directory(workdir)
                if not ok:
                    return False, f"Failed to create workdir {workdir}", None

        # 创建沙箱对象
        sandbox = Sandbox(
            sandbox_id=sandbox_id,
            status="created",
            workdir=workdir,
            policy_name=policy_name,
            created_at=get_current_datetime(),
            mounts=mounts or [],
            env=env or {}
        )

        # 保存状态
        self._sandboxes[sandbox_id] = sandbox
        self._save_sandbox(sandbox)

        return True, f"Sandbox {sandbox_id} created successfully", sandbox_id

    def destroy(self, sandbox_id: str) -> Tuple[bool, str]:
        """销毁沙箱"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False, f"Sandbox {sandbox_id} not found"

        # 停止沙箱如果正在运行
        if sandbox.status == "running":
            self.stop(sandbox_id)

        # 删除目录
        sandbox_dir = os.path.join(SANDBOX_ROOT, sandbox_id)
        if os.path.exists(sandbox_dir):
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        # 从内存移除
        del self._sandboxes[sandbox_id]
        return True, f"Sandbox {sandbox_id} destroyed successfully"

    def start(self, sandbox_id: str, command: List[str]) -> Tuple[bool, str]:
        """启动沙箱执行命令"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False, f"Sandbox {sandbox_id} not found"

        if sandbox.status == "running":
            return False, f"Sandbox {sandbox_id} is already running"

        # 更新状态
        sandbox.status = "running"
        sandbox.command = command
        sandbox.started_at = get_current_datetime()
        self._save_sandbox(sandbox)

        # 通过适配器执行
        ok, pid = openclaw_adapter.exec_background(
            command=command,
            cwd=sandbox.workdir,
            env=sandbox.env
        )

        if not ok:
            sandbox.status = "error"
            self._save_sandbox(sandbox)
            return False, f"Failed to start command: {pid}"

        # 存储 PID
        # (adapter 会管理进程，我们只记录状态)
        return True, f"Sandbox {sandbox_id} started with PID {pid}"

    def stop(self, sandbox_id: str) -> Tuple[bool, str]:
        """停止沙箱"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False, f"Sandbox {sandbox_id} not found"

        if sandbox.status != "running":
            return False, f"Sandbox {sandbox_id} is not running"

        # 调用适配器停止
        ok = openclaw_adapter.kill_process(sandbox_id)
        if not ok:
            return False, f"Failed to kill process for {sandbox_id}"

        sandbox.status = "stopped"
        sandbox.exited_at = get_current_datetime()
        self._save_sandbox(sandbox)
        return True, f"Sandbox {sandbox_id} stopped"

    def get_info(self, sandbox_id: str) -> Tuple[Optional[SandboxInfo], str]:
        """获取沙箱信息"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return None, f"Sandbox {sandbox_id} not found"

        info = SandboxInfo(
            sandbox_id=sandbox.sandbox_id,
            status=sandbox.status,
            workdir=sandbox.workdir,
            created_at=sandbox.created_at,
            policy_name=sandbox.policy_name
        )

        return info, ""

    def list_all(self) -> List[SandboxInfo]:
        """列出所有沙箱"""
        result = []
        for sandbox in self._sandboxes.values():
            info = SandboxInfo(
                sandbox_id=sandbox.sandbox_id,
                status=sandbox.status,
                workdir=sandbox.workdir,
                created_at=sandbox.created_at,
                policy_name=sandbox.policy_name
            )
            result.append(info)
        return result

    def get_output(self, sandbox_id: str, offset: int = 0, limit: Optional[int] = None) -> Tuple[Optional[str], str]:
        """获取沙箱输出（通过适配器）"""
        return openclaw_adapter.get_output(sandbox_id, offset, limit)

    def wait(self, sandbox_id: str, timeout_seconds: Optional[int] = None) -> Tuple[int, str]:
        """等待沙箱执行完成"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return -1, f"Sandbox {sandbox_id} not found"

        exit_code, output = openclaw_adapter.wait(sandbox_id, timeout_seconds)
        if exit_code >= 0:
            sandbox.status = "exited"
            sandbox.exit_code = exit_code
            sandbox.exited_at = get_current_datetime()
            self._save_sandbox(sandbox)

        return exit_code, output

    def add_mount(self, sandbox_id: str, source: str, target: str, readonly: bool = True) -> Tuple[bool, str]:
        """添加挂载点"""
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False, f"Sandbox {sandbox_id} not found"

        if not os.path.exists(source):
            return False, f"Source path {source} does not exist"

        # 这里实际挂载由底层适配器实现，我们只记录
        sandbox.mounts.append({
            "source": source,
            "target": target,
            "readonly": readonly
        })
        self._save_sandbox(sandbox)
        return True, f"Mount added to {sandbox_id}"
