#!/usr/bin/env python3
"""ONES 筛选器查询脚本

尝试通过 ONES API 的筛选器 query 结构来获取分类数据。
已知筛选器 ft-t-001 的 query: {"must": [{"in": {"field_values.field004": ["5jguPeXt"]}}]}
尝试用 field_values.XXyinFzM 筛选"签约项目"
"""

import json, urllib.request, urllib.error
from pathlib import Path

def login():
    """登录 ONES 并获取 token"""
    AUTH_FILE = Path.home() / '.openclaw' / 'data' / 'oa_exports' / 'ones_auth.json'
    data = json.loads(AUTH_FILE.read_text(encoding='utf-8'))
    cookies = data.get('cookies', [])
    cookie_str = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)
    
    url = 'https://ones.bangcle.com/project/api/project/auth/login'
    payload = json.dumps({'email': 'limin.ren@bangcle.com', 'password': 'March-123'}).encode()
    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Cookie', cookie_str)
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read().decode())
    
    token = result['user']['token']
    user_id = result['user']['uuid']
    
    headers = {
        'Ones-User-Id': user_id,
        'Ones-Auth-Token': token,
        'Referer': 'https://ones.bangcle.com/',
        'Content-Type': 'application/json',
    }
    return headers

def try_filter_apis(headers):
    """尝试筛选器 API"""
    print('=== 筛选器 API 执行查询 ===')
    
    filter_query = {
        "query": {
            "must": [{"in": {"field_values.XXyinFzM": ["签约项目"]}}]
        },
        "limit": 5
    }
    
    paths = [
        '/project/api/project/team/RZxvwUZ8/filter/query',
        '/project/api/project/team/RZxvwUZ8/filters/query',
        '/project/api/project/team/RZxvwUZ8/filter/execute',
        '/project/api/project/team/RZxvwUZ8/filters/execute',
        '/project/api/project/team/RZxvwUZ8/projects/query',
        '/project/api/project/team/RZxvwUZ8/project/query',
    ]
    
    for path in paths:
        url = f'https://ones.bangcle.com{path}'
        payload_bytes = json.dumps(filter_query).encode()
        req = urllib.request.Request(url, data=payload_bytes, method='POST', headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=8)
            body = json.loads(resp.read().decode())
            print(f'✅ POST {path}:')
            print(f'   {json.dumps(body, ensure_ascii=False)[:400]}')
            return body
        except urllib.error.HTTPError as e:
            code = e.code
            err_body = e.read().decode()[:80] if e.fp else ''
            if code != 404:
                print(f'❌ {code} POST {path}: {err_body[:60]}')
        except Exception as e:
            print(f'❌ POST {path}: {str(e)[:50]}')
    
    return None

def try_graphql_filter(headers):
    """尝试 GraphQL 筛选"""
    print('\n=== GraphQL 筛选尝试 ===')
    graphql_url = 'https://ones.bangcle.com/project/api/project/team/RZxvwUZ8/items/graphql'
    
    queries = [
        '{ projects(filter: {field: "XXyinFzM", op: "in", value: ["签约项目"]}) { uuid name } }',
        '{ projects(where: {field_values: {XXyinFzM: ["签约项目"]}}) { uuid name } }',
        '{ projects(search: "签约项目") { uuid name } }',
    ]
    
    for q in queries:
        gq = json.dumps({'query': q}).encode()
        req = urllib.request.Request(graphql_url, data=gq, method='POST', headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=8)
            body = json.loads(resp.read().decode())
            projects = body.get('data', {}).get('projects', [])
            print(f'✅ {q[:60]}: {len(projects)} 个')
            if projects:
                print(f'   {json.dumps(projects[0], ensure_ascii=False)[:150]}')
            return projects
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:80] if e.fp else ''
            print(f'❌ {q[:60]}: {err_body[:60]}')
        except Exception as e:
            print(f'❌ {q[:60]}: {str(e)[:50]}')
    
    return None

if __name__ == '__main__':
    headers = login()
    print(f'✅ 登录成功')
    
    result = try_filter_apis(headers)
    if result is None:
        try_graphql_filter(headers)
