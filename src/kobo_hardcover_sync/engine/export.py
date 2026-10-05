"""Everything the state knows about one reader's reading, as plain data for
`kobo-hardcover-sync export`: for a database, a spreadsheet or a dashboard of
the reader's own, with or without Hardcover.

Every book the Kobo has seen touched is in it, not only the ones that sync:
someone who does not use Hardcover still wants their whole shelf. On a shared
Kobo account that includes books others read; `opened_on_this_kobo` tells
them apart, as it does for the minutes. Nothing about a token is in it.

FORMAT goes up when a field changes meaning or goes away; a new field does
not change it.
"""

from __future__ import annotations

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
