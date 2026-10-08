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
import subprocess
import sys
from typing import Tuple, Optional

def get_current_session() -> Optional[dict]:
    """获取当前活跃会话信息"""
    result = subprocess.run(
        ["openclaw", "sessions", "list", "--json", "--limit", "10"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    sessions = data.get("sessions", [])
    # 找到当前活跃的主会话
    for s in sessions:
        key = s.get("key", "")
        if key.startswith("agent:main:main"):
            return s
    # 找不到返回第一个活跃会话
    return sessions[0] if sessions else None

def check_context_usage(session: dict) -> Tuple[float, bool]:
    """检查上下文使用率，返回 (pct, needs_recovery)"""
    total_tokens = session.get("totalTokens") or 0
    model = session.get("model", "model-scheduling/auto")
    
    # 基于实测校准的 ctx 窗口（来自 session_ctx_watch.py）
    CTX_BY_MODEL = {
        "longcat/LongCat-2.0": 1048576,
        "LongCat-2.0": 1048576,
        "coding-plan/deepseek-v4-flash-ga-260731": 1048576,
        "deepseek-v4-flash-ga-260731": 1048576,
        "model-scheduling/auto": 262144,
        "auto": 262144,
        "coding-plan/doubao-seed-2-1-turbo": 262144,
        "doubao-seed-2-1-turbo": 262144,
    }
    default_ctx = 131072
    ctx = CTX_BY_MODEL.get(model, default_ctx)
    
    if ctx == 0 or total_tokens == 0:
        return (0.0, False)
    
    pct = total_tokens / ctx
    # 80% 以上需要恢复
    return (pct, pct >= 0.8)

def execute_command(cmd: str) -> bool:
    """执行 openclaw 命令"""
    print(f"🔧 执行: {cmd}")
    result = subprocess.run(
        cmd.split(),
        capture_output=False,
        timeout=60,
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
    
    # 阶梯 1: /compact
    print("\n📶 阶梯 1/3: 尝试 /compact")
    if execute_command("openclaw /compact"):
        # 重新检查
        session = get_current_session()
        if session:
            pct, needs_recovery = check_context_usage(session)
            print(f"📊 压缩后使用率: {pct * 100:.1f}%")
            if not needs_recovery:
                print("✅ /compact 成功，上下文恢复到安全范围")
                return 0
    
    # 阶梯 2: /reset
    print("\n📶 阶梯 2/3: /compact 未解决，尝试 /reset")
    if execute_command("openclaw /reset"):
        session = get_current_session()
        if session:
            pct, needs_recovery = check_context_usage(session)
            print(f"📊 reset 后使用率: {pct * 100:.1f}%")
            if not needs_recovery:
                print("✅ /reset 成功，上下文恢复到安全范围")
                return 0
    
    # 阶梯 3: /new
    print("\n📶 阶梯 3/3: /reset 未解决，提示用户执行 /new")
    print("⚠️  两步恢复后上下文仍超限，请手动执行:")
    print("    /new")
    print("这会启动全新干净会话，工作进度不会丢失。")
    return 2

if __name__ == "__main__":
    sys.exit(main())
