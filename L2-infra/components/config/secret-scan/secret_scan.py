#!/usr/bin/env python3
"""暂存区/文件 密钥扫描器 — 提交前阻断明文凭据。

设计：
- 默认扫 git 暂存区（staged），只看本次将提交的内容，快且精准。
- 高置信规则（云密钥/私钥/JWT/已知密钥字面量）→ 直接判违规。
- 赋值类规则（password/token/secret = "..."）→ 提取值，过滤占位符后判违规。
- 退出码：0 干净；1 发现密钥；2 用法/环境错误。
- 输出只给文件名+行号+规则名+打码片段，不回显完整密钥。

用法：
  python3 secret_scan.py                # 扫暂存区
  python3 secret_scan.py --files a b    # 扫指定文件
  python3 secret_scan.py --stdin        # 从 stdin 读内容（测试用）
  python3 secret_scan.py --allow-pattern 'REGEX'  # 追加白名单正则
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# ---- 高置信规则：命中即违规 ----
HIGH_CONFIDENCE = [
    ("aws-access-key-id", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,255}")),
    ("google-api-key", re.compile(rb"AIza[0-9A-Za-z_\-]{35}")),
    ("slack-token", re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,72}")),
    ("jwt", re.compile(rb"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
]

# ---- 赋值类规则：key = "value"，提取值再判定 ----
ASSIGN = re.compile(
    rb"""(?ix)
    \b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|
        client[_-]?secret|auth[_-]?token|refresh[_-]?token|corpsecret|
        private[_-]?key|credentials?)\b
    ["']?\s*[:=]\s*
    (["'])([^"'\r\n]{4,80})\1
    """
)

# 占位符/明显非真实值（小写包含即放行）
PLACEHOLDER_MARKERS = (
    b"example", b"placeholder", b"changeme", b"change-in-production",
    b"redacted", b"xxxx", b"your-", b"dummy", b"sample", b"replace-with",
    b"todo", b"none", b"null", b"fake", b"test-value", b"<",
)

# 形如代码表达式的"引号内"右值（调用/下标/引用），不是字面量密钥。
# 注意：裸字母数字（如 hunter2xy）绝不能放行——加了引号就是字面量；
# 未加引号的代码引用在更上游（ASSIGN 要求引号包裹）就不会进入此判定。
CODE_VALUE = re.compile(
    rb"[()\[\]]"          # 调用/下标：create_token(x)、a[0]
    rb"|request\.|self\." # 属性引用
    rb"|getenv|environ"     # 环境读取
    rb"|secrets\.token"    # 随机生成
    rb"|\$\{|\$\(",     # 模板插值
    re.IGNORECASE,
)

# 默认放行的 key（这些 key 名即使出现在赋值规则里也只看值，已由上面过滤；
# 这里列的是"整个键名"白名单，用于降低误报）
ALLOW_LITERAL = (b"REDACTED_SECRET",)


# 测试文件里明显的夹具密码（纯字母短词，含 test/wrong/dummy/fake 等）
_TEST_PATH = re.compile(r"(?:^|/)tests?/|(?:^|/)test_|_test\.[a-z]+$", re.IGNORECASE)
_TEST_PW = re.compile(rb"^[a-z]{3,16}$")
_TEST_MARK = (b"test", b"wrong", b"dummy", b"fake", b"sample", b"example", b"login", b"admin")


_ALLOW_MARKER = b"secret-scan: allow-test-vectors"


def _file_has_allow_marker(path: str) -> bool:
    """检测源文件头部的显式豁免标记（仅限扫描器自身的检测向量集）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(512)
    except OSError:
        return False
    return _ALLOW_MARKER in head


def _is_test_fixture(value: bytes, source: str) -> bool:
    if not _TEST_PATH.search(source):
        return False
    if not _TEST_PW.fullmatch(value):
        return False
    return any(mark in value for mark in _TEST_MARK)


def _mask(value: bytes) -> str:
    s = value.decode("utf-8", "replace")
    if len(s) <= 6:
        return s[:1] + "***"
    return s[:3] + "***" + s[-2:]


def scan_bytes(data: bytes, allow_patterns, source: str = "<data>"):
    """返回违规列表 [(source, line_no, rule, masked)]。"""
    findings = []

    # 行号映射：高置信规则定位行
    line_starts = [0]
    for m in re.finditer(rb"\n", data):
        line_starts.append(m.end())

    def lineno(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for rule, pat in HIGH_CONFIDENCE:
        for m in pat.finditer(data):
            findings.append((source, lineno(m.start()), rule, _mask(m.group(0))))

    for m in ASSIGN.finditer(data):
        value = m.group(2)
        if value in ALLOW_LITERAL:
            continue
        low = value.lower()
        if any(marker in low for marker in PLACEHOLDER_MARKERS):
            continue
        if _is_test_fixture(low, source):
            continue
        if CODE_VALUE.search(value):
            continue
        if any(ap.search(value) for ap in allow_patterns):
            continue
        findings.append((source, lineno(m.start(2)), "hardcoded-credential", _mask(value)))

    return findings


def _git_staged_files():
    # 仅暂存区中新增/修改、且有内容的普通文件
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"],
        capture_output=True, check=True,
    ).stdout
    return [p.decode() for p in out.split(b"\0") if p]


def _git_staged_blob(path: str):
    out = subprocess.run(
        ["git", "show", f":{path}"], capture_output=True
    )
    return out.stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="提交前密钥扫描")
    ap.add_argument("--files", nargs="*", help="扫描指定文件（而非暂存区）")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 读内容")
    ap.add_argument("--allow-pattern", action="append", default=[],
                    help="放行值的正则，可多次")
    args = ap.parse_args(argv)

    allow_patterns = []
    for pat in args.allow_pattern:
        allow_patterns.append(re.compile(pat.encode()))

    findings = []

    if args.stdin:
        findings = scan_bytes(sys.stdin.buffer.read(), allow_patterns, "<stdin>")
    elif args.files:
        for path in args.files:
            if _file_has_allow_marker(path):
                continue
            try:
                with open(path, "rb") as f:
                    findings += scan_bytes(f.read(), allow_patterns, path)
            except OSError:
                pass
    else:
        # 确保在 git 仓库内
        if subprocess.run(["git", "rev-parse", "--git-dir"],
                          capture_output=True).returncode != 0:
            print("secret-scan: 不在 git 仓库内", file=sys.stderr)
            return 2
        for path in _git_staged_files():
            if _file_has_allow_marker(path):
                continue
            # 跳过明显二进制大文件/二进制（私有 key 仍会被高置信抓到，
            # 所以这里只跳过非文本，依据 NUL 字节）
            blob = _git_staged_blob(path)
            if b"\x00" in blob:
                # 仍要查私钥等高置信：对二进制只跑高置信
                for rule, pat in HIGH_CONFIDENCE:
                    for m in pat.finditer(blob):
                        findings.append((path, 0, rule, _mask(m.group(0))))
                continue
            findings += scan_bytes(blob, allow_patterns, path)

    if findings:
        print("❌ 检测到疑似明文凭据，已阻断提交：\n", file=sys.stderr)
        for source, line, rule, masked in findings:
            loc = f"{source}:{line}" if line else source
            print(f"  {loc}  [{rule}]  {masked}", file=sys.stderr)
        print(
            "\n处理方式：\n"
            "  1) 真实密钥 → 改存 ~/.openclaw/secrets/ 或 Secret Store，代码只读取\n"
            "  2) 误报 → 用 --allow-pattern 放行，或在 hook 配置加白名单\n"
            "  3) 紧急 → git commit --no-verify（不推荐，需事后补扫）",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
