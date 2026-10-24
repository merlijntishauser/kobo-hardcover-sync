"""The list of books as the reader sees it, in words and not in markup:
which books a view holds and in what order, and per book the Hardcover
status line and the correction the next sync makes. The page draws it
(web/app.py), and so will the Mac app, through the tool's JSON; what a
sync does with a book is decided in engine/plan.py, once, for both."""

from __future__ import annotations

import json

from .engine import state
from .engine.plan import action, desired, quiet_for
from .web.fmt import fmt_date, fmt_dt, fmt_dur
from .web.strings import T

FILTERS = {
    "all": "1=1",
    "reading": "((status=1 or (status=0 and percent>0)) and coalesce(finished_at,'')='' and state!='finished') or state='rereading'",
    "finished": "(status=2 or coalesce(finished_at,'')!='' or state='finished') and state!='rereading'",
    "unread": "(status=0 and coalesce(percent,0)=0)",
    "history": "history=1",
    "new": "history=0",
    "on": "(mode='on' or (mode='auto' and history=0))",
    "off": "not (mode='on' or (mode='auto' and history=0))",
    "needs_match": "(mode='on' or (mode='auto' and history=0)) and hc_book_id is null and hc_how in ('uncertain','none')",
    # On the Hardcover shelf with an edition that is not marked Ebook: to fix there.
    "not_ebook": "(mode='on' or (mode='auto' and history=0)) and last_sent is not null and coalesce(hc_format_id,0)!=4",
}
FILTER_GROUPS = [
    ("progress", ["all", "reading", "finished", "unread"]),
    ("kobo", ["history", "new"]),
    ("hardcover", ["on", "off", "needs_match", "not_ebook"]),
]

# Each way round. A book never opened has no last-read date: it comes last either way. content_id ends
# every order, so that the list is the same list from one "Show more" to the next.
SORTS = {
    "last_read": "last_read is null, last_read desc, content_id",
    "last_read_old": "last_read is null, last_read asc, content_id",
    "author": "author collate nocase, title collate nocase, content_id",
    "author_za": "author collate nocase desc, title collate nocase desc, content_id",
    "title": "title collate nocase, content_id",
    "title_za": "title collate nocase desc, content_id",
}


def where(reader, q, f):
    """The SQL condition of a view, a search q in filter f, and its arguments."""
    # Each filter in its own parentheses: some contain a top-level OR, which
    # would otherwise escape the reader condition.
    parts, args = [f"({FILTERS.get(f, '1=1')})", "reader=?"], [reader]
    if q:
        parts.append("(title like ? or author like ?)")
        args += [f"%{q}%", f"%{q}%"]
    return " and ".join(parts), args


def query_rows(con, reader, q, f, sort, limit: int = -1, offset: int = 0):
    """The books of a view, in its order; `limit` of them from `offset` (-1: all)."""
    w, args = where(reader, q, f)
    order = SORTS.get(sort, SORTS["last_read"])
    return con.execute(f"select * from reader_book where {w} order by {order} limit ? offset ?", [*args, limit, offset]).fetchall()


def place_of(con, reader, q, f, sort, cid: str) -> int:
    """Where a book stands in a view (0 = first), or -1 when the view does not hold it."""
    w, args = where(reader, q, f)
    order = SORTS.get(sort, SORTS["last_read"])
    found = con.execute(
        f"select n from (select content_id, row_number() over (order by {order}) - 1 as n from reader_book where {w}) where content_id=?",
        [*args, cid],
    ).fetchone()
    return found[0] if found else -1


def filter_counts(con, reader, q):
    out = {}
    for k in FILTERS:
        w, args = where(reader, q, k)
        out[k] = con.execute(f"select count(*) from reader_book where {w}", args).fetchone()[0]
    return out


def filters_of(con, reader, cid: str) -> list[str]:
    """The filters a book is in."""
    out = []
    for f in FILTERS:
        w, args = where(reader, "", f)
        if con.execute(f"select 1 from reader_book where {w} and content_id=?", [*args, cid]).fetchone():
            out.append(f)
    return out


def ids(con, reader, q, f) -> list[str]:
    """Every book a search and filter match, shown or not: what Set all changes."""
    w, args = where(reader, q, f)
    return [r[0] for r in con.execute(f"select content_id from reader_book where {w}", args)]


def hc_status(r, live: bool, quiet: dict) -> tuple[str, str]:
    """(kind, text) of the Hardcover status line: what the next sync does.
    kind: ok | next | wait | warn | err | none (marks.py). `quiet`: plan.quiet for this reader."""
    if r["hc_error"]:
        return "err", T["status_error"]
    if (r["device"], r["content_id"]) in quiet:
        return "none", T["other_copy"]
    a = action(r)
    if a.startswith("needs"):
        return "warn", T["needs_match"]
    if a.startswith("match pending"):
        return "next", T["match_pending"]
    if a:
        return "next", f"{T['next_sync'] if live else T['would_send']}: {a}"
    if state.syncs(r) and r["last_sent"]:
        return "ok", T["up_to_date"]
    if state.syncs(r):
        return "wait", T["not_yet_sent"]
    return "none", T["not_syncing"]


def marked(con, reader: str, live: bool, quiet: dict) -> int:
    """How many books carry the red mark: what the next sync sends."""
    return sum(1 for r in con.execute("select * from reader_book where reader=?", (reader,)) if hc_status(r, live, quiet)[0] == "next")


# The State a reader sets, in the page's words.
STATE_LABEL = {"kobo": "kobo", "finished": "finished_pin", "rereading": "rereading", "want": "want", "dnf": "dnf"}


def progress(r) -> tuple[int, bool, list[str]]:
    """How far the book is, under its title: (percent, finished, the facts
    in words: when it was finished or last read, and the time read)."""
    want = desired(r)
    done = bool(want and want["status"] == "read")
    pct = 100 if done else max(0, min(100, int(r["percent"] or 0)))
    meta = []
    if done:
        when = fmt_date(want.get("finished"))
        meta.append(f"{T['finished_on']} {when}" if when else T["finished_pin"])
    elif pct or r["status"] == 1:
        meta.append(f"{pct}%")
        if r["last_read"]:
            meta.append(f"{T['last_read']} {fmt_date(r['last_read'])}")
    else:
        meta.append(T["not_started"])
    if r["seconds_read"]:
        meta.append(f"{fmt_dur(r['seconds_read'])} {T['read_time']}")
    return pct, done, meta


def edition(r) -> tuple[str, bool]:
    """('Blindness, Ebook', stet): the match and its edition, and whether
    the edition was chosen on Hardcover, so that it is kept as it is."""
    if not r["hc_book_id"]:
        return "", False
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    parts = [r["hc_title"] or ""]
    if r["hc_format"] or sent.get("user_book_id"):
        parts.append(r["hc_format"] or T["format_unknown"])
    return ", ".join(x for x in parts if x), r["hc_edition_by"] == "hardcover"


def details(r) -> dict:
    """What Details shows of a book, in words: what the Kobo says and what
    Hardcover has, as (label, value) pairs without the empty ones; the
    link to the book on Hardcover; the books it could be, while it waits
    for a match; and whether it is on the Hardcover shelf (so it can be
    taken off)."""
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    kobo = [
        (T["col_mode"], T[r["mode"]]),
        (T["col_state"], T[STATE_LABEL[r["state"] or "kobo"]] + (f", {r['state_date']}" if r["state_date"] else "")),
        (
            T["d_kobo_status"],
            {0: T["d_unread"], 1: T["d_reading"], 2: T["d_finished"]}.get(r["status"], "") + (f", {r['percent']}%" if r["percent"] else ""),
        ),
        (T["d_finished_on"], fmt_date(r["finished_at"])),
        (T["d_last_read"], fmt_date(r["last_read"])),
        (T["d_read_time"], fmt_dur(r["seconds_read"]) if r["seconds_read"] else ""),
        (T["d_language"], r["language"] or ""),
        ("ISBN", r["isbn"] or ""),
    ]
    hc = []
    if r["hc_book_id"]:
        how = T.get("how_" + (r["hc_how"] or ""), "")
        hc.append((T["d_book"], (r["hc_title"] or "") + (f" ({how})" if how else "")))
        if r["hc_format"] or r["hc_pages"]:
            words = (r["hc_format"] or T["format_unknown"]) + (f", {r['hc_pages']} {T['d_pages']}" if r["hc_pages"] else "")
            hc.append((T["d_edition"], words + (f" ({T['how_hardcover']})" if r["hc_edition_by"] == "hardcover" else "")))
    if sent.get("user_book_id"):
        shelf = T["hc_" + sent.get("status", "reading")]
        if sent.get("status") == "reading" and sent.get("progress") is not None:
            shelf += f", {sent['progress']}%"
        if sent.get("finished"):
            shelf += f", {fmt_date(sent['finished'])}"
        hc.append((T["d_on_shelf"], shelf))
        hc.append((T["d_last_sync"], fmt_dt(sent.get("at"))))
    if r["hc_error"]:
        hc.append((T["d_error"], r["hc_error"]))
    waiting = not r["hc_book_id"] and r["hc_how"] in ("uncertain", "none")
    return {
        "kobo": [[k, v] for k, v in kobo if v],
        "hardcover": [[k, v] for k, v in hc if v],
        "link": f"https://hardcover.app/id/book/{int(r['hc_book_id'])}" if r["hc_book_id"] else "",
        "candidates": [
            {"id": int(c["book_id"]), "title": c["title"], "author": (c.get("authors") or [""])[0]}
            for c in json.loads(r["hc_candidates"] or "[]")
        ]
        if waiting
        else [],
        "on_shelf": bool(sent.get("user_book_id")),
    }


def entry(r, live: bool, quiet: dict, filters: list[str], cover: str = "") -> dict:
    """A book as the tool's JSON has it (`books --json`, `book --json`):
    its row, its Details, and the filters it is in. `cover`: its
    thumbnail's file, when there is one."""
    pct, done, meta = progress(r)
    kind, words = hc_status(r, live, quiet)
    words_of_edition, kept = edition(r)
    return {
        "id": r["content_id"],
        "title": r["title"] or "",
        "author": r["author"] or "",
        "cover": cover,
        "new": not r["history"],
        "percent": pct,
        "finished": done,
        "facts": meta,
        "last_read": r["last_read"] or "",
        "sync": r["mode"],
        "syncs": state.syncs(r),
        "state": r["state"] or "kobo",
        "state_date": r["state_date"] or "",
        "status": {"kind": kind, "text": words},
        "correction": list(correction(r) or []) if kind == "next" else [],
        "edition": words_of_edition,
        "stet": kept,
        "filters": filters,
        "details": details(r),
    }


def summary(con, reader: str) -> dict:
    """The books in a few counts, for the Mac app's overview: how many the
    Kobo told of, how many are switched on, how many the next sync changes
    and how many wait for a match; whether it sends (live) or only says
    what it would, as whom, and the collection the switched-on books go to."""
    counts = filter_counts(con, reader, "")
    row = con.execute("select hardcover_live, hardcover_user, kobo_collection from reader where name=?", (reader,)).fetchone()
    return {
        "total": counts["all"],
        "on": counts["on"],
        "next": marked(con, reader, bool(row and row[0]), quiet_for(con, reader)),
        "needs_match": counts["needs_match"],
        "live": bool(row and row[0]),
        "user": (row[1] if row else "") or "",
        "collection": ((row[2] if row else "") or "").strip(),
    }


def shelf_words(d: dict) -> str:
    """'Currently reading, 37%' / 'Read, finished 30 Sep 2026': a shelf entry
    in the page's words, for what Hardcover has (last_sent) or will get (desired)."""
    st = d.get("status") if d else None
    if not st:
        return ""
    words = T.get("hc_" + st, st)
    if st == "reading" and d.get("progress") is not None:
        words += f", {d['progress']}%"
    if st == "read" and d.get("finished"):
        words += ", " + T["shelf_finished"].format(date=fmt_date(d["finished"]))
    return words


def correction(r) -> tuple[str, str, str] | None:
    """The proof mark for a row the next sync changes: (kept, struck, inserted),
    'Currently reading,' '35%' '37%'. None when there is no shelf change to show
    (no match yet, or only the edition changes)."""
    a = action(r)
    if not a or not r["hc_book_id"] or a.startswith(("needs", "match pending")):
        return None
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    now = shelf_words(desired(r) or {})
    was = shelf_words(sent) if sent.get("user_book_id") else ""
    if not now or now == was:
        return None
    if was:
        h1, _, t1 = was.partition(", ")
        h2, _, t2 = now.partition(", ")
        if h1 == h2 and t1 and t2:
            return h1 + ",", t1, t2
    return "", was, now
