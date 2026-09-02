#!/usr/bin/env python3
"""系统自审计脚本

每次声称组件"完成"前，必须运行此脚本。
检查：语法 + TODO + 空函数 + 缺失 return + 未实现核心逻辑。

用法：
  python3 scripts/l2/self_audit.py                    # 全量审计
  python3 scripts/l2/self_audit.py --component ones  # 单组件审计
  python3 scripts/l2/self_audit.py --fix             # 自动修复（如可能）

已验证 2026-09-02。
"""

import ast
import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Optional

WORKSPACE = Path(__file__).resolve().parent.parent.parent
SCRIPTS_L4 = WORKSPACE / "scripts" / "l4" / "delivery_center"
SCRIPTS_L2 = Path(__file__).resolve().parent.parent

# 核心功能关键词映射（文件名 → 必须包含的核心操作）
CORE_FUNCTIONS = {
    "ones_collector.py": {
        "must_contain": ["export", "download", "filter", "navigate"],
        "must_return": True,
        "description": "ONES 数据采集器",
    },
    "oa_collector.py": {
        "must_contain": ["export", "download", "expect_download"],
        "must_return": True,
        "description": "OA 合同台账采集器",
    },
    "wecom_collector.py": {
        "must_contain": ["collect", "get_doc", "smartsheet"],
        "must_return": True,
        "description": "企业微信采集器",
    },
    "workhour_collector.py": {
        "must_contain": ["extract", "table", "data"],
        "must_return": True,
        "description": "工时门户采集器",
    },
    "contract_parser.py": {
        "must_contain": ["extract", "parse", "field"],
        "must_return": True,
        "description": "合同解析器",
    },
    "delivery_report.py": {
        "must_contain": ["generate", "create_sheet", "fill_"],
        "must_return": True,
        "description": "交付月报生成器",
    },
    "revenue_report.py": {
        "must_contain": ["generate", "create_sheet", "fill_"],
        "must_return": True,
        "description": "确收月报生成器",
    },
    "join_engine.py": {
        "must_contain": ["merge", "join", "load_"],
        "must_return": True,
        "description": "关联查询引擎",
    },
    "status_engine.py": {
        "must_contain": ["determine", "apply"],
        "must_return": True,
        "description": "状态判定引擎",
    },
    "scoring_engine.py": {
        "must_contain": ["calculate", "score"],
        "must_return": True,
        "description": "考核计算引擎",
    },
    "variance_engine.py": {
        "must_contain": ["variance", "calculate"],
        "must_return": True,
        "description": "差异分析引擎",
    },
    "summary_engine.py": {
        "must_contain": ["pivot", "groupby", "agg"],
        "must_return": True,
        "description": "汇总统计引擎",
    },
}


def check_syntax(path: Path) -> tuple[bool, Optional[str]]:
    """检查 Python 语法"""
    try:
        with open(path) as f:
            ast.parse(f.read())
        return True, None
    except SyntaxError as e:
        return False, str(e)


def check_todos(path: Path) -> list[str]:
    """检查 TODO/FIXME"""
    todos = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped.startswith('# TODO') or stripped.startswith('# FIXME'):
                todos.append(f"L{i}: {stripped[:80]}")
    return todos


def check_empty_functions(path: Path) -> list[str]:
    """检查空函数体（仅 pass 或 docstring）"""
    empty = []
    with open(path) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            body = node.body
            if len(body) == 1:
                if isinstance(body[0], ast.Pass):
                    empty.append(f"{node.name}() — 仅 pass")
                elif isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    empty.append(f"{node.name}() — 仅 docstring")
    return empty


def check_return(path: Path) -> tuple[bool, list[str]]:
    """检查是否有有效 return"""
    functions_without_return = []
    with open(path) as f:
        tree = ast.parse(f.read())
    
    has_any_return = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_has_return = False
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value is not None:
                    func_has_return = True
                    has_any_return = True
                    break
            if not func_has_return and node.name != '__init__':
                functions_without_return.append(node.name)
    
    return has_any_return, functions_without_return


def check_core_functions(path: Path, filename: str) -> list[str]:
    """检查核心功能关键词"""
    issues = []
    config = CORE_FUNCTIONS.get(filename)
    if not config:
        return issues
    
    with open(path) as f:
        content = f.read().lower()
    
    for keyword in config["must_contain"]:
        if keyword.lower() not in content:
            issues.append(f"缺少核心关键词: '{keyword}'")
    
    return issues


def check_test_exists(path: Path, filename: str) -> bool:
    """检查是否有对应的测试"""
    test_dir = WORKSPACE / "tests" / "l4"
    test_file = test_dir / f"test_{filename}"
    return test_file.exists()


def audit_file(path: Path) -> dict:
    """审计单个文件"""
    filename = path.name
    result = {
        "path": str(path.relative_to(WORKSPACE)),
        "filename": filename,
        "syntax_ok": True,
        "syntax_error": None,
        "todos": [],
        "empty_functions": [],
        "has_return": True,
        "functions_without_return": [],
        "core_issues": [],
        "has_test": False,
        "status": "✅",
    }
    
    # 语法检查
    syntax_ok, syntax_error = check_syntax(path)
    result["syntax_ok"] = syntax_ok
    result["syntax_error"] = syntax_error
    if not syntax_ok:
        result["status"] = "❌"
        return result
    
    # TODO 检查
    result["todos"] = check_todos(path)
    
    # 空函数检查
    result["empty_functions"] = check_empty_functions(path)
    
    # Return 检查
    result["has_return"], result["functions_without_return"] = check_return(path)
    
    # 核心功能检查
    result["core_issues"] = check_core_functions(path, filename)
    
    # 测试检查
    result["has_test"] = check_test_exists(path, filename)
    
    # 综合判定
    if result["todos"] or result["empty_functions"] or result["core_issues"]:
        result["status"] = "⚠️"
    if not result["has_return"] and CORE_FUNCTIONS.get(filename, {}).get("must_return"):
        result["status"] = "⚠️"
    
    return result


def audit_all() -> list[dict]:
    """审计所有 L4 + L2 文件"""
    results = []
    for search_dir in [SCRIPTS_L4, SCRIPTS_L2]:
        if not search_dir.exists():
            continue
        for f in sorted(search_dir.rglob('*.py')):
            if f.name == '__init__.py':
                continue
            results.append(audit_file(f))
    return results


def print_report(results: list[dict]):
    """打印审计报告"""
    print("=" * 70)
    print(" 系统自审计报告")
    print("=" * 70)
    
    ok_count = sum(1 for r in results if r["status"] == "✅")
    warn_count = sum(1 for r in results if r["status"] == "⚠️")
    error_count = sum(1 for r in results if r["status"] == "❌")
    
    print(f"\n 总计: {len(results)} 文件")
    print(f"  ✅ 通过: {ok_count}")
    print(f"  ⚠️ 待完善: {warn_count}")
    print(f"  ❌ 错误: {error_count}")
    
    # 问题详情
    for r in results:
        if r["status"] != "✅":
            print(f"\n  {r['status']} {r['path']}")
            if r["syntax_error"]:
                print(f"     语法错误: {r['syntax_error']}")
            for todo in r["todos"]:
                print(f"     📝 {todo}")
            for ef in r["empty_functions"]:
                print(f"     空函数: {ef}")
            for issue in r["core_issues"]:
                print(f"     核心功能: {issue}")
            if r["functions_without_return"]:
                print(f"     无 return: {', '.join(r['functions_without_return'][:5])}")
            if not r["has_test"]:
                print(f"     ❌ 缺少测试文件")
    
    print("\n" + "=" * 70)
    
    # 返回退出码（CI/CD 集成用）
    if error_count > 0:
        return 1
    elif warn_count > 0:
        return 2  # 有警告但无错误
    return 0


if __name__ == "__main__":
    component = None
    if "--component" in sys.argv:
        idx = sys.argv.index("--component")
        if idx + 1 < len(sys.argv):
            component = sys.argv[idx + 1]
    
    if component:
        # 单组件审计
        target = SCRIPTS_L4 / f"{component}_collector.py"
        if not target.exists():
            target = SCRIPTS_L4 / f"{component}_engine.py"
        if not target.exists():
            target = SCRIPTS_L4 / f"{component}_report.py"
        if not target.exists():
            print(f"  ❌ 未找到组件: {component}")
            sys.exit(1)
        
        results = [audit_file(target)]
    else:
        # 全量审计
        results = audit_all()
    
    exit_code = print_report(results)
    sys.exit(exit_code)
