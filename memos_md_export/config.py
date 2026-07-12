"""Configuration parsed from environment variables.

Configuration (environment):
  MEMOS_BASE_URL          e.g. http://memos:5230        (required)
  MEMOS_EXPORT_DIR        e.g. /export                  (required)
  MEMOS_TOKENS            newline/comma-separated access tokens
  MEMOS_TOKENS_FILE       path to a file of tokens, one per line (# = comment)
                          (provide MEMOS_TOKENS or MEMOS_TOKENS_FILE)
  MEMOS_DATE_BASIS        "created" (default) or "updated"
  MEMOS_TIMEZONE          IANA tz for the <date> bucket; default UTC
  MEMOS_INCLUDE_ARCHIVED  "1" to also mirror archived memos under _archived/
  MEMOS_VERIFY_TLS        "0" to disable TLS verification (self-signed)
  MEMOS_INTERVAL_SECONDS  if set, loop forever sleeping this long between runs
"""

from __future__ import annotations

import logging
import os
from datetime import timezone

try:
    from zoneinfo import ZoneInfo  # py3.9+
except ImportError:  # pragma: no cover
    ZoneInfo = None

log = logging.getLogger("memos-export")


class Config:
    def __init__(self) -> None:
        self.base_url = _require("MEMOS_BASE_URL").rstrip("/")
        self.export_dir = _require("MEMOS_EXPORT_DIR")
        self.date_basis = os.getenv("MEMOS_DATE_BASIS", "created").strip().lower()
        if self.date_basis not in ("created", "updated"):
            raise SystemExit("MEMOS_DATE_BASIS must be 'created' or 'updated'")
        self.include_archived = os.getenv("MEMOS_INCLUDE_ARCHIVED", "") == "1"
        self.verify_tls = os.getenv("MEMOS_VERIFY_TLS", "1") != "0"
        self.interval = _int_or_none(os.getenv("MEMOS_INTERVAL_SECONDS"))
        self.tz = _resolve_tz(os.getenv("MEMOS_TIMEZONE"))
        self.tokens = _load_tokens()
        if not self.tokens:
            raise SystemExit("No tokens: set MEMOS_TOKENS or MEMOS_TOKENS_FILE")


def _require(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"{name} is required")
    return v


def _int_or_none(s: str | None) -> int | None:
    if not s or not s.strip():
        return None
    try:
        return int(s)
    except ValueError:
        raise SystemExit("MEMOS_INTERVAL_SECONDS must be an integer") from None


def _resolve_tz(name: str | None):
    if not name or not name.strip():
        return timezone.utc
    if ZoneInfo is None:
        log.warning("zoneinfo unavailable; falling back to UTC")
        return timezone.utc
    try:
        return ZoneInfo(name.strip())
    except Exception:
        raise SystemExit(f"Unknown MEMOS_TIMEZONE: {name}") from None


def _load_tokens() -> list[str]:
    raw = os.getenv("MEMOS_TOKENS", "")
    path = os.getenv("MEMOS_TOKENS_FILE", "").strip()
    if path:
        with open(path, encoding="utf-8") as f:
            raw = raw + "\n" + f.read()
    tokens: list[str] = []
    for piece in raw.replace(",", "\n").splitlines():
        t = piece.strip()
        if t and not t.startswith("#"):
            tokens.append(t)
    # de-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
