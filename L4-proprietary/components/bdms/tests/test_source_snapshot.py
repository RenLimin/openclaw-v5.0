"""源文件快照模块测试（source_snapshot）。

锁定三条契约：
1. 归档把源文件复制进 workspace 快照目录并写 MANIFEST（含 sha256）；
2. 幂等：同内容重复归档不产生 history；
3. 永久：内容变化时旧版自动进 history/，当前为最新版，旧内容不丢失。
"""

import json
from pathlib import Path

import pytest

from bdms.modules.delivery_report.source_snapshot import archive_sources


@pytest.fixture()
def src_file(tmp_path: Path) -> Path:
    sd = tmp_path / "src"
    sd.mkdir()
    f = sd / "209906周报-签约项目统计.csv"
    f.write_text("v1", encoding="utf-8")
    return f


def test_archive_creates_snapshot_and_manifest(tmp_path, src_file):
    root = tmp_path / "snap"
    res = archive_sources("209906", root, [("ones", src_file)])

    snap = root / "209906"
    assert (snap / src_file.name).read_text(encoding="utf-8") == "v1"
    man = json.loads((snap / "MANIFEST.json").read_text(encoding="utf-8"))
    assert man["report_month"] == "209906"
    entry = man["files"][0]
    assert entry["category"] == "ones"
    assert len(entry["sha256"]) == 64
    assert entry["bytes"] > 0
    assert res["history"] == []


def test_archive_idempotent_same_content(tmp_path, src_file):
    root = tmp_path / "snap"
    archive_sources("209906", root, [("ones", src_file)])
    res2 = archive_sources("209906", root, [("ones", src_file)])
    assert res2["history"] == []
    assert not (root / "209906" / "history").exists()


def test_archive_keeps_old_version_in_history(tmp_path, src_file):
    root = tmp_path / "snap"
    archive_sources("209906", root, [("ones", src_file)])

    src_file.write_text("v2-changed", encoding="utf-8")
    res = archive_sources("209906", root, [("ones", src_file)])

    # 当前版本为最新
    assert (root / "209906" / src_file.name).read_text(encoding="utf-8") == "v2-changed"
    # 旧版进 history 且内容不丢
    assert len(res["history"]) == 1
    hist = (root / "209906" / "history" / res["history"][0])
    assert hist.read_text(encoding="utf-8") == "v1"


def test_archive_records_missing_source(tmp_path, src_file):
    root = tmp_path / "snap"
    ghost = src_file.parent / "missing.csv"
    res = archive_sources("209906", root, [("ones", ghost)])
    assert res["archived"][0]["error"] == "SOURCE_MISSING"
