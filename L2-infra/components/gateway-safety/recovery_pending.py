#!/usr/bin/env python3
"""挂起式重启补偿状态（P1-a，stdlib 零依赖）。

场景：safe_restart.sh 因 pre-restart guard 硬阻断（rc=1，compaction in-flight）
而未重启。旧实现记完即弃——若故障在压缩结束后仍在，就永远得不到恢复。

本模块把这次"被安全推迟的重启"挂起为一条 pending 记录，由后续每轮扫描在
guard 放行、且故障仍在、且未超补偿次数/TTL 时安全补一次。同一故障证据只挂
一条（evidence_hash 去抖），最多补 1 次，绝不连续重启。

状态文件位于 OPENCLAW_STATE_DIR（运行态，不入库不入 git）。
"""
import hashlib
import json
import os
from datetime import datetime, timedelta

STATE_DIR = os.path.expanduser("~/.openclaw/state")
PENDING_FILE = os.path.join(STATE_DIR, "pending-recovery.json")

DEFAULT_TTL_MIN = 30
MAX_COMPENSATIONS = 1  # 同一证据最多补 1 次重启


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def evidence_hash(reason, evidence_text):
    """对触发证据做稳定 hash，供去抖（同证据只挂一条）。"""
    raw = f"{reason}|{evidence_text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def load(path=None):
    path = path or PENDING_FILE
    """读取 pending；无/损坏返回 None。"""
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("evidence_hash") else None
    except Exception:
        return None


def save(data, path=None):
    path = path or PENDING_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def clear(path=None):
    path = path or PENDING_FILE
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def upsert(reason, evidence_text, *, path=None, ttl_min=DEFAULT_TTL_MIN):
    path = path or PENDING_FILE
    """挂起一条被推迟的重启；同 evidence_hash 已存在则不重复挂（返回 False）。

    返回 (record, created)。
    """
    eh = evidence_hash(reason, evidence_text)
    existing = load(path)
    if existing and existing.get("evidence_hash") == eh:
        return existing, False

    record = {
        "reason": reason,
        "evidence_hash": eh,
        "evidence": evidence_text[:240],
        "created_at": _now_iso(),
        "expires_at": (datetime.now() + timedelta(minutes=ttl_min)).isoformat(timespec="seconds"),
        "attempts": 0,
        "compensations": 0,
        "last_guard_rc": 1,
    }
    save(record, path)
    return record, True


def touch_guard_rc(rc, *, path=None):
    path = path or PENDING_FILE
    rec = load(path)
    if rec:
        rec["last_guard_rc"] = rc
        save(rec, path)
    return rec


def is_expired(record, *, now=None):
    if not record or not record.get("expires_at"):
        return False
    try:
        exp = datetime.fromisoformat(record["expires_at"])
    except Exception:
        return False
    cur = now or datetime.now()
    return cur > exp


def can_compensate(record, guard_rc, *, now=None):
    """是否满足"现在安全补一次重启"的全部条件：

      guard 放行(rc=0)、未超补偿次数、未超 TTL。
    guard rc=1（仍阻断）/ rc=2（不确定）→ 不补。
    """
    if not record:
        return False
    if guard_rc != 0:
        return False
    if int(record.get("compensations", 0)) >= MAX_COMPENSATIONS:
        return False
    if is_expired(record, now=now):
        return False
    return True


def mark_compensated(*, path=None):
    path = path or PENDING_FILE
    rec = load(path)
    if rec:
        rec["compensations"] = int(rec.get("compensations", 0)) + 1
        rec["attempts"] = int(rec.get("attempts", 0)) + 1
        rec["compensated_at"] = _now_iso()
        save(rec, path)
    return rec
