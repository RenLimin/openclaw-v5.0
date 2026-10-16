#!/usr/bin/env python3
"""
自动上下文压缩恢复 — 三阶梯处理

当自动压缩失败提示 `⚠️ Context is too large and auto-compaction could not recover this turn` 时，
自动按阶梯尝试恢复：
1. 第一步：调用 `/compact` — 原生压缩上下文
2. 第二步：如果仍超阈值，调用 `/reset` — 清理内部状态，保留 transcript
3. 第三步：如果仍超阈值，提示用户执行 `/new` — 全新会话

设计依据：PRD-v1.0 F2 需求，上下文过大处理流程
"""
import json
import shlex
import subprocess
import sys
from typing import Tuple, Optional

def get_current_session() -> Optional[dict]:
    """获取当前活跃会话信息（openclaw sessions list --json）"""
    result = subprocess.run(
        ["openclaw", "sessions", "list", "--json", "--limit", "10"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    sessions = data.get("sessions", [])
    # 找到当前活跃的主会话
    for s in sessions:
        key = s.get("key", "")
        if key.startswith("agent:main:main"):
            return s
    # 找不到返回第一个 running 会话
    for s in sessions:
        if s.get("status") == "running":
            return s
    return sessions[0] if sessions else None

def check_context_usage(session: dict) -> Tuple[float, bool]:
    """检查上下文使用率，返回 (pct, needs_recovery)

    修复 2026-10-16：
    - 原实现硬编码 CTX_BY_MODEL 映射，且 model 字段实际是 "auto" 而非
      "model-scheduling/auto"，映射经常命中不到 → 用默认 131072 误判。
    - 改用 sessions list 自带的 contextTokens 字段（实测为 262144，与真实窗口一致）。
    """
    total_tokens = session.get("totalTokens") or 0
    # 直接读真实 ctx 窗口，不硬编码映射
    ctx = session.get("contextTokens") or 0
    if ctx == 0:
        ctx = 131072  # 兜底

    if ctx == 0 or total_tokens == 0:
        return (0.0, False)

    pct = total_tokens / ctx
    # 80% 以上需要恢复
    return (pct, pct >= 0.8)

def execute_command(cmd: str) -> bool:
    """执行 openclaw 命令（用 shlex.split 正确解析引号内的 session key）"""
    print(f"🔧 执行: {cmd}")
    result = subprocess.run(
        shlex.split(cmd),
        capture_output=False,
        timeout=120,
    )
    return result.returncode == 0

def main() -> int:
    """主流程：三阶梯自动恢复"""
    print("=" * 60)
    print("🚀 上下文自动压缩恢复 — 三阶梯处理")
    print("=" * 60)
    
    session = get_current_session()
    if not session:
        print("❌ 无法获取当前会话信息，中止恢复")
        return 1
    
    session_key = session.get("key", "unknown")
    print(f"📋 当前会话: {session_key}")
    print(f"🤖 使用模型: {session.get('model', 'unknown')}")
    print(f"🔢 当前 tokens: {session.get('totalTokens', 'unknown')}")
    
    pct, needs_recovery = check_context_usage(session)
    print(f"📊 上下文使用率: {pct * 100:.1f}%")
    
    if not needs_recovery:
        print("✅ 上下文使用率在安全范围内，无需恢复")
        return 0
    
    # 阶梯 1: 用正确命令压缩（openclaw sessions compact <key>，LLM 摘要）
    print("\n📶 阶梯 1/3: 尝试 /compact")
    if execute_command(f'openclaw sessions compact "{session_key}"'):
        # 重新检查
        session = get_current_session()
        if session:
            pct, needs_recovery = check_context_usage(session)
            print(f"📊 压缩后使用率: {pct * 100:.1f}%")
            if not needs_recovery:
                print("✅ /compact 成功，上下文恢复到安全范围")
                return 0

    # 阶梯 2: 强制截断兜底（--max-lines 不依赖 LLM 摘要，必定成功）
    print("\n📶 阶梯 2/3: LLM 摘要压缩未解决，尝试强制截断 (--max-lines)")
    if execute_command(f'openclaw sessions compact "{session_key}" --max-lines 200'):
        session = get_current_session()
        if session:
            pct, needs_recovery = check_context_usage(session)
            print(f"📊 截断后使用率: {pct * 100:.1f}%")
            if not needs_recovery:
                print("✅ 强制截断成功，上下文恢复到安全范围")
                return 0

    # 阶梯 3: 提示用户执行 /new（/reset 无 CLI 路径，需在会话内手动执行）
    print("\n📶 阶梯 3/3: 两步恢复后上下文仍超限，提示用户执行 /new")
    print("⚠️  两步恢复后上下文仍超限，请手动执行:")
    print("    /new")
    print("这会启动全新干净会话，工作进度不会丢失。")
    return 2

if __name__ == "__main__":
    sys.exit(main())
