#!/usr/bin/env python3
"""Gateway 日志增量游标。

背景：旧版扫描器每次只看"最近 30 分钟"的 tail，而 cron 每 2h 才跑一次，
两次扫描之间发生、且恰好滑出 30min 窗口的事件会永久漏报（2026-11-03
LLM timeout 漏处置事故）。

本模块按 (inode, offset) 记录每个日志文件的读取位置，每次只返回"自上次
扫描以来新增的行"，因此事件检测不再依赖时间窗口，cron 间隔再长也不漏。

轮转处理：inode 变化或文件变短（被截断/轮转）→ 视为新文件，全量读取
（轮转后的新文件通常很小）。首次部署对既有大日志做 baseline（直接跳到
末尾，不回放历史），避免一上线就告警风暴。

仅依赖 stdlib。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

# 单次最多读取的新增字节数，防止异常膨胀一次性灌入。
MAX_READ_BYTES = 8 * 1024 * 1024


class LogCursorStore:
    """按文件路径持久化 (inode, offset, initialized) 游标。"""

    def __init__(self, state_path: str):
        self.state_path = state_path
        self._state: Dict[str, dict] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                files = data.get("files")
                if isinstance(files, dict):
                    self._state = files
        except (OSError, ValueError):
            self._state = {}
        self._loaded = True

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp = f"{self.state_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"files": self._state}, f, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def read_new_lines(
        self,
        log_path: str,
        *,
        baseline_on_first: bool = True,
        max_read_bytes: int = MAX_READ_BYTES,
    ) -> List[str]:
        """返回自上次读取以来新增的文本行（不含行尾换行）。

        - 文件不存在：返回 []，不写游标。
        - 首次见到该文件：baseline_on_first=True 时跳到当前末尾返回 []；
          False 时全量读取当前内容。
        - inode 变化或文件变短（轮转/截断）：全量读取新文件。
        """
        self._load()
        try:
            st = os.stat(log_path)
        except OSError:
            return []

        inode = st.st_ino
        size = st.st_size
        key = log_path
        cur = self._state.get(key)

        # 判定是否需要从头读：无游标 / 轮转(inode 变) / 截断(size 变短)。
        rotated = cur is None or cur.get("inode") != inode or size < cur.get("offset", 0)

        if rotated:
            if cur is None and baseline_on_first:
                # 首次部署：建立 baseline，不回放历史大日志。
                self._state[key] = {"inode": inode, "offset": size, "initialized": True}
                return []
            start = 0
        else:
            start = int(cur.get("offset", 0))

        if start == size:
            return []

        read_to = min(size, start + max_read_bytes)
        try:
            with open(log_path, "rb") as f:
                f.seek(start)
                chunk = f.read(read_to - start)
        except OSError:
            return []

        # 更新游标到实际读到的位置（即便没读完也推进，避免反复读同一块）。
        self._state[key] = {"inode": inode, "offset": read_to, "initialized": True}

        text = chunk.decode("utf-8", errors="replace")
        # splitlines 同时吞掉 \n / \r\n；末行若无换行也能保留。
        return text.splitlines()
