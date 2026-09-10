"""
State Protocol 测试 — 共享状态 + reducer 合并
"""
import os
import pytest
from state_reducer import StateReducer


class TestStateReducerBasic:
    """基本读写"""

    def test_write_and_read(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        ok, msg = sr.write_state("project/test", "key1", {"value": 42})
        assert ok is True

        data, err = sr.read_state("project/test", "key1")
        assert err == ""
        assert data == {"value": 42}

    def test_read_nonexistent(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        data, err = sr.read_state("project/none", "nope")
        assert data is None
        assert "not found" in err

    def test_overwrite_last_write_wins(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.write_state("proj/a", "k", {"x": 1})
        sr.write_state("proj/a", "k", {"x": 2}, reducer="last-write-wins")
        data, _ = sr.read_state("proj/a", "k")
        assert data == {"x": 2}


class TestReducers:
    """三种 reducer 策略"""

    def test_merge_reducer_dict(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.write_state("proj/merge", "data", {"a": 1, "b": 2})
        ok, _ = sr.write_state("proj/merge", "data", {"b": 3, "c": 4}, reducer="merge")
        assert ok is True

        data, _ = sr.read_state("proj/merge", "data")
        assert data == {"a": 1, "b": 3, "c": 4}

    def test_append_reducer_list(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.write_state("proj/append", "items", [1, 2, 3])
        ok, _ = sr.write_state("proj/append", "items", [4, 5], reducer="append")
        assert ok is True

        data, _ = sr.read_state("proj/append", "items")
        assert data == [1, 2, 3, 4, 5]

    def test_append_reducer_on_non_list_old(self, tmp_workspace):
        """旧值不是 list 时，append 会把旧值包成 list 再拼接"""
        sr = StateReducer(root_path="state")
        sr.write_state("proj/append2", "val", "old_string")
        ok, _ = sr.write_state("proj/append2", "val", ["new"], reducer="append")
        assert ok is True

        data, _ = sr.read_state("proj/append2", "val")
        assert data == ["old_string", "new"]

    def test_unknown_reducer(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        ok, msg = sr.write_state("proj/x", "k", "v", reducer="nonexistent")
        assert ok is False
        assert "Unknown reducer" in msg


class TestStateListAndDelete:
    """list 和 delete 操作"""

    def test_list_states(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.write_state("proj/list", "a", 1)
        sr.write_state("proj/list", "b", 2)
        sr.write_state("proj/list", "c", 3)

        keys, err = sr.list_states("proj/list")
        assert err == ""
        assert sorted(keys) == ["a", "b", "c"]

    def test_list_nonexistent_scope(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        keys, err = sr.list_states("proj/nonexistent")
        assert keys is None
        assert "not found" in err

    def test_delete_state(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.write_state("proj/del", "k", "v")
        ok, _ = sr.delete_state("proj/del", "k")
        assert ok is True

        data, err = sr.read_state("proj/del", "k")
        assert data is None
        assert "not found" in err

    def test_delete_nonexistent(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        ok, msg = sr.delete_state("proj/none", "k")
        assert ok is False
        assert "not found" in msg


class TestCustomReducer:
    """自定义 reducer 注册"""

    def test_register_and_use_custom_reducer(self, tmp_workspace):
        sr = StateReducer(root_path="state")
        sr.register_reducer("sum", lambda old, new: old + new)

        sr.write_state("proj/custom", "total", 10)
        ok, _ = sr.write_state("proj/custom", "total", 5, reducer="sum")
        assert ok is True

        data, _ = sr.read_state("proj/custom", "total")
        assert data == 15
