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

kobo-hardcover-sync token [--code] [--paste] [--remove] [--json]
    Local mode: connect to Hardcover. You approve on Hardcover in the
    browser (--code: with a code to compare instead), and the connection
    is kept in the Keychain. (The page's Settings does the same.) --paste
    takes a token you made on Hardcover yourself instead; --remove ends
    the connection. --json says each step as a line of JSON: where to
    approve, then who signed in, for the Mac app.

kobo-hardcover-sync sync [--verbose] [--steps]
    One sync now. It says each step as it finishes, and then names the
    books that went to Hardcover, each with how far it is read. Those
    titles are shown in the terminal and written nowhere. --verbose also
    shows the log while it runs. --steps says each step, and then the
    outcome, as a line of JSON, and names no book: what the Mac app reads.

kobo-hardcover-sync status [--json]
    What is set up, and what it sees. Quick, and never uses the network.

kobo-hardcover-sync doctor [--json]
    Check everything a sync depends on, and say what to do about what is
    wrong. Changes nothing; asks Hardcover (or your server) one question.
    Ends with status 1 when something stops syncing from working.

kobo-hardcover-sync history [--json]
    The last syncs on this computer, newest first: when, what started it,
    and what it said. The last hundred are kept, without book titles.

kobo-hardcover-sync settings [--set NAME=VALUE] [--json]
    This computer's settings; --set changes one that is true or false
    (eject_after_sync, verbose_log, allow_untested_kobo,
    check_for_updates; in local mode also live, which ends the dry run
    and needs a connection to Hardcover). Mode and server change with
    `setup`.

kobo-hardcover-sync update [--json]
    Ask GitHub now whether there is a newer version, also when the Mac
    app's daily look is switched off. It only says so; Homebrew and pip
    update the tool themselves.

Every --json answer, and every line of sync --steps, carries "schema": 1,
raised when a field changes meaning; the Mac app reads them.

kobo-hardcover-sync books [--json] [--covers]
    Your books, newest read first, each with what the next sync does with
    it on Hardcover; in server mode the server's, for this computer's
    reader. --covers first fetches the covers this computer does not have
    yet, from Kobo or the server. --json for the Mac app: every
    book with its row and its Details, the filters it is in, and the
    page's words for them.

kobo-hardcover-sync book ID [--sync MODE] [--state STATE [--date DATE]] [--search TEXT] [--pick BOOK] [--remove] [--not-now] [--json]
    One book, and the changes the page makes to it: whether it
    syncs (auto, on, off), its State, a match (--search looks on
    Hardcover for the books it could be, --pick takes one of them), and
    --remove, which takes it off your Hardcover shelf now; --not-now puts
    it aside as the tip for a month. With --json it
    answers the book as books --json has it. `books --sync MODE --filter
    F [--search TEXT] [--expect N]` sets Sync for every book of a filter,
    as Set all does on the page; with --expect, only when that is still N
    books.

kobo-hardcover-sync open [--book ID]
    Open the page (local mode: it is started for the occasion). --book
    opens it at that book.

kobo-hardcover-sync export [--output FILE [--every-sync]] [--stop]
    Your reading as JSON: every book the Kobo has seen touched, how far,
    the dates, minutes per day, and what syncs to Hardcover. To standard
    output, or to FILE (readable by you only). For a database or a
    dashboard of your own; Hardcover is not needed for it. --every-sync
    writes FILE again after every sync (local mode); --stop ends that.

kobo-hardcover-sync webhook [URL [--token]] [--test] [--remove]
    Local mode: after every sync that read something new from the Kobo,
    POST it as JSON to URL, an address of your own (docs/webhook.md says
    what is in it). --token asks for a Bearer token to send with it, kept
    in the Keychain. A test is sent first; nothing is stored unless it
    gets a 2xx answer. Without arguments: where it goes now.

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

kobo-hardcover-sync export --reader NAME [--output FILE]
    The same export, on the server, for one reader.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from urllib.parse import quote

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
            ("token", "Connect to Hardcover (when everything runs on this computer)"),
            ("sync", "One sync now"),
            ("status", "What is set up, and what it sees"),
            ("doctor", "Check everything a sync depends on; changes nothing"),
            ("history", "The last syncs, and what each did"),
            ("settings", "This computer's settings; --set NAME=VALUE changes one"),
            ("books", "Your books, and what the next sync does with each"),
            ("book", "One book, and changing how it syncs"),
            ("open", "Open the page with your books"),
            ("export", "Your reading as JSON, for a database of your own"),
            ("webhook", "POST each sync to an address of your own"),
            ("uninstall", "Remove the trigger"),
        ),
    ),
    (
        "On a server",
        (
            ("serve", "Run the server: the page and the upload endpoint"),
            ("import", "Import a KoboReader.sqlite by hand"),
            ("export", "A reader's reading as JSON (--reader NAME)"),
        ),
    ),
)
SHOWN_BOOKS = 12  # a run by hand names this many books, and counts the rest
SCHEMA = 1  # of every JSON answer (--json, sync --steps): what the Mac app reads; raised when a field changes meaning
SETTABLE = ("eject_after_sync", "verbose_log", "allow_untested_kobo", "check_for_updates")  # settings --set


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
    sub = p.add_subparsers(
        dest="cmd",
        required=True,
        metavar="{setup,token,sync,status,doctor,history,settings,update,open,export,webhook,uninstall,serve,import}",
    )
    stp = sub.add_parser("setup", help="make this computer sync a plugged-in Kobo")
    stp.add_argument("--server", default="", help="the server's address, e.g. https://kobo.example.org")
    stp.add_argument("--local", action="store_true", help="everything on this computer, no server")
    stp.add_argument("--new-token", action="store_true", help="replace the upload token (the device must be added again)")
    stp.add_argument("--rebuild-app", action="store_true", help="rebuild the small app (it then needs its permission again)")
    stp.add_argument("--no-trigger", action="store_true", help="only the settings: you run `sync` yourself")
    stp.add_argument("--check", action="store_true", help="first ask the server whether it answers; change nothing if not")
    tok = sub.add_parser("token", help="local mode: store your Hardcover token")
    tok.add_argument("--remove", action="store_true", help="forget the token (and go back to dry run)")
    tok.add_argument("--paste", action="store_true", help="paste a token made on Hardcover, instead of connecting there")
    tok.add_argument("--code", action="store_true", help="connect with a code to compare, instead of in the browser")
    tok.add_argument("--start-over", action="store_true", help="put your books on the shelf of the account you are connected to now")
    tok.add_argument("--json", action="store_true", help="each step as a line of JSON, for the Mac app")
    sub.add_parser("page")  # what `open` starts in local mode; no help text, so it is not listed
    syn = sub.add_parser("sync", help="one sync now")
    syn.add_argument("--trigger", default="", help=argparse.SUPPRESS)  # "mount": the plug-in trigger; "app": Sync now in the Mac app
    syn.add_argument("--verbose", action="store_true", help="also show the log while it runs: a line per book and per request")
    syn.add_argument("--steps", action="store_true", help="each step, then the outcome, as a line of JSON (for the Mac app)")
    sta = sub.add_parser("status", help="what is set up, and what it sees")
    sta.add_argument("--json", action="store_true", help="as JSON")
    doc = sub.add_parser("doctor", help="check everything a sync depends on; changes nothing")
    doc.add_argument("--json", action="store_true", help="as JSON")
    his = sub.add_parser("history", help="the last syncs, and what each did")
    his.add_argument("--json", action="store_true", help="as JSON")
    sts = sub.add_parser("settings", help="this computer's settings")
    sts.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help=f"change one: {', '.join(SETTABLE)}; true or false")
    sts.add_argument("--json", action="store_true", help="as JSON")
    upd = sub.add_parser("update", help="ask now whether there is a newer version")
    upd.add_argument("--json", action="store_true", help="as JSON")
    bks = sub.add_parser("books", help="local mode: your books, and what the next sync does with each")
    bks.add_argument("--json", action="store_true", help="as JSON")
    bks.add_argument("--covers", action="store_true", help="first fetch the covers not on this computer yet")
    bks.add_argument("--sync", choices=state.MODES, help="set Sync for every book of --filter and --search, as Set all on the page")
    bks.add_argument("--filter", default="all", help="with --sync: one of the page's filters (all, on, needs_match, ...)")
    bks.add_argument("--search", default="", metavar="TEXT", help="with --sync: only the books whose title or author holds TEXT")
    bks.add_argument("--expect", type=int, metavar="N", help="with --sync: change nothing unless that is N books")
    bk = sub.add_parser("book", help="local mode: one book, and changing how it syncs")
    bk.add_argument("id", help="the book's id, as books --json gives it")
    bk.add_argument("--sync", choices=state.MODES, help="whether it syncs")
    bk.add_argument("--state", choices=state.STATES, help="its State; the Kobo's own is kobo")
    bk.add_argument("--date", default="", metavar="YYYY-MM-DD", help="with --state finished or rereading: since when")
    bk.add_argument("--search", default="", metavar="TEXT", help="look on Hardcover for the books it could be")
    bk.add_argument("--pick", default="", metavar="BOOK", help="its match: one of the books it could be, by its Hardcover id")
    bk.add_argument("--remove", action="store_true", help="take it off your Hardcover shelf, and stop syncing it")
    bk.add_argument("--not-now", action="store_true", help="not the tip for a month: books --json gives another")
    bk.add_argument("--json", action="store_true", help="as JSON")
    opn = sub.add_parser("open", help="open the page")
    opn.add_argument("--book", default="", metavar="ID", help="at this book (its id in books --json)")
    exp = sub.add_parser("export", help="your reading as JSON, for a database or dashboard of your own")
    exp.add_argument("--output", default="", metavar="FILE", help="write to FILE (readable by you only) instead of the screen")
    exp.add_argument("--reader", default="", metavar="NAME", help="on the server: the reader to export")
    exp.add_argument("--every-sync", action="store_true", help="with --output: write the file again after every sync")
    exp.add_argument("--stop", action="store_true", help="stop writing it after every sync (the file stays)")
    hook = sub.add_parser("webhook", help="local mode: POST each sync to an address of your own")
    hook.add_argument("url", nargs="?", default="", help="the address, https://...")
    hook.add_argument("--token", action="store_true", help="ask for a Bearer token to send with it")
    hook.add_argument("--test", action="store_true", help="send a test now")
    hook.add_argument("--remove", action="store_true", help="stop sending, and forget the address and the token")
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

    if a.cmd == "export":
        return _export(a)
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
        "history": _history,
        "settings": _settings,
        "update": _update,
        "books": _books_list,
        "book": _book,
        "open": _open,
        "uninstall": _uninstall,
        "token": _token,
        "webhook": _webhook,
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
    known = False
    if a.check and server:
        from .computer import remote

        try:
            known = remote.Server(server, computer.secret(UPLOAD)).knows_me() and not a.new_token
        except remote.ServerError as ex:
            unlike = f" Is {server} the address of a kobo-hardcover-sync server?" if ex.status else ""
            sys.exit(f"kobo-hardcover-sync: {ex}{unlike} Nothing was changed.")
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
    if cfg.server and known:
        screen.say(f"1. {cfg.server} knows this computer already. This is its hash:", indent=2, hang=3)
        screen.line(f"     {screen.style(digest, term.CYAN)}")
        screen.say("2. Plug in the Kobo and tap Connect on it.", indent=2, hang=3)
    elif cfg.server:
        screen.say(f"1. Paste this computer's hash at {cfg.server}/settings under Devices, unless it is there already:", indent=2, hang=3)
        screen.line(f"     {screen.style(digest, term.CYAN)}")
        screen.say("2. Plug in the Kobo and tap Connect on it.", indent=2, hang=3)
    elif computer.in_app:  # the app opens the page next; there is no terminal
        screen.say("1. Connect to Hardcover on the page, under Settings.", indent=2, hang=3)
        screen.say("2. Plug in the Kobo and tap Connect on it.", indent=2, hang=3)
        screen.say("3. Pick your books on the page. Nothing goes to Hardcover until you go live under Settings.", indent=2, hang=3)
    else:
        screen.say("1. `kobo-hardcover-sync token` connects to Hardcover.", indent=2, hang=3)
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
    from .engine import hardcover, oauth
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

    def told(text: str, user: str = "") -> None:
        if a.json:
            _json({"done": {"ok": True, "user": user, "message": text}})
        else:
            _one(OK, text)

    try:
        if a.remove:
            accounts.clear_token(con, reader["name"])
            told("Disconnected from Hardcover. Syncing is back in dry run.")
            return
        if a.start_over:
            bound = state.hardcover_account(con, reader["name"])
            state.start_over(con, reader["name"])
            was = f" on the shelf of @{bound[1]}" if bound and bound[1] else ""
            told(f"Started over: what was put{was} is forgotten here. The next sync puts your books on the connected account's shelf.")
            return
        # At a terminal or in the Mac app (--json), and with an app to connect through: sign in on
        # Hardcover. A token that is piped in, or asked for with --paste, is taken as before.
        if oauth.available() and (sys.stdin.isatty() or a.json) and not a.paste:
            connect = _connect_browser if oauth.loopback() and not a.code else _connect
            token, keep = connect(computer, oauth, a.json)
        else:
            if sys.stdin.isatty() and not a.json:
                import getpass

                print(f"Make a token with the permissions this tool needs:\n  {hardcover.NEW_TOKEN_URL}", file=sys.stderr)
                raw = getpass.getpass("Hardcover token: ")
            else:
                raw = sys.stdin.readline()
            token = keep = hardcover.bare(raw)
            del raw
        if not token:
            sys.exit("kobo-hardcover-sync: no token given.")
        try:
            who = hardcover.Client(token).whoami()
        except hardcover.HardcoverError as ex:
            sys.exit(f"kobo-hardcover-sync: {ex}. Nothing was stored.")
        accounts.set_token(con, reader["name"], keep, str(who.get("username") or ""))
        connected = oauth.unpack(keep) is not None
        del token, keep
        done = "Connected" if connected else "Stored"
        user = str(who.get("username") or "")
        told(f"{done}. Hardcover knows you as @{user}." if user else f"{done}.", user)
        assert computer.secret(HARDCOVER)
    finally:
        accounts.token_store = None
        con.close()


BACK_IN_THE_TERMINAL = (
    "<!doctype html><html lang=en><meta charset=utf-8><title>Kobo Hardcover Sync</title>"
    '<body style="font:16px/1.5 system-ui,sans-serif;margin:3rem auto;max-width:34rem;padding:0 1rem">'
    "<h1 style=font-size:1.4rem>Kobo Hardcover Sync</h1><p>{}</p></body></html>"
)


def _connect_browser(computer, oauth, as_json: bool = False) -> tuple[str, str]:
    """Sign in on Hardcover in the browser (engine/oauth.py): Hardcover sends
    the browser back to a moment's address on this computer, and the tool
    takes the code from there. Returns the token to use now and the
    connection to keep. as_json: where to approve as a line of JSON, for
    the Mac app, instead of words for a terminal."""
    back = "Kobo Hardcover Sync" if computer.in_app else "the terminal"
    import threading
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    answer: dict = {}
    came = threading.Event()

    class Back(BaseHTTPRequestHandler):
        def log_message(self, *a):  # the query carries the code: nothing of it goes anywhere
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != oauth.CALLBACK or came.is_set():
                self.send_response(404)
                self.end_headers()
                return
            answer.update(urllib.parse.parse_qsl(u.query))
            refused = answer.get("error") == "access_denied"
            body = BACK_IN_THE_TERMINAL.format(
                f"The sign-in was refused on Hardcover. {back[:1].upper() + back[1:]} says what next."
                if refused
                else f"Back in {back}: it finishes the connection. You can close this tab."
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            came.set()

    server = HTTPServer(("127.0.0.1", 0), Back)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        sign_in = oauth.browser_start(server.server_address[1])
        if as_json:
            _json({"open": sign_in.url, "code": ""})
        else:
            _tell_browser(sign_in.url)
        computer.open_page(sign_in.url)
        if not came.wait(600):
            sys.exit("kobo-hardcover-sync: the sign-in took too long. Nothing was stored.")
        got = oauth.browser_finish(sign_in, answer)
    except oauth.OAuthError as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}. Nothing was stored. `kobo-hardcover-sync token --code` connects with a code instead.")
    finally:
        server.shutdown()
        server.server_close()
    return got.access, got.pack()


def _tell_browser(url: str) -> None:
    screen = term.Screen.of()
    screen.heading("Connect to Hardcover")
    screen.say("Approve on Hardcover, in the browser that is being opened for you. If none opens, go to:", indent=2)
    screen.line(f"  {screen.style(url, term.CYAN)}")
    screen.line()
    screen.say(
        "Waiting for your approval. Ctrl-C stops; `kobo-hardcover-sync token --code` connects with a code instead.",
        style=(term.DIM,),
    )
    sys.stdout.flush()


def _connect(computer, oauth, as_json: bool = False) -> tuple[str, str]:
    """Sign in on Hardcover by the device flow: show where to approve,
    wait until it is done. Returns the token to use now and the connection
    to keep."""
    screen = term.Screen.of()
    try:
        device = oauth.start()
    except oauth.OAuthError as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}. `kobo-hardcover-sync token --paste` takes a pasted token instead.")
    if as_json:
        _json({"open": device.link_with_code, "code": device.user_code})
        computer.open_page(device.link_with_code)
        return _collect(device, oauth)
    screen.heading("Connect to Hardcover")
    screen.say("1. Open this address (it is being opened for you) and approve:", indent=2, hang=3)
    screen.line(f"     {screen.style(device.link_with_code, term.CYAN)}")
    screen.say(f"2. Check that Hardcover shows this code: {screen.style(device.user_code, term.BOLD)}", indent=2, hang=3)
    screen.line()
    screen.say("Waiting for your approval. Ctrl-C stops.", style=(term.DIM,))
    sys.stdout.flush()
    computer.open_page(device.link_with_code)
    return _collect(device, oauth)


def _collect(device, oauth) -> tuple[str, str]:
    """Ask Hardcover, at the pace it asks for, until the sign-in is approved."""
    wait = device.interval
    while True:
        time.sleep(wait)
        try:
            got = oauth.collect(dataclasses.replace(device, interval=wait))
        except oauth.OAuthError as ex:
            sys.exit(f"kobo-hardcover-sync: {ex}. Nothing was stored.")
        if not isinstance(got, int):
            return got.access, got.pack()
        wait = got


def _sync(a, computer) -> None:
    from .computer import runner

    if a.steps:  # the Mac app's window: each step as it finishes, then the outcome, a line of JSON each

        def step(row: Row) -> None:
            _json({"step": row.what, "state": row.state, "text": row.text})

        out = runner.sync(computer, trigger=a.trigger, verbose=a.verbose, on_step=step)
        _json({"done": {"ok": out.ok, "title": out.title, "message": out.message}})
        if computer.in_app and a.trigger:
            from .computer import update

            update.now_and_then()
        if not out.ok:
            sys.exit(1)
        return

    if a.trigger:  # started by the plug-in trigger or the small app: one notification, there
        out = runner.sync(computer, trigger=a.trigger, verbose=a.verbose)
        if out.message:
            computer.notify(out.title, out.message)
        if computer.in_app:  # after the notification, so a sync is never slower for it
            from .computer import update

            update.now_and_then()
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


def _json(data: dict) -> None:
    print(json.dumps({"schema": SCHEMA, **data}), flush=True)


def _last_sync() -> dict | None:
    """The newest sync: from the history, or, before there was one, from
    the last thing a sync said (last-message.txt: title, message, when)."""
    from .computer import config, history

    kept = history.syncs()
    if kept:
        return kept[0]
    try:
        with open(os.path.join(config.state_dir(), "last-message.txt")) as fh:
            lines = [line.strip() for line in fh if line.strip()]
        at = datetime.strptime(lines[-1], "%d %b %Y, %H:%M").astimezone().isoformat(timespec="seconds")
    except (OSError, IndexError, ValueError):
        return None
    return {"at": at, "trigger": "", "ok": True, "title": lines[0], "message": " ".join(lines[1:-1])}


def _book_counts() -> dict | None:
    """The books in counts (booklist.summary), before the first sync None."""
    from . import booklist
    from .computer import config

    path = os.path.join(config.state_dir(), "state.db")
    if not os.path.exists(path):
        return None
    con = state.connect(path)
    try:
        return booklist.summary(con, "me")
    finally:
        con.close()


_STARTED = {"mount": "plugging in the Kobo", "app": "Sync now in the app", "hand": "hand"}


def _status(a, computer) -> None:
    from .computer import config, runner
    from .computer.platform import HARDCOVER, KOBO_DB, UPLOAD
    from .engine import collection

    cfg = config.load()
    if a.json:  # what the Mac app's window opens with: local files only, so it is quick
        return _json(
            {
                "version": __version__,
                "mode": cfg.mode,
                "server": cfg.server,
                "folder": config.state_dir(),
                "kobo": computer.find_kobo(),
                "last_sync": _last_sync(),
                "syncing": runner.running(),
                "books": _book_counts() if cfg.mode == "local" else None,  # in server mode they are on the server
            }
        )
    rows = []
    if not cfg.mode:
        rows.append(Row(FAIL, "Mode", "Not set up on this computer yet.", "Run `kobo-hardcover-sync setup`."))
    else:
        rows.append(Row(OK, "Mode", f"Server mode: uploads to {cfg.server}" if cfg.server else "Local mode: everything on this computer"))
    rows.append(Row(OK, "Folder", config.state_dir()))
    if started := runner.running():
        rows.append(Row(NOTE, "Sync", f"A sync is running now, started by {_STARTED.get(started, started)}."))
    if cfg.mode == "local":
        con = state.connect(os.path.join(config.state_dir(), "state.db"))
        row = con.execute("select hardcover_live, hardcover_user, kobo_collection from reader where name = 'me'").fetchone()
        books = con.execute(
            "select count(*), sum(mode = 'on' or (mode = 'auto' and history = 0)) from reader_book where reader = 'me'"
        ).fetchone()
        con.close()
        if computer.secret(HARDCOVER):
            rows.append(Row(OK, "Token", f"Hardcover token present, kept in {computer.secret_place(HARDCOVER)}"))
        else:
            rows.append(Row(NOTE, "Token", "Not connected to Hardcover yet", "`kobo-hardcover-sync token` connects."))
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
        if cfg.export_to:
            rows.append(Row(OK, "Export", f"Written to {cfg.export_to} after every sync"))
        if cfg.webhook_url:
            rows.append(Row(OK, "Webhook", f"POST to {cfg.webhook_url} after a sync that reads the Kobo"))
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

    if a.json:
        checks = doctor.computer_checks(computer, by_hand=not computer.in_app)  # the app reads the Kobo itself, not a terminal
        _json(
            {
                "version": __version__,
                "summary": doctor.summary(checks),
                "problems": doctor.problems(checks),
                "checks": [
                    {"group": group, "what": c.what, "state": c.state, "found": c.found, "todo": c.todo}
                    for group, some in doctor.grouped(checks)
                    for c in some
                ],
            }
        )
        if doctor.problems(checks):
            sys.exit(1)
        return
    screen = term.Screen.of()
    screen.heading(f"Kobo Hardcover Sync {__version__}")
    screen.say(f"Python {os_platform.python_version()}, {os_platform.platform(terse=True)}", style=(term.DIM,))
    screen.line()
    checks = doctor.computer_checks(computer)
    doctor.show(checks, screen)
    if doctor.problems(checks):
        sys.exit(1)


def _history(a, computer) -> None:
    from .computer import history

    kept = history.syncs()
    if a.json:
        return _json({"syncs": kept})
    if not kept:
        return term.Screen.of().rows([Row(NOTE, "History", "No syncs kept yet: plug in the Kobo.")])
    rows = []
    for s in kept:
        when = datetime.fromisoformat(s["at"]).astimezone().strftime("%-d %b %H:%M")
        said = f"{s['title']}: {s['message']}" if s["message"] else "Nothing new."
        rows.append(Row(OK if s["ok"] else FAIL, when, f"{history.STARTED_BY.get(s['trigger'], s['trigger'])}. {said}"))
    term.Screen.of().rows(rows)


def _settings(a, computer) -> None:
    from .computer import config
    from .computer.platform import HARDCOVER, UPLOAD

    cfg = config.load()
    live = None  # the switch from dry run to sending, kept with the books (on the server in server mode)
    if a.set:
        if not cfg.mode:
            sys.exit("kobo-hardcover-sync: not set up yet: run setup first.")
        for change in a.set:
            name, _, value = change.partition("=")
            if name not in (*SETTABLE, "live"):
                sys.exit(f"kobo-hardcover-sync: {name or change!r} cannot be set here; these can: {', '.join(SETTABLE)}, live.")
            if value.lower() not in ("true", "false"):
                sys.exit(f"kobo-hardcover-sync: {name} is true or false, not {value!r}.")
            if name == "live":
                live = value.lower() == "true"
                # As the page: going live asks Hardcover nothing, but needs a connection (the server checks its own).
                if cfg.mode == "local" and live and not computer.secret(HARDCOVER):
                    sys.exit("kobo-hardcover-sync: connect to Hardcover first: nothing could be sent without it.")
            else:
                setattr(cfg, name, value.lower() == "true")
        config.save(cfg)
    reader = None
    if cfg.mode == "local":
        from .server import accounts

        con = state.connect(os.path.join(config.state_dir(), "state.db"))
        row = accounts.local_reader(con)
        if live is not None:
            con.execute("update reader set hardcover_live=? where name=?", (int(live), row["name"]))
            con.commit()
            row = accounts.local_reader(con)
        reader = (bool(row["hardcover_live"]), row["hardcover_user"] or "")
        con.close()
    connected = bool(computer.secret(HARDCOVER)) if cfg.mode == "local" else False
    if cfg.mode == "server" and live is not None:  # the server answers for this computer's reader, and refuses without a connection
        from .computer import remote

        try:
            there = _books_server(computer).app("POST", "live", {"live": live})
        except remote.ServerError as ex:
            sys.exit(f"kobo-hardcover-sync: {ex}")
        reader, connected = (there["live"], there["user"]), there["connected"]
    values = {name: getattr(cfg, name) for name in SETTABLE} | {"export_to": cfg.export_to, "webhook_url": cfg.webhook_url}
    token = computer.secret(UPLOAD) if cfg.mode == "server" else ""
    found = {
        "mode": cfg.mode,
        "server": cfg.server,
        "upload_token_hash": _token_hash(token) if token else "",
        "hardcover_connected": connected,
        "hardcover_user": reader[1] if reader else "",
        "live": reader[0] if reader else False,  # local mode: sending to Hardcover, not a dry run
        "settings": values,
    }
    del token
    if a.json:
        return _json(found)
    rows = [Row(OK, name, str(value).lower() if isinstance(value, bool) else value or "(none)") for name, value in values.items()]
    if reader:
        rows.append(Row(OK, "live", "true: sending to Hardcover" if reader[0] else "false: a dry run, nothing is sent"))
    if found["upload_token_hash"]:
        rows.insert(0, Row(OK, "upload token", f"its hash is {found['upload_token_hash']}"))
    term.Screen.of().rows(rows)


def _update(a, computer) -> None:
    from .computer import update

    found = update.now()
    if a.json:
        return _json(found)
    if found["problem"] and not found["latest"]:
        row = Row(WARN, "Version", f"This is {found['version']}. {found['problem']}")
    elif found["newer"]:
        upgrade = "Download it there." if computer.in_app else "`brew upgrade` or `pip install -U kobo-hardcover-sync` gets it."
        row = Row(NOTE, "Version", f"{found['latest']} is out; this is {found['version']}: {found['link']}", upgrade)
    else:
        row = Row(OK, "Version", f"{found['version']} is the newest version.")
    term.Screen.of().rows([row])


def _open(a, computer) -> None:
    from .computer import config, page

    cfg = config.load()
    if not cfg.mode:
        sys.exit("kobo-hardcover-sync: not set up yet: run setup first.")
    if a.book and not cfg.server:  # the page lands on the book: its place in the list, then its row
        return computer.open_page(f"{page.link()}&at={quote(a.book, safe='')}#b-{quote(a.book, safe='')}")
    computer.open_page(cfg.server or page.link())


def _books_list(a, computer) -> None:
    from . import appbooks, booklist
    from .computer.platform import HARDCOVER

    if (server := _books_server(computer)) is not None:
        return _server_books_list(a, server)
    folder, con = _local_books()
    try:
        if a.sync:  # Set all: every book of a filter and search, as on the page
            appbooks.set_all(con, "me", a.sync, a.filter, a.search, a.expect)
    except appbooks.Refused as ex:
        if con:
            con.close()
        sys.exit(f"kobo-hardcover-sync: {ex}")
    if a.covers and con:  # the thumbnails the page and the app show; one that Kobo does not have is asked for again in a week
        from .web import covers

        for r in booklist.query_rows(con, "me", "", "all", "last_read"):
            covers.cover_path(folder, r["image_id"])
    found = appbooks.listing(con, "me", lambda r: _cover(folder, r), lambda: bool(computer.secret(HARDCOVER)))
    if con:
        con.close()
    _books_said(a, found)


def _books_said(a, found: dict) -> None:
    """books' answer: JSON for the app, or in a terminal each title with its status line."""
    if a.json:
        return _json(found)
    screen = term.Screen.of()
    if not found["books"]:
        screen.say("No books yet: nothing was read from a Kobo so far.")
    for b in found["books"]:
        screen.book(b["title"], b["percent"], b["finished"], b["status"]["text"])


def _book(a, computer) -> None:
    """One book: what it is, and the changes the page makes to it."""
    from . import appbooks
    from .computer import page
    from .engine import hardcover

    if (server := _books_server(computer)) is not None:
        return _book_said(a, _server_book(a, server))
    folder, con = _local_books()

    def client(**kw):
        return hardcover.Client(page.KeptToken(computer).usable(), **kw)

    try:
        appbooks.change(
            con,
            "me",
            a.id,
            client,
            search=a.search,
            pick=a.pick,
            sync=a.sync or "",
            state_=a.state or "",
            date=a.date,
            remove=a.remove,
            not_now=a.not_now,
        )
        found = appbooks.one(con, "me", a.id, lambda r: _cover(folder, r))
    except (appbooks.Refused, hardcover.HardcoverError) as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}")
    finally:
        if con:
            con.close()
    _book_said(a, found)


def _book_said(a, found: dict) -> None:
    if a.json:
        return _json(found)
    book = found["book"]
    screen = term.Screen.of()
    screen.book(book["title"], book["percent"], book["finished"], book["status"]["text"])
    for label, value in book["details"]["kobo"] + book["details"]["hardcover"]:
        screen.say(f"{label}: {value}", indent=2)


def _local_books():
    """Local mode's folder and its database (None before a Kobo was read); refused before setup."""
    from .computer import config

    cfg = config.load()
    if cfg.mode != "local":
        sys.exit("kobo-hardcover-sync: not set up yet: run setup first.")
    folder = config.state_dir()
    path = os.path.join(folder, "state.db")
    return folder, state.connect(path) if os.path.exists(path) else None


def _books_server(computer):
    """Server mode: the server this computer sends to, which answers for its
    reader (/api/app/); None in local mode and before setup."""
    from .computer import config, remote
    from .computer.platform import UPLOAD

    cfg = config.load()
    if cfg.mode != "server":
        return None
    token = computer.secret(UPLOAD)
    if not token:
        sys.exit("kobo-hardcover-sync: this computer has no upload token: run setup again.")
    return remote.Server(cfg.server, token)


def _server_books_list(a, server) -> None:
    from .computer import remote

    try:
        if a.sync:
            server.app("POST", "books/sync", {"sync": a.sync, "filter": a.filter, "search": a.search, "expect": a.expect})
        found = server.app("GET", "books")
        for b in found["books"]:
            b["cover"] = _server_cover(server, b["cover"], a.covers)
    except remote.ServerError as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}")
    _books_said(a, found)


def _server_book(a, server) -> dict:
    from .computer import remote

    change = {
        "id": a.id,
        "sync": a.sync or "",
        "state": a.state or "",
        "date": a.date,
        "search": a.search,
        "pick": a.pick,
        "remove": a.remove,
        "not_now": a.not_now,
    }
    try:
        found = server.app("POST", "book", change)
    except remote.ServerError as ex:
        sys.exit(f"kobo-hardcover-sync: {ex}")
    found["book"]["cover"] = _server_cover(server, found["book"]["cover"], False)
    return found


def _server_cover(server, path: str, fetch: bool) -> str:
    """The file of a cover the server has (path, as its answer gives it),
    kept on this computer; fetched only with fetch (books --covers). One
    the server does not have is asked for again in a week."""
    from .computer import config, remote

    if not path:
        return ""
    folder = os.path.join(config.state_dir(), "server-covers")
    file = os.path.join(folder, hashlib.sha256(path.encode()).hexdigest()[:40] + ".jpg")
    none = file[:-4] + ".none"
    if os.path.exists(file):
        return file
    if not fetch or (os.path.exists(none) and time.time() - os.path.getmtime(none) < 7 * 86400):
        return ""
    try:
        data = server.cover(path)
    except remote.ServerError:  # not now; the next books --covers asks again
        return ""
    os.makedirs(folder, exist_ok=True)
    if data is None:
        with open(none, "w"):
            pass
        return ""
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as out:
        out.write(data)
    os.replace(out.name, file)
    return file


def _cover(folder: str, r) -> str:
    """The book's cached thumbnail (web/covers.py), or "" while there is none."""
    from .web import covers

    if not r["image_id"] or not covers.ID_OK.match(r["image_id"]):
        return ""
    path = os.path.join(folder, "covers", f"{r['image_id']}.jpg")
    return path if os.path.exists(path) else ""


def _export(a) -> None:
    from .computer import config
    from .engine import export
    from .server import accounts
    from .server.stats import stats

    if a.stop or a.every_sync:
        cfg = config.load()
        if cfg.mode != "local":
            sys.exit("kobo-hardcover-sync: --every-sync is for local mode, where the sync runs on this computer.")
        if a.stop:
            was, cfg.export_to = cfg.export_to, ""
            config.save(cfg)
            term.Screen.of().rows(
                [Row(OK, "Export", f"No longer written after a sync; {was} is left as it is." if was else "Was not written after a sync.")]
            )
            return
        if not a.output or a.output == "-":
            sys.exit("kobo-hardcover-sync: --every-sync needs --output FILE: the file to keep up to date.")
    if a.reader:  # on the server, where `import` puts things too
        path, reader = os.path.join(env("DATA", "/data"), "state.db"), a.reader
    else:
        cfg = config.load()
        if cfg.mode == "server":
            sys.exit(f"kobo-hardcover-sync: your books are on {cfg.server}; export there, with --reader.")
        if not cfg.mode:
            sys.exit("kobo-hardcover-sync: not set up yet: run setup first.")
        path, reader = os.path.join(config.state_dir(), "state.db"), accounts.LOCAL_READER
    if not os.path.exists(path):  # connect() would make an empty one
        sys.exit("kobo-hardcover-sync: nothing to export yet: plug in the Kobo for a first sync.")
    con = state.connect(path)
    try:
        if not con.execute("select 1 from reader where name=?", (reader,)).fetchone():
            sys.exit(f"kobo-hardcover-sync: no reader called {reader}." if a.reader else "kobo-hardcover-sync: nothing to export yet.")
        data = export.document(con, reader, f"kobo-hardcover-sync {__version__}", stats(con, reader))
    finally:
        con.close()
    if not a.output or a.output == "-":
        sys.stdout.write(export.text(data))
        return
    # Titles and reading times are nobody else's business: the file is the reader's alone.
    target = os.path.abspath(os.path.expanduser(a.output))
    export.write(target, data)
    rows = [Row(OK, "Export", f"{plural(len(data['books']), 'book')} written to {a.output}")]
    if a.every_sync:
        cfg = config.load()
        cfg.export_to = target
        config.save(cfg)
        rows.append(Row(OK, "Every sync", "Written again after every sync. `kobo-hardcover-sync export --stop` stops that."))
    term.Screen.of().rows(rows)


def _webhook(a, computer) -> None:
    from .computer import config, webhook
    from .computer.platform import WEBHOOK
    from .engine import export
    from .server import accounts
    from .server.stats import stats

    cfg = config.load()
    if cfg.mode != "local":
        sys.exit(
            "kobo-hardcover-sync: the webhook is for local mode, where the sync runs on this computer."
            if cfg.server
            else "kobo-hardcover-sync: not set up yet: run setup first."
        )
    if a.remove:
        computer.delete_secret(WEBHOOK)
        cfg.webhook_url = ""
        config.save(cfg)
        _one(OK, "No webhook any more: the address and its token are forgotten.")
        return
    url = a.url.strip() or (cfg.webhook_url if a.test or a.token else "")
    if not url and (a.test or a.token):
        sys.exit("kobo-hardcover-sync: no webhook yet: `kobo-hardcover-sync webhook https://...` sets one.")
    if not url:
        if cfg.webhook_url:
            token = "with a token" if computer.secret(WEBHOOK) else "without a token"
            _one(OK, f"After every sync that reads the Kobo: POST to {cfg.webhook_url}, {token}.")
        else:
            _one(NOTE, "No webhook.", "`kobo-hardcover-sync webhook https://...` sets one.")
        return
    if why := webhook.problem(url):
        sys.exit(f"kobo-hardcover-sync: {why}")
    token = computer.secret(WEBHOOK) if not a.url else ""  # a new address gets no old address's token
    if a.token:
        if sys.stdin.isatty():
            import getpass

            raw = getpass.getpass("Token (sent as Authorization: Bearer ...): ")
        else:
            raw = sys.stdin.readline()
        token = raw.strip().removeprefix("Bearer ").strip()
        del raw
        if not token:
            sys.exit("kobo-hardcover-sync: no token given.")
    path = os.path.join(config.state_dir(), "state.db")
    con = state.connect(path)
    try:
        reader = accounts.local_reader(con)["name"]
        dev = con.execute("select device from device where reader=? order by last_import desc limit 1", (reader,)).fetchone()
        device = dev["device"] if dev else ""
        # A test looks like a sync with nothing changed: the present state, and event "test".
        body = export.sync_event(
            con, reader, device, export.before(con, reader, device), f"kobo-hardcover-sync {__version__}", stats(con, reader), "test"
        )
    finally:
        con.close()
    try:
        status = webhook.post(url, token, body)
    except webhook.WebhookError as ex:
        sys.exit(f"kobo-hardcover-sync: the test was not taken: {ex}. Nothing was stored." if a.url else f"kobo-hardcover-sync: {ex}.")
    if a.url or a.token:
        try:
            if token:
                computer.set_secret(WEBHOOK, token)
            else:
                computer.delete_secret(WEBHOOK)
        except ValueError:
            sys.exit("kobo-hardcover-sync: this token has characters the secret store cannot keep. Nothing was stored.")
        cfg.webhook_url = url
        config.save(cfg)
    del token
    rows = [Row(OK, "Test", f"{webhook.host(url)} answered {status}")]
    if a.url or a.token:
        rows.append(Row(OK, "Webhook", f"Every sync that reads something new from the Kobo is POSTed to {url}."))
    term.Screen.of().rows(rows)


def _uninstall(a, computer) -> None:
    from .computer import config
    from .computer.platform import HARDCOVER, UPLOAD, WEBHOOK

    server = config.load().server
    rows = [Row(OK, "", line) for line in computer.remove_trigger()]
    if a.purge:
        computer.delete_secret(UPLOAD)
        computer.delete_secret(HARDCOVER)
        computer.delete_secret(WEBHOOK)
        shutil.rmtree(config.state_dir(), ignore_errors=True)
        rows.append(Row(OK, "", "State and tokens removed.", "Remove the device on the page under Settings, Devices." if server else ""))
    else:
        rows.append(
            Row(NOTE, "", f"State and tokens kept ({config.state_dir()}).", "`kobo-hardcover-sync uninstall --purge` removes them.")
        )
    term.Screen.of().rows(rows, label_width=0)


if __name__ == "__main__":
    main()
