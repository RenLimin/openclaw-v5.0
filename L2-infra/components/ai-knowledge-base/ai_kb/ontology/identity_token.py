"""P6.1 run-scoped 身份令牌：签发 / 校验 / scope 授权（HMAC-SHA256）。

设计契约：DESIGN-DETAIL-operational-ontology-p6-v1.0 §2.2/§2.3/§3.1。

- 令牌 = base64url(claims JSON) + "." + base64url(HMAC-SHA256(secret, payload))；
- secret 默认落 ~/.openclaw/state/ontology-identity.secret（0600），可 env 覆盖；
- scope 语法 "<verb>:<action>:<domain>"，支持 "*" 通配；
- fail-closed：任何校验失败抛 IdentityError 子类，不返回"可用"假结果。

无第三方依赖，仅标准库。secret 永不进日志 / markdown / 返回体。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 时钟偏移容差（秒）
_LEEWAY = 60

_KINDS = {"human", "agent"}
_VERBS = {"propose", "review", "*"}

_DEFAULT_SECRET_PATH = (
    Path.home() / ".openclaw" / "state" / "ontology-identity.secret"
)


# ---------------------------------------------------------------
# 异常
# ---------------------------------------------------------------

class IdentityError(Exception):
    """身份校验失败基类（fail-closed）。"""


class InvalidToken(IdentityError):
    """结构错 / 签名不符 / claims 非法 / 与自报身份冲突。"""


class TokenExpired(IdentityError):
    """令牌超出 exp。"""


class ScopeDenied(IdentityError):
    """无任一 scope 匹配所请求的 verb/action/domain。"""


# ---------------------------------------------------------------
# 编码辅助
# ---------------------------------------------------------------

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _canonical_claims_json(claims: Dict[str, Any]) -> bytes:
    # 规范序列化：sort_keys + 紧凑，签发与指纹计算一致
    return json.dumps(
        claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


# ---------------------------------------------------------------
# scope
# ---------------------------------------------------------------

def parse_scope(scope: str) -> List[str]:
    parts = scope.split(":")
    if len(parts) != 3:
        raise InvalidToken(f"invalid scope (need verb:action:domain): {scope!r}")
    verb, action, domain = parts
    if not (verb and action and domain):
        raise InvalidToken(f"scope segment must not be empty: {scope!r}")
    if verb not in _VERBS:
        raise InvalidToken(f"scope verb must be one of {sorted(_VERBS)}: {verb!r}")
    return parts


def _scope_matches(scope: str, verb: str, action: str, domain: str) -> bool:
    try:
        s_verb, s_action, s_domain = parse_scope(scope)
    except InvalidToken:
        return False
    return (
        (s_verb == "*" or s_verb == verb)
        and (s_action == "*" or s_action == action)
        and (s_domain == "*" or s_domain == domain)
    )


# ---------------------------------------------------------------
# secret 加载
# ---------------------------------------------------------------

def _decode_secret_env(value: str) -> bytes:
    raw = value.strip()
    for decoder in (bytes.fromhex, base64.urlsafe_b64decode, base64.b64decode):
        try:
            data = decoder(raw)
            if len(data) >= 16:
                return data
        except Exception:
            continue
    raise InvalidToken(
        "OPENCLAW_ONTOLOGY_SECRET must be hex/base64 decoding to >=16 bytes"
    )


def _load_or_create_secret(secret_path: Path) -> bytes:
    env = os.environ.get("OPENCLAW_ONTOLOGY_SECRET")
    if env:
        return _decode_secret_env(env)

    if secret_path.exists():
        data = secret_path.read_bytes().strip()
        if len(data) >= 16:
            return data
        raise InvalidToken(f"secret file too short (<16 bytes): {secret_path}")

    # 首次签发：生成 32 字节随机密钥，0600
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    data = secrets.token_bytes(32)
    fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    try:
        os.chmod(secret_path, 0o600)
    except OSError:
        pass
    return data


# ---------------------------------------------------------------
# IdentityAuthority
# ---------------------------------------------------------------

class IdentityAuthority:
    """令牌签发与校验权威。"""

    def __init__(
        self,
        secret: Optional[bytes] = None,
        secret_path: Optional[Path] = None,
        default_ttl: int = 3600,
    ) -> None:
        self.secret_path = secret_path or _DEFAULT_SECRET_PATH
        self._secret = secret
        self.default_ttl = default_ttl

    # ---- secret ----
    @property
    def secret(self) -> bytes:
        if self._secret is None:
            self._secret = _load_or_create_secret(self.secret_path)
        if len(self._secret) < 16:
            raise InvalidToken("signing secret must be >=16 bytes")
        return self._secret

    # ---- 签发 ----
    def issue(
        self,
        *,
        run_id: str,
        subject: str,
        kind: str,
        scopes: List[str],
        ttl: Optional[int] = None,
        now: Optional[int] = None,
    ) -> str:
        if not run_id:
            raise InvalidToken("run_id must not be empty")
        if not subject:
            raise InvalidToken("subject must not be empty")
        if kind not in _KINDS:
            raise InvalidToken(f"kind must be one of {sorted(_KINDS)}")
        if not scopes:
            raise InvalidToken("scopes must not be empty")
        # 签发前校验每个 scope 合法
        for sc in scopes:
            parse_scope(sc)

        iat = int(now if now is not None else time.time())
        exp = iat + int(ttl if ttl is not None else self.default_ttl)
        claims = {
            "run_id": run_id,
            "sub": subject,
            "kind": kind,
            "scopes": list(scopes),
            "iat": iat,
            "exp": exp,
            "jti": "tok-" + secrets.token_hex(8),
        }
        payload_b64 = _b64url_encode(_canonical_claims_json(claims))
        sig = hmac.new(self.secret, payload_b64.encode("ascii"), hashlib.sha256)
        sig_b64 = _b64url_encode(sig.digest())
        return f"{payload_b64}.{sig_b64}"

    # ---- 校验 ----
    def verify(self, token: str, *, now: Optional[int] = None) -> Dict[str, Any]:
        if not token or not isinstance(token, str) or token.count(".") != 1:
            raise InvalidToken("malformed token")
        payload_b64, sig_b64 = token.split(".", 1)
        try:
            payload = _b64url_decode(payload_b64)
            provided_sig = _b64url_decode(sig_b64)
        except Exception as exc:
            raise InvalidToken(f"token base64 decode failed: {exc}") from exc

        expected_sig = hmac.new(
            self.secret, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise InvalidToken("signature mismatch")

        try:
            claims = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise InvalidToken(f"claims json decode failed: {exc}") from exc

        required = {"run_id", "sub", "kind", "scopes", "iat", "exp", "jti"}
        if not required <= set(claims):
            raise InvalidToken(f"missing claims: {sorted(required - set(claims))}")
        if claims["kind"] not in _KINDS:
            raise InvalidToken(f"invalid kind: {claims['kind']!r}")
        if not isinstance(claims["scopes"], list) or not claims["scopes"]:
            raise InvalidToken("scopes must be a non-empty list")
        for sc in claims["scopes"]:
            parse_scope(sc)

        current = int(now if now is not None else time.time())
        if int(claims["exp"]) < current - _LEEWAY:
            raise TokenExpired("token expired")
        return claims

    # ---- 指纹 ----
    def fingerprint(self, token: str) -> str:
        if not token or token.count(".") != 1:
            raise InvalidToken("malformed token")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    # ---- scope 授权 ----
    def authorize(
        self, claims: Dict[str, Any], verb: str, action: str, domain: str
    ) -> bool:
        if verb not in ("propose", "review"):
            raise InvalidToken(f"authorize verb must be propose/review: {verb!r}")
        for sc in claims["scopes"]:
            if _scope_matches(sc, verb, action, domain):
                return True
        raise ScopeDenied(
            f"no scope for {verb}:{action}:{domain} "
            f"(scopes={claims['scopes']})"
        )


# ---------------------------------------------------------------
# operator 兼容令牌
# ---------------------------------------------------------------

def operator_token(
    authority: IdentityAuthority,
    operator_id: str,
    *,
    run_id: str = "local-operator",
    domain_code: str = "*",
    ttl: Optional[int] = None,
) -> str:
    """签发 local operator 令牌（全 scope），人工 REST/CLI 兼容路径。

    sub 前缀 operator: 以区分 agent 主体；kind=human。
    """
    if not operator_id:
        raise InvalidToken("operator_id must not be empty")
    subject = operator_id if operator_id.startswith("operator:") else f"operator:{operator_id}"
    return authority.issue(
        run_id=run_id,
        subject=subject,
        kind="human",
        scopes=[f"*:*:{domain_code}"],
        ttl=ttl,
    )
