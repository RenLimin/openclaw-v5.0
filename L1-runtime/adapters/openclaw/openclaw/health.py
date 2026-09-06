"""
OpenClaw 运行时健康检查
实现 L1 契约的健康检查能力
"""

from typing import Any, Dict, List, Tuple
from .adapter import OpenClawAdapter, HealthStatus


def check_all_components(adapter: OpenClawAdapter) -> Tuple[str, List[Dict[str, Any]]]:
    """检查所有核心组件的健康状态"""
    all_results: List[Dict[str, Any]] = []
    overall_status = "ok"

    # 1. 配置验证
    valid, errors = adapter.config_validate()
    all_results.append({
        "component": "config",
        "status": "ok" if valid else "degraded",
        "errors": errors,
    })
    if not valid:
        overall_status = "degraded"

    # 2. 凭据扫描
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "scripts/credentials.sh", "scan"],
            capture_output=True, text=True, check=True
        )
        all_results.append({
            "component": "credentials",
            "status": "ok",
            "output": result.stdout,
        })
    except subprocess.CalledProcessError as e:
        all_results.append({
            "component": "credentials",
            "status": "degraded",
            "issues": e.stdout.splitlines() if e.stdout else [],
        })
        overall_status = "degraded"
    except Exception as e:
        all_results.append({
            "component": "credentials",
            "status": "down",
            "error": str(e),
        })
        overall_status = "degraded"

    # 3. 记忆检索
    try:
        result = subprocess.run(
            ["python3", "scripts/observability/memory_search_monitor.py", "--check"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            status = "ok"
        elif result.returncode == 1:
            status = "degraded"
        else:
            status = "down"
        all_results.append({
            "component": "memory_search",
            "status": status,
            "output": result.stdout,
        })
        if status != "ok":
            overall_status = status
    except Exception as e:
        all_results.append({
            "component": "memory_search",
            "status": "down",
            "error": str(e),
        })
        overall_status = "down"

    # 4. 模型调度代理
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 3000))
    if result == 0:
        all_results.append({
            "component": "model_scheduling_proxy",
            "status": "ok",
            "message": "监听正常",
        })
        sock.close()
    else:
        all_results.append({
            "component": "model_scheduling_proxy",
            "status": "down",
            "message": "未监听",
        })
        overall_status = "degraded"
        sock.close()

    return overall_status, all_results


def full_health_check(adapter: OpenClawAdapter) -> HealthStatus:
    """执行全量健康检查"""
    base_health = adapter.health()
    if base_health.status == "down":
        return base_health

    overall_status, components = check_all_components(adapter)
    return HealthStatus(
        status=overall_status,
        message=f"全量健康检查完成，整体状态 {overall_status}",
        details={
            "components": components,
            "openclaw_version": adapter.version,
        },
    )
