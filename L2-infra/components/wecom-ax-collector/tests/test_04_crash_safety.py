"""测试：A6 崩溃安全（kill -9 + 半写 JSONL 恢复）。

不是 mock：真起一个子进程往 JSONL 追加，用 SIGKILL 打断，
留下真实的半写尾行；再验证修复后历史记录一条不丢、坏行被清掉。

语义声明：本写入器是 at-least-once —— 「已落盘但未保存已见集」之间被杀，
重启会重复输出该消息；由下游按 msg_id / content_hash 幂等去重。
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import wecom_collector as C

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "session_project_dept.json"


# ---- 直接单元：repair ----

def test_repair_no_file(tmp_path):
    p = tmp_path / "nope.jsonl"
    assert C.JsonlSink.repair(p) == 0


def test_repair_empty_and_clean(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text("")
    assert C.JsonlSink.repair(p) == 0
    p.write_text('{"msg_id":"1"}\n{"msg_id":"2"}\n')
    assert C.JsonlSink.repair(p) == 0


def test_repair_truncates_partial_tail(tmp_path):
    p = tmp_path / "b.jsonl"
    good = '{"msg_id":"1","content":"甲"}\n'
    bad = '{"msg_id":"2","content":"半写'      # 无换行、非合法 JSON
    p.write_bytes(good.encode() + bad.encode())
    dropped = C.JsonlSink.repair(p)
    assert dropped == len(bad.encode())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "坏尾行必须被剔除，且不能连带删掉好行"
    assert json.loads(lines[0])["msg_id"] == "1"


def test_repair_no_newline_single_line(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text('{"msg_id":"x"}')          # 完整 JSON 但无换行
    dropped = C.JsonlSink.repair(p)
    assert dropped == len(b'{"msg_id":"x"}')
    assert p.read_text(encoding="utf-8") == ""


def test_sink_selfheals_before_append(tmp_path):
    p = tmp_path / "d.jsonl"
    good = b'{"msg_id":"1"}\n'
    p.write_bytes(good + b'{"msg_id":"2","half')
    sink = C.JsonlSink(p)
    assert sink.repaired_bytes > 0
    sink.emit({"msg_id": "3"})
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert [m["msg_id"] for m in lines] == ["1", "3"], "半写行须消失，且新记录紧跟其后"


def test_cli_recover(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    jl = tmp_path / "data" / "wecom_messages.jsonl"
    cfg.write_text(json.dumps({
        "jsonl_path": str(jl), "state_path": str(tmp_path / "data" / ".seen_ids.json"),
        "engine_path": str(C.ENGINE_DEFAULT), "bundle_id": "none",
    }), encoding="utf-8")
    jl.parent.mkdir(parents=True, exist_ok=True)
    jl.write_bytes(b'{"msg_id":"1"}\n{"msg_id":"2","ha')
    argv = sys.argv[:]
    sys.argv = ["prog", "--config", str(cfg), "--recover"]
    try:
        code = C.main()
    finally:
        sys.argv = argv
    assert code == 0
    assert jl.read_text(encoding="utf-8") == '{"msg_id":"1"}\n'


# ---- 真实 kill -9 ----

_APPENDER_SRC = r'''
import sys, time
p, ready = sys.argv[1], sys.argv[2]
for i in range(1, 4001):
    with open(p, "ab") as f:
        # 刻意把一条记录拆两段写，让 SIGKILL 能真的落在“写一半”
        f.write(('{"msg_id":"%d","pad":"' % i).encode())
        f.flush()
        if i == 5:
            open(ready, "w").close()      # 通知父进程：半行已落盘
            time.sleep(60)                  # 保持半写状态等被杀
        f.write(b"x" * 60 + b'"}\n')
'''


def _run_real_kill9(tmp_path):
    """真起子进程分两次写同一条记录；见就绪标记即 SIGKILL，保证杀在行中间。

    返回 (jsonl, 被杀时字节数)。
    """
    jl = tmp_path / "killed.jsonl"
    ready = tmp_path / "ready"
    script = tmp_path / "appender.py"
    script.write_text(_APPENDER_SRC, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(script), str(jl), str(ready)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 15
    while time.time() < deadline:
        if ready.exists():
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
            return jl, jl.stat().st_size
        if proc.poll() is not None:
            break
        time.sleep(0.002)
    proc.kill(); proc.wait(timeout=10)
    raise RuntimeError("未能抓到半写状态（就绪标记未出现）")


def test_real_kill9_leaves_partial_line_then_recovers(tmp_path):
    """端到端：SIGKILL 制造真实半写尾行 → repair 后全部可解析、历史零丢失。"""
    jl, size_at_kill = _run_real_kill9(tmp_path)
    raw = jl.read_bytes()

    # 复现 kill -9 的真实后果：最后一行大概率残缺（若恰好落在换行上则跳过）
    last_nl = raw.rfind(b"\n")
    assert raw[last_nl + 1:] != b"", "本用例要求 kill 确实打在写一半时（否则换时间重跑）"

    before_lines = raw[:last_nl + 1].decode("utf-8").splitlines()
    assert all(json.loads(l) for l in before_lines), "截断点之前的行必须全部完好"

    dropped = C.JsonlSink.repair(jl)
    assert dropped == len(raw) - (last_nl + 1), "丢弃量应恰为残缺尾部"

    after = [json.loads(x) for x in jl.read_text(encoding="utf-8").splitlines()]
    assert after == [json.loads(l) for l in before_lines], "修复后不得丢任何一条历史"
    assert [m["msg_id"] for m in after] == sorted(
        (m["msg_id"] for m in after), key=int), "顺序保持"

    # 修复后再写入，新记录能干净续接
    sink = C.JsonlSink(jl)
    sink.emit({"msg_id": "999999"})
    final = [json.loads(x) for x in jl.read_text(encoding="utf-8").splitlines()]
    assert final[-1]["msg_id"] == "999999"
    assert len(final) == len(after) + 1


def test_seen_store_corrupt_recovers(tmp_path):
    """已见集损坏（kill -9 的另一后果）→ 安全降级为空，不崩。"""
    st = tmp_path / "seen.json"
    st.write_text("{ 坏JSON", encoding="utf-8")
    s = C.SeenStore(st)
    assert s.ids == set() and s.content_hashes == set()
    assert s.is_new("abc", "h1") is True
