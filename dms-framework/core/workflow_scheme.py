"""
core/workflow_scheme.py — 工作流方案
WorkFlowScheme: 实体类型 → 状态机名称 的映射表。
支持多套方案切换，L4 业务系统可注册自己的方案。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# WorkflowScheme — 工作流方案
# ---------------------------------------------------------------------------

@dataclass
class WorkflowScheme:
    """工作流方案：实体类型到状态机名称的映射。

    同一套框架可以有多个方案，不同项目/租户可以使用不同方案。
    例如：默认方案用标准流程，敏捷方案用迭代流程。

    mappings 示例:
    {
        "task": "task_flow",
        "milestone": "milestone_flow",
        "deliverable": "approval_flow",
        "risk": "risk_flow",
        "issue": "issue_flow",
    }
    """

    name: str
    description: str = ""
    mappings: dict[str, str] = field(default_factory=dict)  # entity_type -> state_machine_name
    is_default: bool = False

    def get_machine_name(self, entity_type: str) -> str | None:
        return self.mappings.get(entity_type)

    def entity_types(self) -> list[str]:
        return list(self.mappings.keys())

    def add_mapping(self, entity_type: str, machine_name: str) -> None:
        self.mappings[entity_type] = machine_name

    def remove_mapping(self, entity_type: str) -> bool:
        return self.mappings.pop(entity_type, None) is not None


# ---------------------------------------------------------------------------
# 内置方案
# ---------------------------------------------------------------------------

# 默认方案：最基础的工作流
DEFAULT_SCHEME = WorkflowScheme(
    name="default",
    description="默认方案 - 标准交付流程",
    mappings={
        "task": "task_flow",
        "milestone": "milestone_flow",
        "deliverable": "deliverable_flow",
        "risk": "risk_flow",
    },
    is_default=True,
)

# 敏捷方案：适用于 Scrum 项目
AGILE_SCHEME = WorkflowScheme(
    name="agile",
    description="敏捷方案 - Scrum/迭代式交付",
    mappings={
        "task": "agile_task_flow",
        "milestone": "sprint_flow",
        "deliverable": "review_flow",
        "risk": "risk_flow",
        "sprint": "sprint_flow",
        "story": "story_flow",
    },
)

# 瀑布方案：适用于传统交付
WATERFALL_SCHEME = WorkflowScheme(
    name="waterfall",
    description="瀑布方案 - 阶段式交付",
    mappings={
        "task": "waterfall_task_flow",
        "milestone": "phase_flow",
        "deliverable": "formal_approval_flow",
        "risk": "risk_flow",
        "phase": "phase_flow",
    },
)


# ---------------------------------------------------------------------------
# WorkflowSchemeEngine — 方案引擎
# ---------------------------------------------------------------------------

class WorkflowSchemeEngine:
    """工作流方案引擎：管理多套方案 + 切换当前激活方案。

    设计原则：
    - 至少有一套激活方案（默认用 default）
    - L4 可以注册自定义方案
    - 查询实体类型的状态机时，走当前激活方案
    - 支持按项目/租户覆盖方案（通过 project_scheme 映射）
    """

    def __init__(self) -> None:
        self._schemes: dict[str, WorkflowScheme] = {}
        self._active: str = "default"
        self._project_schemes: dict[str, str] = {}  # project_id -> scheme_name
        # 注册内置方案
        self.register(DEFAULT_SCHEME)
        self.register(AGILE_SCHEME)
        self.register(WATERFALL_SCHEME)

    # -- 方案管理 ----------------------------------------------------------

    def register(self, scheme: WorkflowScheme) -> None:
        """注册一套方案。"""
        if scheme.name in self._schemes:
            raise ValueError(f"Workflow scheme '{scheme.name}' already registered")
        self._schemes[scheme.name] = scheme

    def unregister(self, name: str) -> bool:
        """注销方案。不能注销当前激活方案。"""
        if name == self._active:
            raise ValueError(f"Cannot unregister active scheme: {name}")
        return self._schemes.pop(name, None) is not None

    def list_schemes(self) -> list[WorkflowScheme]:
        return list(self._schemes.values())

    def get_scheme(self, name: str) -> WorkflowScheme:
        if name not in self._schemes:
            raise KeyError(f"Workflow scheme '{name}' not found")
        return self._schemes[name]

    # -- 激活方案 ----------------------------------------------------------

    def set_active(self, name: str) -> None:
        """设置全局激活方案。"""
        if name not in self._schemes:
            raise KeyError(f"Workflow scheme '{name}' not found")
        self._active = name

    def get_active(self) -> str:
        return self._active

    # -- 项目级方案 --------------------------------------------------------

    def set_project_scheme(self, project_id: str, scheme_name: str) -> None:
        """为指定项目设置专属方案。"""
        if scheme_name not in self._schemes:
            raise KeyError(f"Workflow scheme '{scheme_name}' not found")
        self._project_schemes[project_id] = scheme_name

    def get_project_scheme(self, project_id: str) -> str:
        """获取项目使用的方案名，没有则返回全局激活方案。"""
        return self._project_schemes.get(project_id, self._active)

    # -- 查询 --------------------------------------------------------------

    def get_machine_name(self, entity_type: str, project_id: str | None = None) -> str:
        """获取指定实体类型使用的状态机名称。

        优先级：项目方案 > 全局激活方案
        找不到时抛出 KeyError。
        """
        scheme_name = self._active
        if project_id and project_id in self._project_schemes:
            scheme_name = self._project_schemes[project_id]

        scheme = self._schemes[scheme_name]
        machine = scheme.get_machine_name(entity_type)
        if machine is None:
            raise KeyError(
                f"Entity type '{entity_type}' not mapped in scheme '{scheme_name}'. "
                f"Available: {scheme.entity_types()}"
            )
        return machine

    def get_entity_types(self, project_id: str | None = None) -> list[str]:
        """获取方案支持的实体类型列表。"""
        scheme_name = self._active
        if project_id and project_id in self._project_schemes:
            scheme_name = self._project_schemes[project_id]
        return self._schemes[scheme_name].entity_types()

    def has_entity_type(self, entity_type: str, project_id: str | None = None) -> bool:
        """检查方案是否支持指定实体类型。"""
        try:
            self.get_machine_name(entity_type, project_id)
            return True
        except KeyError:
            return False
