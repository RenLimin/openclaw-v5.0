#!/usr/bin/env python3
"""回归测试：按需服务（lifecycle=on_demand）待机时，子探针不得渲染为失败。

背景（事故 2026-11-26）：embedding 服务 idleStopMs=600000 空闲即停属设计行为，
父探针已正确判 standby，但展示层把 l1/l2 两个子探针逐条渲染成 ❌，
造成「看起来坏了」的长期误报。修法：待机态子探针统一折叠为 skip。

同时守住反向语义：管理方（gateway）不健康时不得判 standby，
必须保持 failed——否则会把真故障伪装成正常待机。
"""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "service_health_check.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("service_health_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_config(tmp_path, *, manager_cmd="true"):
    cfg = {
        "_comment": "test fixture",
        "_version": 1,
        "services": {
            "demo-on-demand": {
                "name": "Demo 按需服务",
                "description": "fixture",
                "category": "infra",
                "priority": "high",
                "lifecycle": "on_demand",
                "checks": {
                    "l1_health_endpoint": {
                        "type": "command",
                        "command": "false",
                        "timeout": 5,
                        "label": "健康端点",
                    },
                    "l2_business_path": {
                        "type": "command",
                        "command": "false",
                        "timeout": 5,
                        "label": "业务路径",
                    },
                },
                "manager": {
                    "type": "command",
                    "command": manager_cmd,
                    "timeout": 5,
                    "label": "管理方健康",
                },
            }
        },
    }
    p = tmp_path / "services.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def test_standby_suppresses_subprobe_failures(tmp_path):
    """核心断言：待机态下没有任何子探针被判 fail。"""
    mod = _load()
    cfg_path = _write_config(tmp_path)
    report = mod.ServiceChecker(mod.load_config(str(cfg_path))).run(["demo-on-demand"])

    svc = report["services"]["demo-on-demand"]
    assert svc["overall"] == "standby", svc
    assert svc["standby_reason"], "待机原因必须写出"
    assert report["summary"]["standby"] == 1
    assert report["summary"]["failed"] == 0
    assert all(c["status"] != "fail" for c in svc["checks"].values()), svc["checks"]
    assert all(c["status"] == "skip" for c in svc["checks"].values()), svc["checks"]


def test_manager_down_keeps_failed_semantics(tmp_path):
    """管理方不健康时不得判 standby——保持原有 failed 语义。"""
    mod = _load()
    cfg_path = _write_config(tmp_path, manager_cmd="false")
    report = mod.ServiceChecker(mod.load_config(str(cfg_path))).run(["demo-on-demand"])

    svc = report["services"]["demo-on-demand"]
    assert svc["overall"] == "failed", svc
    assert report["summary"]["failed"] == 1
    assert any(c["status"] == "fail" for c in svc["checks"].values())


def test_probe_definitions_preserved():
    """探针定义本身必须保留——服务真跑起来时仍要验业务路径。"""
    mod = _load()
    cfg = mod.load_config(str(SCRIPT.parent.parent / "config" / "services.json"))
    emb = cfg["services"]["llama-cpp-embedding"]
    assert emb.get("lifecycle") == "on_demand"
    assert "l1_health_endpoint" in emb["checks"], "L1 探针不得删除"
    assert "l2_embedding_request" in emb["checks"], "L2 探针不得删除"
    assert emb["checks"]["l2_embedding_request"].get("expect_contains")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_standby_suppresses_subprobe_failures(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_manager_down_keeps_failed_semantics(Path(d))
    test_probe_definitions_preserved()
    print("OK: standby 抑制 + 管理方降级语义 + 探针定义保留 均通过")
