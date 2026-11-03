#!/usr/bin/env python3
"""OA（泛微）知识中心产品中心 — 增量文档同步器。

在 fetch_oa_kb.py（全量）已验证的 API 链路上做增量：
  treeNode -> list(sessionkey) -> table/datas(分页，含 doclastmoddate)
            -> docAccList(附件) -> FileDownload(原件)

增量水位：
  - 基线 baseline_date = 2026-09-20（本地知识库文档截止日）
  - 每轮只处理 doclastmoddate > 水位 的文档（strict >，同日重跑不漏）
  - 成功后水位推进到本轮实际见到的最大 doclastmoddate
  - 状态：~/.openclaw/data/product-kb-oa-sync/state.json
  - 清单：~/.openclaw/data/product-kb-oa-sync/manifests/run-<ts>.json

落盘与 DB 基线同构（9.20 基线路径体系，非 oa-sync 副本目录）：
  <root>/<产品线>/<产品目录>/<文件名>
覆盖更新时旧文件备份到 ~/.openclaw/data/product-kb-oa-sync/trash/<run-ts>/，
不直接删（备份目录在 scan root 之外，避免被 scan 误入库）。

用法：
  python3 scripts/oa_incremental_sync.py                 # 增量同步
  python3 scripts/oa_incremental_sync.py --dry-run       # 只统计不变更
  python3 scripts/oa_incremental_sync.py --since 2026-10-01   # 临时指定水位
  python3 scripts/oa_incremental_sync.py --no-advance    # 跑但不推进水位
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time
import urllib.parse
from typing import Optional
from pathlib import Path

import requests

# 复用全量脚本的常量与递归（同目录），不重造
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_oa_kb import (  # noqa: E402
    PRODUCT_LINES, PRODUCT_CENTER_KEY, DEFAULT_ROOT,
    STATE_PATH as OA_STATE_PATH, DOC_BASE, API_BASE,
)

SYNC_DIR = Path(os.path.expanduser("~/.openclaw/data/product-kb-oa-sync"))
SYNC_STATE = SYNC_DIR / "state.json"
MANIFEST_DIR = SYNC_DIR / "manifests"
BASELINE_DATE = "2026-09-20"
PAGE_SIZE = 10
MAX_PAGES = 200


def _find_node(nodes, key):
    for n in nodes:
        if str(n.get("key", "")) == key:
            return n
        r = _find_node(n.get("childs") or [], key)
        if r:
            return r
    return None


def _walk_leaves(childs, bucket, out):
    """递归收集叶子；落盘桶=bucket（产品线映射名或非产品线分支名）。

    与全量脚本一致，只取叶子自身名作目录（中间层级折叠），保证与
    9.20 基线/full-fetch 的落盘布局一致。
    """
    for n in childs:
        name = n.get("name", "")
        key = str(n.get("key", ""))
        if not bool(n.get("haschild", False)):
            out.append({"key": key, "line": bucket, "name": name,
                        "path": "/" + name})
        else:
            _walk_leaves(n.get("childs") or [], bucket, out)
    return out


def collect_all_pc_leaves(tree: list) -> list:
    """产品中心(key=174)下全部叶子（含已下架/其他资料/退市通知）。

    落盘桶规则：
      - 一级分支是已知产品线 -> PRODUCT_LINES 映射目录名
      - 一级分支是非产品线目录（其他产品（已下架）/其他资料）-> 分支自身名
      - 产品中心直属叶子（退市通知）-> 桶 "产品中心"
    """
    pc = _find_node(tree, PRODUCT_CENTER_KEY)
    if pc is None:
        raise IncrSyncError("目录树中找不到产品中心(key=%s)" % PRODUCT_CENTER_KEY)
    out = []
    for branch in pc.get("childs") or []:
        bkey = str(branch.get("key", ""))
        if not bool(branch.get("haschild", False)):
            # 直属叶子（如退市通知）
            out.append({"key": bkey, "line": "产品中心",
                        "name": branch.get("name", ""),
                        "path": "/" + branch.get("name", "")})
            continue
        bucket = PRODUCT_LINES.get(bkey, branch.get("name", ""))
        _walk_leaves(branch.get("childs") or [], bucket, out)
    return out


class IncrSyncError(RuntimeError):
    pass


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def today_str() -> str:
    return _dt.date.today().isoformat()


def load_sync_state() -> dict:
    if SYNC_STATE.exists():
        return json.loads(SYNC_STATE.read_text())
    return {
        "baseline_date": BASELINE_DATE,
        "watermark": BASELINE_DATE,
        "last_sync_date": None,
        "runs": [],
    }


def save_sync_state(state: dict):
    SYNC_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SYNC_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(SYNC_STATE)


class OaIncrSync:
    def __init__(self, root: Path, watermark: str, dry_run: bool = False,
                 advance: bool = True):
        self.root = root
        self.watermark = watermark
        self.dry_run = dry_run
        self.advance = advance
        self.run_ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.max_seen = watermark
        self.stats = {"scanned_docs": 0, "candidates": 0,
                      "added": 0, "updated": 0, "unchanged": 0,
                      "no_attachment": 0, "errors": 0}
        self.manifest = {"run_ts": self.run_ts, "watermark_before": watermark,
                         "watermark_after": watermark, "dry_run": dry_run,
                         "added": [], "updated": [], "unchanged": [],
                         "no_attachment": [], "errors": []}
        self.ses = self._build_session()
        self.trash_dir = SYNC_DIR / "trash" / self.run_ts

    def _build_session(self) -> requests.Session:
        if not OA_STATE_PATH.exists():
            raise IncrSyncError(
                f"OA 会话文件不存在: {OA_STATE_PATH}；请先建立 OA 登录态")
        st = json.loads(OA_STATE_PATH.read_text())
        ses = requests.Session()
        for c in st.get("cookies", []):
            ses.cookies.set(c["name"], c["value"],
                            domain=c.get("domain", "oa.bangcle.com"),
                            path=c.get("path", "/"))
        ses.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": DOC_BASE + "/",
            "x-requested-with": "XMLHttpRequest",
        })
        return ses

    def _get_json(self, path: str, params: dict, retries: int = 3) -> dict:
        qs = urllib.parse.urlencode(params)
        url = f"{API_BASE}{path}?{qs}"
        last = None
        for i in range(retries):
            try:
                r = self.ses.get(url, timeout=30)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = str(e)
            time.sleep(1 + i)
        raise IncrSyncError(f"GET {path} 失败: {last}")

    def _post_form_json(self, path: str, body: str, retries: int = 3) -> dict:
        url = f"{API_BASE}{path}"
        headers = {"Content-Type":
                   "application/x-www-form-urlencoded; charset=UTF-8"}
        last = None
        for i in range(retries):
            try:
                r = self.ses.post(url, data=body, headers=headers, timeout=30)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = str(e)
            time.sleep(1 + i)
        raise IncrSyncError(f"POST {path} 失败: {last}")

    def check_session(self):
        """轻量探活：treeNode 必须返回 treedata，否则视为登录态失效。"""
        obj = self._get_json("/doc/searchlist/treeNode", {
            "menuIds": "2,760", "menuPathIds": "2,760",
            "isFav": "0", "viewcondition": "2", "extendsKey": "0"})
        if "treedata" not in obj:
            raise IncrSyncError("OA 登录态可能失效（treeNode 无 treedata），"
                                "请先刷新 OA 会话")
        return obj["treedata"]

    def get_leaves(self) -> list:
        tree = self.check_session()
        return collect_all_pc_leaves(tree)

    def get_docs_page(self, seccategory: str, page: int) -> tuple[list, dict]:
        lt = self._get_json("/doc/searchlist/list", {
            "menuIds": "2,760", "menuPathIds": "2,760",
            "seccategory": seccategory, "viewcondition": "2",
            "isFav": "0", "usertype": "1"})
        sk = lt.get("sessionkey", "")
        if not sk:
            return [], {}
        body = f"dataKey={sk}&current={page}&sortParams=%5B%5D&"
        obj = self._post_form_json("/ec/dev/table/datas", body)
        return obj.get("datas", []) or [], obj

    def get_attachments(self, docid: str) -> list:
        try:
            j = self._get_json("/doc/acc/docAccList", {"docid": docid})
        except IncrSyncError:
            return []
        out = []
        for row in j.get("dataList", []) or []:
            fid = row.get("imagefileid")
            fname = row.get("imagefilename")
            if fid and fname:
                out.append({"fileid": str(fid), "filename": fname,
                            "size": row.get("filesize", "")})
        return out

    def download_part(self, fileid: str, target: Path) -> Optional[Path]:
        """下到 target 旁的 .part；成功返回 part 路径（不原子落位，由调用方决定）。"""
        url = f"{DOC_BASE}/weaver/weaver.file.FileDownload?fileid={fileid}"
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            r = self.ses.get(url, stream=True, timeout=180)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            head = tmp.read_bytes()[:64].lower()
            if b"<html" in head or b"login" in head:
                tmp.unlink(missing_ok=True)
                return None
            return tmp
        except Exception as e:
            print(f"      下载失败 {fileid}: {e}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return None

    def _backup_old(self, target: Path) -> Path:
        rel = target.relative_to(self.root)
        dest = self.trash_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        target.replace(dest)
        return dest

    def process_doc(self, node: dict, row: dict):
        docid = str(row.get("id", ""))
        moddate = row.get("doclastmoddate", "") or ""
        if moddate and moddate > self.max_seen:
            self.max_seen = moddate

        target_dir = self.root / node["line"] / node["name"]
        acc = self.get_attachments(docid)
        if not acc:
            self.stats["no_attachment"] += 1
            self.manifest["no_attachment"].append(
                {"docid": docid, "name": row.get("keyword", ""),
                 "moddate": moddate, "category": node["name"]})
            return

        seen_names = set()
        for a in acc:
            fname = a["filename"]
            if fname in seen_names:
                base, ext = os.path.splitext(fname)
                fname = f"{base}_{docid}{ext}"
            seen_names.add(fname)
            target = target_dir / fname
            rel = str(Path(node["line"]) / node["name"] / fname)

            if self.dry_run:
                exists = target.exists()
                kind = "updated" if exists else "added"
                self.stats[kind] += 1
                self.manifest[kind].append(
                    {"file": rel, "docid": docid, "moddate": moddate,
                     "size": a["size"], "dry_run": True})
                print(f"  [dry] {'覆盖' if exists else '新增'} {rel} ({a['size']})")
                continue

            if target.exists():
                old_md5 = md5_file(target)
            else:
                old_md5 = None

            part = self.download_part(a["fileid"], target)
            if part is None:
                self.stats["errors"] += 1
                self.manifest["errors"].append(
                    {"file": rel, "docid": docid, "reason": "download_failed"})
                continue

            new_md5 = md5_file(part)
            if old_md5 is None:
                part.replace(target)
                self.stats["added"] += 1
                self.manifest["added"].append(
                    {"file": rel, "docid": docid, "moddate": moddate,
                     "size": a["size"], "md5": new_md5})
                print(f"  ✓ 新增 {rel}")
            elif old_md5 == new_md5:
                # 内容未变：丢弃下载件，不动本地文件
                part.unlink(missing_ok=True)
                self.stats["unchanged"] += 1
                self.manifest["unchanged"].append(
                    {"file": rel, "docid": docid, "moddate": moddate})
            else:
                # 真正更新：先备份旧文件到 .trash，再原子落位新文件
                backup = self._backup_old(target)
                part.replace(target)
                self.stats["updated"] += 1
                self.manifest["updated"].append(
                    {"file": rel, "docid": docid, "moddate": moddate,
                     "old_md5": old_md5, "new_md5": new_md5,
                     "backup": str(backup.relative_to(self.root))})
                print(f"  ✓ 更新 {rel}（旧版已备份）")

    def run(self):
        leaves = self.get_leaves()
        print(f"产品中心叶子目录 {len(leaves)} 个，水位 > {self.watermark}")
        for idx, node in enumerate(leaves, 1):
            seccat = node["key"]
            page = 1
            cat_candidates = 0
            while page <= MAX_PAGES:
                try:
                    datas, obj = self.get_docs_page(seccat, page)
                except IncrSyncError as e:
                    self.stats["errors"] += 1
                    self.manifest["errors"].append(
                        {"category": node["name"], "page": page, "reason": str(e)})
                    print(f"  ✗ 目录 {node['name']} p{page}: {e}", file=sys.stderr)
                    break
                if not datas:
                    break
                for row in datas:
                    self.stats["scanned_docs"] += 1
                    moddate = row.get("doclastmoddate", "") or ""
                    if not moddate or moddate <= self.watermark:
                        continue
                    cat_candidates += 1
                    self.stats["candidates"] += 1
                    try:
                        self.process_doc(node, row)
                    except Exception as e:
                        self.stats["errors"] += 1
                        self.manifest["errors"].append(
                            {"docid": row.get("id", ""), "reason": str(e)})
                try:
                    page_size = int(obj.get("pageSize") or PAGE_SIZE)
                except (TypeError, ValueError):
                    page_size = PAGE_SIZE
                if len(datas) < page_size:
                    break
                page += 1
            if cat_candidates:
                print(f"[{idx}/{len(leaves)}] {node['line']}/{node['name']} "
                      f"候选 {cat_candidates}")
        return self.finalize()

    def finalize(self) -> dict:
        new_watermark = self.max_seen if self.advance else self.watermark
        self.manifest["watermark_after"] = new_watermark
        self.manifest["stats"] = self.stats

        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        mf = MANIFEST_DIR / f"run-{self.run_ts}.json"
        mf.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2))

        state = load_sync_state()
        state["last_sync_date"] = today_str()
        if self.advance and not self.dry_run:
            state["watermark"] = new_watermark
            state.setdefault("runs", []).append({
                "date": today_str(), "run_ts": self.run_ts,
                "watermark_after": new_watermark,
                "added": self.stats["added"],
                "updated": self.stats["updated"],
                "unchanged": self.stats["unchanged"],
                "no_attachment": self.stats["no_attachment"],
                "errors": self.stats["errors"],
                "manifest": str(mf)})
            save_sync_state(state)
        return {"state": state, "manifest_path": str(mf)}


def main():
    ap = argparse.ArgumentParser(description="OA 产品中心文档增量同步")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="落盘根目录")
    ap.add_argument("--since", default=None,
                    help="临时水位 YYYY-MM-DD（默认读状态文件，首跑=基线 2026-09-20）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不变更")
    ap.add_argument("--no-advance", action="store_true", help="不推进水位")
    args = ap.parse_args()

    state = load_sync_state()
    watermark = args.since or state.get("watermark") or BASELINE_DATE
    root = Path(args.root)

    syncer = OaIncrSync(root, watermark, dry_run=args.dry_run,
                        advance=not args.no_advance)
    try:
        result = syncer.run()
    except IncrSyncError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    s = syncer.stats
    print("\n===== 增量同步完成 =====")
    print(f"扫描文档行: {s['scanned_docs']}  候选(>水位): {s['candidates']}")
    print(f"新增: {s['added']}  更新: {s['updated']}  "
          f"内容未变: {s['unchanged']}  无附件: {s['no_attachment']}  "
          f"错误: {s['errors']}")
    print(f"水位: {watermark} -> {syncer.manifest['watermark_after']}"
          f"{' (未推进)' if args.dry_run or args.no_advance else ''}")
    print(f"清单: {result['manifest_path']}")
    if args.dry_run:
        print("（dry-run：未落盘、未推进水位）")


if __name__ == "__main__":
    main()
