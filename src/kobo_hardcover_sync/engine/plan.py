"""What kobo-hardcover-sync would send to Hardcover (dry run until step 4).

Rules (design section 2, plus the 2026-09-30 finish rule):
- A book with LastTimeFinishedReading counts as Read on that date even when
  it was reopened later (the Kobo then shows reading/unread and a low or
  mid percentage). The State override on the page can pin "finished" (with
  a date) or declare a real "rereading".
- status 2 -> "Read", with the finish date (DateLastRead). History books
  have no known start date.
- status 1, or status 0 with progress -> "Currently reading" with progress,
  and the start date when kobo-hardcover-sync saw it start (first_seen_reading).
- A progress update only when it moved by at least 1 point since the last
  send.
"""

from __future__ import annotations

import json

from .state import being_read, syncs


def desired(row) -> dict | None:
    st = row["state"] or "kobo"
    finished = (row["finished_at"] or "")[:10]
    if st in ("want", "dnf"):  # set aside: Hardcover keeps that status, no progress is sent
        return {"status": st}
    if st == "finished":
        return {"status": "read", "finished": (row["state_date"] or finished or (row["last_read"] or ""))[:10]}
    if st == "rereading":
        d = {"status": "reading", "progress": int(row["percent"] or 0), "reread": True}
        if row["state_date"]:
            d["started"] = row["state_date"]
        return d
    if row["status"] == 2 or finished:
        return {"status": "read", "finished": finished or (row["last_read"] or "")[:10]}
    if being_read(row["status"], row["percent"]):
        d = {"status": "reading", "progress": int(row["percent"] or 0)}
        if row["first_seen_reading"]:
            d["started"] = row["first_seen_reading"][:10]
        return d
    return None


def quiet(rows) -> dict:
    """Several of a reader's Kobo books can be one book on Hardcover: two
    editions, a sample and the book, the same book on two Kobos. One of them
    speaks for it, the one read last; the others are quiet: nothing is sent
    for them. Returns {(device, content_id): the row that speaks instead}."""

    def rank(r):
        return (r["last_read"] or "", r["device"], r["content_id"])

    copies = [r for r in rows if syncs(r) and r["hc_book_id"]]
    speaks: dict = {}
    for r in copies:
        if desired(r) is not None and (r["hc_book_id"] not in speaks or rank(r) > rank(speaks[r["hc_book_id"]])):
            speaks[r["hc_book_id"]] = r
    return {
        (r["device"], r["content_id"]): speaks[r["hc_book_id"]]
        for r in copies
        if r["hc_book_id"] in speaks and speaks[r["hc_book_id"]] is not r
    }


def quiet_for(con, reader: str) -> dict:
    return quiet(con.execute("select * from book where reader=?", (reader,)).fetchall())


def action(row) -> str:
    """Human-readable dry-run action for one book, or ""."""
    if not syncs(row):
        return ""
    want = desired(row)
    if want is None:
        return ""
    if not row["hc_book_id"]:
        return "needs a Hardcover match" if row["hc_how"] in ("uncertain", "none") else "match pending"
    sent = json.loads(row["last_sent"]) if row["last_sent"] else {}
    # kobo-hardcover-sync chose another edition than the one on the shelf (only once a
    # baseline exists: "edition_id" is recorded at the first two-way sync).
    edition = ""
    if (
        sent.get("user_book_id")
        and "edition_id" in sent
        and row["hc_edition_id"]
        and sent["edition_id"] != row["hc_edition_id"]
        and row["hc_edition_by"] != "hardcover"
    ):
        edition = f"set the edition ({row['hc_format'] or 'other edition'})"
    if want["status"] in ("want", "dnf"):
        if sent.get("status") != want["status"]:
            return "mark Want to read" if want["status"] == "want" else "mark Did not finish"
        return edition
    if want["status"] == "read":
        if sent.get("status") != "read":
            return f"mark Read, finished {want['finished'] or 'date unknown'}"
        if want["finished"] and sent.get("finished") and sent["finished"] != want["finished"]:
            return f"set the finish date to {want['finished']}"
        return edition
    if want.get("reread") and not sent.get("reread"):
        s = f"start a re-read, {want['progress']}%"
        return s + (f", started {want['started']}" if "started" in want else "")
    if sent.get("status") != "reading":
        s = f"mark Currently reading, {want['progress']}%"
        return s + (f", started {want['started']}" if "started" in want else "")
    if abs(want["progress"] - int(sent.get("progress") or 0)) >= 1:
        return f"progress {sent.get('progress') or 0}% to {want['progress']}%"
    return edition
