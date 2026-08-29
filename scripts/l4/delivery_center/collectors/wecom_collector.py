"""企业微信数据采集器

通过企业微信在线文档获取确收/验收凭证数据。
数据源：文档 > 共享中心 > 交付中心-财务数据交接记录（按月汇总）
"""

from typing import Optional


# 企业微信在线文档路径
WECOM_DOC_PATH = "文档 > 共享中心 > 交付中心-财务数据交接记录"


def get_sheet_data(doc_url: str) -> Optional[list]:
    """获取企业微信文档数据

    通过 OpenClaw 的 WeCom channel 访问在线文档。

    Args:
        doc_url: 企业微信文档链接

    Returns:
        二维列表（表格数据）
    """
    # TODO: 通过 OpenClaw WeCom channel API 获取在线文档数据
    print(f"企业微信文档获取待实现: {doc_url}")
    return None


def collect_revenue_vouchers(month: str) -> Optional[str]:
    """采集确收凭证数据

    Args:
        month: 报告月份（YYYYMM）

    Returns:
        CSV 文件路径
    """
    print(f"确收凭证采集待实现: {month}")
    return None


def collect_acceptance_vouchers(month: str) -> Optional[str]:
    """采集验收凭证数据

    Args:
        month: 报告月份（YYYYMM）

    Returns:
        CSV 文件路径
    """
    print(f"验收凭证采集待实现: {month}")
    return None
