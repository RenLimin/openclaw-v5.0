"""
OCR 后端引擎集合

提供后端自动发现与注册机制。
"""
from .base import OCRBackend

# 注册表：后端名称 -> 后端类
_BACKEND_REGISTRY = {}


def register_backend(name: str):
    """装饰器：注册 OCR 后端"""
    def decorator(cls):
        _BACKEND_REGISTRY[name] = cls
        return cls
    return decorator


def get_backend_class(name: str):
    """获取后端类（按名称）"""
    return _BACKEND_REGISTRY.get(name)


def list_available_backends():
    """列出所有已注册的后端名称"""
    return list(_BACKEND_REGISTRY.keys())


def discover_backends(lang: str = "chi_sim+eng") -> list:
    """自动发现系统中可用的 OCR 后端

    尝试加载所有已注册的后端，返回可用的实例列表（按优先级排序）。
    加载失败的后端会被跳过，不会抛出异常。

    Args:
        lang: 目标语言代码

    Returns:
        可用后端实例列表，按 priority 升序排列（priority 越小越优先）
    """
    available = []
    for name, cls in _BACKEND_REGISTRY.items():
        try:
            backend = cls()
            if backend.supports_lang(lang):
                if backend.load(lang):
                    available.append(backend)
        except Exception:
            continue  # 加载失败，跳过
    available.sort(key=lambda b: b.priority)
    return available


# 注册内置后端（延迟导入，避免未安装依赖时导入失败）
def _register_builtin_backends():
    """注册所有内置后端（类注册，不加载模型）"""
    try:
        from .tesseract import TesseractBackend
        _BACKEND_REGISTRY["tesseract"] = TesseractBackend
    except ImportError:
        pass

    try:
        from .rapidocr import RapidOCRBackend
        _BACKEND_REGISTRY["rapidocr"] = RapidOCRBackend
    except ImportError:
        pass

    try:
        from .paddleocr import PaddleOCRBackend
        _BACKEND_REGISTRY["paddleocr"] = PaddleOCRBackend
    except ImportError:
        pass

    try:
        from .easyocr import EasyOCRBackend
        _BACKEND_REGISTRY["easyocr"] = EasyOCRBackend
    except ImportError:
        pass


# 模块导入时只注册类，不加载模型
_register_builtin_backends()

__all__ = [
    "OCRBackend",
    "register_backend",
    "get_backend_class",
    "list_available_backends",
    "discover_backends",
]
