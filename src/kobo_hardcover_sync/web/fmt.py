"""Small formatting helpers shared by the pages."""

from __future__ import annotations

import html
from datetime import UTC, datetime

from ..engine.state import local_tz


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def fmt_date(s) -> str:
    try:
        d = datetime.strptime((s or "")[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def fmt_dt(s) -> str:
    """UTC timestamp from the state db -> local '30 Sep 2026, 12:24'."""
    try:
        d = datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC).astimezone(local_tz())
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y, %H:%M')}"


def shorten(s, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def fmt_dur(seconds) -> str:
    h, m = divmod(int(seconds or 0) // 60, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def fmt_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("bytes", "kB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1000
