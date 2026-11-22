"""agent 派发后端（dispatch）——可插拔执行接口。

DESIGN §2/§7.3：`agent` 字段的派发后端采用「可插拔接口 + 默认派发」。
本模块提供默认后端：通过 `openclaw agent` CLI 发起一次 agent turn
（`sessions_spawn` 的工具级等价物——脚本进程无法直接调用 agent 工具，
CLI 是文档认可的 programmatic 路径，见 docs/tools/agent-send.md）。

约束：
- 绝对路径兜底 openclaw（AGENTS.md：子进程调外部 CLI 禁止裸命令名依赖 PATH）
- 每任务独立 session-key（`agent:main:dag-<run_id>-<task_id>`），互不污染
- 任务级超时透传 CLI `--timeout`
- 要求 agent 以 JSON 回报 outputs；解析失败 → 任务失败（不静默）
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

# openclaw CLI 候选绝对路径（PATH 兜底）
_CLI_CANDIDATES = (
    "/opt/homebrew/bin/openclaw",
    "/usr/local/bin/openclaw",
    str(Path.home() / ".openclaw" / "tmp" / "agent-cli" / "openclaw"),
)

# 要求 agent 回报的 JSON 契约
_REPLY_SCHEMA = (
    '并在最终回复中只输出一个 JSON 对象（无额外文字）：\n'
    '{"outputs": {"<output_name>": <value>, ...}}\n'
    '若无可产出 outputs，输出 {}。若执行失败，输出 {"error": "<原因>"}。'
)


def resolve_cli() -> str:
    """定位 openclaw CLI（绝对路径优先，PATH 兜底）。"""
    found = shutil.which("openclaw")
    if found:
        return found
    for cand in _CLI_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise FileNotFoundError(
        "未找到 openclaw CLI（PATH 与候选路径均无）；请确认 Gateway 已安装"
    )


def build_prompt(task, inputs: dict) -> str:
    """构造派发消息：DAG 上下文 + 动作 + 输入 + JSON 回报契约。"""
    outputs = list(task.outputs) if task.outputs else []
    return (
        f"你是 DAG 工作流「{getattr(task, 'dag_name', 'dag')}」中的任务节点。\n"
        f"任务 ID: {task.id}\n"
        f"角色: {task.agent}\n"
        f"动作: {task.action}\n"
        f"期望 outputs: {outputs}\n"
        f"输入: {json.dumps(inputs, ensure_ascii=False, default=str)}\n\n"
        f"请执行该动作，{_REPLY_SCHEMA}"
    )


def _iter_json_objects(text: str):
    """按括号平衡提取 {...} 子串（容忍嵌套与字符串内括号）。"""
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start:i + 1]
                    start = -1


def parse_reply(final_text: str) -> dict:
    """从 agent 回复文本解析 outputs；无法解析 → 抛 ValueError。

    取文本中最后一个可解析的平衡 JSON 对象（容忍前后解释性文字）。
    """
    for raw in reversed(list(_iter_json_objects(final_text))):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "outputs" in obj:
            return obj["outputs"]
        if isinstance(obj, dict) and "error" in obj:
            raise ValueError(f"agent 回报失败: {obj['error']}")
    raise ValueError(f"agent 回复未含可解析的 outputs JSON: {final_text[:200]!r}")


def make_agent_dispatcher(
    *,
    cli: str | None = None,
    agent_id: str = "main",
    run_id: str = "run",
    timeout_s: int = 600,
    prompt_builder: Callable = build_prompt,
) -> Callable:
    """构造 TaskRunner 兼容的派发函数 fn(task, inputs) -> dict | None。

    - cli: openclaw 可执行路径（默认 resolve_cli()）
    - agent_id: 目标 agent（默认 main）
    - run_id: 本次 run 标识（用于 session-key 隔离）
    - timeout_s: 单任务 CLI 超时（<=0 表示不限）
    """
    cli_path = cli or resolve_cli()

    def _dispatch(task, inputs: dict) -> dict | None:
        prompt = prompt_builder(task, inputs)
        session_key = f"agent:{agent_id}:dag-{run_id}-{task.id}"
        cmd = [
            cli_path,
            "agent",
            "--agent",
            agent_id,
            "--session-key",
            session_key,
            "--message",
            prompt,
            "--json",
        ]
        if timeout_s and timeout_s > 0:
            cmd += ["--timeout", str(timeout_s)]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_s) if timeout_s and timeout_s > 0 else None,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"派发失败 (rc={proc.returncode}): "
                f"{(proc.stderr or proc.stdout).strip()[:300]}"
            )
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI 输出非 JSON: {proc.stdout[:300]!r}") from exc
        if not env.get("ok"):
            err = env.get("error", {}) or {}
            raise RuntimeError(f"agent turn 失败: {err.get('message', env)}")

        final_text = env.get("final") or ""
        if not final_text and env.get("payloads"):
            final_text = " ".join(p.get("text", "") for p in env["payloads"])
        if not task.outputs:
            return None
        return parse_reply(final_text)

    return _dispatch
