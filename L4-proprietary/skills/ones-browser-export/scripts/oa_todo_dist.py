#!/usr/bin/env python3
"""OA 待办全量分布统计（只读）

用途：回答「我名下待办按流程怎么分布、目标流程有几条」，并区分两个口径：
  - 树/计数口径：doingBaseInfo.treedata + doingCountInfo.treecount
      → 只含**当前启用的流程节点**（如 type_40 → wf_840）
  - 列表口径：/api/ec/dev/table/datas 全量分页
      → 含**历史流程定义的遗留待办**（如 wf_778/wf_752 同名旧「销售合同验收文件归档流程」）

⚠️ 两个口径数字对不上是**正常**的，原因见 references/oa-workflow-fields.md 第七节。
⚠️ dataKey 必须用当次页面 POST 捕获的，硬编码旧值会失败（会话绑定）。

用法：
  python3 scripts/oa_todo_dist.py                 # 打印分布 + 目标流程明细
  python3 scripts/oa_todo_dist.py --save          # 额外落盘 tmp/oa-pif/full_todo_items.json
  python3 scripts/oa_todo_dist.py --max-pages 12  # 限制分页数（默认 20）
前置：OA storage_state（~/.openclaw/data/clm-oa-recon/state.json），过期先 refresh_oa_session()。
"""
from __future__ import annotations
import argparse, json, re, sys, time
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

STATE = Path.home() / ".openclaw/data/clm-oa-recon/state.json"
URL = "https://oa.bangcle.com/spa/workflow/index_mobx.jsp#/main/workflow/listDoing"
API = "/api/ec/dev/table/datas"

TARGETS = [
    ("820", "PoC需求申请流程"),
    ("815", "提前实施需求申请流程"),
    ("916", "销售合同下单流程（数据审核触发）"),
    ("840", "销售合同验收文件归档流程"),
    ("757", "销售合同审核流程"),
    ("923", "差旅申请单"),
    ("778", "销售合同验收文件归档流程（旧定义）"),
    ("752", "销售合同验收文件归档流程（旧定义）"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="落盘 tmp/oa-pif/full_todo_items.json")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--out", default="tmp/oa-pif/full_todo_items.json")
    a = ap.parse_args()

    items: list[dict] = []
    seen: set = set()
    st = {"dataKey": None}
    tree = {"nodes": [], "counts": {}}

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE))
        page = ctx.new_page()

        def on_req(r):
            if API in r.url and r.post_data:
                m = re.search(r"dataKey=([^&]+)", r.post_data)
                if m:
                    st["dataKey"] = m.group(1)

        def on_resp(r):
            u = r.url
            try:
                if "doingBaseInfo" in u:
                    d = json.loads(r.text())
                    for n in (d.get("treedata") or []):
                        for leaf in (n.get("childs") or []):
                            tree["nodes"].append({"domid": leaf.get("domid"), "name": leaf.get("name")})
                elif "doingCountInfo" in u:
                    d = json.loads(r.text())
                    tree["counts"] = d.get("treecount") or {}
                elif API in u:
                    d = json.loads(r.text())
                    for it in d.get("datas", []):
                        rid = it.get("requestid")
                        if rid and rid not in seen:
                            seen.add(rid)
                            items.append(it)
            except Exception:
                pass

        page.on("request", on_req)
        page.on("response", on_resp)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        time.sleep(8)

        if "iam.bangcle.com" in page.url:
            ctx.close(); b.close()
            print("OA 会话过期：先 refresh_oa_session()（见 SKILL.md）", file=sys.stderr)
            return 2

        dk = st["dataKey"]
        print(f"dataKey: {dk}")
        print(f"首屏: {len(items)} 条")
        for cur in range(2, a.max_pages + 1):
            if not dk:
                break
            js = """
            async ({dk, cur}) => {
              const r = await fetch('/api/ec/dev/table/datas', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'dataKey=' + dk + '&current=' + cur + '&sortParams=%5B%5D&'
              });
              return await r.text();
            }"""
            try:
                d = json.loads(page.evaluate(js, {"dk": dk, "cur": cur}))
                its = d.get("datas", [])
            except Exception as e:
                print(f"page{cur} 解析失败: {str(e)[:120]}")
                break
            new = [i for i in its if i.get("requestid") not in seen]
            for i in new:
                seen.add(i.get("requestid")); items.append(i)
            print(f"  page{cur}: {len(its)} 条 / 新增 {len(new)} / 累计 {len(items)}")
            if not its or not new:
                break
        ctx.close(); b.close()

    print()
    print(f"TOTAL: {len(items)} 条（唯一 requestid {len(seen)}）")
    print()
    print("=== 树/计数口径（当前启用流程节点）===")
    for n in tree["nodes"]:
        c = tree["counts"].get(n["domid"]) or {}
        print(f"  {n['domid']:<10} {n['name']}  flowAll={c.get('flowAll','-')} flowDoing={c.get('flowDoing','-')}")
    print()
    print("=== 列表口径（table/datas 全量）===")
    dist = Counter(str(i.get("workflowid")) for i in items)
    tree_ids = {(n["domid"] or "").removeprefix("wf_") for n in tree["nodes"]}
    for wid, name in TARGETS:
        hits = [i for i in items if str(i.get("workflowid")) == wid]
        flag = "" if wid in tree_ids else "  ← 不在树节点中（历史/停用流程定义）"
        print(f"  wf_{wid:<5} {name}: {len(hits)}{flag}")
        for h in hits[:8]:
            print(f"      {h.get('requestid')} {(h.get('requestname') or '')[:64]} | {h.get('createdate')} | {h.get('status')}")
    other = {k: v for k, v in dist.items() if k not in {w for w, _ in TARGETS}}
    if other:
        print(f"  其他 workflowid: {dict(sorted(other.items(), key=lambda x: -x[1]))}")

    if a.save:
        out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        print(f"\n已落盘: {out}（{len(items)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
