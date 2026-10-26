"""The Mac app's answers about books (`books --json`, `book ID --json`) and
the changes it makes to them. The same in local mode, where the tool
answers from this computer's database, and on the server (/api/app/),
where a device's token answers for its own reader. The rows are the
page's (booklist.py)."""

from __future__ import annotations

import json

from . import booklist
from .engine import state
from .term import plural
from .web.strings import T


class Refused(Exception):
    """A change that is not made; str() says why, status as the server answers it."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _quiet(con, reader: str) -> dict:
    from .engine.plan import quiet_for

    return quiet_for(con, reader) if con else {}


def listing(con, reader: str, cover_of, connected) -> dict:
    """Every book with its row and its Details, the filters it is in, the
    page's sorts and words, and the first run while it is a dry run.
    cover_of(row) is what the answer says of its cover; connected() whether
    the reader has a Hardcover connection, asked only for the first run;
    con None before a Kobo was read."""
    rows = booklist.query_rows(con, reader, "", "all", "last_read") if con else []
    live = bool(con and booklist.summary(con, reader)["live"])
    quiet = _quiet(con, reader)
    member = {f: set(booklist.ids(con, reader, "", f)) if con else set() for f in booklist.FILTERS}
    place = {r["content_id"]: n for n, r in enumerate(rows)}
    books = [booklist.entry(r, live, quiet, [f for f in booklist.FILTERS if r["content_id"] in member[f]], cover_of(r)) for r in rows]
    sorts = [  # each sort of the page, with its order as places in books
        {
            "key": k,
            "label": T["sort_" + k],
            "order": [place[r["content_id"]] for r in booklist.query_rows(con, reader, "", "all", k)] if con else [],
        }
        for k in booklist.SORTS
    ]
    summary = booklist.summary(con, reader) if con else {"user": "", "on": 0}
    first = None
    if con and rows and not live:  # the page's first run: until going live ends it
        history = sum(1 for r in rows if r["history"])
        first = {
            "title": T["fr_title"],
            "text": T["fr_text"].format(n=len(rows), h=history),
            "on": summary["on"],
            "tally": f"{T['fr_tally']} {T['fr_dry']}",
            "connected": connected(),
            "steps": [T["fr_connect"], T["fr_pick"], T["fr_live"]],
        }
    return {
        "live": live,
        "user": summary["user"],
        "first_run": first,
        "books": books,
        "sorts": sorts,
        "words": {  # the page's words, so that the app says the same
            "filters": [{"group": T["g_" + g], "keys": [[k, T["f_" + k]] for k in keys]} for g, keys in booklist.FILTER_GROUPS],
            "sections": [T["d_section_kobo"], T["d_section_hardcover"]],
            "syncs": [[m, T[m]] for m in state.MODES],
            "states": [[s, T[booklist.STATE_LABEL[s]]] for s in state.STATES],
            "legend": [[k, T["legend_" + k]] for k in ("next", "wait", "ok", "stet", "warn", "err", "none")],
        },
    }


def _row(con, reader: str, cid: str):
    row = con and con.execute("select * from reader_book where reader=? and content_id=?", (reader, cid)).fetchone()
    if not row:
        raise Refused(f"no book with the id '{cid}': `books --json` gives each book's id.", 404)
    return row


def one(con, reader: str, cid: str, cover_of) -> dict:
    """One book as listing() has it, and the counts that changed with it."""
    row = _row(con, reader, cid)
    summary = booklist.summary(con, reader)
    return {
        "book": booklist.entry(row, summary["live"], _quiet(con, reader), booklist.filters_of(con, reader, cid), cover_of(row)),
        "books": summary,
    }


def change(con, reader: str, cid: str, client, *, search="", pick="", sync="", state_="", date="", remove=False) -> None:
    """The changes the page makes to one book. client(**kw) is a Hardcover
    client, asked for only by a search and a removal; its HardcoverError
    goes to the caller."""
    from .engine import hardcover, job

    row = _row(con, reader, cid)
    if search:  # the books it could be, while it has no match
        if row["hc_book_id"]:
            raise Refused("this book has its match already.")
        found = hardcover.shown(client(tries=1).search(search))
        con.execute(
            "update book set hc_how=?, hc_candidates=? where reader=? and content_id=? and hc_book_id is null",
            ("uncertain" if found else "none", json.dumps(found), reader, cid),
        )
        con.commit()
    if pick:
        row = _row(con, reader, cid)
        chosen = [c for c in json.loads(row["hc_candidates"] or "[]") if str(c["book_id"]) == str(pick)]
        if not chosen:
            raise Refused(f"{pick} is not one of the books it could be (`book ID --json`, details, candidates).")
        job.pick(con, reader, cid, int(chosen[0]["book_id"]), chosen[0]["title"], chosen[0].get("pages") or None)
    if sync:
        if sync not in state.MODES:
            raise Refused(f"Sync is one of {', '.join(state.MODES)}, not '{sync}'.")
        state.set_mode(con, reader, [cid], sync)
    if state_:
        if state_ not in state.STATES:
            raise Refused(f"State is one of {', '.join(state.STATES)}, not '{state_}'.")
        try:
            state.set_state(con, reader, cid, state_, date if state_ in ("finished", "rereading") else "")
        except ValueError as ex:  # a date that is not one
            raise Refused(str(ex)) from ex
    if remove:  # off the Hardcover shelf now, and no longer synced
        job.remove(con, reader, cid, client())


def set_all(con, reader: str, sync: str, filter_: str, search: str, expect: int | None) -> None:
    """Set all, as on the page: Sync for every book the filter and search
    match; with expect, only while that is still that many books."""
    if con is None:
        raise Refused("no books yet: nothing was read from a Kobo so far.")
    if sync not in state.MODES:
        raise Refused(f"Sync is one of {', '.join(state.MODES)}, not '{sync}'.")
    if filter_ not in booklist.FILTERS:
        raise Refused(f"--filter is one of {', '.join(booklist.FILTERS)}, not '{filter_}'.")
    ids = booklist.ids(con, reader, search, filter_)
    if expect is not None and expect != len(ids):  # the list moved since it was counted: nothing changes
        raise Refused(f"the list holds {plural(len(ids), 'book')} now, not {expect}: nothing was changed.", 409)
    state.set_mode(con, reader, ids, sync)
