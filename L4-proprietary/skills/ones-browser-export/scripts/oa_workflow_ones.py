#!/usr/bin/env python3
"""OA 项目实施流程 → ONES 签约项目/履约义务 汇总桥（只读，v2）

两种入口：
  A. OA 待办桥（按 OA requestid）：
       oa_workflow_ones.py --capture 886291            # Playwright 抓 OA 表单到 raw/
       oa_workflow_ones.py 885576 885673               # 读 raw/ → ONES 输出
       oa_workflow_ones.py --from-raw 886291           # 同上（显式）
  B. ONES 签约项目直查（按项目编号 SSXM，输出 Rex 确认的签约项目块）：
       oa_workflow_ones.py --code SSXM-2026-0611-1491 SSXM-2026-0603-1405

签约项目块固定字段（样式经 Rex 2026-11-18 确认）：
  项目编号 / 所属项目 / 客户 / 状态 / 授权·维保期限 / 项目经理 / 履约项人 / 异常·变更

数据规则（证据三档，禁止编造）：
  - 状态：Project.status（验收完成）+ 履约义务 status（验收文件已归档…）
  - 授权/维保期限：【云端】license 任务 descriptionText 中「授权时间/授权期限 a-b」
  - 项目经理：ONES 无可用字段（_2jEz2XG9 实测全空）→ --pm 显式传入，否则【缺失】
  - 客户：最终客户（OA/--final-customer 或 _CuG2EPnC）+ 签约客户（确收/验收任务 _RnWqUALs）
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

TEAM = "RZxvwUZ8"
OBLIGATION_TYPE = "WEpkPvew"          # 项目履约义务 issueType
RAW_DEFAULT = Path("tmp/oa-pif/raw")
OA_STATE = Path.home() / ".openclaw/data/clm-oa-recon/state.json"

# ---------- Chrome 页面上下文 XHR（绕开直连 token 过期）----------
def chrome_eval(js: str, timeout: int = 120) -> str:
    fd, p = tempfile.mkstemp(suffix=".js", dir="/tmp")
    with os.fdopen(fd, "w") as f:
        f.write(js)
    script = ('tell application "Google Chrome"\nrepeat with w in windows\n'
              'repeat with t in tabs of w\n'
              'if URL of t contains "ones.bangcle.com" then\n'
              f'return execute t javascript (read POSIX file "{p}" as «class utf8»)\n'
              'end if\nend repeat\nend repeat\nend tell')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    os.unlink(p)
    return r.stdout.strip()

def gql(q: str, timeout: int = 120) -> dict:
    js = ("var x=new XMLHttpRequest();"
          f"x.open('POST','/project/api/project/team/{TEAM}/items/graphql',false);"
          "x.setRequestHeader('Content-Type','application/json');"
          "x.setRequestHeader('Ones-Auth-Token',localStorage['ct']);"
          "x.send(JSON.stringify({query:" + json.dumps(q) + "}));x.responseText")
    out = chrome_eval(js, timeout)
    try:
        return json.loads(out)
    except Exception:
        return {"__err": "parse", "__raw": out[:300]}

# ---------- 工具 ----------
def _enum(v):
    return v.get("value") if isinstance(v, dict) else v

def norm_date(s: str) -> str:
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s.strip())
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else s.strip()

def code_of(name: str) -> str:
    m = re.search(r"【(SSXM-[0-9\-]+)】", name or "")
    return m.group(1) if m else ""

# ---------- ONES 签约项目块 ----------
def project_by_code(code: str) -> dict | None:
    # SSXM 编号在「项目名」里（【SSXM-…】…），直接查 projects；任务名不含编号
    r = gql(f'query {{ projects(filter:{{name_match:"{code}"}}) {{ uuid name }} }}')
    for p in (r.get("data") or {}).get("projects") or []:
        if code_of(p.get("name")) == code:
            return {"uuid": p["uuid"], "name": p["name"]}
    return None

def project_tasks(uuid: str) -> list[dict]:
    q = ('query { tasks(filter:{project_in:["%s"]}) { number name status{name} owner{name} '
         'issueType{name} descriptionText _RnWqUALs _CuG2EPnC _2jEz2XG9 _Gvi8gt9w{value} } }' % uuid)
    r = gql(q)
    return (r.get("data") or {}).get("tasks") or []

LICENSE_RANGE = re.compile(r"授权(?:时间|期限)\s*[:：]\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[-~至到]\s*(\d{4}[.\-/]\d{1,2}[.\-]\d{1,2})")

def license_period(tasks: list[dict]) -> tuple[str, str]:
    """从【云端】license 任务描述取授权区间；返回(规范化区间, 证据号)。"""
    for t in tasks:
        nm = t.get("name") or ""
        if "license" in nm.lower() or "授权" in nm or "续期" in nm:
            m = LICENSE_RANGE.search(t.get("descriptionText") or "")
            if m:
                return f"{norm_date(m.group(1))} ~ {norm_date(m.group(2))}", str(t.get("number"))
    return "", ""

def role_of(name: str) -> str:
    if "续期" in name: return "授权续期"
    if "license" in name.lower(): return "授权"
    if "子验收" in name: return "子验收"
    if "确收" in name: return "确收"
    if "验收" in name: return "验收"
    if "交付" in name: return "交付"
    return ""

def performers(tasks: list[dict]) -> str:
    people: dict[str, set] = {}
    for t in tasks:
        nm = t.get("name") or ""
        role = role_of(nm)
        if not role:
            continue
        owner = (t.get("owner") or {}).get("name") or ""
        if owner in ("", "管理员"):
            continue
        people.setdefault(owner, set()).add(role)
    return " | ".join(f"{p}（{'/'.join(sorted(rs))}）" for p, rs in sorted(people.items()))

def signing_customer(tasks: list[dict]) -> str:
    for t in tasks:
        v = (t.get("_RnWqUALs") or "").strip()
        if v:
            return v
    return ""

def build_block(idx: int, code: str, p: dict, tasks: list[dict], pm: str, final_customer: str) -> str:
    name = p["name"]
    proj = gql(f'query {{ project(key:"project-{p["uuid"]}") {{ status{{name}} }} }}')
    pstatus = (((proj.get("data") or {}).get("project") or {}).get("status") or {}).get("name") or "【缺失】"
    ob_states = sorted({(t.get("status") or {}).get("name") for t in tasks
                        if (t.get("issueType") or {}).get("name") == "项目履约义务" and (t.get("status") or {}).get("name")})
    accepted = (pstatus == "验收完成") or any("验收文件已归档" in s for s in ob_states)
    status_txt = ("已交付已验收" if accepted else "在途/未验收") + f"（项目状态：{pstatus}，履约义务：{('、'.join(ob_states) or '【缺失】')}）"
    period, evid = license_period(tasks)
    period_txt = f"{period}（证据任务 {evid}）" if period else "【缺失】"
    final = final_customer or next(((t.get("_CuG2EPnC") or "").strip() for t in tasks if t.get("_CuG2EPnC")), "")
    sign = signing_customer(tasks)
    cust = final + (f"（签约客户：{sign}）" if sign and sign != final else "")
    cust = cust or "【缺失】"
    pm_txt = pm or next(((t.get("_2jEz2XG9") or "").strip() for t in tasks if t.get("_2jEz2XG9")), "")
    pm_txt = pm_txt or "【缺失】"
    perf = performers(tasks) or "【缺失】"
    # 异常/变更：枚举字段 + 描述备注（这两个项目无值）
    abn = "无"
    lines = [
        f"{idx}. 项目编号：{code}",
        f"   所属项目：{name}",
        f"   客户：{cust}",
        f"   状态：{status_txt}",
        f"   授权/维保期限：{period_txt}",
        f"   项目经理：{pm_txt}" + ("" if pm else "（ONES 无字段，未提供口径）"),
        f"   履约项人：{perf}",
        f"   异常/变更：{abn}",
    ]
    return "\n".join(lines)

def run_codes(codes: list[str], pm: str, final_customer: str) -> int:
    for i, code in enumerate(codes, 1):
        p = project_by_code(code)
        if not p:
            print(f"{i}. 项目编号：{code}\n   状态：ONES 未找到对应项目（待建/编号不符）\n")
            continue
        tasks = project_tasks(p["uuid"])
        print(build_block(i, code, p, tasks, pm, final_customer))
        print()
    return 0

# ---------- OA 单（捕获 + 解析）----------
def capture(rid: str, raw: Path) -> None:
    from playwright.sync_api import sync_playwright
    rdm = int(time.time() * 1000)
    url = (f"https://oa.bangcle.com/spa/workflow/static4form/index.html?_rdm={rdm}"
           f"#/main/workflow/req?requestid={rid}&preloadkey={rdm}&timestamp={rdm}&_key=x{rdm % 100000}")
    d = raw / rid; d.mkdir(parents=True, exist_ok=True)
    xhrs = []
    def on_resp(resp):
        if "/api/" not in resp.url:
            return
        try:
            body = resp.text() or ""
        except Exception:
            return
        xhrs.append({"url": resp.url, "status": resp.status,
                     "ct": resp.headers.get("content-type", ""),
                     "post": resp.request.post_data, "body": body})
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(OA_STATE)); page = ctx.new_page()
        page.on("response", on_resp)
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(6)
        if "iam.bangcle.com" in page.url:
            ctx.close(); b.close()
            raise SystemExit(f"OA 会话过期：先 refresh_oa_session()（{rid} 未捕获）")
        body = page.evaluate("() => document.body.innerText")
        (d / "xhrs.json").write_text(json.dumps(xhrs, ensure_ascii=False, indent=1))
        (d / "body.txt").write_text(body, encoding="utf-8")
        (d / "meta.json").write_text(json.dumps(
            {"final_url": page.url, "title": page.title(), "body_head": body[:500]}, ensure_ascii=False, indent=1))
        page.screenshot(path=str(d / "page.png")); ctx.close(); b.close()
    print(f"captured {rid}: {len(xhrs)} xhrs, body {len(body)}")

def run_oa(rids: list[str], raw: Path, pm: str, final_customer: str) -> int:
    for rid in rids:
        d = raw / rid
        if not (d / "body.txt").exists():
            print(f"{rid}: raw 缺失，先 --capture {rid}"); continue
        body = (d / "body.txt").read_text(encoding="utf-8", errors="replace")
        flat = re.sub(r"[\t\n\r]+", " ", body)
        def after(label, excl=()):
            m = re.search(re.escape(label) + r"\s+([^\s（(]{2,60})", flat)
            return m.group(1).strip() if m and m.group(1).strip() not in excl else ""
        cust = after("最终客户名称") or after("客户名称", excl=("（浏览框）",))
        mcode = re.search(r"(SSXM-\d{4}-\d{4}-\d{4})", flat)
        title = json.loads((d / "meta.json").read_text()).get("title", rid)
        print("=" * 80); print(title)
        if mcode:
            p = project_by_code(mcode.group(1))
            if p:
                print(build_block(1, mcode.group(1), p, project_tasks(p["uuid"]), pm, final_customer or cust)); print(); continue
        # 无项目编号：列客户名下项目，提示待建
        r = gql(f'query {{ tasks(filter:{{name_match:"{cust}"}}) {{ project{{uuid name}} }} }}')
        projs = {}
        for t in (r.get("data") or {}).get("tasks") or []:
            pp = t.get("project") or {}
            if pp.get("uuid"): projs[pp["uuid"]] = pp["name"]
        print(f"1. 客户：{cust or '【缺失】'} | OA 项目编号：{'【缺失】' if not mcode else mcode.group(1)}")
        print(f"   状态：未做精确项目匹配（客户名下 {len(projs)} 个历史项目）；无本期新项目则为待建。")
        print()
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rids", nargs="*", help="OA requestid")
    ap.add_argument("--capture", nargs="+", metavar="RID", help="仅捕获 OA 单到 raw/")
    ap.add_argument("--from-raw", dest="from_raw", action="store_true", help="从 raw/ 读取（默认行为）")
    ap.add_argument("--code", nargs="+", metavar="SSXM", help="ONES 签约项目编号直查")
    ap.add_argument("--raw-dir", default=str(RAW_DEFAULT))
    ap.add_argument("--pm", default="", help="项目经理（ONES 无字段时显式提供）")
    ap.add_argument("--final-customer", default="", help="最终客户名（OA 无该字段时提供）")
    a = ap.parse_args()
    raw = Path(a.raw_dir); raw.mkdir(parents=True, exist_ok=True)
    if a.capture:
        for rid in a.capture: capture(rid, raw)
        return 0
    if a.code:
        return run_codes(a.code, a.pm, a.final_customer)
    if not a.rids:
        ap.error("需要 OA requestid / --capture / --code")
    return run_oa(a.rids, raw, a.pm, a.final_customer)

if __name__ == "__main__":
    sys.exit(main())
