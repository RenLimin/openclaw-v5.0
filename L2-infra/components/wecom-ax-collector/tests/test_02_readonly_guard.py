"""只读红线机器门禁（gateway-owner 2026-11-24 明令）。

规则：通过 AX 操作【已登录】的企业微信/微信客户端，严格只读，
      严禁任何发送/输入/点击/设值动作。

本测试静态扫描引擎源码，剥离注释后命中任一禁用 API 即失败：
  - CGEvent / CGEventSource / .post(tap:)   —— 合成鼠标/键盘事件
  - mouseEvent / keyDown / keyUp            —— 具体输入事件
  - AXUIElementSetAttributeValue            —— 给 AX 元素写值（可写入输入框）
  - AXUIElementPerformAction                 —— 触发按钮（如「发送」）

注释里允许出现这些词（用于说明红线），故扫描前先剥除 // 与 /* */ 注释。
"""
from __future__ import annotations

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "engine" / "wecom_ax_engine.swift"
COLLECTOR = Path(__file__).resolve().parents[1] / "scripts" / "wecom_collector.py"

# 禁用的「会对客户端产生输入/副作用」的 API（剥离注释后不应出现）
FORBIDDEN_SWIFT = [
    "CGEvent(",
    "CGEventSource",
    "CGEventCreateMouseEvent",
    "CGEventCreateKeyboardEvent",
    "mouseEventSource",
    ".post(tap:",
    "AXUIElementSetAttributeValue",
    "AXUIElementPerformAction",
    "keyDown",
    "keyUp",
]


def strip_comments(src: str) -> str:
    # 去块注释
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    # 去整行与行内 // 注释
    lines = []
    for line in src.splitlines():
        idx = line.find("//")
        lines.append(line if idx < 0 else line[:idx])
    return "\n".join(lines)


def test_engine_source_exists():
    assert ENGINE.exists(), f"引擎源码缺失: {ENGINE}"


def test_engine_has_no_input_or_write_primitives():
    code = strip_comments(ENGINE.read_text(encoding="utf-8"))
    hits = [tok for tok in FORBIDDEN_SWIFT if tok in code]
    assert not hits, (
        "只读红线：引擎中出现被禁止的输入/写入原语，禁止通过 AX 对企微/微信发送或操作："
        f"{hits}。如需例外必须由 gateway-owner 书面授权。"
    )


def test_engine_uses_only_readonly_ax_get():
    """允许的 AX 调用应只有 Copy/Get 系列只读接口。"""
    code = strip_comments(ENGINE.read_text(encoding="utf-8"))
    ax_calls = set(re.findall(r"AXUIElement\w+", code))
    mutating = {c for c in ax_calls if "Set" in c or "Perform" in c}
    assert not mutating, f"发现写入/动作类 AX API：{sorted(mutating)}"
    # 至少确实在用只读 Get（证明扫描对象正确）
    assert "AXUIElementCopyAttributeValue" in ax_calls


def test_click_subcommand_removed():
    code = strip_comments(ENGINE.read_text(encoding="utf-8"))
    assert 'case "click"' not in code, "click 子命令必须移除（只读红线）"


def test_collector_has_no_ui_input_and_webhook_default_off():
    """Python 调度器不得合成 UI 输入；唯一网络出口 webhook 默认关闭。"""
    code = COLLECTOR.read_text(encoding="utf-8")
    for bad in ["pyautogui", "pynput", "CGEvent", "keyboard.write", "pyperclip.copy"]:
        assert bad not in code, f"调度器不得引入 UI 输入手段：{bad}"
    # webhook 仅允许作为「导出到自有端点」的可选出口，且默认配置必须为 null
    example = Path(__file__).resolve().parents[1] / "config.example.json"
    import json
    cfg = json.loads(example.read_text(encoding="utf-8"))
    assert cfg.get("webhook_url") is None, "webhook 默认必须关闭（webhook_url=null）"
