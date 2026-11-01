"""Small helpers: time, HTML escaping, logging that never shows secrets."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape
from typing import Any

CAPTION_LIMIT, TEXT_LIMIT = 1024, 4096


def utcnow() -> datetime:
    """Aware UTC now, truncated to milliseconds (what MongoDB stores)."""
    now = datetime.now(UTC)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def h(text: Any) -> str:
    """HTML-escape for parse_mode=HTML."""
    return escape(str(text if text is not None else ""), quote=False)


class RedactFilter(logging.Filter):
    """Never let the bot token, the Claude API key or the Mongo URL reach a log line."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        if self.secrets:
            msg = record.getMessage()
            hit = False
            for s in self.secrets:
                if s in msg:
                    msg = msg.replace(s, "<secret>")
                    hit = True
            if hit:
                record.msg = msg
                record.args = None
        return True


def setup_logging(level: str, *, secrets: Iterable[str] = ()) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.addFilter(RedactFilter(secrets))
    root.addHandler(stream)
    # httpx logs every request URL, and Telegram URLs contain the token
    for noisy in ("httpx", "httpcore", "httpx2", "anthropic", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
