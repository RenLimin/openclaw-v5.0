#!/usr/bin/env python3
"""log_cursor.LogCursorStore 单元测试（stdlib unittest + 真实临时文件）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from log_cursor import LogCursorStore  # noqa: E402


class LogCursorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "gateway.log")
        self.state = os.path.join(self.tmp.name, "cursor.json")
        self.store = LogCursorStore(self.state)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.store.read_new_lines(self.log), [])

    def test_first_run_baselines_no_history(self):
        with open(self.log, "w") as f:
            f.write("old line 1\nold line 2\n")
        # 首次默认 baseline：跳末尾，不回放历史
        self.assertEqual(self.store.read_new_lines(self.log), [])
        self.store.save()
        # 第二次仍无新增
        store2 = LogCursorStore(self.state)
        self.assertEqual(store2.read_new_lines(self.log), [])

    def test_first_run_full_read_when_baseline_disabled(self):
        with open(self.log, "w") as f:
            f.write("a\nb\n")
        lines = self.store.read_new_lines(self.log, baseline_on_first=False)
        self.assertEqual(lines, ["a", "b"])

    def test_incremental_read_after_append(self):
        with open(self.log, "w") as f:
            f.write("line1\nline2\n")
        self.assertEqual(self.store.read_new_lines(self.log), [])  # baseline
        self.store.save()

        with open(self.log, "a") as f:
            f.write("line3\nline4\n")
        store2 = LogCursorStore(self.state)
        self.assertEqual(store2.read_new_lines(self.log), ["line3", "line4"])

    def test_no_trailing_newline_last_line_preserved(self):
        with open(self.log, "w") as f:
            f.write("base\n")
        self.store.read_new_lines(self.log)
        self.store.save()
        with open(self.log, "a") as f:
            f.write("partial-without-newline")
        store2 = LogCursorStore(self.state)
        self.assertEqual(
            store2.read_new_lines(self.log), ["partial-without-newline"]
        )

    def test_rotation_inode_change_rereads_from_start(self):
        with open(self.log, "w") as f:
            f.write("old-generation\n")
        self.store.read_new_lines(self.log)
        self.store.save()
        inode_before = os.stat(self.log).st_ino

        # 模拟轮转：删除后以同名重建（inode 变化）
        os.remove(self.log)
        with open(self.log, "w") as f:
            f.write("rotated-new\n")
        if os.stat(self.log).st_ino == inode_before:
            self.skipTest("filesystem reused inode; rotation path not exercisable")
        store2 = LogCursorStore(self.state)
        self.assertEqual(store2.read_new_lines(self.log), ["rotated-new"])

    def test_truncation_shorter_file_rereads(self):
        with open(self.log, "w") as f:
            f.write("x" * 100 + "\n")
        self.store.read_new_lines(self.log)
        self.store.save()
        # 截断为更短的新内容
        with open(self.log, "w") as f:
            f.write("short\n")
        store2 = LogCursorStore(self.state)
        self.assertEqual(store2.read_new_lines(self.log), ["short"])


if __name__ == "__main__":
    unittest.main()
