"""
OpenClaw 会话发起适配层
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
实现 L1 抽象接口：会话发起
依赖 OpenClaw sessions_spawn 工具
"""

import sys
from pathlib import Path
# Task is in scripts/orchestrator/scheduler.py
component_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(component_root / "scripts"))
from orchestrator.scheduler import Task

# 工具已经注入到运行时上下文，不需要导入模块
from openclaw.tools import sessions_spawn

class OpenClawTaskSpawner:
    """
    基于 OpenClaw sessions_spawn 工具的任务发起器
    遵循 L1 适配层契约：只实现会话发起，不侵入核心调度逻辑
    """

    def __init__(
        self,
        default_model: Optional[str] = None,
        default_run_timeout: int = 1800,
        context_mode: str = "isolated",
        visible: bool = True,
    ):
        """
        :param default_model: 默认模型（不指定则用原生默认）
        :param default_run_timeout: 默认超时秒
        :param context_mode: 上下文模式（isolated 干净上下文，默认正确）
        :param visible: 是否在侧边栏显示，默认 True（开发可见方便跟踪）
        """
        self.default_model = default_model
        self.default_run_timeout = default_run_timeout
        self.context_mode = context_mode
        self.visible = visible

    def spawn_task(self, task: Task) -> bool:
        """
        发起任务：组装参数调用 sessions_spawn
        遵循协议：任务 description 就是任务，从 TASK.yml 读
        :return: 是否成功发起
        """
        try:
            # 构建任务描述：name + 目标列表 + 依赖说明
            description = f"# {task.name}\n\n"
            description += f"任务ID: {task.id}\n\n"
            description += "## Goals\n\n"
            for goal in task.goals:
                status = goal.get("status", "pending")
                description += f"- [{status}] {goal.get('description', 'Unnamed goal')}\n"

            if task.dependencies:
                description += "\n## Dependencies\n\n"
                description += "已完成前置依赖，可独立执行\n"

            description += "\n请严格按任务卡目标完成，更新状态后结束。"

            # 准备参数
            params = {
                "task": description,
                "task_name": task.id,
                "label": task.name,
                "context": self.context_mode,
                "visible": self.visible,
                "runTimeoutSeconds": self.default_run_timeout,
            }

            if self.default_model:
                params["model"] = self.default_model

            # 调用工具发起
            result = sessions_spawn(**params)

            # 检查结果：accepted 表示成功入队列
            if result and result.get("status") == "accepted":
                print(f"✅ 任务 {task.id} 已发起，sessionKey: {result.get('childSessionKey')}")
                return True
            else:
                print(f"❌ 任务 {task.id} 发起失败: {result}")
                return False

        except Exception as e:
            print(f"💥 任务 {task.id} 发起异常: {str(e)}")
            return False
