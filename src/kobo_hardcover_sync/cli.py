"""The command.

On the computer the Kobo is plugged into:

kobo-hardcover-sync setup [--server URL | --local] [--no-trigger] [--new-token] [--rebuild-app]
    Make this computer sync a plugged-in Kobo: the trigger that starts a
    sync when the Kobo is plugged in. Without --server everything happens
    on this computer (local mode). With it, this computer sends the Kobo's
    reading data to that server: an upload token goes into the Keychain
    and its hash is printed, for the page's Settings, Devices. Safe to run
    again; takes over an older installation. --no-trigger leaves the
    trigger out: you run `sync` yourself.

kobo-hardcover-sync token [--remove]
    Local mode: ask for your Hardcover token, check it with Hardcover, and
    keep it in the Keychain. (The page's Settings does the same.)

kobo-hardcover-sync sync [--verbose]
    One sync now. It says each step as it finishes, and then names the
    books that went to Hardcover, each with how far it is read. Those
    titles are shown in the terminal and written nowhere. --verbose also
    shows the log while it runs.

kobo-hardcover-sync status
    What is set up, and what it sees. Quick, and never uses the network.

kobo-hardcover-sync doctor
    Check everything a sync depends on, and say what to do about what is
    wrong. Changes nothing; asks Hardcover (or your server) one question.
    Ends with status 1 when something stops syncing from working.

kobo-hardcover-sync open
    Open the page (local mode: it is started for the occasion).

kobo-hardcover-sync uninstall [--purge]
    Remove the trigger; --purge also the state and the tokens.

On the server:

kobo-hardcover-sync serve [--host 127.0.0.1] [--port 3012]
    Run the server: the page and the upload endpoint. Needs
    KHS_TRUSTED_PROXIES (the address of the sign-in proxy) and does not
    start without it. Listens on the loopback address unless told
    otherwise; the container passes --host 0.0.0.0.

kobo-hardcover-sync import <file> --reader NAME --device NAME [--raw]
    Import a KoboReader.sqlite by hand, on the server. --raw accepts a
    copy that still has the `user` table (Kobo login tokens); nothing
    from that table is read or stored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile

from . import __version__, term
from .engine import kobo_db, state
from .env import env
from .term import FAIL, NOTE, OK, WARN, Row, plural

HOME_PAGE = "https://github.com/merlijntishauser/kobo-hardcover-sync"
COMMANDS = (
    (
        "On the computer you plug the Kobo into",
        (
            ("setup", "Make this computer sync a plugged-in Kobo"),
            ("token", "Store your Hardcover token (when everything runs on this computer)"),
            ("sync", "One sync now"),
            ("status", "What is set up, and what it sees"),
            ("doctor", "Check everything a sync depends on; changes nothing"),
            ("open", "Open the page with your books"),
            ("uninstall", "Remove the trigger"),
        ),
    ),
    (
        "On a server",
        (
            ("serve", "Run the server: the page and the upload endpoint"),
            ("import", "Import a KoboReader.sqlite by hand"),
        ),
    ),
)
SHOWN_BOOKS = 12  # a run by hand names this many books, and counts the rest


class _Parser(argparse.ArgumentParser):
    """argparse, with a first page written for a reader instead of drawn up from the parser."""

    def format_help(self) -> str:
        if self.prog != "kobo-hardcover-sync":
            return super().format_help()
        out: list[str] = []
        screen = term.Screen.of(sys.stdout)
        screen._write = out.append
        screen.heading(f"Kobo Hardcover Sync {__version__}")
        screen.say("Keeps your shelf on Hardcover in step with what you read on a Kobo.")
        for title, commands in COMMANDS:
            screen.line()
            screen.heading(title)
            for name, what in commands:
                screen.line(f"  {screen.style(f'{name:<10}', term.CYAN)} {what}")
        screen.line()
        screen.say("kobo-hardcover-sync <command> --help says more about one command.")
        screen.line(screen.style(HOME_PAGE, term.DIM))
        return "".join(out)


def main(argv: list[str] | None = None, computer=None) -> None:
    p = _Parser(prog="kobo-hardcover-sync")
    p.add_argument("--version", action="version", version=f"kobo-hardcover-sync {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{setup,token,sync,status,doctor,open,uninstall,serve,import}")
    stp = sub.add_parser("setup", help="make this computer sync a plugged-in Kobo")
    stp.add_argument("--server", default="", help="the server's address, e.g. https://kobo.example.org")
    stp.add_argument("--local", action="store_true", help="everything on this computer, no server")
    stp.add_argument("--new-token", action="store_true", help="replace the upload token (the device must be added again)")
    stp.add_argument("--rebuild-app", action="store_true", help="rebuild the small app (it then needs its permission again)")
    stp.add_argument("--no-trigger", action="store_true", help="only the settings: you run `sync` yourself")
    tok = sub.add_parser("token", help="local mode: store your Hardcover token")
    tok.add_argument("--remove", action="store_true", help="forget the token (and go back to dry run)")
    sub.add_parser("page")  # what `open` starts in local mode; no help text, so it is not listed
    syn = sub.add_parser("sync", help="one sync now")
    syn.add_argument("--trigger", default="", help=argparse.SUPPRESS)  # "mount": started by the plug-in trigger
    syn.add_argument("--verbose", action="store_true", help="also show the log while it runs: a line per book and per request")
    sub.add_parser("status", help="what is set up, and what it sees")
    sub.add_parser("doctor", help="check everything a sync depends on; changes nothing")
    sub.add_parser("open", help="open the page")
    uni = sub.add_parser("uninstall", help="remove the trigger")
    uni.add_argument("--purge", action="store_true", help="also remove the state and the upload token")
    srv = sub.add_parser("serve", help="run the server: the page and the upload endpoint")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=3012)
    imp = sub.add_parser("import", help="import a KoboReader.sqlite by hand, on the server")
    imp.add_argument("file")
    imp.add_argument("--reader", required=True)
    imp.add_argument("--device", required=True)
    imp.add_argument("--raw", action="store_true", help="allow the user table (it is never read)")
    a = p.parse_args(argv)

    if a.cmd == "serve":
        return _serve(a)
    if a.cmd == "import":
        con = kobo_db.open_db(a.file, allow_user_table=a.raw)
        books = kobo_db.read_books(con)
        st = state.connect(os.path.join(env("DATA", "/data"), "state.db"))
        print(json.dumps(state.import_books(st, a.reader, a.device, books, source=os.path.basename(a.file))))
        return

    if a.cmd == "page":
        from .computer import page

        return page.serve()

    from .computer import platform

    try:
        computer = computer or platform.pick()
    except platform.Unsupported as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}")
    commands = {
        "setup": _setup,
        "sync": _sync,
        "status": _status,
        "doctor": _doctor,
        "open": _open,
        "uninstall": _uninstall,
        "token": _token,
    }
    commands[a.cmd](a, computer)


def _serve(a) -> None:
    import uvicorn

    from . import logs
    from .server import proxy

    logs.to_stderr()  # KHS_LOG=verbose: a line per book, with titles
    try:
        if not proxy.parse(env("TRUSTED_PROXIES", "")):
            sys.exit("kobo-hardcover-sync: not started. " + proxy.HOW)
    except proxy.BadSetting as ex:
        sys.exit(f"kobo-hardcover-sync: not started. {ex}")
    # No proxy_headers: the address the app checks must be the one that
    # really connected (the proxy), not one a header claims.
    uvicorn.run("kobo_hardcover_sync.web.app:app", host=a.host, port=a.port, proxy_headers=False)


def _own_path() -> str:
    """Where the trigger will find this tool: the path it was started by.
    With two installations on one computer (say Homebrew's and uv's) that is
    the one `setup` was run from, not the first one on the PATH. Homebrew's
    path, /opt/homebrew/bin/..., stays the same through upgrades."""
    started = sys.argv[0]
    if os.path.isabs(started) and os.path.basename(started) == "kobo-hardcover-sync" and os.access(started, os.X_OK):
        return started
    return shutil.which("kobo-hardcover-sync") or os.path.abspath(started)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _setup(a, computer) -> None:
    from .computer import config
    from .computer.platform import UPLOAD

    if a.server and a.local:
        sys.exit("kobo-hardcover-sync: --server or --local, not both")
    cfg = config.load()
    server = "" if a.local else (a.server or cfg.server)
    if server and not server.startswith(("https://", "http://")):
        sys.exit("kobo-hardcover-sync: the server's address starts with https://")
    cfg.server = server.rstrip("/")
    config.save(cfg)

    screen = term.Screen.of()
    rows = [
        Row(
            OK,
            "Mode",
            f"Server mode: this computer uploads to {cfg.server}." if cfg.server else "Local mode: everything happens on this computer.",
        )
    ]
    digest = ""
    if cfg.server:
        token = computer.secret(UPLOAD)
        if a.new_token or not token:
            token = secrets.token_hex(32)
            computer.set_secret(UPLOAD, token)
            rows.append(Row(OK, "Token", "New upload token stored on this computer."))
        else:
            rows.append(Row(OK, "Token", "Keeping the existing upload token."))
        digest = _token_hash(token)
        del token

    said: list[str] = []
    if a.no_trigger:
        rows.append(Row(NOTE, "Trigger", "No trigger installed: run `kobo-hardcover-sync sync` with the Kobo plugged in."))
    else:
        said = computer.install_trigger(_own_path(), a.rebuild_app)
        works, found = computer.trigger_state()
        if works:
            rows.append(Row(OK, "Trigger", found))
        else:  # what went wrong installing it says more than what is found afterwards
            rows.append(Row(WARN, "Trigger", " ".join(line.strip() for line in said) or found))
            said = []
    screen.heading("Setup")
    screen.rows(rows)
    if said:
        screen.line()
        for line in said:  # what the computer did, and what it asks of you; a path stays on its own line, whole
            screen.line(line) if line.startswith(" ") else screen.say(line, indent=2)

    screen.line()
    screen.heading("Next")
    if cfg.server:
        screen.say(f"1. Paste this computer's hash at {cfg.server}/settings under Devices, unless it is there already:", indent=2, hang=3)
        screen.line(f"     {screen.style(digest, term.CYAN)}")
        screen.say("2. Plug in the Kobo and tap Connect on it.", indent=2, hang=3)
    else:
        screen.say("1. `kobo-hardcover-sync token` stores your Hardcover token.", indent=2, hang=3)
        screen.say("2. Plug in the Kobo and tap Connect on it.", indent=2, hang=3)
        screen.say(
            "3. `kobo-hardcover-sync open` shows your books. Nothing goes to Hardcover until you go live under Settings.", indent=2, hang=3
        )


def _one(state: str, text: str, todo: str = "") -> None:
    """One line of result: a mark and a sentence."""
    term.Screen.of().rows([Row(state, "", text, todo)], label_width=0)


def _token(a, computer) -> None:
    from .computer import config, page
    from .computer.platform import HARDCOVER
    from .engine import hardcover
    from .server import accounts

    cfg = config.load()
    if cfg.mode != "local":
        sys.exit(
            "kobo-hardcover-sync: in server mode the Hardcover token is set on the server's page, under Settings."
            if cfg.server
            else "kobo-hardcover-sync: not set up yet: run setup first."
        )
    con = state.connect(os.path.join(config.state_dir(), "state.db"))
    reader = accounts.local_reader(con)
    accounts.token_store = page.KeptToken(computer)
    try:
        if a.remove:
            accounts.clear_token(con, reader["name"])
            _one(OK, "Hardcover token removed. Syncing is back in dry run.")
            return
        if sys.stdin.isatty():
            import getpass

            print(f"Make a token with the permissions this tool needs:\n  {hardcover.NEW_TOKEN_URL}", file=sys.stderr)
            raw = getpass.getpass("Hardcover token: ")
        else:
            raw = sys.stdin.readline()
        token = hardcover.bare(raw)
        if not token:
            sys.exit("kobo-hardcover-sync: no token given.")
        try:
            who = hardcover.Client(token).whoami()
        except hardcover.HardcoverError as ex:
            sys.exit(f"kobo-hardcover-sync: {ex}. Nothing was stored.")
        accounts.set_token(con, reader["name"], token, str(who.get("username") or ""))
        del token, raw
        _one(OK, f"Stored. Hardcover knows you as @{who.get('username')}." if who.get("username") else "Stored.")
        assert computer.secret(HARDCOVER)
    finally:
        accounts.token_store = None
        con.close()


def _sync(a, computer) -> None:
    from .computer import runner

    if a.trigger:  # started by the plug-in trigger or the small app: one notification, there
        out = runner.sync(computer, trigger=a.trigger, verbose=a.verbose)
        if out.message:
            computer.notify(out.title, out.message)
        if not out.ok:
            sys.exit(1)
        return

    # By hand: each step as it finishes, then the books it was about.
    screen = term.Screen.of()
    width = len("Collection")

    def step(row: Row) -> None:
        screen.rows([row], label_width=width)
        sys.stdout.flush()

    screen.line()
    out = runner.sync(computer, verbose=a.verbose, on_step=step)
    if not out.ok:
        step(Row(FAIL, out.about, out.message))
        sys.exit(1)
    _books(screen, out.books, out.live)
    if out.closing:
        screen.line()
        screen.say(out.closing)


def _books(screen: term.Screen, books: list[dict], live: bool) -> None:
    """The books of a run, as lines of the reading log. Titles are shown
    here, to the person at the terminal, and written nowhere."""
    for went, heading in (
        ("sent", "Sent to Hardcover"),
        ("planned", "Would be sent to Hardcover (dry run)"),
        ("failed", "Not sent"),
    ):
        some = [b for b in books if b["went"] == went]
        if not some:
            continue
        screen.line()
        screen.heading(heading)
        for b in some[:SHOWN_BOOKS]:
            screen.book(b["title"], b["percent"], b["finished"], b["error"] or b["what"])
        if len(some) > SHOWN_BOOKS:
            screen.say(f"and {plural(len(some) - SHOWN_BOOKS, 'more book')}; the page lists them all.", indent=2, style=(term.DIM,))


def _status(a, computer) -> None:
    from .computer import config, runner
    from .computer.platform import HARDCOVER, KOBO_DB, UPLOAD
    from .engine import collection

    cfg = config.load()
    rows = []
    if not cfg.mode:
        rows.append(Row(FAIL, "Mode", "Not set up on this computer yet.", "Run `kobo-hardcover-sync setup`."))
    else:
        rows.append(Row(OK, "Mode", f"Server mode: uploads to {cfg.server}" if cfg.server else "Local mode: everything on this computer"))
    rows.append(Row(OK, "Folder", config.state_dir()))
    if cfg.mode == "local":
        con = state.connect(os.path.join(config.state_dir(), "state.db"))
        row = con.execute("select hardcover_live, hardcover_user, kobo_collection from reader where name = 'me'").fetchone()
        books = con.execute("select count(*), sum(mode = 'on' or (mode = 'auto' and history = 0)) from book where reader = 'me'").fetchone()
        con.close()
        if computer.secret(HARDCOVER):
            rows.append(Row(OK, "Token", f"Hardcover token present, kept in {computer.secret_place(HARDCOVER)}"))
        else:
            rows.append(Row(NOTE, "Token", "No Hardcover token yet", "`kobo-hardcover-sync token` stores one."))
        live = bool(row and row[0])
        rows.append(
            Row(
                OK if live else NOTE,
                "Sending",
                f"{'Live' if live else 'Dry run'}; {books[1] or 0} of {plural(books[0], 'book')} switched on",
            )
        )
        name = (row[2] if row else "") or ""
        rows.append(Row(OK if name else NOTE, "Collection", f"'{name}' on the Kobo" if name else "None on the Kobo"))
    elif cfg.mode:
        token = computer.secret(UPLOAD)
        rows.append(
            Row(OK, "Token", f"Upload token present; its hash is {_token_hash(token)}")
            if token
            else Row(FAIL, "Token", "No upload token", "Run `kobo-hardcover-sync setup` again.")
        )
        del token
    mount = computer.find_kobo()
    if not mount:
        rows.append(Row(NOTE, "Kobo", "Not found"))
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="khs-") as tmp:
                con = sqlite3.connect(runner.copy_database(os.path.join(mount, KOBO_DB), tmp))
                try:
                    version = con.execute("select version from DbVersion").fetchone()[0]
                finally:
                    con.close()
            tested = "tested" if version in collection.KNOWN_VERSIONS else "not tested yet: the collection will not be written"
            dev = kobo_db.device(mount)
            what = ", ".join(x for x in (dev.model, f"software {dev.software}" if dev.software else "") if x)
            rows.append(Row(OK, "Kobo", f"{mount}{' (' + what + ')' if what else ''}, database version {version} ({tested})"))
        except (OSError, sqlite3.Error, TypeError) as ex:
            rows.append(Row(WARN, "Kobo", f"{mount}, but its database could not be read ({ex})", "`kobo-hardcover-sync doctor` says more."))
    try:
        with open(os.path.join(config.state_dir(), "last-message.txt")) as fh:
            lines = [line.strip() for line in fh if line.strip()]
        rows.append(Row(OK, "Last sync", f"{lines[-1]}: {lines[0]}: {' '.join(lines[1:-1])}"))
    except (FileNotFoundError, IndexError):
        rows.append(Row(NOTE, "Last sync", "Nothing synced yet"))
    term.Screen.of().rows(rows)


def _doctor(a, computer) -> None:
    import platform as os_platform

    from . import doctor

    screen = term.Screen.of()
    screen.heading(f"Kobo Hardcover Sync {__version__}")
    screen.say(f"Python {os_platform.python_version()}, {os_platform.platform(terse=True)}", style=(term.DIM,))
    screen.line()
    checks = doctor.computer_checks(computer)
    doctor.show(checks, screen)
    if doctor.problems(checks):
        sys.exit(1)


def _open(a, computer) -> None:
    from .computer import config, page

    cfg = config.load()
    if not cfg.mode:
        sys.exit("kobo-hardcover-sync: not set up yet: run setup first.")
    computer.open_page(cfg.server or page.link())


def _uninstall(a, computer) -> None:
    from .computer import config
    from .computer.platform import HARDCOVER, UPLOAD

    server = config.load().server
    rows = [Row(OK, "", line) for line in computer.remove_trigger()]
    if a.purge:
        computer.delete_secret(UPLOAD)
        computer.delete_secret(HARDCOVER)
        shutil.rmtree(config.state_dir(), ignore_errors=True)
        rows.append(Row(OK, "", "State and tokens removed.", "Remove the device on the page under Settings, Devices." if server else ""))
    else:
        rows.append(
            Row(NOTE, "", f"State and tokens kept ({config.state_dir()}).", "`kobo-hardcover-sync uninstall --purge` removes them.")
        )
    term.Screen.of().rows(rows, label_width=0)


if __name__ == "__main__":
    main()
