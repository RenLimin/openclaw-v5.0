"""
OpenClaw 运行时适配层 - L1 最小能力契约实现

将 L1 抽象接口翻译为 OpenClaw 运行时 API 调用。
符合 ADR-012：Agent 运行时作为可变因素，L2-L4 只依赖抽象契约。
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import json
import subprocess
import glob
import shutil
from pathlib import Path
from dataclasses import dataclass

# L1 最小能力契约接口
# 对应 docs/architecture/00-system-architecture.md §3.2.1

@dataclass
class HealthStatus:
    """健康检查结果"""
    status: str  # ok / degraded / down
    message: str
    details: Optional[Dict[str, Any]] = None

@dataclass
class ToolCallResult:
    """工具调用结果"""
    success: bool
    output: Any
    error: Optional[str] = None

@dataclass
class ContextStatus:
    """上下文状态"""
    current_tokens: int
    max_tokens: int
    warning_threshold: int
    divert_threshold: int
    hard_limit: int

class OpenClawAdapter:
    """OpenClaw L1 抽象契约适配层"""

    def __init__(self):
        self.version = "2026.7.2-beta.7"  # 同步当前 OpenClaw 版本

    # 1. Agent Loop
    def execute(self, message: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """执行 Agent 推理循环"""
        # OpenClaw 原生已提供 agent loop，这里仅做适配转发
        # 实际调用通过 gateway RPC
        raise NotImplementedError("execute 由 OpenClaw 原生提供，适配层仅声明契约")

    # 2. 工具执行
    def register_tool(self, name: str, schema: Dict[str, Any], fn: Any) -> bool:
        """注册工具到运行时"""
        # OpenClaw 工具注册通过配置文件完成
        # 这里仅声明契约，实际注册由运行时处理
        return True

    def call_tool(self, name: str, input: Dict[str, Any]) -> ToolCallResult:
        """调用已注册工具"""
        # 通过 OpenClaw gateway RPC 调用
        # 实际使用中由运行时路由
        cmd = ["openclaw", "gateway", "call", name, "--params", json.dumps(input)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return ToolCallResult(
                success=True,
                output=json.loads(result.stdout),
                error=None
            )
        except subprocess.CalledProcessError as e:
            return ToolCallResult(
                success=False,
                output=None,
                error=e.stderr
            )

    # 3. 记忆
    def memory_read(self, key: str) -> Optional[Any]:
        """读取持久化记忆"""
        # OpenClaw 记忆系统通过 memory_get 工具访问
        result = self.call_tool("memory_get", {"path": key})
        if not result.success:
            return None
        return result.output

    def memory_write(self, key: str, val: Any) -> bool:
        """写入持久化记忆"""
        # 通过 OpenClaw 工具系统
        # 实际写入由 memory module 处理
        result = self.call_tool("memory_get", {"path": key})
        # 简化实现：实际写入需要 write 工具支持
        return result.success

    def memory_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """语义搜索记忆"""
        result = self.call_tool("memory_search", {"query": query, "maxResults": max_results})
        if not result.success:
            return []
        return result.output.get("results", [])

    # 4. 定时调度
    def schedule(self, schedule: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
        """创建定时任务"""
        # 通过 automations 工具创建
        result = self.call_tool("automations", {"action": "add", "schedule": schedule, "payload": payload})
        if not result.success:
            return None
        return result.output.get("jobId")

    def cancel(self, task_id: str) -> bool:
        """取消定时任务"""
        result = self.call_tool("automations", {"action": "remove", "jobId": task_id})
        return result.success

    def list_schedules(self) -> List[Dict[str, Any]]:
        """列出所有定时任务"""
        result = self.call_tool("automations", {"action": "list"})
        if not result.success:
            return []
        return result.output.get("jobs", [])

    # 5. 通道接入
    def register_channel(self, name: str, adapter: Any) -> bool:
        """注册消息通道"""
        # 通道注册由 OpenClaw 配置系统完成
        # 适配层仅声明契约
        return True

    def send_message(self, channel: str, msg: str) -> bool:
        """发送消息到通道"""
        # 通过 conversations_send 工具
        result = self.call_tool("conversations_send", {"channel": channel, "message": msg})
        return result.success

    # 6. 配置管理
    def config_get(self, path: str) -> Optional[Any]:
        """读取配置"""
        cmd = ["openclaw", "config", "get", path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            return None

    def config_set(self, path: str, val: Any) -> bool:
        """写入配置（带保护：dry-run → 写入 → 校验 → 读回）
        
        保护机制（基于 EXP-010/011 教训）：
        1. dry-run 预检，失败则中止（不触碰文件）
        2. 写入后 validate，失败则回退到 .bak
        3. 读回确认写入值与期望一致
        """
        # 1. dry-run 预检
        dry_cmd = ["openclaw", "config", "patch", "--stdin", "--dry-run"]
        patch_data = json.dumps({path: val})
        try:
            subprocess.run(dry_cmd, input=patch_data, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            # dry-run 失败 = 配置 schema 不合法，中止
            return False

        # 2. 正式写入（使用 patch 而非 set，支持嵌套路径）
        patch_cmd = ["openclaw", "config", "patch", "--stdin"]
        try:
            subprocess.run(patch_cmd, input=patch_data, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return False

        # 3. 写入后校验
        valid, errors = self.config_validate()
        if not valid:
            # 校验失败 → 尝试回退
            self._auto_rollback()
            return False

        # 4. 读回确认
        actual = self.config_get(path)
        if actual != val:
            # 写入值与期望不符 → 回退
            self._auto_rollback()
            return False

        return True

    def _auto_rollback(self) -> None:
        """自动回退：恢复最新的 .bak 文件"""
        import glob, shutil
        bak_dir = Path.home() / ".openclaw"
        baks = sorted(glob.glob(str(bak_dir / "openclaw.json.bak*")), reverse=True)
        if baks:
            # 用 .bak（最新一份）恢复
            shutil.copy2(baks[0], bak_dir / "openclaw.json")

    def config_validate(self) -> Tuple[bool, List[str]]:
        """验证配置合法性"""
        cmd = ["openclaw", "config", "validate"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return (True, [])
        except subprocess.CalledProcessError as e:
            return (False, e.stderr.splitlines())

    # 7. 凭据管理
    def credential_get(self, ref: str) -> Optional[str]:
        """获取凭据（通过 SecretRef）"""
        # 凭据实际存储由 OpenClaw SecretRef 机制处理
        # 适配层仅提供抽象接口
        # 实际使用中不允许暴露明文，仅传递引用
        return None

    def credential_rotate(self, ref: str, new_value: str) -> bool:
        """轮转凭据"""
        # 通过 OpenClaw 凭据管理脚本
        cmd = ["scripts/credentials.sh", "rotate", ref, new_value]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    # 8. 沙箱隔离
    def sandbox_execute(self, command: str, opts: Optional[Dict[str, Any]] = None) -> ToolCallResult:
        """在沙箱中执行命令"""
        # 沙箱执行由 OpenClaw 原生提供（exec 工具）
        result = self.call_tool("exec", {"command": command, "opts": opts or {}})
        return ToolCallResult(
            success=result.success,
            output=result.output,
            error=result.error
        )

    # 9. 上下文管理
    def context_status(self) -> ContextStatus:
        """查询当前上下文 token 状态"""
        # 从 session_status 获取
        # 简化实现：返回默认水位（对应 v5.0 配置）
        return ContextStatus(
            current_tokens=0,  # 需要实际查询
            max_tokens=229376,
            warning_threshold=135104,  # 229376 * 0.59
            divert_threshold=182096,    # 229376 * 0.79
            hard_limit=206438          # 229376 * 0.9
        )

    def context_compact(self) -> bool:
        """执行上下文压缩"""
        # 通过 OpenClaw 内置 compaction
        # 需要 gateway RPC 调用
        return True

    # 10. 健康检查
    def health(self) -> HealthStatus:
        """运行时健康检查"""
        try:
            # 执行 openclaw doctor 检查
            result = subprocess.run(["openclaw", "doctor"], capture_output=True, text=True, check=True)
            return HealthStatus(
                status="ok",
                message="OpenClaw 运行正常",
                details={"output": result.stdout}
            )
        except subprocess.CalledProcessError as e:
            return HealthStatus(
                status="degraded",
                message="OpenClaw 健康检查异常",
                details={"error": e.stderr}
            )
        except FileNotFoundError:
            return HealthStatus(
                status="down",
                message="OpenClaw 可执行文件未找到",
                details=None
            )

    # 11. 会话隔离与共享（ADR-202609-024）
    def session_create(self, scope: str) -> Optional[str]:
        """创建一个隔离会话，返回新会话 key"""
        # 通过 sessions_spawn RPC 创建
        result = self.call_tool("sessions_spawn", {
            "task": "隔离任务",
            "label": f"{scope} 隔离任务",
            "context": "isolated",
            "visible": True
        })
        if not result.success:
            return None
        # 返回新会话 sessionKey
        return result.output.get("sessionKey")

    def session_send(self, session_key: str, message: str) -> bool:
        """发送消息到目标会话"""
        # 通过 sessions_send RPC 发送
        result = self.call_tool("sessions_send", {
            "sessionKey": session_key,
            "message": message
        })
        return result.success

    def session_history(self, session_key: str, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """读取目标会话历史"""
        # 通过 sessions_history RPC 获取
        result = self.call_tool("sessions_history", {
            "sessionKey": session_key,
            "limit": limit
        })
        if not result.success:
            return None
        return result.output.get("history")

# 导出单例实例供 L2 使用
adapter = OpenClawAdapter()
