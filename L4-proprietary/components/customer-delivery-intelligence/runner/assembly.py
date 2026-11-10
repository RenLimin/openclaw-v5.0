"""装配层：注入配置 -> store/engine/steps，保持引擎与业务解耦。"""
from __future__ import annotations
import os
import yaml
from .state import CheckpointStore
from .engine import Engine
from .steps import n1_guard, n2_collect, n4_parse, n5_compose, n7_render


def load_config(path: str | None = None) -> dict:
    path = path or os.environ.get("CDI_CONFIG", "config.yaml")
    if not os.path.exists(path):
        path = "config.example.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_engine(config: dict | None = None) -> Engine:
    config = config or load_config()
    store = CheckpointStore(config["storage"]["checkpoint_db"])
    steps = {
        "N1_guard": n1_guard.run,
        "N2_collect": n2_collect.run,
        "N4_parse": n4_parse.run,
        "N5_compose": n5_compose.run,
        "N7_render": n7_render.run,
    }
    return Engine(store, steps)
