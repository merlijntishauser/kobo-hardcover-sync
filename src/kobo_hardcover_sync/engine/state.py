"""kobo-hardcover-sync's own state: which books sync, per reader and device.

Every row is keyed by (reader, device, content_id), so more readers and
devices are a config change later (design section 4).

Selection rule (design, 2026-09-30):
- At a device's first import, every book that already has reading time or
  device events is *history*: mode "off" until the reader picks it.
- A book whose first device-local Event comes after that first import is
  *new*: mode "auto", which counts as on and can be switched off.

The same book on two Kobos of one reader is two rows, one per Kobo, for
what each Kobo says (progress, status, dates). What is set for the book
(PER_BOOK: Sync, State, the Hardcover match and record) is one per book
(2026-10-08): it is written by (reader, content_id), so to every Kobo's row at
once, and a Kobo that brings a book along later takes it over.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .kobo_db import Book

MODES = ("auto", "on", "off")
# What Hardcover gets, per book: follow the Kobo, pin as finished, or a re-read.
STATES = ("kobo", "finished", "rereading", "want", "dnf")

SCHEMA = """
create table if not exists device (
  reader text not null, device text not null,
  first_import text not null, last_import text not null,
  primary key (reader, device));
create table if not exists book (
  reader text not null, device text not null, content_id text not null,
  title text, author text, isbn text,
  percent integer, status integer, last_read text, seconds_read integer,
  first_event text, first_seen_reading text,
  history integer not null, mode text not null,
  hardcover_id text, last_sent text,
  finished_at text, state text not null default 'kobo', state_date text,
  primary key (reader, device, content_id));
create table if not exists reading_day (
  reader text not null, device text not null, day text not null, seconds integer not null,
  primary key (reader, device, day));
create table if not exists job (
  reader text not null, started text not null, finished text, live integer not null,
  status text not null, detail text);
create table if not exists import (
  reader text not null, device text not null, at text not null,
  books integer, new_books integer, source text);
-- Readers, their upload tokens (hash only) and their Hardcover token
-- (encrypted): see accounts.py.
create table if not exists reader (
  name text primary key, display_name text, identities text not null default '[]',
  is_admin integer not null default 0, hardcover_live integer not null default 0,
  kobo_collection text, hardcover_token_enc text, hardcover_user text, created text not null,
  stats_token_sha256 text);
create table if not exists device_token (
  token_sha256 text primary key, reader text not null, device text not null, created text not null);
create table if not exists meta (key text primary key, value text);
-- The Hardcover account a reader's shelf records (book.last_sent) belong to.
create table if not exists hardcover_account (
  reader text primary key, user_id integer not null, username text, since text not null);
"""
# What is set for a book rather than read from a Kobo: the same on each Kobo's row of it.
PER_BOOK = (
    "mode",
    "history",  # with mode: whether "auto" counts as on
    "state",
    "state_date",
    "state_changed",
    "hc_how",
    "hc_book_id",
    "hc_edition_id",
    "hc_pages",
    "hc_title",
    "hc_candidates",
    "hc_looked",
    "hc_error",
    "hc_edition_by",
    "hc_format_id",
    "hc_format",
    "hc_edition_checked",
    "last_sent",
)
# Each Kobo's rows ranked by the one read last, as plan.quiet ranks the copies that may speak.
READ_LAST = "coalesce(last_read, '') desc, device desc"
# One row per book of a reader, the copy on the Kobo it was read on last: what the page lists.
BOOK_VIEW = f"""
create view if not exists reader_book as
  select * from (select *, row_number() over (partition by reader, content_id order by {READ_LAST}) as copy from book)
  where copy = 1;
"""


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_tz():
    """Where the reader is: the TZ setting, else None, which stands for the
    computer's own time zone (in a container that is UTC unless TZ says
    otherwise)."""
    import os
    from zoneinfo import ZoneInfo

    tz = os.environ.get("TZ")
    return ZoneInfo(tz) if tz else None


def local_day() -> str:
    return datetime.now(local_tz()).strftime("%Y-%m-%d")


def being_read(status, percent) -> bool:
    """The Kobo says the book is being read: marked so, or unread with progress."""
    return status == 1 or (status == 0 and (percent or 0) > 0)


def record_sent(con: sqlite3.Connection, reader: str, row, last_sent: str | None, off: bool = False) -> None:
    """What Hardcover has is known per Hardcover book, not per Kobo book: the
    record goes to `row` and to every other copy of the same Hardcover book
    (plan.quiet). off: the book was taken off the shelf there, so every copy
    stops syncing too."""
    also = ", mode='off'" if off else ""
    con.execute(
        f"update book set last_sent=?{also} where reader=? and (content_id=? or hc_book_id=?)",
        (last_sent, reader, row["content_id"], row["hc_book_id"]),
    )


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("pragma table_info(book)")}
    for col, decl in (
        ("finished_at", "text"),
        ("state", "text not null default 'kobo'"),
        ("state_date", "text"),
        # Hardcover match (step 4): how = isbn|search|manual|uncertain|none
        ("hc_how", "text"),
        ("hc_book_id", "integer"),
        ("hc_edition_id", "integer"),
        ("hc_pages", "integer"),
        ("hc_title", "text"),
        ("hc_candidates", "text"),
        ("hc_error", "text"),
        ("image_id", "text"),
        ("language", "text"),
        # Two-way sync. hc_edition_by: "auto" (kobo-hardcover-sync's choice)
        # or "hardcover" (chosen there by the reader, never overwritten).
        ("hc_edition_by", "text"),
        ("hc_format_id", "integer"),
        ("hc_format", "text"),
        ("hc_edition_checked", "text"),
        ("state_changed", "text"),
        # The version of the matching rules (hardcover.MATCH_RULES) that last looked this book up.
        ("hc_looked", "integer"),
    ):
        if col not in have:  # state.db from before 2026-09-30 12:xx
            con.execute(f"alter table book add column {col} {decl}")
    reader_cols = {r[1] for r in con.execute("pragma table_info(reader)")}
    if "stats_token_sha256" not in reader_cols:
        con.execute("alter table reader add column stats_token_sha256 text")
    if "client_version" not in {r[1] for r in con.execute("pragma table_info(device)")}:
        # The version of the tool on the computer that uploaded last: "" for one too old to say (2026-10-04).
        con.execute("alter table device add column client_version text")
    if "list_size" not in reader_cols:  # books the list shows at first: null the usual 100, 0 all of them (2026-10-04)
        con.execute("alter table reader add column list_size integer")
    con.executescript(BOOK_VIEW)
    if con.execute("select 1 from meta where key='per_book'").fetchone() is None:
        # Before 2026-10-08 a second Kobo's copy of a book began with its own Sync and State. The Kobo it
        # was read on last is the one the page showed and the one that spoke for it: that one counts.
        cols = ", ".join(PER_BOOK)
        con.execute(
            f"""update book set ({cols}) = (select {cols} from book w where w.reader=book.reader and w.content_id=book.content_id
                  order by coalesce(w.last_read, '') desc, w.device desc limit 1)
                where exists (select 1 from book o where o.reader=book.reader and o.content_id=book.content_id and o.device!=book.device)"""
        )
        con.execute("insert or ignore into meta values ('per_book', ?)", (now(),))  # two connections at once: both align, the same
        con.commit()
    return con


def import_books(con: sqlite3.Connection, reader: str, device: str, books: list[Book], source: str = "") -> dict:
    """Merge a parsed database into the state. Returns counts."""
    at = now()
    dev = con.execute("select first_import from device where reader=? and device=?", (reader, device)).fetchone()
    first_import = dev["first_import"] if dev else at
    is_first = dev is None
    added = new_auto = changed = read_seconds = 0
    for b in books:
        if not (b.seconds_read or b.first_event or b.percent):
            continue  # never touched by anyone: not interesting yet
        row = con.execute(
            "select mode, first_seen_reading, percent, status, finished_at, seconds_read from book where reader=? and device=? and content_id=?",
            (reader, device, b.content_id),
        ).fetchone()
        reading_now = being_read(b.status, b.percent)
        if row is None:
            # New to kobo-hardcover-sync. Opened on this device after the first import -> new/auto.
            # Already on another of the reader's Kobos: the book brings what was set for it.
            elsewhere = con.execute(
                f"select {', '.join(PER_BOOK)} from book where reader=? and content_id=? order by {READ_LAST} limit 1",
                (reader, b.content_id),
            ).fetchone()
            is_new = elsewhere is None and (not is_first) and bool(b.first_event) and b.first_event >= first_import[:19]
            mode = "auto" if is_new else "off"
            new_auto += is_new
            added += 1
            con.execute(
                """insert into book (reader, device, content_id, title, author, isbn, percent, status,
                   last_read, seconds_read, first_event, first_seen_reading, history, mode, finished_at, image_id, language)
                   values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    reader,
                    device,
                    b.content_id,
                    b.title,
                    b.author,
                    b.isbn,
                    b.percent,
                    b.status,
                    b.last_read,
                    b.seconds_read,
                    b.first_event,
                    at if (reading_now and not is_first) else "",
                    0 if is_new else 1,
                    mode,
                    b.finished_at,
                    b.image_id,
                    b.language,
                ),
            )
            if elsewhere:
                con.execute(
                    f"update book set {', '.join(c + '=?' for c in PER_BOOK)} where reader=? and device=? and content_id=?",
                    (*elsewhere, reader, device, b.content_id),
                )
        else:
            if (row["percent"], row["status"], row["finished_at"] or "") != (b.percent, b.status, b.finished_at):
                changed += 1
            # Reading time is account-wide, so only books opened on THIS
            # device (a local Event) count towards this reader's minutes;
            # otherwise what others on the account read on their own Kobos leaks in.
            grew = b.seconds_read - (row["seconds_read"] or 0)
            if b.first_event and 0 < grew < 16 * 3600:
                read_seconds += grew
            # The start date is the import that first saw the book being read.
            # One that was already being read when it was first seen has none.
            first_seen = row["first_seen_reading"] or (at if reading_now and not being_read(row["status"], row["percent"]) else "")
            con.execute(
                """update book set title=?, author=?, isbn=?, percent=?, status=?, last_read=?,
                   seconds_read=?, first_event=?, first_seen_reading=?, finished_at=?, image_id=?, language=?
                   where reader=? and device=? and content_id=?""",
                (
                    b.title,
                    b.author,
                    b.isbn,
                    b.percent,
                    b.status,
                    b.last_read,
                    b.seconds_read,
                    b.first_event,
                    first_seen,
                    b.finished_at,
                    b.image_id,
                    b.language,
                    reader,
                    device,
                    b.content_id,
                ),
            )
    if read_seconds:
        con.execute(
            """insert into reading_day values (?,?,?,?)
                       on conflict (reader, device, day) do update set seconds = seconds + excluded.seconds""",
            (reader, device, local_day(), read_seconds),
        )
    if is_first:
        con.execute("insert into device (reader, device, first_import, last_import) values (?,?,?,?)", (reader, device, at, at))
    else:
        con.execute("update device set last_import=? where reader=? and device=?", (at, reader, device))
    con.execute("insert into import values (?,?,?,?,?,?)", (reader, device, at, len(books), new_auto, source))
    con.commit()
    return {
        "books": len(books),
        "tracked_added": added,
        "new_auto": new_auto,
        "changed": changed,
        "minutes_read": read_seconds // 60,
        "first_import": is_first,
    }


def set_mode(con: sqlite3.Connection, reader: str, content_ids: list[str], mode: str) -> int:
    """Sync for these books, on every Kobo they are on (PER_BOOK)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    n = 0
    for cid in content_ids:
        n += con.execute("update book set mode=? where reader=? and content_id=?", (mode, reader, cid)).rowcount
    con.commit()
    return n


def set_state(con: sqlite3.Connection, reader: str, content_id: str, st: str, date: str = "") -> int:
    """The State of this book, on every Kobo it is on (PER_BOOK)."""
    if st not in STATES:
        raise ValueError(f"state must be one of {STATES}")
    if date and not (len(date) == 10 and date[4] == "-" and date[7] == "-"):
        raise ValueError("date must be YYYY-MM-DD")
    # state_changed: a State set here since the last sync wins over an edit
    # made on Hardcover in the same period.
    n = con.execute(
        "update book set state=?, state_date=?, state_changed=? where reader=? and content_id=?",
        (st, date or None, now(), reader, content_id),
    ).rowcount
    con.commit()
    return n


def hardcover_account(con: sqlite3.Connection, reader: str) -> tuple[int, str] | None:
    """(user id, username) of the Hardcover account this reader's books were put on, or None."""
    r = con.execute("select user_id, username from hardcover_account where reader=?", (reader,)).fetchone()
    return (r["user_id"], r["username"] or "") if r else None


def bind_account(con: sqlite3.Connection, reader: str, who: dict) -> None:
    con.execute("insert or ignore into hardcover_account values (?,?,?,?)", (reader, who["id"], str(who.get("username") or ""), now()))
    con.commit()


def has_records(con: sqlite3.Connection, reader: str) -> bool:
    """Something of this reader's is on a Hardcover shelf, as far as this tool knows."""
    return con.execute("select 1 from book where reader=? and last_sent is not null limit 1", (reader,)).fetchone() is not None


def start_over(con: sqlite3.Connection, reader: str) -> None:
    """Forget what was put on the bound account's shelf, and the account: the
    next live sync puts the books that sync on the shelf of the account the
    token is for. Sync, State and matches stay; the old shelf is not touched."""
    con.execute("update book set last_sent=null, hc_error=null where reader=?", (reader,))
    con.execute("delete from hardcover_account where reader=?", (reader,))
    con.commit()


def syncs(row) -> bool:
    return row["mode"] == "on" or (row["mode"] == "auto" and not row["history"])
