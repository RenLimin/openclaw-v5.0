#!/usr/bin/env python3
"""
CLI 入口：运行会话编排调度器，发起所有 pending 任务
用法：
  python3 run_scheduler.py [--dry-run] [--interval 10] [--model <model-name>] [--timeout 1800]
"""

import argparse
import sys
from pathlib import Path

# 添加当前组件路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.orchestrator.scheduler import TaskScheduler
from adapters.openclaw.spawner import OpenClawTaskSpawner

def main():
    parser = argparse.ArgumentParser(description="Run task scheduler for pending tasks")
    parser.add_argument("--dry-run", action="store_true", help="Only sort, don't spawn")
    parser.add_argument("--interval", type=float, default=10.0, help="Start interval in seconds (default 10.0)")
    parser.add_argument("--model", type=str, default=None, help="Default model for spawned tasks (optional)")
    parser.add_argument("--timeout", type=int, default=1800, help="Default run timeout in seconds (default 1800)")
    args = parser.parse_args()

    # 创建调度器
    scheduler = TaskScheduler(default_start_interval_sec=args.interval)

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        stats = scheduler.run(lambda t: True, dry_run=True)
    else:
        # 创建 OpenClaw spawner
        spawner = OpenClawTaskSpawner(
            default_model=args.model,
            default_run_timeout=args.timeout,
        )
        stats = scheduler.run(lambda t: spawner.spawn_task(t), interval_sec=args.interval)

    print("\n=== 最终统计 ===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    return 0 if stats["started"] == stats["total_pending"] else 1

if __name__ == "__main__":
    sys.exit(main())
