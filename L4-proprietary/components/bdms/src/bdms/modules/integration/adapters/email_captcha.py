"""IAM 邮件验证码获取 — IMAP 直读网易企业邮箱。

背景：IAM 登录触发邮件验证码（发件人 imb@bangcle.com，主题
「梆梆安全统一认证平台登录验证码」，正文含 6 位验证码，60 秒有效）。

原先实现依赖 localhost:5000 外部服务（/api/latest-captcha），
该服务从未启动导致登录失败。本模块改为 IMAP 直读邮箱：

1. IMAP 登录（SSL）并记录基准序号（登录前的最大邮件序号）
2. 预扫描最近 max_scan 封邮件（覆盖登录前已到达的验证码）
3. 轮询新邮件直到超时（验证码 60s 有效，轮询 90s 兜底）

注意：网易 IMAP 服务端搜索不可靠（FROM 搜索返回 0、中文 SUBJECT 编码异常），
因此一律用「拉取邮件头自行匹配」的方式。
"""
from __future__ import annotations

import imaplib
import logging
import re
import ssl
import time
from datetime import datetime, timedelta
from email import message_from_bytes, message_from_string
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_IMAP_HOST = "hwhzimap.qiye.163.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SENDER = "imb@bangcle.com"
DEFAULT_SUBJECT_KEYWORD = "登录验证码"
DEFAULT_CODE_LENGTH = 6
DEFAULT_POLL_TIMEOUT = 90  # 验证码 60s 有效，轮询 90s 兜底
DEFAULT_POLL_INTERVAL = 3
DEFAULT_MAX_SCAN = 10
DEFAULT_FRESH_WINDOW = 90  # 预扫描邮件新鲜度窗口（秒）


def _decode(s) -> str:
    """解码 RFC2047 编码的邮件头字段。"""
    if not s:
        return ""
    out = ""
    for p, enc in decode_header(s):
        if isinstance(p, bytes):
            out += p.decode(enc or "utf-8", errors="replace")
        else:
            out += p
    return out


def _fetch_body(msg) -> str:
    """提取邮件纯文本正文。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    payload = msg.get_payload(decode=True)
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace") if payload else ""


def _extract_code(text: str, code_length: int = DEFAULT_CODE_LENGTH) -> Optional[str]:
    """从正文提取验证码。

    优先匹配「验证码为：XXXXXX」模式（允许中间换行/空格/全角冒号），
    兜底匹配正文中独立出现的 code_length 位数字。
    """
    m = re.search(r"(?:验证码|code|Code)[^0-9]{0,20}(\d{%d,8})" % code_length, text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{%d})(?!\d)" % code_length, text)
    return m.group(1) if m else None


def _is_fresh(date_header: str, fresh_window: int) -> bool:
    """检查邮件日期是否在新鲜度窗口内（验证码 60s 有效）。"""
    if not date_header:
        return True  # 无日期头不拦截，交给序号轮询兜底
    try:
        dt = parsedate_to_datetime(date_header)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        return (now - dt) <= timedelta(seconds=fresh_window)
    except Exception:
        return True


class _ImapScan:
    """IMAP 验证码扫描器（单次登录生命周期）。"""

    def __init__(self, mail, sender: str, subject_keyword: str,
                 code_length: int, fresh_window: int):
        self.mail = mail
        self.sender = sender
        self.subject_keyword = subject_keyword
        self.code_length = code_length
        self.fresh_window = fresh_window

    def _check_one(self, msg_id) -> Optional[str]:
        """检查单封邮件：先看头（发件人+主题+日期），匹配再拉全文提取验证码。"""
        try:
            status, data = self.mail.fetch(
                str(msg_id), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not data or not data[0]:
                return None
            header = data[0][1].decode("utf-8", errors="replace")
            msg = message_from_string(header)
            sender_h = _decode(msg.get("From", ""))
            subject_h = _decode(msg.get("Subject", ""))
            if self.sender not in sender_h or self.subject_keyword not in subject_h:
                return None
            if not _is_fresh(msg.get("Date", ""), self.fresh_window):
                logger.info("邮件过旧，跳过: ID=%s date=%s", msg_id, msg.get("Date", ""))
                return None
            status2, data2 = self.mail.fetch(str(msg_id), "(BODY.PEEK[])")
            if status2 != "OK" or not data2 or not data2[0]:
                return None
            full = message_from_bytes(data2[0][1])
            body = _fetch_body(full)
            code = _extract_code(body, self.code_length)
            if code:
                logger.info("命中验证码邮件 ID=%s，提取验证码=%s", msg_id, code)
            return code
        except Exception as e:
            logger.debug("检查邮件 %s 失败: %s", msg_id, e)
            return None

    def scan(self, ids: List[bytes]) -> Optional[str]:
        """扫描一组邮件 ID，返回首个匹配的验证码。"""
        for raw_id in ids:
            msg_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            code = self._check_one(msg_id)
            if code:
                return code
        return None


def fetch_latest_captcha(
    imap_host: str = DEFAULT_IMAP_HOST,
    imap_port: int = DEFAULT_IMAP_PORT,
    username: str = "",
    password: str = "",
    sender: str = DEFAULT_SENDER,
    subject_keyword: str = DEFAULT_SUBJECT_KEYWORD,
    code_length: int = DEFAULT_CODE_LENGTH,
    poll_timeout: int = DEFAULT_POLL_TIMEOUT,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_scan: int = DEFAULT_MAX_SCAN,
    fresh_window: int = DEFAULT_FRESH_WINDOW,
) -> Optional[str]:
    """通过 IMAP 获取最新 IAM 登录验证码。

    Args:
        imap_host/imap_port: IMAP 服务器（默认网易企业邮箱推荐服务器）
        username/password: 邮箱账号 + 客户端授权密码
        sender: 验证码邮件发件人（默认 imb@bangcle.com）
        subject_keyword: 主题关键词（默认 登录验证码）
        code_length: 验证码位数（默认 6）
        poll_timeout: 轮询总超时（秒）
        poll_interval: 轮询间隔（秒）
        max_scan: 预扫描邮件数（覆盖登录前已到达的验证码）
        fresh_window: 预扫描邮件新鲜度窗口（秒）

    Returns:
        验证码字符串；失败/超时返回 None
    """
    if not username or not password:
        logger.error("IMAP 凭据未配置（username/password 为空）")
        return None

    try:
        ctx = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(host=imap_host, port=imap_port, ssl_context=ctx)
        mail.login(username, password)
        mail.select("INBOX")
    except Exception as e:
        logger.error("IMAP 连接失败: %s", e)
        return None

    try:
        status, data = mail.search(None, "ALL")
        if status != "OK":
            logger.error("IMAP 搜索失败: %s", status)
            return None
        all_ids = data[0].split()
        baseline = int(all_ids[-1]) if all_ids else 0
        logger.info("IMAP 已连接，基准序号=%d，总邮件数=%d", baseline, len(all_ids))

        scanner = _ImapScan(mail, sender, subject_keyword, code_length, fresh_window)

        # 1. 预扫描最近 max_scan 封（登录前可能已到达的验证码）
        pre_ids = all_ids[-max_scan:] if all_ids else []
        if pre_ids:
            code = scanner.scan(pre_ids)
            if code:
                return code

        # 2. 轮询新邮件（验证码 60s 有效，登录触发后邮件通常 2-5s 到达）
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            time.sleep(poll_interval)
            try:
                status, data = mail.search(None, "ALL")
                if status != "OK":
                    continue
                current_ids = data[0].split()
                new_ids = [raw for raw in current_ids
                           if int(raw.decode()) > baseline]
                if new_ids:
                    code = scanner.scan(new_ids)
                    if code:
                        return code
                    baseline = int(current_ids[-1].decode())
            except Exception as e:
                logger.debug("轮询失败: %s", e)
                continue

        logger.error("获取验证码超时（%ds 内未收到新验证码邮件）", poll_timeout)
        return None
    finally:
        try:
            mail.logout()
        except Exception:
            pass
