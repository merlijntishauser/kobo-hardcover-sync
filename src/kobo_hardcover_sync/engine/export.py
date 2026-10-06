"""Everything the state knows about one reader's reading, as plain data for
`kobo-hardcover-sync export`: for a database, a spreadsheet or a dashboard of
the reader's own, with or without Hardcover.

Every book the Kobo has seen touched is in it, not only the ones that sync:
someone who does not use Hardcover still wants their whole shelf. On a shared
Kobo account that includes books others read; `opened_on_this_kobo` tells
them apart, as it does for the minutes. Nothing about a token is in it.

FORMAT goes up when a field changes meaning or goes away; a new field does
not change it.

The summary (/api/stats) is the caller's to give: it lives with the server,
and the engine does not reach into that.
"""

from __future__ import annotations

import json
import os
import sqlite3

from . import state

FORMAT = 1
KOBO_STATUS = {0: "unread", 1: "reading", 2: "finished"}


def _text(value):
    return value or None  # the state keeps "" for "not known"; null says that in JSON


def _book(r: sqlite3.Row) -> dict:
    hardcover = None
    if r["hc_book_id"]:
        hardcover = {
            "book_id": r["hc_book_id"],
            "edition_id": r["hc_edition_id"],
            "title": _text(r["hc_title"]),
            "matched_by": _text(r["hc_how"]),
            "last_sent": _text(r["last_sent"]),
        }
    return {
        "device": r["device"],
        "kobo_id": r["content_id"],
        "title": _text(r["title"]),
        "author": _text(r["author"]),
        "isbn": _text(r["isbn"]),
        "language": _text(r["language"]),
        "status": KOBO_STATUS.get(r["status"], "unread"),
        "percent": r["percent"] or 0,
        "last_read": _text(r["last_read"]),
        "finished": _text(r["finished_at"]),
        # The import that first saw the book being read: the Kobo itself keeps no start date.
        "started": _text((r["first_seen_reading"] or "")[:10]),
        "seconds_read": r["seconds_read"] or 0,
        "opened_on_this_kobo": bool(r["first_event"]),
        "sync": r["mode"],
        "syncs": state.syncs(r),
        "state": r["state"],
        "state_date": _text(r["state_date"]),
        "hardcover": hardcover,
    }


def reading(con: sqlite3.Connection, reader: str) -> dict:
    """The reader's devices, books and minutes per day, oldest first."""
    devices = con.execute("select device, first_import, last_import from device where reader=? order by first_import", (reader,))
    books = con.execute("select * from book where reader=? order by device, coalesce(last_read, ''), content_id", (reader,))
    days = con.execute("select day, device, seconds from reading_day where reader=? order by day, device", (reader,))
    return {
        "devices": [{"device": d["device"], "first_sync": d["first_import"], "last_sync": d["last_import"]} for d in devices],
        "books": [_book(b) for b in books],
        "reading_days": [{"day": d["day"], "device": d["device"], "seconds": d["seconds"]} for d in days],
    }


def document(con: sqlite3.Connection, reader: str, tool: str, summary: dict) -> dict:
    """The whole export: what made it and when, the summary, and the reading."""
    return {
        "format": FORMAT,
        "tool": tool,
        "made": state.now(),
        "reader": reader,
        "summary": {k: v for k, v in summary.items() if k != "reader"},
        **reading(con, reader),
    }


def write(path: str, data: dict) -> None:
    """To `path`, readable by its owner only, and whole or not at all: a
    dashboard that reads the file mid-sync sees the old one, never half."""
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text(data))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ---------- one sync, for a webhook ----------
def _seen(con: sqlite3.Connection, reader: str, device: str) -> dict | None:
    """What the state holds for this device's books, to compare after an
    import; None for a device this reader never synced before."""
    if not con.execute("select 1 from device where reader=? and device=?", (reader, device)).fetchone():
        return None
    rows = con.execute(
        "select content_id, percent, status, finished_at, seconds_read from book where reader=? and device=?", (reader, device)
    )
    return {r["content_id"]: tuple(r)[1:] for r in rows}


def before(con: sqlite3.Connection, reader: str, device: str) -> dict | None:
    """Taken just before an import; sync_event compares with it."""
    return _seen(con, reader, device)


def current(con: sqlite3.Connection, reader: str) -> dict | None:
    """The book being read: opened on this reader's own Kobo, marked reading,
    not finished, read last. The same choice as the stats summary."""
    r = con.execute(
        """select * from book where reader=? and first_event!='' and status=1 and coalesce(finished_at,'')=''
           order by last_read desc limit 1""",
        (reader,),
    ).fetchone()
    return _book(r) if r else None


def sync_event(con, reader: str, device: str, earlier: dict | None, tool: str, summary: dict, event: str = "sync") -> dict:
    """What a webhook gets after a sync that read the Kobo: the book being
    read, the books whose progress, status, finish date or reading time
    changed in this sync (new ones included), and the summary. A device's
    first sync lists no changes: everything would be new, and it is history."""
    now = _seen(con, reader, device) or {}
    changed = [] if earlier is None else [cid for cid, seen in now.items() if earlier.get(cid) != seen]
    rows = {r["content_id"]: r for r in con.execute("select * from book where reader=? and device=?", (reader, device))}
    return {
        "event": event,
        "format": FORMAT,
        "tool": tool,
        "made": state.now(),
        "reader": reader,
        "device": device or None,
        "first_sync": earlier is None,
        "reading": current(con, reader),
        "changed": [_book(rows[cid]) for cid in sorted(changed, key=lambda c: rows[c]["last_read"] or "", reverse=True)],
        "summary": {k: v for k, v in summary.items() if k != "reader"},
    }
