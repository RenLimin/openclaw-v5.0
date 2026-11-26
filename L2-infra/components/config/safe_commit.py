#!/usr/bin/env python3
"""统一安全提交器（跨会话隔离 index，plumbing 直提）。

为什么需要它
------------
本仓 `.git/index` 是**跨会话共享**的：并行会话 `git add` 的内容会留在 index 里，
任何人的裸 `git commit` 都会把外来改动一起提走；且 pre-commit hook 内部会
`git add` 自动重生的文件，进一步污染（事故见 AGENTS.md §git index 共享红线）。

本工具用**隔离临时 index + plumbing**（read-tree/add/write-tree/commit-tree/update-ref）：
  - 只提交**显式列出**的路径，绝不带入他人 staged 内容；
  - **不触碰共享 `.git/index`**（其 mtime 保持不变）；
  - 绕过 hook 时自动补跑门禁预检（凭据扫描 + registry 校验），门禁不丢。

用法
----
    # 试运行（只看会提什么，不写 ref）
    python3 L2-infra/components/config/safe_commit.py \
        --paths L3-business/skills/x/SKILL.md --dry-run

    # 正式提交（逐条显式列路径；消息用文件避免 shell 转义）
    python3 L2-infra/components/config/safe_commit.py \
        --paths a.md b.py --message-file /tmp/msg.txt

    # 只预检不提交
    python3 L2-infra/components/config/safe_commit.py --paths a.md --preflight-only

规则（与 docs/conventions/commit-and-config.md §3 同步）
------------------------------------------------------
1. 禁止裸 `git commit`、禁止 `git add` 后不带路径提交；
2. 路径必须**逐条显式**给出（zsh 不对无引号变量分词，`-- $FILES` 会静默失败）；
3. 提交前必查 `git show --stat` 非空且清单与预期一致；
4. 分支非 main 或存在并行会话在途时，先 `--dry-run` 复核；
5. push 需单独决定，本工具不 push。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]          # .../workspace
SECRET_SCAN = REPO_ROOT / "L2-infra/components/config/secret-scan/secret_scan.py"
REGISTRY = REPO_ROOT / "L2-infra/components/config/capability-registry/capability_registry.py"


def sh(args, cwd=REPO_ROOT, env=None, check=False) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(args, cwd=str(cwd), env=e, check=check,
                          capture_output=True, text=True)


def run_preflight(paths: list[str]) -> bool:
    """门禁预检：凭据扫描 + registry 自校验。返回是否通过。"""
    ok = True
    if SECRET_SCAN.exists():
        r = sh([sys.executable, str(SECRET_SCAN)])
        if r.returncode != 0:
            print("❌ 明文凭据扫描未通过，禁止提交")
            print(r.stdout[-2000:], r.stderr[-2000:])
            ok = False
        else:
            print("✅ 明文凭据扫描通过")
    else:
        print(f"⚠️  未找到 {SECRET_SCAN}，跳过凭据扫描")
    if REGISTRY.exists():
        r = sh([sys.executable, str(REGISTRY), "--validate"])
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        if r.returncode != 0:
            print("❌ registry 自校验未通过：", tail)
            ok = False
        else:
            print("✅ registry 自校验通过：", tail)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="统一安全提交器（隔离 index）")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("--paths", nargs="+", required=True,
                    help="逐条显式列出要提交的路径（相对 repo 根）")
    ap.add_argument("--message", default=None, help="提交信息（单行或含\\n）")
    ap.add_argument("--message-file", default=None, help="从文件读提交信息")
    ap.add_argument("--dry-run", action="store_true", help="只演示，不写 ref")
    ap.add_argument("--preflight-only", action="store_true",
                    help="只跑门禁预检，不提交")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="跳过门禁预检（仅在明确知道后果时使用）")
    ap.add_argument("--author", default=None,
                    help="覆盖 author（默认沿用 git config）")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"❌ 不是 git 仓库：{repo}")
        return 2

    paths = [str(Path(p).relative_to(repo)) if Path(p).is_absolute() else p
             for p in args.paths]

    # 0) 路径有效性：工作树存在，或在 HEAD 中已跟踪（= 本次提交的删除）
    #     事故 2026-11-26：原实现要求磁盘必须存在，导致合法的「删除文件」无法提交；
    #     而 git add 对已删路径实测 rc=0、正确产出 staged D。故改为二者其一即可。
    head_paths = set(sh(["git", "ls-tree", "-r", "--name-only", "HEAD"],
                         cwd=repo).stdout.split())
    missing = [p for p in paths
               if not (repo / p).exists() and p not in head_paths]
    if missing:
        print("❌ 路径不存在（且不在 HEAD 中，非删除操作）：")
        for p in missing:
            print("   ", p)
        return 2

    # 1) 门禁预检
    if not args.skip_preflight and not args.dry_run:
        if not run_preflight(paths):
            return 1
    elif args.preflight_only:
        return 0 if run_preflight(paths) else 1

    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
    base = sh(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    tmpidx = tempfile.mktemp(prefix="safeidx.", dir="/tmp")
    env = {"GIT_INDEX_FILE": tmpidx}
    try:
        sh(["git", "read-tree", base], cwd=repo, env=env)

        for p in paths:
            r = sh(["git", "add", "--", p], cwd=repo, env=env)
            if r.returncode != 0:
                print(f"❌ git add 失败：{p}\n{r.stderr}")
                return 1

        staged = sh(["git", "diff", "--cached", "--name-only"],
                    cwd=repo, env=env).stdout.split()
        # diff --cached 对全新 index 需与 base 比：上面已 read-tree base，故有效
        staged = sorted(set(staged))

        print(f"\n=== 分支 {branch}  基线 {base[:8]} ===")
        print(f"=== 将提交 {len(staged)} 项 ===")
        for p in staged:
            print("   ", p)

        extra = [p for p in staged if p not in set(paths)]
        if extra:
            print("❌ staged 里出现未列出的路径（可能是指数污染），中止：")
            for p in extra:
                print("   ", p)
            return 1

        tree = sh(["git", "write-tree"], cwd=repo, env=env).stdout.strip()
        if not tree:
            print("❌ write-tree 产出空树")
            return 1

        if args.dry_run:
            print("\n[dry-run] 到此为止，未写 ref。")
            return 0

        msg = args.message_file and Path(args.message_file).read_text(encoding="utf-8") \
            or args.message or ""
        if not msg.strip():
            print("❌ 缺少 --message / --message-file")
            return 2

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(msg)
            msg_path = f.name
        cmd = ["git", "commit-tree", tree, "-p", base, "-F", msg_path]
        if args.author:
            cmd += ["--author", args.author]
        r = sh(cmd, cwd=repo)
        os.unlink(msg_path)
        if r.returncode != 0:
            print("❌ commit-tree 失败：\n", r.stderr)
            return 1
        commit = r.stdout.strip()

        head_ref = f"refs/heads/{branch}"
        u = sh(["git", "update-ref", head_ref, commit, base], cwd=repo)
        if u.returncode != 0:
            print("❌ update-ref 失败：\n", u.stderr)
            return 1

        # 提交后硬核对账
        stat = sh(["git", "show", "--stat", "--oneline", commit], cwd=repo).stdout
        print("\n=== 新提交 ===")
        print(stat.strip())
        actual = sorted(sh(["git", "show", "--name-only", "--pretty=format:", commit],
                           cwd=repo).stdout.split())
        if not actual:
            print("❌ 空提交！立即核查（不得推送）")
            return 1
        if actual != staged:
            print("❌ 实际清单与预期不一致")
            return 1
        print("✅ 对账一致（非空、清单匹配）")
        print(f"新提交：{commit}")
        return 0
    finally:
        try:
            os.unlink(tmpidx)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
