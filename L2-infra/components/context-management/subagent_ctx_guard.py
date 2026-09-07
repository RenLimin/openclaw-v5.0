#!/usr/bin/env python3
"""
Subagent 上下文保护辅助脚本

根据任务描述和预估步数，计算建议的分段策略和每段 token 预算。
核心是把 AGENTS.md 中的 subagent 上下文保护规范固化为可调用脚本。

用法:
    python3 subagent_ctx_guard.py <task_desc> <estimated_steps> [--model <model_id>]

示例:
    python3 subagent_ctx_guard.py "重构项目代码结构" 80
    python3 subagent_ctx_guard.py "批量处理 100 个文件" 120 --model coding-plan/doubao-seed-2-1-turbo
"""

import json
import sys
import argparse
from pathlib import Path

# 默认模型 ctx window 配置（单位: tokens）
# 基于实测校准，保守取值（取标称值的 80% 作为有效上限）
DEFAULT_CTX_WINDOWS = {
    "coding-plan/doubao-seed-2-1-turbo": 200000,   # 标称 262144 → 80%
    "coding-plan/doubao-seed-2-0-lite-260215": 200000,
    "coding-plan/doubao-seed-code-preview-251028": 200000,
    "coding-plan/deepseek-v4-flash": 800000,       # 标称 1M → 80%
    "model-scheduling/auto": 200000,                # 保守按 doubao 算
}

# 每步预估 token 用量（经验值）
TOKENS_PER_STEP = {
    "exec_output": 2000,       # 每步 exec 输出预估
    "file_read": 5000,         # 每次文件读取预估（中等大小文件）
    "tool_call": 500,          # 工具调用开销
    "thinking": 1000,          # 思考/推理 token
    "base_prompt": 8000,       # 基础 prompt（system + AGENTS.md 摘要）
}

OUTPUT_TOKEN_LIMIT = 2000  # 回传主会话的输出限制

def load_openclaw_config():
    """尝试从 openclaw.json 读取模型配置"""
    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        return cfg
    except (json.JSONDecodeError, OSError):
        return {}

def get_ctx_window(model_id: str) -> int:
    """获取模型的有效 ctx window（保守值）"""
    if model_id in DEFAULT_CTX_WINDOWS:
        return DEFAULT_CTX_WINDOWS[model_id]
    
    # 尝试从配置中读取
    cfg = load_openclaw_config()
    providers = cfg.get("models", {}).get("providers", {})
    for prov_id, prov_cfg in providers.items():
        for m in prov_cfg.get("models", []):
            if m.get("id") == model_id or f"{prov_id}/{m.get('id')}" == model_id:
                # 取 80% 作为有效上限
                return int(m.get("contextWindow", 128000) * 0.8)
    
    # 默认保守值
    return 100000

def calc_budget(task_desc: str, estimated_steps: int, model_id: str) -> dict:
    """
    计算 subagent 任务的分段策略和 token 预算
    
    返回:
    {
        "model": str,
        "ctx_window": int,           # 有效 ctx window
        "safe_threshold": int,       # 安全阈值（50% ctx）
        "estimated_total_tokens": int,
        "needs_segmentation": bool,
        "segments": int,             # 建议分段数
        "per_segment_steps": int,    # 每段步数
        "per_segment_budget": int,   # 每段 token 预算
        "output_limit": int,         # 输出 token 限制
        "timeout_seconds": int,      # 建议 runTimeoutSeconds
        "recommendations": [str],    # 建议清单
    }
    """
    ctx_window = get_ctx_window(model_id)
    safe_threshold = ctx_window // 2  # 50% 安全线
    
    # 预估总 token：基础 prompt + 每步开销 * 步数 + 输出预留
    base_prompt = TOKENS_PER_STEP["base_prompt"]
    step_cost = TOKENS_PER_STEP["exec_output"] + TOKENS_PER_STEP["tool_call"] + TOKENS_PER_STEP["thinking"]
    estimated_total = base_prompt + step_cost * estimated_steps + OUTPUT_TOKEN_LIMIT
    
    needs_segmentation = estimated_total > safe_threshold
    
    if needs_segmentation:
        # 计算需要分几段
        usable_per_seg = safe_threshold - base_prompt - OUTPUT_TOKEN_LIMIT
        steps_per_seg = max(1, usable_per_seg // step_cost)
        segments = (estimated_steps + steps_per_seg - 1) // steps_per_seg
        per_seg_budget = safe_threshold
    else:
        segments = 1
        steps_per_seg = estimated_steps
        per_seg_budget = estimated_total
    
    # 超时建议
    if estimated_steps <= 10:
        timeout = 600
    elif estimated_steps <= 30:
        timeout = 1800
    else:
        timeout = 3600
    
    recommendations = []
    recommendations.append(f"📊 任务预估总 token: ~{estimated_total:,}（模型 ctx 有效上限: {ctx_window:,}）")
    
    if needs_segmentation:
        recommendations.append(f"⚠️  预估超过 50% 安全线（{safe_threshold:,}），必须分段执行")
        recommendations.append(f"📋 建议分为 {segments} 段，每段 ~{steps_per_seg} 步，每段预算 ~{per_seg_budget:,} tokens")
    else:
        recommendations.append(f"✅ 单段可容纳（使用率 {estimated_total / safe_threshold * 100:.1f}%）")
    
    recommendations.append(f"⏱️  建议 runTimeoutSeconds: {timeout}s")
    recommendations.append(f"📝 输出回传主会话不超过 {OUTPUT_TOKEN_LIMIT} tokens（约 {OUTPUT_TOKEN_LIMIT * 4:,} 字符）")
    recommendations.append(f"💡 详细结果写入文件，主会话只读取摘要")
    
    if estimated_steps > 50:
        recommendations.append(f"🚨 超过 50 步的长任务必须拆成多个 subagent 串行执行")
    
    return {
        "model": model_id,
        "ctx_window": ctx_window,
        "safe_threshold": safe_threshold,
        "estimated_total_tokens": estimated_total,
        "needs_segmentation": needs_segmentation,
        "segments": segments,
        "per_segment_steps": steps_per_seg,
        "per_segment_budget": per_seg_budget,
        "output_limit": OUTPUT_TOKEN_LIMIT,
        "timeout_seconds": timeout,
        "recommendations": recommendations,
        "step_cost_breakdown": {
            "base_prompt": TOKENS_PER_STEP["base_prompt"],
            "per_step_exec_output": TOKENS_PER_STEP["exec_output"],
            "per_step_tool_call": TOKENS_PER_STEP["tool_call"],
            "per_step_thinking": TOKENS_PER_STEP["thinking"],
            "per_step_total": step_cost,
        }
    }

def format_report(result: dict, task_desc: str, estimated_steps: int) -> str:
    """格式化输出报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("🔒 Subagent 上下文保护评估")
    lines.append("=" * 60)
    lines.append(f"任务描述: {task_desc}")
    lines.append(f"预估步数: {estimated_steps} 步")
    lines.append(f"使用模型: {result['model']}")
    lines.append(f"有效 ctx: {result['ctx_window']:,} tokens（标称值 80%）")
    lines.append(f"安全阈值: {result['safe_threshold']:,} tokens（50% ctx）")
    lines.append("")
    lines.append("--- 预估分析 ---")
    lines.append(f"预估总 token: ~{result['estimated_total_tokens']:,}")
    lines.append(f"安全线使用率: {result['estimated_total_tokens'] / result['safe_threshold'] * 100:.1f}%")
    lines.append(f"是否需要分段: {'⚠️ 是' if result['needs_segmentation'] else '✅ 否'}")
    lines.append("")
    lines.append("--- 分段策略 ---")
    if result['needs_segmentation']:
        lines.append(f"建议分段数: {result['segments']} 段")
        lines.append(f"每段步数: ~{result['per_segment_steps']} 步")
        lines.append(f"每段预算: ~{result['per_segment_budget']:,} tokens")
    else:
        lines.append("单段执行即可")
    lines.append(f"建议超时: {result['timeout_seconds']}s (runTimeoutSeconds)")
    lines.append(f"输出限制: {result['output_limit']:,} tokens（回传主会话）")
    lines.append("")
    lines.append("--- 每步开销明细 ---")
    bd = result['step_cost_breakdown']
    lines.append(f"  基础 prompt: {bd['base_prompt']:,} tokens")
    lines.append(f"  每步 exec 输出: {bd['per_step_exec_output']:,} tokens")
    lines.append(f"  每步工具调用: {bd['per_step_tool_call']:,} tokens")
    lines.append(f"  每步思考开销: {bd['per_step_thinking']:,} tokens")
    lines.append(f"  每步总计: {bd['per_step_total']:,} tokens")
    lines.append("")
    lines.append("--- 建议清单 ---")
    for i, rec in enumerate(result['recommendations'], 1):
        lines.append(f"  {i}. {rec}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(
        description="Subagent 上下文保护评估 — 计算分段策略和 token 预算",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("task_desc", help="任务描述")
    parser.add_argument("estimated_steps", type=int, help="预估步数")
    parser.add_argument("--model", default="coding-plan/doubao-seed-2-1-turbo",
                        help="模型 ID（默认: coding-plan/doubao-seed-2-1-turbo）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    
    args = parser.parse_args()
    
    result = calc_budget(args.task_desc, args.estimated_steps, args.model)
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result, args.task_desc, args.estimated_steps))
    
    # 返回码：需要分段返回 1，否则返回 0（方便脚本调用判断）
    sys.exit(1 if result['needs_segmentation'] else 0)

if __name__ == "__main__":
    main()
