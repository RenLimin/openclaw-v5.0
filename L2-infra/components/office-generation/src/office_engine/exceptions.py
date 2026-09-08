"""统一异常类"""


class OfficeEngineError(Exception):
    """Office 引擎基础异常"""
    pass


class OfficeParseError(OfficeEngineError):
    """解析错误"""
    pass


class OfficeFormatError(OfficeEngineError):
    """格式错误"""
    pass


class OfficeUnsupportedError(OfficeEngineError):
    """不支持的操作"""
    pass
