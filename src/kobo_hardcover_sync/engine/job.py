"""One sync run for a reader:
  1. take over what the reader changed on Hardcover (syncback, live only);
  2. match unmatched books;
  3. choose an edition where the reader has not chosen one (ebook first);
  4. send what changed.
Dry run unless the reader went live under Settings: in a dry run
only the plan is recorded and nothing is written to Hardcover.

The caller hands over the reader's Hardcover token: where it is kept
(the server's database, or the computer's own secret store) is not the
engine's business."""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta

from . import hardcover, state, syncback
from .plan import action, desired, quiet

log = logging.getLogger(__name__)  # titles only at debug level (see logs.py)
_running: set[str] = set()
_lock = threading.Lock()
# Where a reader's sync is, for the page to show while it runs: {"phase": "start" | "shelf" | "match" | "send",
# "done": books sent so far, "total": books to send}. Set before the work begins, gone when it ends.
progress: dict[str, dict] = {}


def begin(reader: str) -> None:
    """Say a sync for this reader is on its way, before its thread is started: the page drawn
    right after a click then already shows it running."""
    progress[reader] = {"phase": "start", "done": 0, "total": 0}


def syncing_rows(con, reader):
    return [r for r in con.execute("select * from book where reader=?", (reader,)) if state.syncs(r)]


def run(db_path: str, reader: str, live: bool, client: hardcover.Client | None = None, token: str = "") -> dict:
    with _lock:
        if reader in _running:
            return {"status": "already running"}
        _running.add(reader)
    progress[reader] = {"phase": "shelf" if live else "match", "done": 0, "total": 0}
    con = state.connect(db_path)
    started = state.now()
    con.execute("insert into job (reader, started, live, status) values (?,?,?,?)", (reader, started, int(live), "running"))
    con.commit()
    counts = {"matched": 0, "uncertain": 0, "sent": 0, "planned": 0, "errors": 0, "adopted": 0, "removed": 0, "editions": 0}
    # The books this run was about, for a reader watching it (the command, by hand). They are handed back
    # and nowhere else: not kept with the run, not logged.
    books = []

    def about(r, what, went, error=""):
        books.append(
            {
                "title": r["hc_title"] or r["title"],
                "percent": r["percent"],
                "finished": desired(r)["status"] == "read",
                "what": what,
                "went": went,
                "error": error,
            }
        )

    try:
        client = client or hardcover.Client(token)
        shelf = client.shelf() if live else []
        if live:
            counts.update(syncback.pull(con, reader, shelf))
        progress[reader] = {"phase": "match", "done": 0, "total": 0}
        # Not looked up yet, or waiting for the reader since rules that have changed since: those get one more look.
        todo = [
            r
            for r in syncing_rows(con, reader)
            if not r["hc_book_id"] and (r["hc_how"] not in ("uncertain", "none") or (r["hc_looked"] or 1) < hardcover.MATCH_RULES)
        ]
        for cid, m in hardcover.match_books(client, todo).items():
            con.execute(
                """update book set hc_how=?, hc_book_id=?, hc_edition_id=?, hc_pages=?, hc_title=?, hc_candidates=?, hc_looked=?
                           where reader=? and content_id=?""",
                (
                    m["how"],
                    m["book_id"],
                    m["edition_id"],
                    m["pages"],
                    m["title"],
                    json.dumps(m["candidates"]),
                    hardcover.MATCH_RULES,
                    reader,
                    cid,
                ),
            )
            counts["matched" if m["book_id"] else "uncertain"] += 1
            if m["book_id"]:
                log.debug("matched %r: Hardcover book %s (%s)", m["title"], m["book_id"], m["how"])
            else:
                log.debug("no sure match for Kobo book %s: left for the reader to choose", cid)
        con.commit()
        counts["editions"] = choose_editions(con, reader, client)
        existing = {u["book_id"]: u for u in shelf}
        rows = syncing_rows(con, reader)
        silent = quiet(rows)
        rows = [r for r in rows if r["hc_book_id"] and (r["device"], r["content_id"]) not in silent and action(r)]
        progress[reader] = {"phase": "send", "done": 0, "total": len(rows)}
        for i, r in enumerate(rows):
            progress[reader] = {"phase": "send", "done": i, "total": len(rows)}
            what = action(r)
            if not live:
                counts["planned"] += 1
                log.debug("would send %r: %s", r["title"], what)
                about(r, what, "planned")
                continue
            try:
                sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
                new = hardcover.apply(client, r, desired(r), sent, existing.get(r["hc_book_id"]))
                new["at"] = state.now()
                state.record_sent(con, reader, r, json.dumps(new))
                con.execute("update book set hc_error=null where reader=? and content_id=?", (reader, r["content_id"]))
                counts["sent"] += 1
                log.debug("sent %r: %s", r["title"], what)
                about(r, what, "sent")
            except hardcover.HardcoverError as e:
                if e.stops_the_run:  # no token, no connection, too many requests: the next book would hear the same
                    con.commit()
                    raise
                con.execute("update book set hc_error=? where reader=? and content_id=?", (str(e)[:300], reader, r["content_id"]))
                counts["errors"] += 1
                log.warning("a book could not be sent (%s); its row on the page says why", e.kind)
                log.debug("not sent %r: %s", r["title"], e)
                about(r, what, "failed", str(e))
            con.commit()
        status = "ok" if not counts["errors"] else "errors"
    except hardcover.HardcoverError as e:
        status, counts["fatal"] = "failed", str(e)[:300]
    finally:
        with _lock:
            _running.discard(reader)
    con.execute(
        "update job set finished=?, status=?, detail=? where reader=? and started=?",
        (state.now(), status, json.dumps(counts), reader, started),
    )
    con.commit()
    progress.pop(reader, None)  # after the job is recorded: the page then finds the result where it looks
    log.log(
        logging.INFO if status == "ok" else logging.ERROR,
        "hardcover (%s) for %s: %s",
        "live" if live else "dry run",
        reader,
        {"status": status, **counts},
    )
    return {"status": status, **counts, "books": books}


def could_not_start(db_path: str, reader: str, live: bool, why: str) -> None:
    """Record a run that never began, so that the page can say why: the
    reader's connection to Hardcover has ended, for one."""
    con = state.connect(db_path)
    at = state.now()
    con.execute(
        "insert into job (reader, started, finished, live, status, detail) values (?,?,?,?,?,?)",
        (reader, at, at, int(live), "failed", json.dumps({"fatal": why[:300]})),
    )
    con.commit()
    con.close()
    log.error("hardcover (%s) for %s did not start: %s", "live" if live else "dry run", reader, why)


EDITION_RECHECK_DAYS = 30


def choose_editions(con, reader: str, client) -> int:
    """Pick an edition (hardcover.choose_edition) for matched books whose
    edition the reader has not chosen on Hardcover. Checked once, and again
    after EDITION_RECHECK_DAYS: the catalogue gains editions over time."""
    cutoff = (datetime.now(UTC) - timedelta(days=EDITION_RECHECK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        r
        for r in syncing_rows(con, reader)
        if r["hc_book_id"] and r["hc_edition_by"] != "hardcover" and (not r["hc_edition_checked"] or r["hc_edition_checked"] < cutoff)
    ]
    if not rows:
        return 0
    editions = client.editions_for_books(sorted({r["hc_book_id"] for r in rows}), sorted({r["isbn"] for r in rows if r["isbn"]}))
    changed = 0
    for r in rows:
        e = hardcover.choose_edition(r["isbn"] or "", r["language"] or "", editions.get(r["hc_book_id"], []))
        if e and e["id"] != r["hc_edition_id"]:
            con.execute(
                """update book set hc_edition_id=?, hc_edition_by='auto', hc_pages=?, hc_format_id=?, hc_format=?
                           where reader=? and content_id=?""",
                (
                    e["id"],
                    e.get("pages") or r["hc_pages"],
                    e.get("reading_format_id"),
                    hardcover.format_name(e.get("reading_format_id"), e.get("edition_format")),
                    reader,
                    r["content_id"],
                ),
            )
            changed += 1
        elif e:
            con.execute(
                "update book set hc_edition_by='auto', hc_format_id=?, hc_format=? where reader=? and content_id=?",
                (
                    e.get("reading_format_id"),
                    hardcover.format_name(e.get("reading_format_id"), e.get("edition_format")),
                    reader,
                    r["content_id"],
                ),
            )
        con.execute("update book set hc_edition_checked=? where reader=? and content_id=?", (state.now(), reader, r["content_id"]))
    con.commit()
    return changed


def start(db_path: str, reader: str, live: bool, token: str) -> None:
    begin(reader)
    threading.Thread(target=run, args=(db_path, reader, live), kwargs={"token": token}, daemon=True).start()


def pick(con, reader: str, content_id: str, book_id: int, title: str, pages) -> None:
    # What was sent belongs to the book it was sent for: another book starts
    # without it (it takes over the record of a copy that is already there).
    known = con.execute(
        "select last_sent from book where reader=? and hc_book_id=? and content_id!=? and last_sent is not null",
        (reader, book_id, content_id),
    ).fetchone()
    con.execute(
        "update book set last_sent=? where reader=? and content_id=? and hc_book_id is not ?",
        (known["last_sent"] if known else None, reader, content_id, book_id),
    )
    con.execute(
        """update book set hc_how='manual', hc_book_id=?, hc_edition_id=null, hc_pages=?, hc_title=?, hc_error=null,
                   hc_edition_by=null, hc_edition_checked=null, hc_format_id=null, hc_format=null
                   where reader=? and content_id=?""",
        (book_id, pages, title, reader, content_id),
    )
    con.commit()


def remove(con, reader: str, content_id: str, client: hardcover.Client) -> None:
    r = con.execute("select * from book where reader=? and content_id=?", (reader, content_id)).fetchone()
    sent = json.loads(r["last_sent"]) if r and r["last_sent"] else {}
    if sent.get("user_book_id"):
        client.delete_user_book(sent["user_book_id"])
    con.execute("update book set last_sent=null, mode='off' where reader=? and content_id=?", (reader, content_id))
    con.commit()
