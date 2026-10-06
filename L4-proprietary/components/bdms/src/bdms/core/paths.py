"""路径解析 — 统一管理所有外部数据源与输出路径。"""

from pathlib import Path
import os

# ─── 组件根目录 ───
COMPONENT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = COMPONENT_DIR / "config"
DATA_DIR = COMPONENT_DIR / "data"
OUTPUT_DIR = COMPONENT_DIR / "output"

DB_PATH = Path(os.environ.get("BDMS_DB", DATA_DIR / "bdms.db"))


def ensure_dirs() -> None:
    """确保必要目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── 外部数据源 ───

def ones_dir() -> Path:
    """ONES 导出目录（签约/POC/异常 CSV）。"""
    return Path.home() / ".openclaw" / "data" / "ones_exports"


def team_report_dir() -> Path:
    """团队报告根目录（按月分目录，含确收对比表）。"""
    return Path("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告")


def month_dir(month: str) -> Path:
    """指定月份的团队报告目录。"""
    return team_report_dir() / month


# ─── ONES 数据文件解析 ───

def find_ones_file(month: str, kind: str) -> Path | None:
    """查找 ONES 数据文件。

    优先级：
    1. 精确匹配 {YYYYMM}周报-{kind}.csv
    2. 月份回退：搜索前N个月的正确文件（YYYYMM周报-xxx.csv）
    3. 最后回退到通用文件名
    """
    year_prefix = month[:4]
    month_num = int(month[4:6])
    base = ones_dir()

    # 1. 精确匹配当月文件
    month_patterns = {
        "sign": f"{month}周报-签约项目统计.csv",
        "poc": f"{month}周报-POC&提前实施统计.csv",
        "exception": f"{month}-签约项目异常处置.csv",
    }
    p = base / month_patterns.get(kind, "")
    if p.exists():
        return p

    # 2. 月份回退：搜索前N个月的正确文件
    fb_templates = {
        "sign": f"{year_prefix}" + "{mm}" + "周报-签约项目统计.csv",
        "poc": f"{year_prefix}" + "{mm}" + "周报-POC&提前实施统计.csv",
        "exception": f"{year_prefix}" + "{mm}" + "-签约项目异常处置.csv",
    }
    tmpl = fb_templates.get(kind)
    if tmpl:
        for offset in range(1, 12):
            prev_num = month_num - offset
            if prev_num <= 0:
                break
            prev_mm = str(prev_num).zfill(2)
            candidate = base / tmpl.format(mm=prev_mm)
            if candidate.exists():
                return candidate

    # 3. 最后回退到通用文件名
    fallback_names = {
        "sign": "签约项目统计.csv",
        "poc": "poc_提前实施.csv",
        "exception": "异常处置.csv",
    }
    fallback = fallback_names.get(kind)
    if fallback:
        p = base / fallback
        if p.exists():
            return p

    return None


def find_revenue_source(month: str) -> Path | None:
    """查找确收对比表（差异分析 xlsx）。

    优先查找当月目录，若不存在则回退到前一月份目录。
    """
    # 先尝试当月目录
    d = month_dir(month)
    if d.exists():
        for p in sorted(d.glob("*确收*对比表*.xlsx")):
            if p.name.startswith("~$"):
                continue
            return p
        for p in sorted(d.glob("*确收*.xlsx")):
            if p.name.startswith("~$"):
                continue
            return p

    # 回退：按月份降序查找最近的确收源文件
    try:
        month_int = int(month)
        for offset in range(1, 3):
            prev_month = str(month_int - offset).zfill(6)
            prev_dir = month_dir(prev_month)
            if not prev_dir.exists():
                continue
            for p in sorted(prev_dir.glob("*确收*对比表*.xlsx")):
                if p.name.startswith("~$"):
                    continue
                return p
            for p in sorted(prev_dir.glob("*确收*.xlsx")):
                if p.name.startswith("~$"):
                    continue
                return p
    except ValueError:
        pass

    return None


def output_path(filename: str) -> Path:
    """输出文件路径。"""
    ensure_dirs()
    return OUTPUT_DIR / filename
