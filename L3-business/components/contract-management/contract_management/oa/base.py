"""
OA 连接器抽象基类 — L3 厂商中立契约
=====================================

仅定义接口，不提供任何实现、不做网络/文件调用。
具体厂商实现放在更上层的集成层。

process_instance_id 在不同系统中可承载不同主键，
本层仅以字符串透传，不解释其语义。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class OaProvider(ABC):
    """OA 系统连接器抽象。实现方必须自行处理会话、鉴权与幂等。"""

    @abstractmethod
    def get_contract_attachment(self, process_instance_id: str) -> Any:
        """获取合同流程/记录的附件。返回上层集成层定义的附件对象。"""
        raise NotImplementedError

    @abstractmethod
    def query_process(self, process_instance_id: str) -> Any:
        """查询流程/记录状态信息。"""
        raise NotImplementedError

    @abstractmethod
    def push_result(self, process_instance_id: str, action: str,
                    comment: str, approver: str) -> bool:
        """把审批结果回推 OA。同意/驳回等高影响动作的实际决策须由人完成。"""
        raise NotImplementedError

    @abstractmethod
    def register_callback(self, handler: Callable[..., Any]) -> None:
        """注册 OA 事件回调处理器。"""
        raise NotImplementedError
