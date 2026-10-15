#!/usr/bin/env python3
"""从 ONES 重新导出 202606 三份原始数据（签约/POC/异常）。

驱动已登录 ONES 的 Chrome（osascript），点击筛选器 → 更多操作 → 导出工作项。
不使用任何已有文件，导出后保存到 bdms/raw_data_202606/。
"""
import subprocess
import sys
import time
import shutil
from pathlib import Path

DOWNLOAD_CANDIDATES = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Downloads" / "ONES",
]


def run_js(js: str) -> str:
    """在第一个 ONES 标签页执行 JS。"""
    script = f'''
tell application "Google Chrome"
    set t to first tab of first window whose URL contains "ones.bangcle.com"
    execute t javascript "{js}"
end tell
'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return f"ERR: {r.stderr.strip()[:200]}"
    return r.stdout.strip()


def newest_csv(since: float) -> Path | None:
    """查找 since 之后最新修改的 CSV。"""
    best = None
    best_m = since
    for d in DOWNLOAD_CANDIDATES:
        if not d.exists():
            continue
        for f in d.glob("*.csv"):
            m = f.stat().st_mtime
            if m > best_m:
                best = f
                best_m = m
    return best


def click_filter(label_substr: str) -> str:
    js = f'''(function(){{var a=document.querySelectorAll('a');for(var i=0;i<a.length;i++){{var t=(a[i].innerText||'').trim();if(t.indexOf('{label_substr}')!==-1){{a[i].click();return 'ok:'+i;}}}}return 'nf';}})()'''
    return run_js(js)


def click_more_menu() -> str:
    js = """(function(){var e=document.querySelector('[class*=more-menu-icon]');if(e){e.click();return 'ok';}return 'nf';})()"""
    return run_js(js)


def click_export_item() -> str:
    js = """(function(){var items=document.querySelectorAll('[class*=dropdown-menu-item-label]');for(var i=0;i<items.length;i++){var t=(items[i].innerText||'');if(t.indexOf('导出')!==-1&&t.indexOf('工作项')!==-1){items[i].click();return 'ok:'+i;}}return 'nf:'+items.length;})()"""
    return run_js(js)


def click_confirm() -> str:
    js = """(function(){var b=document.querySelectorAll('button');for(var i=0;i<b.length;i++){var t=(b[i].innerText||'').trim();if(t==='确定'||t==='确认'){b[i].click();return 'ok:'+i;}}return 'nf';})()"""
    return run_js(js)


def export_one(label: str, out_name: str, wait_filter: int = 12, wait_dl: int = 25) -> str:
    print(f"\n=== 导出: {label} ===")
    since = time.time()
    r = click_filter(label)
    print(f"  切换筛选器: {r}")
    time.sleep(wait_filter)
    r = click_more_menu()
    print(f"  更多操作: {r}")
    time.sleep(3)
    r = click_export_item()
    print(f"  导出工作项: {r}")
    time.sleep(4)
    r = click_confirm()
    print(f"  确认: {r}")
    print(f"  等待下载 {wait_dl}s...")
    time.sleep(wait_dl)

    f = newest_csv(since)
    if not f:
        return f"   ❌ 未检测到下载 ({label})"
    print(f"   下载: {f} ({f.stat().st_size:,} bytes)")
    dest_dir = Path(__file__).resolve().parent.parent / "raw_data_202606"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / out_name
    shutil.copy2(f, dest)
    print(f"   已保存: {dest} ({dest.stat().st_size:,} bytes)")
    return "   ✅ 完成"


if __name__ == "__main__":
    print("=== 开始 ONES 202606 重新导出 ===")
    # 先确认 ONES 标签页
    title = run_js("document.title")
    print(f"当前 ONES 标签页: {title}")
    if title.startswith("ERR"):
        print("❌ 无法访问 ONES 标签页"); sys.exit(1)

    export_one("签约项目统计", "202606周报-签约项目统计.csv")
    export_one("POC&提前实施统计", "202606周报-POC&提前实施统计.csv")
    export_one("签约项目异常处置", "202606-签约项目异常处置.csv")
    print("\n=== ONES 202606 导出结束 ===")
