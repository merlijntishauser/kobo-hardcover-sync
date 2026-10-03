"""The check: look at everything a sync depends on, change nothing, and say
per item what was found and what to do about it.

Two places show it. `kobo-hardcover-sync doctor` on the computer the Kobo
is plugged into, and the Check card under Settings on the page. In local
mode both show the same list. In server mode each side can only see its own
half: the computer sees the Kobo and whether the server knows it, the
server sees the reader's Hardcover token and what was uploaded.

Looking is all it does. The Kobo's database is copied and the copy is read;
this tool's own database is opened read-only; Hardcover is asked one
question (whose token is this). Nothing in the result names a book or shows
a token.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from . import term
from .engine import collection, hardcover, kobo_db, oauth, state
from .term import FAIL, NOTE, OK, WARN, WORDS  # noqa: F401 (the page asks for them here)
from .web.fmt import fmt_dt

# What is looked at belongs to one of three things, and is shown under it.
COMPUTER, KOBO, HARDCOVER = "This computer", "Your Kobo", "Hardcover"
GROUPS = {
    COMPUTER: ("Setup", "Trigger", "Folder", "Upload token", "Server", "Last sync", "Log"),
    KOBO: ("Kobo", "Database", "Kobo software", "Collection", "Backups", "Computers", "Computer"),
    HARDCOVER: ("Token", "Hardcover", "Books", "Sending", "Matches", "Errors", "Last run"),
}
ON_THE_COMPUTER = "The Kobo itself is checked on the computer it is plugged into: run `kobo-hardcover-sync doctor` there."


@dataclass(frozen=True)
class Check:
    what: str  # the thing looked at: "Kobo", "Hardcover", ...
    state: str  # OK: fine. NOTE: worth knowing, nothing to mend. WARN: something works less well. FAIL: syncing does not work.
    found: str  # what was found, a sentence
    todo: str = ""  # what to do, when there is something to do


def problems(checks: list[Check]) -> int:
    return sum(c.state == FAIL for c in checks)


def summary(checks: list[Check]) -> str:
    bad, warn = problems(checks), sum(c.state == WARN for c in checks)
    if not bad and not warn:
        return "Everything a sync depends on is in order."
    parts = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in ((bad, "problem"), (warn, "warning")) if n]
    return f"{' and '.join(parts)}: {'its line says' if bad + warn == 1 else 'their lines say'} what to do."


# ---------- Hardcover ----------
def hardcover_check(token: str, add_one: str, client=None, run_out: bool = False) -> Check:
    """Is Hardcover there, and does it accept the token. One request.
    add_one: where a token is entered, for the reader who has none.
    run_out: there is a connection, and its access token has run out; a
    check renews nothing, so there is nothing to ask Hardcover with."""
    if run_out and client is None:
        return Check("Hardcover", NOTE, "The connection to Hardcover is renewed at the next sync; it was not asked about now.")
    if not token and client is None:
        return Check("Hardcover", NOTE, "No Hardcover token yet, so nothing is sent to Hardcover.", add_one)
    try:
        who = (client or hardcover.Client(token, tries=1)).whoami()
    except hardcover.HardcoverError as ex:
        # Not reachable, or too many requests: Hardcover's side or the network, and it passes.
        passing = ex.kind in ("unreachable", "rate")
        return Check("Hardcover", WARN if passing else FAIL, f"{ex}.")
    name = str(who.get("username") or "")
    whose = f": it is @{name}'s" if name else ""
    return Check("Hardcover", OK, f"Hardcover is reachable and accepts the token{whose}.")


# ---------- the reader's books and runs (this tool's own database) ----------
def reader_checks(con, reader: str, has_token: bool) -> list[Check]:
    row = con.execute("select hardcover_live from reader where name=?", (reader,)).fetchone()
    books = con.execute("select * from book where reader=?", (reader,)).fetchall()
    on = [b for b in books if state.syncs(b)]
    out = []
    if not books:
        out.append(Check("Books", NOTE, "No books yet: nothing was read from a Kobo so far.", "Plug in the Kobo."))
    else:
        out.append(
            Check(
                "Books",
                OK if on else NOTE,
                f"{len(on)} of {len(books)} books are switched on.",
                "" if on else "Switch on the books that should sync, on the page.",
            )
        )
    if row is not None and row["hardcover_live"]:
        out.append(Check("Sending", OK, "Live: changes go to the Hardcover shelf."))
    else:
        out.append(
            Check(
                "Sending",
                NOTE,
                "Dry run: the page shows what would be sent, and nothing goes to Hardcover.",
                "Go live under Settings when the plan looks right." if has_token else "",
            )
        )
    waiting = sum(1 for b in on if not b["hc_book_id"] and b["hc_how"] in ("uncertain", "none"))
    if waiting:
        out.append(
            Check(
                "Matches",
                WARN,
                f"{_books(waiting)} switched on {_verb(waiting, 'has', 'have')} no Hardcover match yet and cannot sync.",
                "Choose the right book in Details on the page.",
            )
        )
    failed = sum(1 for b in on if b["hc_error"])
    if failed:
        out.append(Check("Errors", WARN, f"{_books(failed)} could not be sent at the last sync.", "The page says why, on the book's row."))
    job = con.execute("select * from job where reader=? order by started desc limit 1", (reader,)).fetchone()
    if job is None:
        out.append(Check("Last run", NOTE, "Nothing was sent or planned for Hardcover yet."))
    elif job["status"] == "failed":
        try:
            why = str(json.loads(job["detail"] or "{}").get("fatal") or "")
        except ValueError:
            why = ""
        out.append(Check("Last run", WARN, f"The last run for Hardcover ({_when(job['started'])}) stopped: {why or 'no reason recorded'}."))
    else:
        out.append(Check("Last run", OK, f"The last run for Hardcover was {_when(job['started'])}."))
    return out


def _books(n: int) -> str:
    return f"{n} book{'' if n == 1 else 's'}"


def _verb(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _when(stamp: str) -> str:
    return fmt_dt(stamp) or "at an unknown time"


# ---------- the server's half (the page in server mode) ----------
def server_checks(
    con, reader: str, token_state: str, token: str, can_store: bool, devices: list, client=None, run_out: bool = False
) -> list[Check]:
    """token: the reader's token as it is kept, nothing renewed
    (accounts.token_peek). run_out: a connection whose access token has
    run out."""
    out = []
    if token_state == "unreadable":
        out.append(Check("Token", FAIL, "The stored Hardcover token cannot be read any more.", "Enter it again under Hardcover, above."))
    elif not can_store and token_state != "env":
        out.append(Check("Token", FAIL, "Tokens cannot be stored: the server has no KHS_SECRET_KEY.", "Ask the admin."))
    if token_state != "unreadable":
        out.append(hardcover_check(token, "Add one under Hardcover, above.", client, run_out))
    out += reader_checks(con, reader, bool(token) or run_out)
    if not devices:
        out.append(
            Check(
                "Computers",
                WARN,
                "No computer uploads your Kobo yet.",
                "Run `kobo-hardcover-sync setup --server <this address>` on the computer you plug the Kobo into, and add its hash under Devices.",
            )
        )
    for d in devices:
        if d["last_import"]:
            out.append(Check("Computer", OK, f"{d['device']}: last upload {_when(d['last_import'])}."))
        else:
            out.append(
                Check(
                    "Computer",
                    NOTE,
                    f"{d['device']}: no upload yet.",
                    "Plug in the Kobo on that computer. If nothing arrives, run `kobo-hardcover-sync doctor` there.",
                )
            )
    out.append(Check("Kobo", NOTE, ON_THE_COMPUTER))
    return out


# ---------- the computer's half, and all of local mode ----------
def computer_checks(computer, cfg=None, client=None, opener=None, by_hand: bool = True) -> list[Check]:
    """Everything that can be seen from the computer the Kobo is plugged
    into. client and opener let tests stand in for Hardcover and the server."""
    from .computer import config, remote
    from .computer.platform import HARDCOVER, KOBO_DB, UPLOAD
    from .server.accounts import LOCAL_READER

    cfg = cfg or config.load()
    folder = config.state_dir()
    if not cfg.mode:
        return [Check("Setup", FAIL, "This computer is not set up yet.", "Run `kobo-hardcover-sync setup`.")]
    out = [
        Check(
            "Setup",
            OK,
            f"Server mode: this computer uploads to {cfg.server}." if cfg.server else "Local mode: everything happens on this computer.",
        )
    ]

    works, said = computer.trigger_state()
    out.append(
        Check(
            "Trigger", OK if works else WARN, said, "" if works else "Until then, run `kobo-hardcover-sync sync` with the Kobo plugged in."
        )
    )

    if os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK):
        out.append(Check("Folder", OK, f"The tool's folder is {folder}."))
    else:
        out.append(
            Check(
                "Folder", FAIL, f"The tool's folder, {folder}, cannot be written to.", "Check who owns it; KHS_HOME names another folder."
            )
        )

    wanted = None  # the collection's name; None: not known
    if cfg.server:
        token = computer.secret(UPLOAD)
        if not token:
            out.append(Check("Upload token", FAIL, "No upload token on this computer.", "Run `kobo-hardcover-sync setup` again."))
        else:
            digest = hashlib.sha256(token.encode()).hexdigest()
            out.append(Check("Upload token", OK, f"Present, kept in {computer.secret_place(UPLOAD)}; its hash starts with {digest[:8]}."))
            server = remote.Server(cfg.server, token, opener)
            try:
                wanted = (server.collection() or ("", []))[0]
                out.append(Check("Server", OK, f"{server.host} is reachable and knows this computer."))
            except remote.ServerError as ex:
                out.append(Check("Server", FAIL, str(ex)))
        del token
        out.append(
            Check("Hardcover", NOTE, f"Your Hardcover token and your books are checked on the server: {cfg.server}/settings, Check.")
        )
    else:
        kept = computer.secret(HARDCOVER)
        token = oauth.peek(kept)  # as it is kept: a check renews nothing
        if kept:
            what = "The connection to Hardcover" if oauth.unpack(kept) else "A Hardcover token"
            out.append(Check("Token", OK, f"{what} is kept in {computer.secret_place(HARDCOVER)}."))
        out.append(
            hardcover_check(token, "`kobo-hardcover-sync token`, or Settings on the page.", client, run_out=bool(kept) and not token)
        )
        has_token = bool(kept) or client is not None
        del token, kept
        own = os.path.join(folder, "state.db")
        if not os.path.isfile(own):
            wanted = ""
            out.append(Check("Books", NOTE, "No books yet: nothing was read from a Kobo so far.", "Plug in the Kobo."))
        else:
            try:
                with contextlib.closing(_read_only(own)) as con:
                    row = con.execute("select kobo_collection from reader where name=?", (LOCAL_READER,)).fetchone()
                    wanted = ((row["kobo_collection"] if row else "") or "").strip()
                    out += reader_checks(con, LOCAL_READER, has_token)
            except (sqlite3.Error, IndexError) as ex:  # IndexError: a column a newer version added
                out.append(
                    Check(
                        "Books",
                        WARN,
                        f"This tool's own database could not be read ({ex}).",
                        "Run `kobo-hardcover-sync sync` once, then check again.",
                    )
                )

    out += kobo_checks(computer, cfg, wanted, os.path.join(folder, "collection"), KOBO_DB, by_hand)
    out.append(_last_told(folder))
    out.append(
        Check(
            "Log",
            NOTE if cfg.verbose_log else OK,
            f"{os.path.join(folder, 'agent.log')}"
            + (" (verbose: it holds book titles)." if cfg.verbose_log else " (counts and messages, no book titles)."),
        )
    )
    return out


def _read_only(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{quote(path)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _last_told(folder: str) -> Check:
    try:
        with open(os.path.join(folder, "last-message.txt")) as fh:
            lines = [line.strip() for line in fh if line.strip()]
        return Check("Last sync", OK, f"{lines[-1]}: {lines[0]}: {' '.join(lines[1:-1])}")
    except (OSError, IndexError):
        return Check("Last sync", NOTE, "No sync has said anything yet.")


def kobo_checks(computer, cfg, wanted: str | None, collection_dir: str, kobo_db_path: str, by_hand: bool = True) -> list[Check]:
    """The Kobo, its database, whether this tool may write its collection
    there, the collection and the backups."""
    from .computer import runner

    mount = computer.find_kobo()
    if not mount:
        return [
            Check(
                "Kobo",
                NOTE,
                "No Kobo found, so its database and the collection were not checked.",
                "Plug it in, tap Connect on the Kobo, and run this check again.",
            ),
            _backups(collection_dir),
        ]
    dev = kobo_db.device(mount)
    about = ", ".join(x for x in (dev.model, f"software {dev.software}" if dev.software else "") if x)
    out = [Check("Kobo", OK, f"Found at {mount}{' (' + about + ')' if about else ''}.")]
    db = os.path.join(mount, kobo_db_path)
    with tempfile.TemporaryDirectory(prefix="khs-") as tmp:
        try:
            copy = runner.copy_database(db, tmp)
        except OSError as ex:
            return [*out, Check("Database", FAIL, runner.unreadable(computer, ex, by_hand)), _backups(collection_dir)]
        try:
            with contextlib.closing(kobo_db.open_db(copy, allow_user_table=True)) as con:  # the copy never leaves this folder
                n = len(kobo_db.read_books(con))
                out.append(Check("Database", OK, f"The Kobo's database can be read: {_books(n)} on it."))
                out.append(_gate(con, cfg.allow_untested_kobo))
        except (kobo_db.NotAKoboDatabase, sqlite3.Error):
            return [*out, Check("Database", FAIL, runner.DAMAGED), _backups(collection_dir)]
        out.append(_collection(copy, db, wanted, collection_dir))
    out.append(_backups(collection_dir))
    return out


def _gate(con, allowed: bool) -> Check:
    """May the collection be written to this Kobo? The same gate the write
    goes through."""
    what = "Kobo software"
    try:
        version = collection.check(con, allow_untested=False)
    except collection.UnsupportedKobo as ex:
        try:
            collection.check(con, allow_untested=True)
        except collection.UnsupportedKobo:
            return Check(what, WARN, str(ex))  # it lacks something the write needs: no setting lets that through
        if allowed:
            return Check(
                what, NOTE, f"Database version {ex.version} has not been tested; allow_untested_kobo lets the collection be written anyway."
            )
        return Check(
            what,
            WARN,
            f"This Kobo's software has not been tested with kobo-hardcover-sync yet (its database is version {ex.version}). "
            "The collection is not written to it; syncing to Hardcover is not affected.",
            collection.UNTESTED_HOW,
        )
    return Check(
        what, OK, f"Database version {version} is one this tool was tested with (Kobo software {collection.KNOWN_VERSIONS[version]})."
    )


def _collection(copy: str, db: str, wanted: str | None, collection_dir: str) -> Check:
    what = "Collection"
    if wanted is None:
        return Check(what, NOTE, "Which collection is wanted is not known: the server did not say.")
    if not wanted:
        return Check(what, NOTE, "No collection is wanted, so nothing is ever written to the Kobo.")
    try:
        found = collection.status(copy, wanted, collection_dir)
    except (collection.CollectionError, sqlite3.Error) as ex:
        return Check(what, WARN, f"The collection could not be looked at: {ex}")
    if found["present"] and not found["ours"]:
        return Check(
            what,
            WARN,
            f"A collection named '{wanted}' is on this Kobo and was not made by this tool, so it is left alone.",
            "Choose another name under Settings, or remove that collection on the Kobo.",
        )
    if not os.access(db, os.W_OK):
        return Check(
            what,
            WARN,
            f"The Kobo's database cannot be written to, so the collection '{wanted}' cannot be kept.",
            "Check how the Kobo is mounted.",
        )
    if found["present"]:
        return Check(what, OK, f"'{wanted}' is on the Kobo, with {_books(found['books'])}.")
    return Check(what, NOTE, f"'{wanted}' is not on the Kobo yet: a sync makes it once a book is switched on.")


def _backups(collection_dir: str) -> Check:
    folder = os.path.join(collection_dir, "backups")
    try:
        made = sorted(
            os.path.getmtime(os.path.join(folder, f))
            for f in os.listdir(folder)
            if f.startswith("KoboReader-") and f.endswith(".sqlite.gz")
        )
    except OSError:
        made = []
    if not made:
        return Check("Backups", NOTE, "No copy of the Kobo's database yet: one is made before the first write to the Kobo.")
    newest = datetime.fromtimestamp(made[-1])
    return Check(
        "Backups",
        OK,
        f"{len(made)} {_verb(len(made), 'copy', 'copies')} of the Kobo's database from before a write, the newest of "
        f"{newest.day} {newest:%b %Y, %H:%M}, in {folder}.",
    )


# ---------- shown ----------
def grouped(checks: list[Check]) -> list[tuple[str, list[Check]]]:
    """The checks under the thing they are about, in the order found. A
    check nobody gave a place still shows, at the end."""
    out = [(name, [c for c in checks if c.what in whats]) for name, whats in GROUPS.items()]
    placed = {what for whats in GROUPS.values() for what in whats}
    out.append(("Also", [c for c in checks if c.what not in placed]))
    return [(name, some) for name, some in out if some]


def show(checks: list[Check], screen: term.Screen) -> None:
    """The check as the command prints it."""
    width = max(len(c.what) for c in checks)
    for name, some in grouped(checks):
        screen.heading(name)
        screen.rows([term.Row(c.state, c.what, c.found, c.todo) for c in some], label_width=width)
        screen.line()
    screen.say(summary(checks))


def report(checks: list[Check], width: int = 80) -> str:
    """The same as plain text: what a pipe, a file or a bug report gets."""
    out: list[str] = []
    show(checks, term.Screen(out.append, colour=False, width=width))
    return "".join(out).rstrip("\n")
