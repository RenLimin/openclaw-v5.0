#!/usr/bin/env python3
"""L0 工具输出压缩中间件

借鉴 RTK (rtk-ai/rtk) 的设计思路，对工具输出进行智能压缩，
减少 token 消耗 40-60%。

已验证 2026-09-02。
"""

import re
from typing import Optional

# 压缩规则配置
COMPRESSION_RULES = {
    "exec": {
        "max_lines": 100,
        "max_chars": 5000,
        "strategy": "truncate",  # truncate / summarize / filter
    },
    "read": {
        "max_lines": 200,
        "max_chars": 10000,
        "strategy": "truncate",
    },
    "web_fetch": {
        "max_chars": 8000,
        "strategy": "extract_text",  # 提取正文，去除 HTML
    },
    "web_search": {
        "max_results": 5,
        "strategy": "summarize",  # 只保留标题+摘要
    },
}


def compress_output(tool_name: str, output: str) -> str:
    """压缩工具输出

    Args:
        tool_name: 工具名称
        output: 原始输出

    Returns:
        压缩后的输出
    """
    if not output:
        return output

    rules = COMPRESSION_RULES.get(tool_name)
    if not rules:
        return output

    strategy = rules.get("strategy", "truncate")

    if strategy == "truncate":
        return _truncate(output, rules)
    elif strategy == "extract_text":
        return _extract_text(output, rules)
    elif strategy == "summarize":
        return _summarize(output, rules)
    elif strategy == "filter":
        return _filter(output, rules)

    return output


def _truncate(output: str, rules: dict) -> str:
    """截断输出"""
    max_lines = rules.get("max_lines", 100)
    max_chars = rules.get("max_chars", 5000)

    lines = output.split("\n")

    # 按行数截断
    if len(lines) > max_lines:
        kept_lines = lines[:max_lines]
        truncated_count = len(lines) - max_lines
        kept_lines.append(f"\n... [截断 {truncated_count} 行，共 {len(lines)} 行]")
        lines = kept_lines

    result = "\n".join(lines)

    # 按字符数截断
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n... [截断，原输出 {len(output)} 字符]"

    return result


def _extract_text(output: str, rules: dict) -> str:
    """提取正文（去除 HTML 标签）"""
    # 简单去除 HTML 标签
    text = re.sub(r"<[^>]+>", "", output)
    # 去除多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 截断
    max_chars = rules.get("max_chars", 8000)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [截断，原输出 {len(output)} 字符]"
    return text.strip()


def _summarize(output: str, rules: dict) -> str:
    """摘要（只保留关键信息）"""
    max_results = rules.get("max_results", 5)
    lines = output.split("\n")

    # 过滤空行和装饰性内容
    meaningful = [
        l for l in lines
        if l.strip() and not l.strip().startswith(("---", "===", "***"))
    ]

    if len(meaningful) > max_results:
        meaningful = meaningful[:max_results]
        meaningful.append(f"\n... [只显示前 {max_results} 条，共 {len(lines)} 条]")

    return "\n".join(meaningful)


def _filter(output: str, rules: dict) -> str:
    """过滤（只保留匹配的行）"""
    patterns = rules.get("patterns", [])
    if not patterns:
        return output

    lines = output.split("\n")
    matched = []
    for line in lines:
        for pattern in patterns:
            if re.search(pattern, line):
                matched.append(line)
                break

    if not matched:
        return f"[过滤后无匹配内容，原输出 {len(lines)} 行]"

    return "\n".join(matched)


if __name__ == "__main__":
    # 测试
    test_output = "\n".join([f"Line {i}: some output content" for i in range(250)])
    print("=== exec 压缩测试 ===")
    compressed = compress_output("exec", test_output)
    print(f"原始: {len(test_output)} 字符, 压缩后: {len(compressed)} 字符")
    print(compressed[:500])
