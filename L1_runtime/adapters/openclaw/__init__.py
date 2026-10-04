# OpenClaw adapter package

from .openclaw import OpenClawRuntimeAdapter

# 导出单例
adapter = OpenClawRuntimeAdapter()


def get_runtime_adapter() -> OpenClawRuntimeAdapter:
    """获取 OpenClaw RuntimeAdapter 实例。
    
    L2-L4 通过此函数获取运行时适配器，避免直接 import 具体实现。
    """
    return adapter
