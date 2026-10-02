"""Hardcover -> kobo-hardcover-sync: take over what the reader changed on Hardcover.

Per shelf book, Hardcover's current state is compared with the baseline
kobo-hardcover-sync recorded when it last wrote or read that book (last_sent["hc"]).
A difference is an edit made on Hardcover, and becomes the same kind of
override the reader can set on the page:

  Read, or another finish date      -> State "finished", pinned with that date
  finished book set back to Reading -> State "rereading"
  Want to read / Did not finish     -> State "want" / "dnf": left alone
  removed from the shelf            -> Sync off, not added again
  another edition                   -> adopted, marked as the reader's choice

A State set on the page since the last sync wins over a Hardcover edit of
the same period. Progress is never taken from Hardcover: the Kobo knows.

First run for a book (no baseline yet): the status is compared with what
kobo-hardcover-sync sent; the edition is only recorded, because until now every
edition on the shelf was kobo-hardcover-sync's or Hardcover's default, not a choice.
"""

from __future__ import annotations

import json
import logging

from . import hardcover, state
from .plan import desired, quiet
from .state import syncs

MANY = 3  # this many books gone from the shelf at once, and none left: not believed
log = logging.getLogger(__name__)


def _edition_fields(ub: dict) -> dict:
    e = ub.get("edition") or {}
    return {
        "id": ub.get("edition_id"),
        "pages": e.get("pages"),
        "format_id": e.get("reading_format_id"),
        "format": hardcover.format_name(e.get("reading_format_id"), e.get("edition_format")),
    }


def pull(con, reader: str, shelf: list[dict]) -> dict:
    by_id = {u["id"]: u for u in shelf}
    counts = {"adopted": 0, "removed": 0}
    rows = con.execute("select * from book where reader=?", (reader,)).fetchall()
    silent = quiet(rows)
    # A shelf without a single one of the books that sync is not the reader
    # tidying up: it is another account's shelf, or a token that may not read
    # this one. Switching every book off for that would be the wrong answer.
    tracked = [(r, s) for r in rows if r["last_sent"] and (s := json.loads(r["last_sent"])).get("user_book_id")]
    ours = {s["user_book_id"] for r, s in tracked if syncs(r)}
    if len(ours) >= MANY and ours.isdisjoint(by_id):
        raise hardcover.HardcoverError(
            f"None of the {len(ours)} books this tool put on your Hardcover shelf are on the shelf Hardcover showed. "
            "Nothing was switched off. Is the token from another Hardcover account, or may it not read your library? "
            "If you took them off yourself, switch them off here too",
            "answer",
        )
    gone = set()
    for r, sent in tracked:
        ub_id = sent["user_book_id"]
        ub = by_id.get(ub_id)
        if ub is None:
            # Taken off the shelf on Hardcover: respect it, keep the match.
            # Every copy of the book goes off, or the next one would add it again.
            state.record_sent(con, reader, r, None, off=True)
            counts["removed"] += ub_id not in gone
            gone.add(ub_id)
            log.debug("off the shelf on Hardcover, switched off here: %r", r["title"])
            continue
        if (r["device"], r["content_id"]) in silent:
            continue  # another copy speaks for this Hardcover book, and its record is copied to this one below
        reads = ub.get("user_book_reads") or []
        read = next((x for x in reads if x["id"] == sent.get("read_id")), reads[-1] if reads else {})
        cur = {
            "status_id": ub["status_id"],
            "edition_id": ub.get("edition_id"),
            "finished_at": read.get("finished_at"),
            "started_at": read.get("started_at"),
        }
        base = sent.get("hc")
        if base is None:
            changed_status = cur["status_id"] != hardcover.STATUS_IDS.get(sent.get("status"))
            changed_date = changed_edition = False
        else:
            changed_status = cur["status_id"] != base.get("status_id")
            changed_edition = cur["edition_id"] != base.get("edition_id")
            # No known date on our side is not a change (Hardcover fills one in itself).
            changed_date = cur["status_id"] == 3 and base.get("finished_at") is not None and cur["finished_at"] != base.get("finished_at")
        local_newer = bool(r["state_changed"]) and r["state_changed"] > (sent.get("at") or "")
        ed = _edition_fields(ub)
        sets = {}
        adopted = False
        if (changed_status or changed_date) and not local_newer:
            sid = cur["status_id"]
            if sid == 3:
                date = cur["finished_at"] or state.local_day()
                follow = desired({**dict(r), "state": "kobo"})
                if follow and follow["status"] == "read" and follow.get("finished") == date:
                    sets.update(state="kobo", state_date=None)  # the Kobo says the same
                else:
                    sets.update(state="finished", state_date=date)
                sent.update(status="read", finished=date, reread=False)
                adopted = True
            elif sid == 2:
                if r["status"] == 2 or r["finished_at"]:
                    sets.update(state="rereading", state_date=cur["started_at"])
                    sent.update(status="reading", reread=True, progress=None)
                else:
                    sets.update(state="kobo", state_date=None)
                    sent.update(status="reading", reread=False)
                adopted = True
            elif sid in (1, 5):
                name = hardcover.STATUS_NAMES[sid]
                sets.update(state=name, state_date=None)
                sent.update(status=name, reread=False)
                adopted = True
        if changed_edition:
            sets.update(
                hc_edition_id=ed["id"],
                hc_edition_by="hardcover",
                hc_pages=ed["pages"] or r["hc_pages"],
                hc_format_id=ed["format_id"],
                hc_format=ed["format"],
            )
            adopted = True
        elif not r["hc_edition_id"] or r["hc_edition_id"] == ed["id"]:
            # Same edition as the shelf: keep format and page count current
            # (title-matched books have no edition of their own).
            sets.update(hc_format_id=ed["format_id"], hc_format=ed["format"], hc_pages=ed["pages"] or r["hc_pages"])
        if reads and sent.get("read_id") not in [x["id"] for x in reads]:
            sent["read_id"] = reads[-1]["id"]  # our entry was replaced on Hardcover
        sent["hc"] = cur
        sent["edition_id"] = cur["edition_id"]
        if adopted:
            sent["at"] = state.now()
            counts["adopted"] += 1
            log.debug("taken over from Hardcover for %r: %s", r["title"], ", ".join(sets) or "the edition")
        if sets:
            con.execute(
                f"update book set {', '.join(k + '=?' for k in sets)} where reader=? and content_id=?",
                (*sets.values(), reader, r["content_id"]),
            )
        state.record_sent(con, reader, r, json.dumps(sent))
    con.commit()
    return counts
