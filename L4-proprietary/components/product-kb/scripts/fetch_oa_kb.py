#!/usr/bin/env python3
"""OA（泛微）知识中心 — 产品中心全量文档抓取器。

链路（2026-11-02 侦察实证）：
  1. IAM SSO 登录（复用 bangcle-contract refresh_oa_session，避免重造）
  2. GET /api/doc/searchlist/treeNode  -> 全目录树（产品中心 key=174，114 个叶子）
  3. GET /api/doc/searchlist/list      -> 每节点取 sessionkey（列表会话）
  4. POST /api/ec/dev/table/datas      -> 用 sessionkey 作 dataKey 取文档列表（分页）
  5. 每篇文档 -> 详情页 /api/doc/detail/basicInfo 取 docMain 标题
  6. 附件表 datas -> imagefileid（附件 fileid）
  7. GET /weaver/weaver.file.FileDownload?fileid=<数字> -> 直接下载原件（无需加密 token）

落盘：<目标根>/oa-sync/<产品线>/<子目录>/<文件名>
之后可被 product-kb scan_docs.sh 增量扫描入库。

用法：
  python3 scripts/fetch_oa_kb.py                     # 全量同步产品中心
  python3 scripts/fetch_oa_kb.py --dry-run           # 只统计不下载
  python3 scripts/fetch_oa_kb.py --root /path/to/dir # 自定义落盘根
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# 允许复用 bangcle-contract 的 OA 会话能力（复用不重造）
CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "bangcle-contract"
if str(CONTRACT_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTRACT_ROOT))
CONTRACT_OA_DIR = CONTRACT_ROOT / "services" / "oa"
if str(CONTRACT_OA_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACT_OA_DIR))

STATE_PATH = Path(os.path.expanduser("~/.openclaw/data/clm-oa-recon/state.json"))
DEFAULT_ROOT = Path(os.path.expanduser("~/Bangcle Workspace/07. Bangcle Prod"))
PRODUCT_CENTER_KEY = "174"  # 产品中心
DOC_BASE = "https://oa.bangcle.com"
API_BASE = DOC_BASE + "/api"

# 产品线 key -> 目录名（映射自 tree，用于落盘组织）
PRODUCT_LINES = {
    "798": "安全保护产品线",
    "799": "安全监测产品线",
    "800": "安全检测产品线",
    "928": "安全服务产品线",
    "1998": "内容安全产品线",
    "2000": "物联网服务产品线",
}


class OAKmError(RuntimeError):
    pass


def ensure_session() -> bool:
    """确保 OA 会话有效（state.json 可用则直接用，否则 IAM 重登）。"""
    if STATE_PATH.exists():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True,
                                             env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"})
                ctx = browser.new_context(storage_state=str(STATE_PATH))
                page = ctx.new_page()
                # 探测：调一个轻接口，看是否跳登录
                r = page.goto(DOC_BASE + "/wui/index.html#/main/document/search?menuIds=2,760",
                              wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                ok = "iam.bangcle.com" not in page.url
                browser.close()
                if ok:
                    return True
        except Exception:
            pass
    # 会话失效 -> IAM 重登（复用 bangcle-contract 的 refresh_oa_session）
    try:
        from services.oa.browser_fallback import refresh_oa_session
        return refresh_oa_session()
    except Exception as e:
        print(f"⚠️ 会话重登失败: {e}", file=sys.stderr)
        return False


class OAKmFetcher:
    def __init__(self, root: Path, dry_run: bool = False):
        self.root = root
        self.dry_run = dry_run
        self._pw = None
        self._ctx = None
        self._page = None
        self.stats = {"docs": 0, "files": 0, "bytes": 0, "skipped": 0, "errors": 0}

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"})
        # 关键：必须加载 state.json 里的 cookie，否则未登录访问 SPA 会被重定向到
        # iam.bangcle.com，跨域 fetch API -> "Failed to fetch"
        ctx_kw = {}
        if STATE_PATH.exists():
            ctx_kw["storage_state"] = str(STATE_PATH)
        self._ctx = self._browser.new_context(**ctx_kw)
        self._page = self._ctx.new_page()
        self._page.goto(DOC_BASE + "/wui/index.html#/main/document/search?menuIds=2,760",
                        wait_until="domcontentloaded", timeout=60000)
        try:
            self._page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        self._page.wait_for_timeout(8000)
        # 真实 API 探测（逐字复制已验证成功的测试脚本逻辑）
        last_err = None
        for attempt in range(3):
            try:
                url = (API_BASE + "/doc/searchlist/treeNode?"
                       "menuIds=2%2C760&menuPathIds=2%2C760&isFav=0&viewcondition=2&extendsKey=0")
                t = self._page.evaluate("""async (u)=>{
                  try {
                    const r = await fetch(u,{credentials:'include'});
                    const t = await r.text();
                    return '__STATUS__:' + r.status + '__BODY__:' + t;
                  } catch(e) { return '__FETCHERR__:'+e.message; }
                }""", url)
                if t.startswith("__FETCHERR__"):
                    raise OAKmError("会话失效（fetch 失败: %s）" % t[:100])
                parts = t.split("__BODY__:", 1)
                status = parts[0].replace("__STATUS__:", "")
                body = parts[1] if len(parts) > 1 else ""
                if status != "200" or not body:
                    raise OAKmError("会话失效（status=%s body_len=%d）" % (status, len(body)))
                j = json.loads(body)
                if not isinstance(j, dict) or "treedata" not in j:
                    raise OAKmError("会话失效（API 返回异常，可能已跳登录）")
                return
            except (json.JSONDecodeError, OAKmError) as e:
                last_err = e
                time.sleep(3)
        raise OAKmError("会话失效（API 探测失败: %s）" % last_err)

    def stop(self):
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None

    def _get(self, path: str, params: dict, retries: int = 3) -> str:
        import urllib.parse
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
        url = f"{API_BASE}{path}?{qs}&__random__={int(time.time()*1000)}"
        last = None
        for i in range(retries):
            try:
                t = self._page.evaluate("""async (u)=>{
                  try {
                    const r = await fetch(u,{credentials:'include'});
                    const txt = await r.text();
                    return '__STATUS__:' + r.status + '__BODY__:' + txt;
                  } catch(e) { return '__FETCHERR__:'+e.message; }
                }""", url)
            except Exception as e:
                last = e
                time.sleep(2)
                continue
            if t.startswith("__FETCHERR__"):
                last = OAKmError(t[:120])
                time.sleep(2)
                continue
            parts = t.split("__BODY__:", 1)
            status = parts[0].replace("__STATUS__:", "")
            body = parts[1] if len(parts) > 1 else ""
            if status == "200" and body:
                return body
            last = OAKmError("status=%s body_len=%d" % (status, len(body)))
            time.sleep(2)
        raise OAKmError("API 请求失败 %s: %s" % (path, last))

    def _post_form(self, path: str, body: str) -> str:
        return self._page.evaluate(
            """async ({url, body}) => {
              const r = await fetch(url, {credentials:'include', method:'POST',
                headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}, body});
              return await r.text();
            }""", {"url": API_BASE + path, "body": body})

    def get_tree(self) -> list:
        """全量目录树。"""
        t = self._get("/doc/searchlist/treeNode",
                      {"menuIds": "2,760", "menuPathIds": "2,760",
                       "isFav": "0", "viewcondition": "2", "extendsKey": "0"})
        return json.loads(t).get("treedata", [])

    def collect_leaves(self, nodes, in_product=False, path="", prod_line=None):
        """收集产品中心下所有叶子节点（带产品线归属）。委托统一递归函数。"""
        return collect_leaves_safe(nodes, in_product, path, prod_line)

    def get_docs(self, seccategory: str, page_num: int = 1) -> dict:
        """取一个目录的一页文档（list 换 sessionkey -> datas）。"""
        lt = self._get("/doc/searchlist/list",
                       {"menuIds": "2,760", "menuPathIds": "2,760",
                        "seccategory": seccategory, "viewcondition": "2",
                        "isFav": "0", "usertype": "1"})
        sk = json.loads(lt).get("sessionkey", "")
        if not sk:
            return {"datas": [], "total": 0}
        body = f"dataKey={sk}&current={page_num}&sortParams=%5B%5D&"
        try:
            obj = json.loads(self._post_form("/ec/dev/table/datas", body))
        except Exception:
            return {"datas": [], "total": 0}
        return obj

    def get_doc_title(self, docid: str) -> str:
        """详情页标题。"""
        try:
            t = self._get("/doc/detail/basicInfo", {"docid": docid})
            d = json.loads(t)
            return d.get("data", {}).get("docMain", "") or d.get("data", {}).get("docSubject", "")
        except Exception:
            return ""

    def get_attachments(self, docid: str) -> list:
        """附件列表：GET /api/doc/acc/docAccList -> dataList（无需开详情页）。

        每个附件含 imagefileid / imagefilename / filesizenum / isMainFile。
        """
        try:
            t = self._get("/doc/acc/docAccList", {"docid": docid})
            j = json.loads(t)
        except Exception:
            return []
        acc = []
        for row in j.get("dataList", []) or []:
            fid = row.get("imagefileid")
            fname = row.get("imagefilename")
            if fid and fname:
                acc.append({"fileid": str(fid), "filename": fname,
                            "size": row.get("filesize", ""),
                            "sizenum": row.get("filesizenum", "")})
        return acc

    def _build_http_session(self):
        """从 state.json 提取 cookie，构建 requests.Session 直下。"""
        import requests as req
        ses = req.Session()
        try:
            st = json.loads(STATE_PATH.read_text())
            for c in st.get("cookies", []):
                ses.cookies.set(c["name"], c["value"],
                                domain=c.get("domain", ""), path=c.get("path", "/"))
        except Exception:
            pass
        ses.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        return ses

    def download(self, fileid: str, target: Path) -> bool:
        """下载附件到目标路径（requests 直下，避免 browser evaluate base64 编码）。"""
        if not hasattr(self, "_http_ses"):
            self._http_ses = self._build_http_session()
        url = f"{DOC_BASE}/weaver/weaver.file.FileDownload?fileid={fileid}"
        try:
            resp = self._http_ses.get(url, stream=True, timeout=120)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            target.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with open(target, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            # 防登录页误存
            head = target.read_bytes()[:64]
            if b"<html" in head.lower() or b"login" in head.lower():
                target.unlink()
                self.stats["errors"] += 1
                return False
            self.stats["bytes"] += total
            return True
        except Exception as e:
            print(f"    下载失败 {fileid}: {e}")
            self.stats["errors"] += 1
            return False

    def fetch_docs_in_category(self, node: dict):
        """抓一个叶子目录的全部文档。"""
        seccat = node["key"]
        rel_dir = Path(node["line"]) / node["name"]
        target_dir = self.root / "oa-sync" / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        seen_names = set()

        # 分页拉文档
        page_num = 1
        while True:
            obj = self.get_docs(seccat, page_num)
            datas = obj.get("datas", [])
            if not datas:
                break
            for row in datas:
                docid = str(row.get("id", ""))
                if not docid:
                    continue
                self.stats["docs"] += 1
                # 附件（docAccList 自带文件名，不再逐篇调 get_doc_title）
                acc = self.get_attachments(docid)
                if not acc:
                    # 有些文档正文就是内容（html），无附件；跳过但计数
                    continue
                for a in acc:
                    fname = a["filename"]
                    # 重名避免
                    base, ext = os.path.splitext(fname)
                    fname = f"{base}.{ext}" if ext else f"{base}.bin"
                    if fname in seen_names:
                        fname = f"{base}_{docid}{ext}"
                    seen_names.add(fname)
                    target = target_dir / fname
                    if target.exists() and target.stat().st_size > 0:
                        self.stats["skipped"] += 1
                        continue
                    if self.dry_run:
                        self.stats["files"] += 1
                        continue
                    ok = self.download(a["fileid"], target)
                    if ok:
                        self.stats["files"] += 1
                        print(f"  ✓ [{node['line']}/{node['name']}] {fname} ({a['size']})")
                    else:
                        print(f"  ✗ [{node['line']}/{node['name']}] {fname}")
            # 分页判断：该接口不返回总数字段，按「本页行数 < pageSize」判定末页
            try:
                page_size = int(obj.get("pageSize") or 10)
            except (TypeError, ValueError):
                page_size = 10
            if len(datas) < page_size:
                break
            page_num += 1
            if page_num > 200:  # 防死循环
                break

    def run(self):
        tree = self.get_tree()
        leaves = self.collect_leaves(tree)
        print(f"产品中心叶子目录: {len(leaves)}")
        for leaf in leaves:
            try:
                self.fetch_docs_in_category(leaf)
            except Exception as e:
                print(f"  ✗ 目录 {leaf['path']} 失败: {e}", file=sys.stderr)
                self.stats["errors"] += 1
        return self.stats


# treeNode childs 递归的辅助（定义在 collect_leaves 前使用）
def collect_leaves_safe(childs, in_product, path, prod_line):
    # 递归收集（统一入口：174 产品中心开关 + 产品线归属都在此生效）
    out = []
    for n in childs:
        name = n.get("name", "")
        key = str(n.get("key", ""))
        hc = bool(n.get("haschild", False))
        cur_path = path + "/" + name
        cur_in = in_product or (key == PRODUCT_CENTER_KEY)
        cur_line = prod_line
        if key in PRODUCT_LINES:
            cur_line = PRODUCT_LINES[key]
        if cur_in and not hc and cur_line:
            out.append({"key": key, "path": cur_path, "name": name, "line": cur_line})
        childs2 = n.get("childs") or []
        if childs2:
            out += collect_leaves_safe(childs2, cur_in, cur_path, cur_line)
    return out


def main():
    ap = argparse.ArgumentParser(description="OA 知识中心产品中心全量抓取")
    ap.add_argument("--dry-run", action="store_true", help="只统计不下载")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="落盘根目录")
    ap.add_argument("--no-login", action="store_true", help="不自动重登（直接失败）")
    args = ap.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    # 会话准备：进程最前 refresh（此时无 Playwright 实例，避免 Sync API 冲突）
    # 若 --no-login 则跳过，直接试 state
    if not args.no_login:
        from services.oa.browser_fallback import refresh_oa_session
        if not refresh_oa_session():
            print("❌ 无法建立 OA 会话", file=sys.stderr)
            sys.exit(1)

    fetcher = OAKmFetcher(root, dry_run=args.dry_run)
    try:
        try:
            fetcher.start()
        except OAKmError:
            print("⚠️ 会话探测失败，尝试重登…", file=sys.stderr)
            fetcher.stop()
            from services.oa.browser_fallback import refresh_oa_session
            if not refresh_oa_session():
                print("❌ 无法建立 OA 会话", file=sys.stderr)
                sys.exit(1)
            fetcher = OAKmFetcher(root, dry_run=args.dry_run)  # 重建（浏览器已关）
            fetcher.start()
        stats = fetcher.run()
        print(f"\n完成: 文档 {stats['docs']} 篇 / 文件 {stats['files']} 个 / "
              f"{stats['bytes']/1024/1024:.1f} MB / 跳过 {stats['skipped']} / 错误 {stats['errors']}")
        if args.dry_run:
            print("（dry-run 未下载）")
    finally:
        fetcher.stop()


if __name__ == "__main__":
    main()
