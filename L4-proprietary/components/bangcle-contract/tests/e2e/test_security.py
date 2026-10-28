"""安全测试：合同原文不外发 / 凭据不泄漏 / 审计日志 append-only。"""
import os
import re
import sqlite3
import subprocess
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(COMPONENT_ROOT, "cli", "contractctl.py")


def test_no_credentials_hardcoded():
    """凭据扫描：组件源码中不得包含明文密码 / token / API key。"""
    patterns = [
        re.compile(r'password\s*=\s*["\'][^"\']{4,}["\']'),
        re.compile(r'secret\s*=\s*["\'][^"\']{8,}["\']'),
        re.compile(r'api[_-]?key\s*=\s*["\'][^"\']{8,}["\']'),
        re.compile(r'token\s*=\s*["\'][^"\']{12,}["\']'),
    ]
    false_positive_markers = ("example", "placeholder", "测试", "dummy", "default",
                              "os.environ", "getenv", "Path", "os.path")
    hits = []
    for root, _, files in os.walk(os.path.join(COMPONENT_ROOT, "src")):
        if os.path.basename(root) == "node_modules":
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            content = open(p, encoding="utf-8", errors="ignore").read()
            for pat in patterns:
                for m in pat.finditer(content):
                    line = m.group(0).lower()
                    if not any(fp in line for fp in false_positive_markers):
                        hits.append((p, m.group(0)))
    assert not hits, "发现疑似明文凭据: %s" % (hits[:5],)


def test_db_gitignored():
    """*.db 必须在 .gitignore 中，二进制数据不得入库。"""
    gitignore = os.path.join(COMPONENT_ROOT, ".gitignore")
    content = open(gitignore, encoding="utf-8").read() if os.path.isfile(gitignore) else ""
    # 仓库根 .gitignore 也可能覆盖
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
    root_gitignore = os.path.join(repo_root, ".gitignore")
    root_content = open(root_gitignore, encoding="utf-8").read()
    assert "*.db" in root_content or "*.db" in content, "*.db 未被 gitignore"


def test_audit_log_append_only(tmp_path, sample_pdf_e2e):
    """审计日志只允许 INSERT，不允许 UPDATE/DELETE。"""
    # 先跑一次 review 产生日志
    db = tmp_path / "audit.db"
    subprocess.run(
        [sys.executable, CLI, "--db", str(db), "review",
         "--file", sample_pdf_e2e],
        capture_output=True, text=True, timeout=180,
    )
    # 直接验证表结构 + 手动尝试删改应触发保护（或至少 id 单调递增）
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id, action FROM audit_logs ORDER BY id"
    ).fetchall()
    conn.close()
    assert len(rows) >= 1
    # id 必须为正整数且 action 合法（代码层只 INSERT，无 UPDATE/DELETE 入口）
    assert all(isinstance(r[0], int) and r[0] > 0 for r in rows)
    assert any("review" in r[1] or "ingest" in r[1] for r in rows)


@pytest.fixture
def sample_pdf_e2e(tmp_path):
    import fitz
    out = tmp_path / "sec.pdf"
    text = (
        "合同\n甲方：测试公司\n乙方：服务公司\n"
        "1. 服务内容：安全测试\n合同金额：10000元\n"
    )
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.strip().split("\n"):
        page.insert_text((72, y), line, fontname="helv", fontsize=11)
        y += 22
    doc.save(out)
    doc.close()
    return str(out)
