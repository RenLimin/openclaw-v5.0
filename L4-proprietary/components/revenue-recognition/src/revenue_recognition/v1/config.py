"""路径与常量配置"""

from pathlib import Path

# 手工报表路径
MANUAL_REPORT_PATH = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)

# 模块目录
MODULE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = MODULE_DIR / "data"
OUTPUT_DIR = MODULE_DIR / "output"
DB_PATH = DATA_DIR / "revenue.db"

# Sheet 名
SHEET_PLAN_DRAFT = "计划确收底稿"
SHEET_BUDGET_EXEC = "预算执行表"
SHEET_SUMMARY = "汇总"
SHEET_SUMMARY_ANALYSIS = "汇总分析"
SHEET_MONTHLY_RECORD = "月度汇总记录"
SHEET_PERFORMANCE_RECORD = "履约汇总记录"
SHEET_VARIANCE = "确收差异分析"
SHEET_TREND = "预算趋势分析"
SHEET_LEGEND = "图例"
SHEET_REBUILD_PERF = "重拆履约"

# 预算执行表 列映射 (列号从1开始)
class BudgetCol:
    CATEGORY = 1        # A 分类(递延/新签)
    CONTRACT_NO = 2     # B 合同编号
    CONTRACT_NO_CAL = 3 # C 合同编号（校准）
    CUSTOMER = 4        # D 客户名称
    END_USER = 5        # E 最终用户名称
    SIGN_SUBJECT = 6    # F 签约主体
    ARCHIVE_MONTH = 7   # G 合同归档月份
    PERF_ID_BUDGET = 8  # H 履约ID（预算）
    PERF_DETAIL = 9     # I 履约明细(预算）
    PERF_ID = 10        # J 履约ID
    REV_METHOD = 11     # K 收入确认方法
    PERF_AMOUNT = 12    # L 单项履约义务金额
    REV_PRIOR = 13      # M 截止20251231已确收金额
    REV_FUTURE = 14     # N 2026年及以后计划确收
    NO_PLAN = 15        # O 年初-未立项&项目异常未计划确收
    UNREV_PRIOR = 16    # P 截止20251231未确收金额
    UNREV_ADJ = 17      # Q 截止20251231未确收金额（调整）
    PLAN_START = 18     # R 计划开始时间
    PLAN_END = 19       # S 计划结束时间
    PLAN_DONE = 20      # T 计划完成时间
    # U(21)-AF(32): 202601-202612 月度计划
    MONTH_START = 21    # U = 202601
    MONTH_END = 32      # AF = 202612
    YEAR_EST = 33       # AG 2026年预计
    H1_PLAN = 34        # AH 202601-06预计
    H1_ACTUAL = 35      # AI 202601-06确收
    H1_AHEAD = 36       # AJ 202601-06提前完成
    H1_BEHIND = 37      # AK 202601-06滞后未完成
    # AL(38)-AQ(43): 202601-202606 月度实际
    ACTUAL_START = 38   # AL = 202601
    ACTUAL_END = 43     # AQ = 202606
    DISAPPEAR_2026 = 44       # AR 2026消失金额
    DISAPPEAR_FUTURE = 45     # AS 2026年及以后消失金额
    DISAPPEAR_NOTE = 46        # AT 消失备注
    REBUILD_PERF = 47           # AU 重拆履约，提前和滞后同增

# 计划确收底稿 列映射
class PlanCol:
    NOTE = 1            # A 年初-填写说明
    INIT_EST_DATE = 2   # B 年初-交付预计完成时间
    EST_DATE = 3        # C 交付预计完成时间
    CONTRACT_NO = 4     # D 合同编号
    ARCHIVE_MONTH = 5   # E 合同归档月份
    CONTRACT_NO2 = 6    # F 合同编号
    PROD_SEQ = 7        # G 标准产品服务名称序号
    PERF_ID = 8         # H 履约ID
    BUDGET_PERF_ID = 9  # I 对应预算履约ID
    DEPT = 10           # J 现行部门
    CONTRACT_NAME = 11  # K 合同名称
    CUSTOMER = 12       # L 客户名称
    END_USER = 13       # M 最终用户名称
    CONTRACT_NOTE = 14  # N 合同备注
    OPS_NOTE = 15       # O 合同操作备注
    TAX_RATE = 16       # P 产品服务税率
    SIGN_DATE = 17      # Q 合同签订日期
    CONTRACT_START = 18 # R 合同起始时间
    CONTRACT_END = 19   # S 合同结束时间
    SERVICE_MONTHS = 20 # T 服务期限（月）
    CONTRACT_TYPE = 21  # U 合同类型
    VERSION_TYPE = 22   # V 合同版本类型
    GIFT = 23           # W 是否赠送项项目
    PROD_CATEGORY = 24  # X 标准产品类别
    PROD_NAME = 25      # Y 合同产品服务名称
    PERF_DETAIL = 26    # Z 履约义务明细
    STD_PROD_NAME = 27  # AA 标准产品服务名称
    REV_SUBJECT = 28    # AB 收入对应科目
    TAX_SUBJECT = 29    # AC 末级税金科目名称
    PRICE_BASIS = 30    # AD 价格拆分依据
    ACCEPT_TYPE = 31    # AE 验收文件类型
    ACCEPT_TERM = 32    # AF 合同约定的验收条款
    PAYMENT_TERM = 33   # AG 合同约定的收款节奏
    REV_METHOD = 34     # AH 收入确认方法
    NO_EXEC_REASON = 35 # AI 履约不执行原因
    QTY_UNIT = 36       # AJ 数量单位
    QTY = 37            # AK 数量
    CONTRACT_AMOUNT = 38    # AL 合同金额
    CONFIRM_AMOUNT = 39     # AM 确认合同额
    PERF_AMOUNT = 40        # AN 单项履约义务金额
    PLAN_PERF_AMOUNT = 41   # AO 计划履约金额
    REV_BEFORE_2025 = 42    # AP 截止20251231已确收
    REV_2026_FUTURE = 43    # AQ 2026年及以后计划确收
    PLAN_DISAPPEAR = 44      # AR 计划-消失金额
    DISAPPEAR_REASON = 45    # AS 消失原因

# 汇总输出列
SUMMARY_MONTHS = [f"2026{m:02d}" for m in range(1, 13)]
