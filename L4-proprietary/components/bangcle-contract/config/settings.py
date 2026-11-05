"""Bangcle 合同审查 MVP 配置。"""
import os

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.abspath(os.path.join(COMPONENT_DIR, "..", "..", ".."))

COMPONENT_DB = os.path.join(COMPONENT_DIR, "data", "bangcle_contract.db")
PRODUCT_KB_PATH = os.path.join(
    WORKSPACE_ROOT, "L4-proprietary", "components", "product-kb", "data", "product_kb.db"
)

MATCH_THRESHOLD = 0.5      # ContractMatcher 命中阈值
SATISFIED_SCORE = 0.85     # 高于此且无 alert 才算 satisfied
PARTIAL_SCORE = 0.5

SEMANTIC_ENABLED = False   # 本期写死关闭（合同原文不外发）

DISCLAIMER = (
    "本报告由 AI 基于受控规则库辅助生成，不构成法律意见，"
    "合同原文未外发，最终以法务审核为准。"
)

SUPPORTED_FORMATS = [
    "pdf", "docx", "doc", "xlsx", "pptx", "txt", "md", "html", "htm",
    "png", "jpg", "jpeg", "tif", "tiff",
]
