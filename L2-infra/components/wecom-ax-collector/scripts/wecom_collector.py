#!/usr/bin/env python3
"""企业微信 macOS AX 采集调度器（Phase 1）

职责：调度 Swift 引擎做定时快照 → 解析 → 指纹去重 → 输出 JSONL / webhook。
设计：见 docs/research/DESIGN-wecom-ax-collector-phase1.md

用法：
    python3 wecom_collector.py --config config.yaml            # 常驻轮询
    python3 wecom_collector.py --config config.yaml --once     # 单次采集（调试/测试）
    python3 wecom_collector.py --config config.yaml --list     # 列出可见会话

依赖：仅标准库（yaml 若缺失则回退 JSON 配置）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wecom_parser  # noqa: E402
import wecom_images  # noqa: E402

ENGINE_DEFAULT = Path(__file__).resolve().parent.parent / "engine" / "wecom_ax_engine"
BUNDLE_ID = "com.tencent.WeWorkMac"


# ---------------------------------------------------------------- 配置
@dataclass
class Config:
    interval_seconds: float = 3.0
    mode: str = "current"          # current | list
    sessions: list[str] = field(default_factory=list)
    max_retries: int = 5
    backoff_base: float = 1.0
    jsonl_path: Path = Path("data/wecom_messages.jsonl")
    state_path: Path = Path("data/.seen_ids.json")
    webhook_url: str | None = None
    engine_path: Path = ENGINE_DEFAULT
    bundle_id: str = BUNDLE_ID
    include_items: bool = False    # 调试用：输出原始 AX item 坐标
    images_enabled: bool = False   # 是否提取消息区图片本体（AXImageData → PNG）
    image_dir: Path = Path("data/images")
    image_catalog: Path = Path("data/.image_catalog.json")

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            data = _load_yaml(raw)
        else:
            data = json.loads(raw)
        base = path.parent
        for key in ("jsonl_path", "state_path", "engine_path", "image_dir", "image_catalog"):
            v = data.get(key)
            if not v:
                continue
            p = Path(v)
            # 相对路径优先相对配置文件所在目录（= 组件根）；若不存在则回退到脚本同级
            if not p.is_absolute():
                cand = (base / p).resolve()
                alt = (Path(__file__).resolve().parent.parent / p).resolve()
                p = cand if cand.exists() else alt
            data[key] = p
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def _load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    # 极简 YAML 子集：仅支持本组件配置用到的扁平键值
    out: dict[str, Any] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, _, v = s.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            out[k] = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
        elif v in ("true", "false"):
            out[k] = v == "true"
        elif v.isdigit():
            out[k] = int(v)
        elif _is_float(v):
            out[k] = float(v)
        elif v in ("null", "~", ""):
            out[k] = None
        else:
            out[k] = v.strip('"\'')
    return out


def _is_float(s: str) -> bool:
    try:
        float(s); return True
    except ValueError:
        return False


# ---------------------------------------------------------------- 引擎调用
class EngineError(RuntimeError):
    pass


def run_engine(cfg: Config, subcmd: str, session_kw: str = "", extra: list[str] | None = None) -> dict:
    """调用 Swift 引擎，返回解析后的 JSON。失败抛 EngineError。"""
    cmd = [str(cfg.engine_path), subcmd]
    if session_kw:
        cmd += ["--session", session_kw]
    if extra:
        cmd += extra
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise EngineError(f"engine {subcmd} rc={proc.returncode}: {proc.stderr.strip()[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise EngineError(f"engine {subcmd} 输出非 JSON: {e}; head={proc.stdout[:200]!r}") from e


def check_prerequisites(cfg: Config) -> list[str]:
    """自检：权限/进程/二进制。返回问题列表（空 = 通过）。"""
    problems = []
    if not cfg.engine_path.exists():
        problems.append(f"引擎不存在: {cfg.engine_path}（需 swiftc 编译）")
    if platform.system() != "Darwin":
        problems.append(f"非 macOS 环境: {platform.system()}")
    try:
        r = subprocess.run(["pgrep", "-f", cfg.bundle_id], capture_output=True, text=True)
        if not r.stdout.strip():
            problems.append("企业微信未运行")
    except Exception as e:
        problems.append(f"进程探测失败: {e}")
    # 辅助功能权限：尝试一次最小 AX 调用
    if not problems:
        try:
            snap = run_engine(cfg, "sessions")
            if snap.get("count", 0) == 0:
                problems.append("AX 可读但会话数为 0，疑似缺少『辅助功能』授权")
        except EngineError as e:
            problems.append(f"AX 读取失败（需辅助功能授权）: {e}")
    return problems


# ---------------------------------------------------------------- 去重与输出
def _content_hash(msg: dict) -> str:
    """纯内容指纹（不含坐标）：用于吸收 y 漂移的二次校验。"""
    content = str(msg.get("content", "")).strip()
    sender = str(msg.get("sender", "")).strip()
    return hashlib.sha1(f"{sender}|{content}".encode("utf-8")).hexdigest()[:16]


def message_id(msg: dict, y_bucket: int | None = None) -> str:
    """确定性指纹：归一化 y 桶 + 发送者 + 内容。

    刻意 **不含会话名**：实测 `_selected_session()` 存在回退到窗口标题
    「企业微信」的抖动，会话名进指纹会导致整批消息被误判为新消息。
    会话名仅作记录字段，不参与去重判定。
    """
    content = str(msg.get("content", "")).strip()
    sender = str(msg.get("sender", "")).strip()
    y = y_bucket if y_bucket is not None else _infer_y_bucket(msg)
    basis = "|".join([str(y), sender, content])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _infer_y_bucket(msg: dict) -> int:
    items = msg.get("items") or []
    ys = [it.get("y") for it in items if isinstance(it.get("y"), (int, float))]
    if not ys:
        return 0
    return int(round(sum(ys) / len(ys) / 10.0) * 10)


class SeenStore:
    """已见消息 ID 持久化存储，重启不丢。

    同时维护 content_hash 集合：当 y 坐标因渲染/滚动发生漂移时，
    用「发送者+内容」二次校验避免把同一条消息重复输出。
    """

    def __init__(self, path: Path):
        self.path = path
        self.ids: set[str] = set()
        self.content_hashes: set[str] = set()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.ids = set(data.get("ids", []))
                    self.content_hashes = set(data.get("content_hashes", []))
                elif isinstance(data, list):  # 兼容旧格式
                    self.ids = set(data)
            except (json.JSONDecodeError, OSError):
                self.ids, self.content_hashes = set(), set()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "ids": sorted(self.ids),
            "content_hashes": sorted(self.content_hashes),
        }), encoding="utf-8")
        tmp.replace(self.path)

    def is_new(self, mid: str, content_hash: str = "") -> bool:
        if mid in self.ids:
            return False
        if content_hash and content_hash in self.content_hashes:
            # 坐标漂移但内容一致 → 视为已见
            self.ids.add(mid)
            return False
        return True

    def mark(self, *mids: str, content_hashes: list[str] | None = None):
        self.ids.update(mids)
        if content_hashes:
            self.content_hashes.update(content_hashes)


class JsonlSink:
    def __init__(self, path: Path):
        self.path = path

    def emit(self, record: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_record(session: str, msg: dict, mid: str, cfg: Config,
                 images: list[dict] | None = None) -> dict:
    rec = {
        "msg_id": mid,
        "content_hash": _content_hash(msg),
        "session": session,
        "sender": msg.get("sender", ""),
        "content": msg.get("content", ""),
        "ts": msg.get("ts", ""),
        "is_self": bool(msg.get("is_self")),
        "is_system": bool(msg.get("is_system")),
        "mentions": msg.get("mentions") or [],
        "media": msg.get("media"),
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    if images:
        # 只带内容图元数据；UI 资产不入记录（噪声）
        rec["images"] = images
    if cfg.include_items:
        rec["items"] = msg.get("items") or []
    return rec


# ---------------------------------------------------------------- 采集流程
class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.seen = SeenStore(cfg.state_path)
        self.sink = JsonlSink(cfg.jsonl_path)
        self.catalog = wecom_images.ImageCatalog(cfg.image_catalog)

    def extract_images(self, session: str) -> tuple[list[dict], list[dict]]:
        """读取当前会话消息区图片，分类后返回 (全部分类结果, 内容图清单)。

        严格只读：引擎只 Get AXImageData，不点击、不写客户端。
        落盘流程（单向净化）：
          1) engine --out 先把消息区全部图片写入 _staging（sha 前缀、天然去重）；
          2) 本层按分类结果，仅把 content 提升为正式文件，其余从 staging 删除。
        这样磁盘上只保留疑似真实聊天图片，UI 资产不残留。
        """
        staging = self.cfg.image_dir / "_staging"
        data = run_engine(self.cfg, "images",
                          extra=["--only-message", "--out", str(staging)])
        imgs = data.get("images") or []
        result: list[dict] = []
        kept: list[dict] = []
        for im in imgs:
            sha = str(im.get("sha256") or "")
            hits = self.catalog.hits(sha) if sha else 0
            verdict = wecom_images.classify_image(im, session_hits=hits)
            entry = dict(im)
            entry.update(verdict)
            entry["session"] = session
            result.append(entry)
            if verdict.get("category") == "content" and sha:
                kept.append(entry)
                self.catalog.add(sha, session)
        self.catalog.save()
        self._promote_content(result)
        return result, kept

    def _promote_content(self, entries: list[dict]):
        """staging → 正式目录：仅 content 保留，其余删除。"""
        staging = self.cfg.image_dir / "_staging"
        self.cfg.image_dir.mkdir(parents=True, exist_ok=True)
        for e in entries:
            src = staging / str(e.get("file") or "")
            if e.get("category") == "content":
                dst = self.cfg.image_dir / src.name
                try:
                    if dst.exists() or not src.exists():
                        e["saved_as"] = dst.name
                        if src.exists():
                            src.unlink()
                    else:
                        src.replace(dst)
                        e["saved_as"] = dst.name
                except OSError as exc:
                    print(f"[warn] 图片归位失败: {exc}", file=sys.stderr)
            elif src.exists():
                try:
                    src.unlink()   # UI 资产：不留痕
                except OSError:
                    pass

    def _selected_session(self) -> str:
        """取左侧列表中 selected 的会话名；失败回退窗口标题。"""
        try:
            data = run_engine(self.cfg, "sessions")
            for s in data.get("sessions", []):
                if s.get("selected"):
                    return str(s.get("name", "")) or "unknown"
        except EngineError:
            pass
        try:
            snap = run_engine(self.cfg, "snapshot")
            return snap.get("window") or "unknown"
        except EngineError:
            return "unknown"

    def collect_current(self) -> tuple[list[dict], int, str]:
        """采集当前打开会话（会话名取自左侧 selected 项）。"""
        data = run_engine(self.cfg, "snapshot")
        msgs = wecom_parser.parse_messages(data.get("items") or [])
        session = self._selected_session()

        img_all: list[dict] = []
        assoc: dict[int, int] = {}
        self.image_stats = {"total": 0, "content": 0}
        if self.cfg.images_enabled:
            try:
                img_all, kept = self.extract_images(session)
                assoc = wecom_images.associate(img_all, msgs)
                self.image_stats = {"total": len(img_all), "content": len(kept)}
            except EngineError as e:
                print(f"[warn] 图片提取失败(不影响文本采集): {e}", file=sys.stderr)

        new_records = []
        hashes = []
        for mi, m in enumerate(msgs):
            ch = _content_hash(m)
            if not self.seen.is_new(message_id(m), ch):
                continue
            hashes.append(ch)
            # 关联该消息的内容图（仅 content；UI 资产不入记录）
            keep = []
            if self.cfg.images_enabled:
                keep = [img_all[i] for i, t in assoc.items()
                        if t == mi and img_all[i].get("category") == "content"]
            new_records.append(
                build_record(session, m, message_id(m), self.cfg,
                              images=keep or None))
        self.seen.mark(*[r["msg_id"] for r in new_records], content_hashes=hashes)
        return new_records, len(msgs), session

    def flush(self, records: list[dict]):
        for rec in records:
            self.sink.emit(rec)
            if self.cfg.webhook_url:
                self._webhook(rec)

    def _webhook(self, rec: dict):
        import urllib.request
        try:
            req = urllib.request.Request(
                self.cfg.webhook_url,
                data=json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:  # 网络失败不影响本地落盘
            print(f"[warn] webhook 失败: {e}", file=sys.stderr)

    def once(self) -> dict:
        """单次采集，返回统计。"""
        stats = {"at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                 "new": 0, "total": 0, "sessions": [], "read_only": True}
        # 只读红线：引擎不再切换会话。list 模式 = 仅当【当前人工打开的会话】
        # 命中白名单时采集该会话；current 模式 = 无脑采当前会话。两种模式都只读。
        current_name = self._selected_session()
        if self.cfg.mode == "list" and self.cfg.sessions:
            hit = any(k and (k in current_name or current_name in k)
                      for k in self.cfg.sessions)
            if not hit:
                stats["skipped"] = f"当前会话 {current_name!r} 不在白名单，只读模式不自动切换"
                return stats
        try:
            recs, total, name = self.collect_current()
            self.flush(recs)
            self.seen.save()
            stats["new"] += len(recs)
            stats["total"] += total
            stats["sessions"].append({"name": name, "new": len(recs), "total": total})
            if self.cfg.images_enabled:
                stats["images"] = getattr(self, "image_stats", {"total": 0, "content": 0})
        except EngineError as e:
            print(f"[error] 采集失败(current={current_name}): {e}", file=sys.stderr)
            stats.setdefault("errors", []).append(str(e))
        return stats

    def run(self):
        print(f"[collector] 启动 mode={self.cfg.mode} interval={self.cfg.interval_seconds}s "
              f"jsonl={self.cfg.jsonl_path}", flush=True)
        attempt = 0
        while True:
            try:
                stats = self.once()
                if stats["new"]:
                    print(f"[collector] +{stats['new']} 新消息 "
                          f"(本轮扫描 {stats['total']})", flush=True)
                else:
                    print(f"[collector] 无新消息 (扫描 {stats['total']})", flush=True)
                attempt = 0
            except KeyboardInterrupt:
                raise
            except Exception as e:
                attempt += 1
                delay = min(self.cfg.backoff_base * (2 ** (attempt - 1)), 60)
                print(f"[error] 第 {attempt} 次失败，{delay:.0f}s 后重试: {e}", file=sys.stderr)
                if attempt >= self.cfg.max_retries:
                    print("[fatal] 达到最大重试次数，退出", file=sys.stderr)
                    raise
                time.sleep(delay)
                continue
            time.sleep(self.cfg.interval_seconds)


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="企业微信 macOS AX 采集调度器")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--once", action="store_true", help="单次采集")
    ap.add_argument("--list", action="store_true", help="列出可见会话")
    ap.add_argument("--check", action="store_true", help="前置条件自检")
    args = ap.parse_args()

    cfg = Config.load(args.config)

    if args.check:
        problems = check_prerequisites(cfg)
        if problems:
            print("自检未通过：")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("自检通过：引擎就绪、企微运行中、AX 可读")
        return 0

    if args.list:
        data = run_engine(cfg, "sessions")
        print(f"共 {data.get('count')} 个会话：")
        for i, s in enumerate(data.get("sessions", []), 1):
            tag = f"[{s.get('tag')}]" if s.get("tag") else ""
            unread = f" ({s.get('unread')})" if s.get("unread") else ""
            print(f"{i:>3}. {s.get('name')} {tag}{unread}")
        return 0

    col = Collector(cfg)
    if args.once:
        stats = col.once()
        col.seen.save()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0 if not stats.get("errors") else 2

    try:
        col.run()
    except KeyboardInterrupt:
        print("\n[collector] 已停止", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
