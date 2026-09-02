"""
会话隔离与共享组件 — 状态合并核心
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import os
import json
from typing import Dict, Any, Optional, Tuple, Callable, List
from .utils import ensure_directory

# 内置 reducers
REDUCERS = {
    "append": lambda old, new: old + new if isinstance(old, list) else [old] + new,
    "merge": lambda old, new: {**old, **new} if isinstance(old, dict) else new,
    "last-write-wins": lambda old, new: new,
}

class StateReducer:
    """状态合并reducer — 确定性合并并行写入"""

    def __init__(self, root_path: str = "state"):
        """
        :param root_path: 状态根目录
        """
        self.root_path = root_path
        self._reducers = REDUCERS.copy()

    def register_reducer(self, name: str, reducer: Callable[[Any, Any], Any]) -> None:
        """注册自定义reducer"""
        self._reducers[name] = reducer

    def get_full_path(self, scope: str, key: str) -> str:
        """获取完整路径: scope: `project/bdms` → `state/project/bdms/key.json`"""
        return os.path.join(self.root_path, scope, f"{key}.json")

    def read_state(self, scope: str, key: str) -> Tuple[Optional[Any], str]:
        """读取当前状态"""
        full_path = self.get_full_path(scope, key)
        if not os.path.exists(full_path):
            return None, f"State {scope}/{key} not found"

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, ""
        except Exception as e:
            return None, f"Failed to read state: {str(e)}"

    def write_state(
        self,
        scope: str,
        key: str,
        new_data: Any,
        reducer: str = "last-write-wins"
    ) -> Tuple[bool, str]:
        """
        写入状态，应用reducer合并
        :param scope: 范围 (e.g. project/bdms)
        :param key: 状态键
        :param new_data: 新数据
        :param reducer: reducer 名称
        :return: (success, message)
        """
        if reducer not in self._reducers:
            return False, f"Unknown reducer: {reducer}, available: {list(self._reducers.keys())}"

        full_path = self.get_full_path(scope, key)
        ok, err = ensure_directory(os.path.dirname(full_path))
        if not ok:
            return False, err

        # 读取旧数据
        old_data, err = self.read_state(scope, key)
        if err and "not found" not in err:
            return False, err

        # 应用reducer
        if old_data is None:
            final_data = new_data
        else:
            final_data = self._reducers[reducer](old_data, new_data)

        # 写入
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2, ensure_ascii=False)
            return True, f"State {scope}/{key} written successfully"
        except Exception as e:
            return False, f"Failed to write state: {str(e)}"

    def list_states(self, scope: str) -> Tuple[Optional[List[str]], str]:
        """列出该scope下所有状态"""
        full_path = os.path.join(self.root_path, scope)
        if not os.path.exists(full_path):
            return None, f"Scope {scope} not found"

        try:
            files = [f for f in os.listdir(full_path) if f.endswith(".json")]
            keys = [os.path.splitext(f)[0] for f in files]
            return keys, ""
        except Exception as e:
            return None, f"Failed to list states: {str(e)}"

    def delete_state(self, scope: str, key: str) -> Tuple[bool, str]:
        """删除状态"""
        full_path = self.get_full_path(scope, key)
        if not os.path.exists(full_path):
            return False, f"State {scope}/{key} not found"

        try:
            os.remove(full_path)
            return True, f"State {scope}/{key} deleted"
        except Exception as e:
            return False, f"Failed to delete state: {str(e)}"
