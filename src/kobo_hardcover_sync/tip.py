"""The tip: one book from the reader's own shelf, put to them as a question
(docs/plans/2026-10-26-mac-app-server-books-and-covers-design.md). Chosen
from what the tool already knows; nothing is asked of Hardcover or anyone
else. The first rule that finds a book gives it, the same one all day,
until the reader puts it aside."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import booklist
from .engine import state
from .web.strings import T

LEFT_OFF_AFTER = timedelta(days=183)  # not read for half a year
ASIDE_FOR = timedelta(days=30)  # Not now


def _left_off(r, pct: int, done: bool, today: date) -> bool:
    """Started, stopped somewhere in the middle, not read for half a year."""
    return not done and 10 <= pct <= 90 and bool(r["last_read"]) and r["last_read"][:10] <= (today - LEFT_OFF_AFTER).isoformat()


def _wanted(r, pct: int, done: bool, today: date) -> bool:
    """On the reader's Want to read (set here, or taken over from Hardcover), and on the Kobo, unopened."""
    return r["state"] == "want" and not done and pct == 0


def _never_opened(r, pct: int, done: bool, today: date) -> bool:
    return r["state"] == "kobo" and not done and pct == 0 and not r["last_read"] and not r["status"]


RULES = (("left_off", _left_off), ("wanted", _wanted), ("never_opened", _never_opened))


def pick(con, reader: str, today: date | None = None) -> dict | None:
    """{"id", "rule", "text"} of today's tip, or None when no rule finds a book."""
    today = today or date.fromisoformat(state.local_day())
    aside = {r[0] for r in con.execute("select content_id from tip_aside where reader=? and until>?", (reader, today.isoformat()))}
    rows = [
        r
        for r in con.execute("select * from reader_book where reader=? order by content_id", (reader,))
        if r["content_id"] not in aside and r["state"] not in ("finished", "dnf")
    ]
    for rule, fits in RULES:
        found = []
        for r in rows:
            pct, done, _ = booklist.progress(r)
            if fits(r, pct, done, today):
                found.append((r, pct))
        if found:
            r, pct = found[today.toordinal() % len(found)]  # a day's tip, another one tomorrow
            return {"id": r["content_id"], "rule": rule, "text": _words(rule, r, pct)}
    return None


def _words(rule: str, r, pct: int) -> str:
    if rule == "left_off":
        when = datetime.strptime(r["last_read"][:10], "%Y-%m-%d")
        return T["tip_left_off"].format(pct=pct, month=when.strftime("%B %Y"))
    return T["tip_" + rule]


def put_aside(con, reader: str, content_id: str, today: date | None = None) -> None:
    """Not now: this book is not the tip for a month."""
    until = (today or date.fromisoformat(state.local_day())) + ASIDE_FOR
    con.execute(
        "insert into tip_aside (reader, content_id, until) values (?, ?, ?)"
        " on conflict (reader, content_id) do update set until=excluded.until",
        (reader, content_id, until.isoformat()),
    )
    con.commit()
