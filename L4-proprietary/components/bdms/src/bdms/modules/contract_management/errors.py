"""合同管理错误码体系 — CR-4xxx / CR-5xxx / CR-6xxx。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

对齐 DESIGN-DETAIL §15 错误处理。
"""


class ContractManagementError(Exception):
    """合同管理模块基础异常。"""

    code: str = "CR-0000"
    http_status: int = 500
    user_message: str = "合同管理模块内部错误"

    def __init__(self, message: str = "", user_message: str = ""):
        super().__init__(message or self.user_message)
        if user_message:
            self.user_message = user_message

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "http_status": self.http_status,
            "message": str(self),
            "user_message": self.user_message,
        }


# ─── CR-4xxx：客户端/业务错误 ───

class ContractNotFoundError(ContractManagementError):
    """合同不存在或已被删除。"""
    code = "CR-4001"
    http_status = 404
    user_message = "合同不存在或已被删除"


class InvalidTransitionError(ContractManagementError):
    """当前状态不支持该操作。"""
    code = "CR-4002"
    http_status = 400
    user_message = "当前状态不支持该操作"


class ContractValidationError(ContractManagementError):
    """合同校验失败（必填项缺失等）。"""
    code = "CR-4003"
    http_status = 400
    user_message = "合同校验失败"


class ContractDuplicateError(ContractManagementError):
    """合同编号已存在。"""
    code = "CR-4004"
    http_status = 409
    user_message = "合同编号已存在"


class ContractReadOnlyError(ContractManagementError):
    """合同已归档，只读。"""
    code = "CR-4006"
    http_status = 409
    user_message = "合同已归档，只读，不可修改"


# ─── CR-5xxx：处理/解析错误 ───

class OCRExtractError(ContractManagementError):
    """OCR 识别失败。"""
    code = "CR-5001"
    http_status = 422
    user_message = "OCR 识别失败，请人工录入"


class DocxGenerateError(ContractManagementError):
    """文档生成失败。"""
    code = "CR-5002"
    http_status = 500
    user_message = "文档生成失败"


class ContractParseError(ContractManagementError):
    """合同文本无法解析。"""
    code = "CR-5005"
    http_status = 422
    user_message = "合同文本无法解析"


# ─── CR-6xxx：外部集成错误 ───

class OaFetchError(ContractManagementError):
    """OA 自动获取失败（浏览器自动化异常）。"""
    code = "CR-6001"
    http_status = 502
    user_message = "OA 自动获取失败，请稍后重试或手动录入"


class WecomParseError(ContractManagementError):
    """WeCom 消息解析失败。"""
    code = "CR-6002"
    http_status = 400
    user_message = "消息解析失败，请检查指令格式"


class RelationConflictError(ContractManagementError):
    """合同关联关系冲突。"""
    code = "CR-6003"
    http_status = 409
    user_message = "合同关联关系冲突"


# ─── 错误码查找表 ───

ERROR_CODE_MAP: dict[str, type] = {
    "CR-4001": ContractNotFoundError,
    "CR-4002": InvalidTransitionError,
    "CR-4003": ContractValidationError,
    "CR-4004": ContractDuplicateError,
    "CR-4006": ContractReadOnlyError,
    "CR-5001": OCRExtractError,
    "CR-5002": DocxGenerateError,
    "CR-5005": ContractParseError,
    "CR-6001": OaFetchError,
    "CR-6002": WecomParseError,
    "CR-6003": RelationConflictError,
}


def get_error_by_code(code: str) -> type[ContractManagementError] | None:
    """按错误码获取异常类。"""
    return ERROR_CODE_MAP.get(code)


# ─── 降级链辅助 ───

class DegradationInfo:
    """降级信息记录。"""

    def __init__(self, feature: str, reason: str, fallback: str = ""):
        self.feature = feature
        self.reason = reason
        self.fallback = fallback

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "degraded": True,
            "reason": self.reason,
            "fallback": self.fallback,
        }
