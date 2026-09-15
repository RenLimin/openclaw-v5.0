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

    优先按月份精确匹配 `{month}周报-{kind}.csv`，
    回退到默认文件名。

    kind: "sign" | "poc" | "exception"
    """
    patterns = {
        "sign": [f"{month}周报-签约项目统计.csv", "签约项目统计.csv"],
        "poc": [f"{month}周报-POC&提前实施统计.csv", "poc_提前实施.csv", "POC&提前实施统计.csv"],
        "exception": [f"{month}-签约项目异常处置.csv", "异常处置.csv"],
    }
    base = ones_dir()
    for name in patterns.get(kind, []):
        p = base / name
        if p.exists():
            return p
    return None


def find_revenue_source(month: str) -> Path | None:
    """查找确收对比表（差异分析 xlsx）。"""
    d = month_dir(month)
    if not d.exists():
        return None
    # 匹配 *计划确收*对比表*.xlsx（排除临时文件）
    for p in sorted(d.glob("*确收*对比表*.xlsx")):
        if p.name.startswith("~$"):
            continue
        return p
    for p in sorted(d.glob("*确收*.xlsx")):
        if p.name.startswith("~$"):
            continue
        return p
    return None


def output_path(filename: str) -> Path:
    """输出文件路径。"""
    ensure_dirs()
    return OUTPUT_DIR / filename
