"""
Office 合同审批配置
"""
import os

# 工作空间根目录
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# 数据库路径（L2 持久化适配）
DB_PATH = os.path.join(BASE_DIR, "contracts.db")

# 合同输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 默认甲方（Office 场景下固定为我方公司）
DEFAULT_PARTY_A = "北京梆梆安全科技有限公司"
DEFAULT_PARTY_A_ADDRESS = "北京市海淀区"
DEFAULT_PARTY_A_CONTACT = "商务部"

# 审批角色映射（Office 场景）
OFFICE_APPROVAL_ROLES = {
    1: ["销售经理"],
    2: ["销售经理", "法务审查员"],
    3: ["销售总监", "法务审查员", "财务经理"],
    4: ["VP/CEO", "法务总监", "财务总监"],
}

# 审批 SLA（工作日）
APPROVAL_SLA_DAYS = {
    1: 1,
    2: 2,
    3: 3,
    4: 5,
}

# 合同类型
CONTRACT_TYPES = {
    "tech_service": "技术服务合同",
    "software_license": "软件许可合同",
    "sow": "工作说明书(SOW)",
    "purchase": "采购合同",
    "nda": "保密协议",
}
