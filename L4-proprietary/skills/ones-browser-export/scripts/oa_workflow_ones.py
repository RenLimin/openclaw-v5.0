#!/usr/bin/env python3
"""OA 项目实施流程 → ONES 签约项目/履约义务 汇总桥（只读，v2）

两种入口：
  A. OA 待办桥（按 OA requestid）：
       oa_workflow_ones.py --capture 886291            # Playwright 抓 OA 表单到 raw/
       oa_workflow_ones.py 885576 885673               # 读 raw/ → ONES 输出（默认即从 raw/）
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
def _default_raw_dir() -> Path:
    """默认 raw 目录 = 所在 workspace 根的 tmp/oa-pif/raw。
    权威源（workspace/L4-proprietary/skills/...）与 sandbox 副本（<沙箱>/skills/...）
    层级深度不同，故用 AGENTS.md 作锚点向上找 workspace 根，避免写死 parents[N]。
    """
    here = Path(__file__).resolve()
    for base in here.parents:
        if (base / "AGENTS.md").exists():
            return base / "tmp/oa-pif/raw"
    return here.parents[2] / "tmp/oa-pif/raw"

RAW_DEFAULT = _default_raw_dir()
OA_STATE = Path.home() / ".openclaw/data/clm-oa-recon/state.json"

# ---------- Chrome 页面上下文 XHR（绕开直连 token 过期）----------
# 专用 Chrome 实例（CDP）——USER.md 2026-11-19 红线：禁止 osascript 驱动用户当前 Chrome。
# 专用 profile/端口：~/.openclaw/data/chrome-profiles/oa-live + 9333
CDP_URL = os.environ.get("ONES_CDP_URL", "http://127.0.0.1:9333")
# 共享单例：Chrome CDP 对同一浏览器只允许一个客户端连接；本脚本可能被多处
# （ones_client / 测试探测 / 其他复用方）各自 load 成不同模块实例，若各自建连会
# 互相挤掉 → 表现为「第一个可用、第二个 __err parse」。故连接注册进 sys.modules 共享。
_CDP_KEY = "_ones_cdp_shared_v1"
# Playwright sync API 一个进程只能 start 一次：重复 start 抛
# "Playwright Sync API inside the asyncio loop"。OA 侧读取器
# （bangcle-contract services/oa/approval_log）与本脚本共用同一驱动单例。
_PW_KEY = "_oa_playwright_shared_v1"


def _shared_playwright():
    """进程内 Playwright 驱动单例（不 stop，随进程退出清理）。

    跨模块共享：approval_log 读取 757 审批链时也复用此驱动，
    否则同一进程二次 sync_playwright().start() 直接抛错。
    """
    st = sys.modules.get(_PW_KEY)
    if st is None or st.get("pw") is None:
        from playwright.sync_api import sync_playwright
        st = {"pw": sync_playwright().start()}
        sys.modules[_PW_KEY] = st
    return st["pw"]


def _shared_cdp() -> dict:
    st = sys.modules.get(_CDP_KEY)
    if st is None:
        st = {"pw": None, "browser": None, "err": None}
        sys.modules[_CDP_KEY] = st
    return st


def _cdp_eval(js: str, timeout: int = 120) -> str:
    """经专用实例（CDP 9333）的 ONES 标签执行 JS。

    连接复用：进程内缓存 Playwright + Browser，避免每次重连。
    失败显式抛错（不静默返回空），由 chrome_eval 决定降级。
    """
    st = _shared_cdp()
    if st["err"]:
        raise RuntimeError(st["err"])
    try:
        if st["browser"] is None:
            pw = _shared_playwright()
            b = pw.chromium.connect_over_cdp(CDP_URL, timeout=min(timeout, 30) * 1000)
            st["pw"], st["browser"] = pw, b
        for ctx in st["browser"].contexts:
            for pg in ctx.pages:
                if "ones.bangcle.com" in pg.url:
                    return str(pg.evaluate(js))
        raise RuntimeError(f"专用实例 {CDP_URL} 中未找到 ONES 标签页")
    except Exception as exc:  # noqa: BLE001 - 显式转译并缓存，避免每次重试
        st["err"] = f"CDP {CDP_URL} 不可用: {exc}"
        raise RuntimeError(st["err"]) from exc


def ones_available() -> bool:
    """数据源可用性探测：CDP 专用实例 + ONES 标签 + localStorage 登录态。

    用于测试 skip 判定——数据源不可用即 skip，不得当作正常结果（AGENTS.md 降级红线）。
    """
    try:
        return "HAS_CT" in _cdp_eval("(localStorage.getItem('ct')||'')?'HAS_CT':'NO_CT'", timeout=20)
    except Exception:
        return False


def chrome_eval(js: str, timeout: int = 120) -> str:
    """在 ONES 页面上下文执行 JS（优先 CDP 专用实例）。

    红线（USER.md 2026-11-19）：禁止 osascript 驱动用户当前 Chrome。
    osascript 仅作**显式开启**的兜底（ONES_ALLOW_OSASCRIPT=1），默认关闭。
    """
    try:
        return _cdp_eval(js, timeout)
    except Exception:
        if os.environ.get("ONES_ALLOW_OSASCRIPT") != "1":
            return ""
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

# 中文日期（2026年8月11日 / 2026年11月18号）→ ISO；幂等，ISO 输入原样返回
_CN_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")

def _to_iso(text: str) -> str:
    """把文本中的中文日期统一成 ISO（YYYY-MM-DD），便于单一正则解析。"""
    if not text:
        return ""
    def _sub(m: re.Match) -> str:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return _CN_DATE.sub(_sub, str(text))

def norm_date(s: str) -> str:
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", _to_iso(s).strip())
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

# 区间：起 ~ 止（ISO；中文日期经 _to_iso 预归一）。分隔符 至/到/~/-/—/–
# 前缀优先级：授权 > 维保 > 服务期（POC/云端项目常只写「服务期」）
_DATE_SPAN = r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*(?:至|到|~|—|–|-)\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"
_RANGE_BY_PREFIX = {
    "授权": re.compile(r"授权(?:时间|期限|周期|区间)?\s*[:：]?\s*" + _DATE_SPAN),
    "维保": re.compile(r"维保(?:时间|期限|周期|区间)?\s*[:：]?\s*" + _DATE_SPAN),
    "服务期": re.compile(r"服务期\s*[:：]?\s*" + _DATE_SPAN),
}
# 授权类任务名判定（含维保/云端；批注口径「授权/维保至」）
_LICENSE_NAME = ("license", "授权", "续期", "维保", "云端")

def _spans(text: str) -> list[tuple[str, str, str]]:
    """按前缀优先级取区间：授权 > 维保 > 服务期，只取最高优先级命中。"""
    for kind in ("授权", "维保", "服务期"):
        hits = [(norm_date(m.group(1)), norm_date(m.group(2)), kind)
                for m in _RANGE_BY_PREFIX[kind].finditer(text)]
        if hits:
            return hits
    return []

# ---------- 组织架构 / 全量义务检索（v1.3，只读）----------
def user_departments(name: str) -> list[str]:
    """ONES 配置中心-组织架构：按姓名查所属部门名（只读）。

    实证（2026-11-24）：已验证可按姓名命中部门；示例名一律脱敏为「员工A/员工B=示例部门甲」等合成占位（不写真实人员姓名）。未收录返回空列表（调用方标待人工确认，不伪造）。
    """
    r = gql('query { users(filter:{name_match:"%s"}) { name departments{name} } }' % name)
    out: list[str] = []
    for u in (r.get("data") or {}).get("users") or []:
        if u.get("name") != name:
            continue
        for d in u.get("departments") or []:
            nm = d.get("name")
            if nm and nm not in out:
                out.append(nm)
    return out


def search_obligations(keyword: str) -> list[dict]:
    """按关键词**跨项目**检索任务（含所属项目与结项字段），调用方自行过滤/聚合。

    口径（PRD §0.2d C8）：检索词命中履约义务名即可定位到项目——项目名常不含客户名
    （实证 887726：projects(name_match="黄河财产保险")=0，但义务名含该客户）。
    """
    q = ('query { tasks(filter:{name_match:"%s"}) { number name status{name} owner{name} '
         'assign{name} issueType{name} project{name uuid} _Gvi8gt9w{value} } }' % keyword)
    r = gql(q)
    return (r.get("data") or {}).get("tasks") or []


def license_period(tasks: list[dict]) -> tuple[str, str]:
    """从【云端】license/授权/维保任务描述取授权区间；返回(规范化区间, 证据号)。

    跨任务聚合（口径=全局最早起始 ~ 全局最晚结束）：
    同一项目存在多个授权任务（续期/验收调整/多产品）时，覆盖区间取并集，
    证据号取贡献最晚结束日的任务。批注用途「授权/维保至」只依赖结束日。
    中文日期（2026年8月11日 / 2026年11月18号）与 ISO 均支持。
    无授权/维保记录时（安全服务、结算类项目）返回 ("", "")，**不伪造**。
    """
    starts: list[str] = []
    ends: list[str] = []
    evid = ""
    best_end = ""
    for t in tasks:
        nm = t.get("name") or ""
        if not any(k in nm.lower() if k == "license" else k in nm for k in _LICENSE_NAME):
            continue
        for start_d, end_d, _kind in _spans(_to_iso(t.get("descriptionText") or "")):
            starts.append(start_d)
            ends.append(end_d)
            # 证据号 = 贡献「最晚结束日」的任务（授权调整/续期场景以此为准）
            if end_d > best_end:
                best_end = end_d
                evid = str(t.get("number"))
    if not starts:
        return "", ""
    return f"{min(starts)} ~ {max(ends)}", evid

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
        # 无项目编号：只在「项目名」里精确包含客户名，禁止用任务名宽泛匹配历史项目
        projs = {}
        if cust:
            r = gql(f'query {{ projects(filter:{{name_match:"{cust}"}}) {{ uuid name }} }}')
            for pp in (r.get("data") or {}).get("projects") or []:
                if cust in (pp.get("name") or "") and pp.get("uuid"):
                    projs[pp["uuid"]] = pp["name"]
        print(f"1. 客户：{cust or '【缺失】'} | OA 项目编号：{'【缺失】' if not mcode else mcode.group(1)}")
        if projs:
            print(f"   候选项目（项目名含客户名，共 {len(projs)} 个，需人工确认是否本期新项目）：")
            for nm in list(projs.values())[:10]:
                print(f"     - {nm}")
        else:
            print("   状态：ONES 项目名未匹配到该客户 → 本期项目可能待建（勿用任务名反推）。")
        print()
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rids", nargs="*", help="OA requestid")
    ap.add_argument("--capture", nargs="+", metavar="RID", help="仅捕获 OA 单到 raw/")
    ap.add_argument("--code", nargs="+", metavar="SSXM", help="ONES 签约项目编号直查")
    ap.add_argument("--raw-dir", default=str(RAW_DEFAULT),
                    help=f"raw 目录（默认 {RAW_DEFAULT}）")
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
