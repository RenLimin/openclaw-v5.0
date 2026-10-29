"""P8 §6 / AC-5：合同原文不外发（运行期 + 静态双证明）。

运行期：在 socket 层装守卫——
  - connect 仅放行本机（127.0.0.1/::1/localhost）；任何外部连接直接 fail
  - 记录所有 send/sendall 字节，断言不含合同特征串（原文/甲乙方/金额/合同号）
  覆盖 digitize→parse→risk→kb 全链路（真实 PDF，非 mock）。
静态：grep 确认链路无指向公网 LLM/模型 endpoint 的字面量与 POST。

允许方向：从 OA 域名拉取附件属"入站"，本测试只跑本地文件链（不触网）。
"""
import io
import os
import socket as _socket
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")
for p in (COMPONENT_ROOT, L3_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 合同特征串（一旦外发即可被检出）
SECRET_MARKERS = [
    "SECRET_PROJECT_ALPHA_9527",   # 项目名
    "甲方机密单位_42",
    "乙方机密供应商_88",
    "合同号HT-MARK-2026-0001",
    "金额陆拾陆万捌仟元",
]


@pytest.fixture
def contract_pdf(tmp_path):
    import fitz
    out = tmp_path / "secret.pdf"
    body = [
        "技术服务合同",
        "合同号HT-MARK-2026-0001",
        "甲方：甲方机密单位_42",
        "乙方：乙方机密供应商_88",
        "项目名称：SECRET_PROJECT_ALPHA_9527",
        "服务内容：梆梆安全测评服务",
        "合同金额：金额陆拾陆万捌仟元（668000元）",
        "服务期限自2026年1月1日至2026年12月31日。",
    ]
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in body:
        page.insert_text((72, y), line, fontname="helv", fontsize=11)
        y += 22
    doc.save(out)
    doc.close()
    return str(out)


class _EgressGuard:
    """socket 守卫：放行本机，拦截外部，并记录外发字节。"""

    def __init__(self):
        self.sent = bytearray()
        self.external_attempts = []
        self._orig_connect = _socket.socket.connect
        self._orig_send = _socket.socket.send
        self._orig_sendall = _socket.socket.sendall

    def _is_local(self, addr):
        try:
            host = addr[0]
        except Exception:
            return False
        return host in ("127.0.0.1", "::1", "localhost", "0.0.0.0")

    def install(self):
        guard = self

        def connect(self, addr):
            if not guard._is_local(addr):
                guard.external_attempts.append(addr)
                raise AssertionError("检测到外部网络连接（原文不外发红线）: %r" % (addr,))
            return guard._orig_connect(self, addr)

        def send(self, data, flags=0):
            if isinstance(data, (bytes, bytearray)):
                guard.sent.extend(data)
            return guard._orig_send(self, data, flags)

        def sendall(self, data, flags=0):
            if isinstance(data, (bytes, bytearray)):
                guard.sent.extend(data)
            return guard._orig_sendall(self, data, flags)

        _socket.socket.connect = connect
        _socket.socket.send = send
        _socket.socket.sendall = sendall

    def restore(self):
        _socket.socket.connect = self._orig_connect
        _socket.socket.send = self._orig_send
        _socket.socket.sendall = self._orig_sendall


def test_chain_does_not_exfiltrate(contract_pdf):
    from contract_review.ingest import ingest_file
    from contract_review.digitize import digitize
    from contract_review.parser import parse_shallow
    from contract_review.risk import run_risk
    from contract_review.kb_match import run_kb_match

    guard = _EgressGuard()
    guard.install()
    try:
        ingested = ingest_file(contract_pdf, source="upload",
                               staging_dir=os.path.dirname(contract_pdf))
        dt = digitize(ingested.local_path)
        parsed = parse_shallow(dt.full_text)
        run_risk(dt)
        run_kb_match(dt.full_text, parsed=parsed)
    finally:
        guard.restore()

    # 1) 无任何外部连接尝试
    assert guard.external_attempts == [], guard.external_attempts
    # 2) 外发字节（本机方向也一并检查）不含任何合同特征
    sent = bytes(guard.sent)
    for marker in SECRET_MARKERS:
        assert marker.encode() not in sent, "合同原文出现在网络外发字节中: %s" % marker


def test_static_no_public_model_endpoint():
    """静态：链路模块无公网模型 endpoint / 无外部 POST。"""
    chain_dir = os.path.join(COMPONENT_ROOT, "contract_review")
    banned = ("api.openai.com", "openai.", "api.anthropic.com", "generativelanguage",
              "dashscope.", "volces.com", "ark.cn-", "aip.baidubce",
              "requests.post", "requests.get", "urlopen", "httpx.post",
              ".post(`http", "socket.socket(")
    hits = []
    for f in os.listdir(chain_dir):
        if not f.endswith(".py"):
            continue
        text = open(os.path.join(chain_dir, f), encoding="utf-8").read()
        for b in banned:
            if b in text:
                hits.append((f, b))
    assert hits == [], "链路发现公网模型/网络调用: %s" % hits
