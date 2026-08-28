"""工时数据采集器

通过浏览器自动化访问工时门户，获取工时填报数据。
注意：工时门户通过 IAM 认证，复用 IAM Cookie。
"""

from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in, get_cookie

WORKHOUR_BASE = "https://workhour.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "workhour_exports"


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def collect_workhour(month: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出工时填报数据

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        导出的 Excel 文件路径
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 未安装")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            print("工时门户 URL 待确认")
            return None

        except Exception as e:
            print(f"工时导出失败: {e}")
            return None
        finally:
            browser.close()


def generate_project_summary(workhour_file: str) -> str:
    """从工时数据生成按项目汇总

    Args:
        workhour_file: 工时填报 Excel 文件路径

    Returns:
        汇总后的 CSV 文件路径
    """
    import pandas as pd

    df = pd.read_excel(workhour_file)
    summary = df.groupby("项目名称")["登记工时"].sum().reset_index()
    summary.columns = ["项目名称", "总工时"]

    output_path = workhour_file.replace(".xlsx", "_summary.csv")
    summary.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"按项目汇总已生成: {output_path}")
    return output_path
