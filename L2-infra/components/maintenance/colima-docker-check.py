#!/usr/bin/env python3
"""
Colima/Docker 依赖健康巡检和自动修复

功能：
1. 检测 Docker daemon 可用性
2. 如果不可用，检测 Colima 是否运行
3. 如果 Colima 未运行，尝试启动 Colima（通过 launchctl，如果失败手动 colima start）
4. 报告状态，记录错误
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

def is_docker_available() -> bool:
    """检测 Docker 是否可用"""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False
    )
    return result.returncode == 0

def is_colima_running() -> bool:
    """检测 Colima 是否正在运行"""
    result = subprocess.run(
        ["colima", "status"],
        capture_output=True,
        text=True,
        check=False
    )
    return "colima is running" in result.stdout

def check_launchd_available() -> bool:
    """是否是 macOS 且有 launchd"""
    if sys.platform != "darwin":
        return False
    return shutil.which("launchctl") is not None

def check_launchd_colima() -> bool:
    """检查 launchd 里的 colima 配置是否正常"""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.colima.auto.plist"
    if not plist_path.exists():
        print("⚠️  launchd 中没有 colima 自启动配置")
        return False
    
    # 简单检查 plist 里是否有正确路径和 PATH
    with open(plist_path, "r") as f:
        content = f.read()
    
    if "/opt/homebrew/bin/colima" not in content:
        print("⚠️  colima 路径配置不对（当前应该在 /opt/homebrew/bin/colima）")
        return False
    
    if "EnvironmentVariables" not in content or "/opt/homebrew/bin" not in content:
        print("⚠️  没有配置正确 PATH，colima 启动会找不到 limactl")
        return False
    
    return True

def restart_colima_via_launchd() -> bool:
    """通过 launchd 重启 colima"""
    print("🔄 尝试通过 launchd 重启 colima...")
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.colima.auto.plist"
    unload_result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
        text=True,
        check=False
    )
    if unload_result.returncode != 0:
        print(f"❌ 卸载旧配置失败: {unload_result.stderr}")
    
    load_result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
        check=False
    )
    if load_result.returncode != 0:
        print(f"❌ 加载新配置失败: {load_result.stderr}")
        return False
    
    # 给启动留时间
    print("⌛ 等待 Colima 启动（15秒）...")
    for _ in range(3):
        if is_docker_available():
            return True
        sys.sleep(5)
    
    return is_docker_available()

def main():
    print("=== 开始 Colima/Docker 健康检查 ===\n")
    
    # 1. 先直接检查 Docker
    if is_docker_available():
        print("✅ Docker 已经可用，无需修复")
        print("\n=== 检查完成，一切正常 ===")
        sys.exit(0)
    
    print("❌ Docker daemon 不可用，开始排查...\n")
    
    # 2. 检查 Colima 是否运行
    if is_colima_running():
        print("⚠️  Colima 正在运行，但 Docker 还是不可用")
        # 尝试重新加载 launchd
    else:
        print("❌ Colima 未运行")
    
    # 3. 检查 launchd 配置
    if not check_launchd_available():
        print("❌ 当前系统不是 macOS 或者没有 launchd，无法自动修复")
        print("请手动执行: colima start")
        sys.exit(1)
    
    if not check_launchd_colima():
        print("❌ 自启动配置不正确，请手动修复或者重新配置自启")
        sys.exit(1)
    
    # 4. 尝试启动
    if restart_colima_via_launchd():
        print("✅ 成功启动 Colima，Docker 现在可用了")
        print("\n=== 检查完成，修复成功 ===")
        sys.exit(0)
    else:
        # 最后尝试手动 colima start
        print("\n⚠️  launchd 启动失败，尝试直接 colima start...")
        result = subprocess.run(
            ["colima", "start"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0 and is_docker_available():
            print("✅ 手动 colima start 成功，Docker 现在可用")
            print("\n=== 检查完成，修复成功 ===")
            sys.exit(0)
        else:
            print(f"❌ 修复失败: {result.stderr}")
            print("\n=== 检查完成，修复失败，请手动处理 ===")
            sys.exit(1)

if __name__ == "__main__":
    main()
