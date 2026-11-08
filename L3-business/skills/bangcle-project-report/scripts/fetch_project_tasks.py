#!/usr/bin/env python3
"""fetch_project_tasks.py — P1 取数与完整性

输入 (stdin JSON):
  {
    "customer": "中国建设银行股份有限公司",
    "period": {"start": "2026-01-01", "end": "2026-12-31"},
    "teamUUID": "RZxvwUZ8"  // 可选
  }

输出 (stdout JSON):
  {
    "projects": [{projectUUID, projectCode, projectName, contractNo, standardProduct, status}],
    "tasks": [raw Task objects],
    "completeness": {
      "fetchedAt": "ISO8601",
      "perProject": {"<code>": {"fetched": N, "total": N, "hitCap": false}},
      "globalTruncated": false
    }
  }

退出码: 0=成功, 2=数据/BLOCK
凭据：浏览器 localStorage['ct']，不写入产出。

注意：实测 ONES GraphQL 的 tasks 字段忽略 page/pageSize 参数，
返回全部匹配任务。本脚本按「一次性全量拉取 + 条数校验」策略工作。
"""
import json
import sys
import time
import subprocess
import os
import re
from datetime import datetime, timezone, timedelta

# ── 常量 ──────────────────────────────────────────────────────────────
DEFAULT_TEAM_UUID = "RZxvwUZ8"
GRAPHQL_ENDPOINT = "/project/api/project/team/{team}/items/graphql"
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds
CST = timezone(timedelta(hours=8))
# 单项目任务数上限（触顶阈值）：超过视为数据截断
TASK_CAP = 5000


# ── 浏览器注入 gql() ─────────────────────────────────────────────────
def _run_js(js: str) -> str:
    """通过 osascript 在已登录 ONES 的 Chrome 标签页执行 JS。"""
    escaped = js.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    cmd = [
        "osascript", "-e",
        f'tell application "Google Chrome" to execute '
        f'(first tab of first window whose URL contains "ones.bangcle.com") '
        f'javascript "{escaped}"'
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def gql(query: str, team_uuid: str = DEFAULT_TEAM_UUID) -> dict:
    """在浏览器内执行 GraphQL 查询，返回 data 字段。
    必须使用 query { ... } 包装器，否则 ONES 返回 500。
    """
    endpoint = GRAPHQL_ENDPOINT.format(team=team_uuid)
    inject = (
        "window.__r=null;(async()=>{try{"
        f"var resp=await fetch('{endpoint}',"
        "{method:'POST',headers:{'Content-Type':'application/json',"
        "'Ones-Auth-Token':localStorage.getItem('ct')},"
        f"body:JSON.stringify({{query:{json.dumps(query)}}})}});"
        "window.__r=await resp.text();"
        "}catch(e){window.__r='ERR:'+e;}})();'go'"
    )
    _run_js(inject)

    for attempt in range(20):
        time.sleep(1)
        v = _run_js("window.__r")
        if v and v != "null":
            if v.startswith("ERR"):
                raise RuntimeError(v)
            try:
                d = json.loads(v)
            except json.JSONDecodeError:
                # 空响应或截断，重试
                if attempt < 19:
                    continue
                raise RuntimeError(f"GraphQL 返回非 JSON: {v[:200]}")
            if "errors" in d:
                raise RuntimeError(json.dumps(d["errors"], ensure_ascii=False))
            if "code" in d and d.get("code") == 500:
                raise RuntimeError(f"ONES ServerError: {d.get('errcode', 'unknown')}")
            return d["data"]
    raise TimeoutError("GraphQL 无响应（20s 超时）")


def gql_with_retry(query: str, team_uuid: str = DEFAULT_TEAM_UUID) -> dict:
    """带指数退避的 GraphQL 调用（最多 3 次）。"""
    for attempt in range(MAX_RETRIES):
        try:
            return gql(query, team_uuid)
        except RuntimeError as e:
            err_str = str(e)
            if "801" in err_str and attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE ** (attempt + 1)
                print(f"[WARN] 限流 801，{wait}s 后重试 ({attempt+1}/{MAX_RETRIES})",
                      file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"GraphQL 连续 {MAX_RETRIES} 次失败")


# ── 项目枚举 ─────────────────────────────────────────────────────────
def fetch_projects(team_uuid: str, customer: str = "") -> list:
    """枚举团队下所有项目，按客户名过滤，取合同字段 _7KF6tXvk。
    
    实测：团队下有 19000+ 项目，必须按客户名过滤，否则遍历全部项目会超时。
    过滤规则：projectName 包含客户名关键词，或 contractNo 非空且 projectName 匹配。
    """
    query = 'query { projects { uuid name _7KF6tXvk } }'
    for attempt in range(3):
        try:
            data = gql_with_retry(query, team_uuid)
            break
        except Exception as e:
            if attempt < 2:
                print(f"[WARN] 项目枚举失败，重试 ({attempt+1}/3): {e}", file=sys.stderr)
                time.sleep(2)
            else:
                raise
    
    all_projects = data.get("projects", [])
    print(f"[INFO] 团队项目总数: {len(all_projects)}", file=sys.stderr)
    
    # 按客户名过滤
    customer_keywords = []
    if customer:
        # 提取客户名关键词（去掉"股份有限公司"等后缀）
        customer_keywords = [customer]
        # 常见简称映射
        if "建设银行" in customer or "建行" in customer:
            customer_keywords.extend(["建行", "中国建设银行", "建设银行"])
        if "华夏银行" in customer:
            customer_keywords.extend(["华夏"])
    
    projects = []
    for p in all_projects:
        name = p.get("name", "") or ""
        contract_no = p.get("_7KF6tXvk") or ""
        
        # 过滤：项目名包含任一关键词
        matched = False
        if customer_keywords:
            for kw in customer_keywords:
                if kw in name:
                    matched = True
                    break
        else:
            matched = True  # 无客户名时取全部（不推荐）
        
        if matched:
            projects.append({
                "projectUUID": p.get("uuid", ""),
                "projectCode": _extract_project_code(name),
                "projectName": name,
                "contractNo": contract_no or None,
                "standardProduct": None,
                "status": "unknown",
            })
    
    print(f"[INFO] 过滤后项目数: {len(projects)} (关键词: {customer_keywords})", file=sys.stderr)
    return projects


def _extract_project_code(name: str) -> str:
    """从项目名解析项目编号（SSXM-...）。"""
    m = re.search(r'(SSXM-[\w-]+)', name or "")
    return m.group(1) if m else ""


# ── 逐项目取数 ───────────────────────────────────────────────────────
def fetch_tasks_for_project(project_uuid: str, team_uuid: str) -> dict:
    """拉取单项目全部任务。
    
    实测：ONES GraphQL tasks 字段忽略 page/pageSize，返回全部匹配任务。
    策略：一次性全量拉取 + 条数校验（超 TASK_CAP 视为触顶截断）。
    """
    query = (
        'query { tasks(filter:{project_in:["%s"]}) { '
        'number uuid name statusCategory createTime '
        'status { name category } owner { name } issueType { name } '
        'project { uuid name } products { uuid name } descriptionText '
        '} }'
    ) % project_uuid

    for attempt in range(3):
        try:
            data = gql_with_retry(query, team_uuid)
            tasks = data.get("tasks", [])
            if isinstance(tasks, list):
                break
            print(f"[WARN] 项目 {project_uuid} 返回非列表，重试 ({attempt+1}/3)", file=sys.stderr)
            time.sleep(2)
        except Exception as e:
            if attempt < 2:
                print(f"[WARN] 项目 {project_uuid} 取数失败，重试 ({attempt+1}/3): {e}", file=sys.stderr)
                time.sleep(2)
            else:
                raise
    else:
        print(f"[ERROR] 项目 {project_uuid} 连续 3 次失败", file=sys.stderr)
        sys.exit(2)

    if not isinstance(tasks, list):
        print(f"[ERROR] 项目 {project_uuid} 返回非列表: {type(tasks)}", file=sys.stderr)
        sys.exit(2)

    fetched = len(tasks)
    hit_cap = fetched >= TASK_CAP

    if hit_cap:
        print(f"[ERROR] 项目 {project_uuid} 任务数 {fetched} >= 触顶阈值 {TASK_CAP}",
              file=sys.stderr)

    return {
        "tasks": tasks,
        "fetched": fetched,
        "total": fetched,
        "hitCap": hit_cap,
    }


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(2)

    customer = input_data.get("customer", "")
    period = input_data.get("period", {})
    team_uuid = input_data.get("teamUUID", DEFAULT_TEAM_UUID)

    if not customer:
        print(json.dumps({"error": "customer is required"}))
        sys.exit(2)

    print(f"[INFO] 取数: customer={customer}, period={period}, team={team_uuid}",
          file=sys.stderr)

    # S1: 项目枚举（按客户名过滤）
    projects = fetch_projects(team_uuid, customer)
    print(f"[INFO] 枚举到 {len(projects)} 个项目", file=sys.stderr)

    # S2: 逐项目取全
    all_tasks = []
    per_project = {}
    global_truncated = False

    for p in projects:
        code = p["projectCode"] or p["projectUUID"][:8]
        result = fetch_tasks_for_project(p["projectUUID"], team_uuid)
        all_tasks.extend(result["tasks"])
        per_project[code] = {
            "fetched": result["fetched"],
            "total": result["total"],
            "hitCap": result["hitCap"],
        }
        if result["hitCap"]:
            global_truncated = True
        print(f"[INFO]   项目 {code}: fetched={result['fetched']}",
              file=sys.stderr)

    completeness = {
        "fetchedAt": datetime.now(CST).isoformat(),
        "perProject": per_project,
        "globalTruncated": global_truncated,
    }

    output = {
        "projects": projects,
        "tasks": all_tasks,
        "completeness": completeness,
    }

    # 落盘中间产物
    raw_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))),
        "analysis_output", "ones_raw"
    )
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(
        raw_dir,
        f"fetch_{customer[:10]}_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 原始数据落盘: {raw_path}", file=sys.stderr)

    print(json.dumps(output, ensure_ascii=False))
    if global_truncated:
        sys.exit(2)


if __name__ == "__main__":
    main()
