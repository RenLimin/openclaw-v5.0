"""
L2 沙箱隔离核心服务 — 沙箱生命周期管理 + 权限控制
遵循 ADR-013: 沙箱隔离契约下沉到 L2，只依赖 L1 抽象接口，不绑定具体运行时

功能：
- 沙箱创建/销毁/启动/停止
- 权限策略检查（哪些命令可执行）
- 沙箱状态查询
- 文件挂载管理（只读/读写）
- 输出捕获
"""
import sys
import importlib
from pathlib import Path
# service.py: L2-infra/components/sandbox-isolation/service.py
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
L1_RUNTIME = WORKSPACE_ROOT / "L1-runtime"
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(L1_RUNTIME))

from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
# L1-runtime has hyphen so we can't import as package directly, add to sys.path first
openclaw_adapter_module = importlib.import_module('adapters.openclaw.openclaw.adapter')
openclaw_adapter = openclaw_adapter_module.adapter
from scripts.policy import SandboxPolicy
from scripts.sandbox import SandboxManager, SandboxInfo

class SandboxIsolationService:
    """L2 沙箱隔离核心服务"""

    def __init__(self):
        self.adapter = openclaw_adapter
        self.policy = SandboxPolicy()
        self.manager = SandboxManager()

    def create_sandbox(
        self,
        policy_name: str,
        workdir: Optional[str] = None,
        mounts: Optional[List[Dict[str, str]]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        创建新沙箱
        :param policy_name: 权限策略名称
        :param workdir: 工作目录（可选，默认使用临时目录）
        :param mounts: 挂载配置 [{source: path, target: path, readonly: bool}]
        :param env: 环境变量
        :return: (success, message, sandbox_id)
        """
        # 验证策略
        if not self.policy.policy_exists(policy_name):
            return False, f"Policy {policy_name} does not exist", None

        # 创建沙箱
        return self.manager.create(
            policy_name=policy_name,
            workdir=workdir,
            mounts=mounts,
            env=env
        )

    def destroy_sandbox(self, sandbox_id: str) -> Tuple[bool, str]:
        """销毁沙箱"""
        return self.manager.destroy(sandbox_id)

    def start_sandbox(self, sandbox_id: str, command: List[str]) -> Tuple[bool, str]:
        """启动沙箱执行命令"""
        # 权限检查
        ok, err = self.policy.check_command(sandbox_id, command)
        if not ok:
            return False, err

        return self.manager.start(sandbox_id, command)

    def stop_sandbox(self, sandbox_id: str) -> Tuple[bool, str]:
        """停止沙箱"""
        return self.manager.stop(sandbox_id)

    def get_sandbox_info(self, sandbox_id: str) -> Tuple[Optional[SandboxInfo], str]:
        """获取沙箱信息"""
        return self.manager.get_info(sandbox_id)

    def list_sandboxes(self) -> List[SandboxInfo]:
        """列出所有沙箱"""
        return self.manager.list_all()

    def get_output(self, sandbox_id: str, offset: int = 0, limit: Optional[int] = None) -> Tuple[Optional[str], str]:
        """获取沙箱输出"""
        return self.manager.get_output(sandbox_id, offset, limit)

    def wait_sandbox(self, sandbox_id: str, timeout_seconds: Optional[int] = None) -> Tuple[int, str]:
        """等待沙箱执行完成，返回退出码"""
        return self.manager.wait(sandbox_id, timeout_seconds)

    def add_mount(self, sandbox_id: str, source: str, target: str, readonly: bool = True) -> Tuple[bool, str]:
        """添加挂载"""
        return self.manager.add_mount(sandbox_id, source, target, readonly)

    def check_policy(self, policy_name: str, command: List[str]) -> Tuple[bool, str]:
        """检查命令是否符合策略"""
        return self.policy.check_policy(policy_name, command)
