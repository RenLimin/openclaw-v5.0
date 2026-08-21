#!/usr/bin/env python3
"""生成系统资产清单 (docs/architecture/01-asset-inventory.md)。

数据源全部为实时命令输出，无手写内容：
  - openclaw --version           → L1 基座版本
  - openclaw plugins list --json  → 插件资产
  - openclaw skills list --json   → 技能资产
  - openclaw agents list --json   → agent 资产
  - openclaw cron list --json     → 调度资产
  - openclaw config get <path>    → 工具策略 / 凭据 provider
  - git / 文件系统                → 文档资产、仓库状态

用法:
    python3 scripts/gen_asset_inventory.py            # 写入文件
    python3 scripts/gen_asset_inventory.py --check    # 只检查是否有漂移 (退出码 1 = 有差异)
    python3 scripts/gen_asset_inventory.py --stdout   # 打印到标准输出

设计约束 (对应 ADR-202608-001):
  - 只读：脚本不修改任何系统状态
  - 幂等：同样的系统状态生成同样的输出 (时间戳除外)
  - 失败可见：某个数据源不可用时在清单中标记，不静默跳过
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "architecture" / "01-asset-inventory.md"
SECRETS_DIR = Path.home() / ".openclaw" / "secrets"
CST = timezone(timedelta(hours=8))

UNAVAILABLE = "⚠️ 数据源不可用"


# --------------------------------------------------------------------------
# 数据采集
# --------------------------------------------------------------------------


def run(cmd: list[str], *, timeout: int = 30) -> str | None:
    """执行命令，失败返回 None（不抛异常，让清单标记不可用）。"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def run_json(cmd: list[str], *, timeout: int = 30):
    """执行命令并解析 JSON，失败返回 None。"""
    out = run(cmd, timeout=timeout)
    if out is None:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def collect() -> dict:
    """采集所有数据源。每个 key 的值为 None 表示该数据源不可用。"""
    version_out = run(["openclaw", "--version"])
    return {
        "version": version_out.strip().splitlines()[0] if version_out else None,
        "plugins": run_json(["openclaw", "plugins", "list", "--json"], timeout=60),
        "skills": run_json(["openclaw", "skills", "list", "--json"], timeout=60),
        "agents": run_json(["openclaw", "agents", "list", "--json"]),
        "cron": run_json(["openclaw", "cron", "list", "--json"]),
        "tools": run_json(["openclaw", "config", "get", "tools"]),
        "secret_providers": run_json(["openclaw", "config", "get", "secrets.providers"]),
        "node": (run(["node", "--version"]) or "").strip() or None,
        "git_remote": (run(["git", "remote", "get-url", "origin"]) or "").strip() or None,
        "git_commit": (run(["git", "rev-parse", "--short", "HEAD"]) or "").strip() or None,
        "git_count": (run(["git", "rev-list", "--count", "HEAD"]) or "").strip() or None,
    }


# --------------------------------------------------------------------------
# 各区渲染
# --------------------------------------------------------------------------


def render_l1(data: dict) -> list[str]:
    lines = ["## L1 — 系统层资产 (OpenClaw 基座)", ""]
    lines.append("| 资产 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| OpenClaw | {data['version'] or UNAVAILABLE} |")
    lines.append(f"| Node.js | {data['node'] or UNAVAILABLE} |")
    lines.append("")
    lines.append("> L1 不可修改，升级跟随官方版本。breaking changes 需走 ADR。")
    lines.append("")
    return lines


def render_plugins(data: dict) -> list[str]:
    lines = ["## L2 — 插件资产 (Plugins)", ""]
    payload = data["plugins"]
    if not payload:
        lines += [UNAVAILABLE, ""]
        return lines

    plugins = payload.get("plugins", [])
    enabled = [p for p in plugins if p.get("enabled")]
    by_origin = Counter(p.get("origin", "?") for p in plugins)

    lines.append(
        f"**总计** {len(plugins)} 个（启用 {len(enabled)}） · "
        + " · ".join(f"{k} {v}" for k, v in sorted(by_origin.items()))
    )
    lines.append("")
    lines.append("> 内置（bundled）插件随 OpenClaw 版本提供，多为按需激活的模型 provider。下表只列**主动安装**或**实际提供工具**的插件。")
    lines.append("")

    def capabilities(p: dict) -> list[str]:
        caps = []
        for key, label in (
            ("webSearchProviderIds", "web-search"),
            ("webFetchProviderIds", "web-fetch"),
            ("channelIds", "channel"),
            ("providerIds", "model-provider"),
            ("memoryEmbeddingProviderIds", "memory-embedding"),
        ):
            if p.get(key):
                caps.append(f"{label}: {', '.join(p[key])}")
        return caps

    notable = [
        p for p in enabled if p.get("origin") != "bundled" or p.get("toolNames")
    ]

    lines.append("| ID | 来源 | 提供的工具 | 提供的能力 |")
    lines.append("|---|---|---|---|")
    for p in sorted(notable, key=lambda x: x.get("id", "")):
        tools = ", ".join(f"`{t}`" for t in p.get("toolNames") or []) or "—"
        lines.append(
            f"| `{p.get('id')}` | {p.get('origin', '?')} | {tools} | "
            f"{'; '.join(capabilities(p)) or '—'} |"
        )
    lines.append("")

    bundled_providers = sorted(
        p.get("id", "")
        for p in enabled
        if p.get("origin") == "bundled" and p.get("providerIds")
    )
    if bundled_providers:
        lines.append(
            f"**内置模型 provider**（{len(bundled_providers)} 个，按需激活）："
            + ", ".join(f"`{i}`" for i in bundled_providers)
        )
        lines.append("")
    return lines


def render_skills(data: dict) -> list[str]:
    lines = ["## L2 — 技能资产 (Skills)", ""]
    payload = data["skills"]
    if not payload:
        lines += [UNAVAILABLE, ""]
        return lines

    skills = payload.get("skills", [])
    by_source = Counter(s.get("source", "?") for s in skills)
    eligible = [s for s in skills if s.get("eligible")]

    lines.append(f"**总计** {len(skills)} 个（可用 {len(eligible)}）")
    lines.append("")
    lines.append("| 来源 | 数量 | 说明 |")
    lines.append("|---|---|---|")
    source_desc = {
        "openclaw-bundled": "OpenClaw 内置（随版本升级）",
        "openclaw-managed": "已安装的托管技能",
        "openclaw-extra": "插件附带技能",
        "openclaw-workspace": "**本 workspace 自建**（受版本控制）",
    }
    for source, count in sorted(by_source.items()):
        lines.append(f"| `{source}` | {count} | {source_desc.get(source, '—')} |")
    lines.append("")

    workspace_skills = sorted(
        (s for s in skills if s.get("source") == "openclaw-workspace"),
        key=lambda x: x.get("name", ""),
    )
    if workspace_skills:
        lines.append("### 自建技能（workspace）")
        lines.append("")
        lines.append("| 名称 | 描述 |")
        lines.append("|---|---|")
        for s in workspace_skills:
            desc = (s.get("description") or "").replace("|", "\\|")
            if len(desc) > 90:
                desc = desc[:87] + "..."
            lines.append(f"| `{s.get('name')}` | {desc} |")
        lines.append("")
    return lines


def render_agents(data: dict) -> list[str]:
    lines = ["## L2 — Agent 资产", ""]
    agents = data["agents"]
    if not agents:
        lines += [UNAVAILABLE, ""]
        return lines

    lines.append("| ID | 身份 | 模型 | Workspace | 默认 |")
    lines.append("|---|---|---|---|---|")
    for a in agents:
        identity = f"{a.get('identityEmoji', '')} {a.get('identityName') or a.get('name')}".strip()
        lines.append(
            f"| `{a.get('id')}` | {identity} | `{a.get('model', '?')}` | "
            f"`{a.get('workspace', '?')}` | {'✅' if a.get('isDefault') else '—'} |"
        )
    lines.append("")
    return lines


def render_tools(data: dict) -> list[str]:
    lines = ["## L2 — 工具策略资产", ""]
    tools = data["tools"]
    if not tools:
        lines += [UNAVAILABLE, ""]
        return lines

    lines.append("| 配置项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| `tools.profile` | `{tools.get('profile', '(未设置)')}` |")
    for key in ("alsoAllow", "allow", "deny"):
        if tools.get(key):
            lines.append(
                f"| `tools.{key}` | " + ", ".join(f"`{t}`" for t in tools[key]) + " |"
            )
    lines.append("")
    if tools.get("alsoAllow"):
        lines.append(
            "> `alsoAllow` 是 profile 之上的显式例外，理由见 "
            "[EXP-20260821-001](../knowledge-base/by-category/project-experience/correct/"
            "EXP-20260821-001-tavily-tools-also-allow.md)。"
        )
        lines.append("")
    return lines


def render_credentials(data: dict) -> list[str]:
    """凭据资产：只列 provider 名与文件名，绝不读取内容。"""
    lines = ["## L2 — 凭据资产 (仅元信息，不含凭据值)", ""]

    providers = data["secret_providers"]
    lines.append("### SecretRef Providers")
    lines.append("")
    if providers:
        lines.append("| 别名 | 说明 |")
        lines.append("|---|---|")
        for alias in sorted(providers):
            lines.append(f"| `{alias}` | 配置值由 OpenClaw redact，详见 `openclaw config get secrets.providers` |")
    else:
        lines.append("_(未配置 SecretRef provider)_")
    lines.append("")

    lines.append("### 凭据文件")
    lines.append("")
    if SECRETS_DIR.is_dir():
        entries = sorted(
            p for p in SECRETS_DIR.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )
        if entries:
            lines.append("| 文件 | 权限 | 大小 |")
            lines.append("|---|---|---|")
            for p in entries:
                mode = oct(p.stat().st_mode & 0o777)[2:]
                flag = "" if mode == "600" else " ⚠️"
                lines.append(f"| `~/.openclaw/secrets/{p.name}` | `{mode}`{flag} | {p.stat().st_size} B |")
            lines.append("")
            lines.append("> ⚠️ 标记表示权限不是 600，应执行 `chmod 600` 收紧。")
        else:
            lines.append("_(目录为空)_")
    else:
        lines.append(f"_(目录不存在: {SECRETS_DIR})_")
    lines.append("")
    return lines


def render_cron(data: dict) -> list[str]:
    lines = ["## L2 — 调度资产 (Cron)", ""]
    payload = data["cron"]
    if not payload:
        lines += [UNAVAILABLE, ""]
        return lines

    jobs = payload.get("jobs", [])
    if not jobs:
        lines += ["_(无调度任务)_", ""]
        return lines

    lines.append("| 名称 | 启用 | 调度 | 目标 |")
    lines.append("|---|---|---|---|")
    for j in jobs:
        schedule = j.get("schedule") or {}
        kind = schedule.get("kind", "?")
        if kind == "cron":
            desc = f"cron `{schedule.get('expr', '?')}`"
        elif kind == "every":
            desc = f"每 {int(schedule.get('everyMs', 0)) // 1000}s"
        elif kind == "at":
            desc = f"一次性 {schedule.get('at', '?')}"
        else:
            desc = kind
        lines.append(
            f"| {j.get('displayName') or j.get('name', '?')} | "
            f"{'✅' if j.get('enabled') else '—'} | {desc} | "
            f"`{j.get('sessionTarget', '?')}` |"
        )
    lines.append("")
    return lines


def render_docs() -> list[str]:
    """文档资产：扫描文件系统。"""
    lines = ["## 文档资产", ""]
    kb = REPO_ROOT / "docs" / "knowledge-base"

    adrs = sorted(kb.rglob("ADR-*.md")) if kb.is_dir() else []
    exps = sorted(kb.rglob("EXP-*.md")) if kb.is_dir() else []
    templates = sorted((kb / "templates").glob("*.md")) if (kb / "templates").is_dir() else []

    lines.append("| 类别 | 数量 |")
    lines.append("|---|---|")
    lines.append(f"| ADR（架构决策记录） | {len(adrs)} |")
    lines.append(f"| EXP（经验卡片） | {len(exps)} |")
    lines.append(f"| 模板 | {len(templates)} |")
    lines.append("")

    def render_group(title: str, paths: list[Path]) -> None:
        if not paths:
            return
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| 文件 | 状态 |")
        lines.append("|---|---|")
        for p in paths:
            status = "—"
            try:
                for raw in p.read_text(encoding="utf-8").splitlines()[:20]:
                    if raw.startswith("status:"):
                        status = raw.split(":", 1)[1].strip()
                        break
            except OSError:
                status = UNAVAILABLE
            # 本文件在 docs/architecture/，到 docs/ 其他子目录用 ../
            rel = p.relative_to(REPO_ROOT / "docs")
            lines.append(f"| [`{p.stem}`](../{rel.as_posix()}) | {status} |")
        lines.append("")

    render_group("ADR 清单", adrs)
    render_group("经验卡片清单", exps)
    return lines


def render_repo(data: dict) -> list[str]:
    lines = ["## 仓库资产", ""]
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| Remote | {data['git_remote'] or UNAVAILABLE} |")
    lines.append(f"| HEAD | `{data['git_commit'] or '?'}` |")
    lines.append(f"| Commit 数 | {data['git_count'] or '?'} |")
    lines.append("")
    lines.append("**不入版本控制**（见 `.gitignore`）：`MEMORY.md` · `memory/` · `skills/` · `business/*/logs/`")
    lines.append("")
    return lines


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def build_document(data: dict) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "# 系统资产清单",
        "",
        "> **本文件由脚本自动生成，请勿手工编辑。**",
        "> 生成器：`scripts/gen_asset_inventory.py` · 触发：git pre-commit hook",
        "> 手动重生成：`python3 scripts/gen_asset_inventory.py`",
        "",
        f"最后生成：{now}",
        "",
        "本清单是 [系统架构文档](./00-system-architecture.md) 的附件，按 4 层架构组织"
        "（层级定义见 [ADR-202608-001](../knowledge-base/by-category/project-experience/adr/"
        "ADR-202608-001-four-layer-architecture.md)）。",
        "",
        "**安全边界**：本清单只记录资产的**存在与元信息**，绝不包含凭据值、token、密钥内容。",
        "",
        "---",
        "",
    ]

    for section in (
        render_l1(data),
        render_plugins(data),
        render_skills(data),
        render_agents(data),
        render_tools(data),
        render_credentials(data),
        render_cron(data),
        render_docs(),
        render_repo(data),
    ):
        lines += section

    lines += [
        "---",
        "",
        "## L3 / L4 资产",
        "",
        "_(未启动 — 详见 [架构文档 §6 演进路线](./00-system-architecture.md#6-演进路线))_",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成系统资产清单")
    parser.add_argument("--check", action="store_true", help="只检查漂移，有差异返回 1")
    parser.add_argument("--stdout", action="store_true", help="打印到标准输出，不写文件")
    args = parser.parse_args()

    content = build_document(collect())

    if args.stdout:
        sys.stdout.write(content)
        return 0

    def strip_timestamp(text: str) -> str:
        """比较时忽略时间戳行，避免每次都判定为漂移。"""
        return "\n".join(
            line for line in text.splitlines() if not line.startswith("最后生成：")
        )

    old = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    changed = strip_timestamp(old) != strip_timestamp(content)

    if args.check:
        if changed:
            print(f"资产清单已过期: {OUTPUT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
            print("运行 python3 scripts/gen_asset_inventory.py 更新", file=sys.stderr)
            return 1
        print("资产清单是最新的")
        return 0

    if not changed:
        print("资产清单无变化，跳过写入")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"已更新 {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
