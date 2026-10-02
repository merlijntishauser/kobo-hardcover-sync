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

kobo-hardcover-sync sync
    One sync now.

kobo-hardcover-sync status
    What is set up, and what it sees.

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

from . import __version__
from .engine import kobo_db, state
from .env import env


def main(argv: list[str] | None = None, computer=None) -> None:
    p = argparse.ArgumentParser(prog="kobo-hardcover-sync")
    p.add_argument("--version", action="version", version=f"kobo-hardcover-sync {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{setup,token,sync,status,open,uninstall,serve,import}")
    stp = sub.add_parser("setup", help="make this computer sync a plugged-in Kobo")
    stp.add_argument("--server", default="", help="the server's address, e.g. https://kobo.example.org")
    stp.add_argument("--local", action="store_true", help="everything on this computer, no server")
    stp.add_argument("--new-token", action="store_true", help="replace the upload token (the device must be added again)")
    stp.add_argument("--rebuild-app", action="store_true", help="rebuild the small app (it then needs its permission again)")
    stp.add_argument("--no-trigger", action="store_true", help="only the settings: you run `sync` yourself")
    tok = sub.add_parser("token", help="local mode: store your Hardcover token")
    tok.add_argument("--remove", action="store_true", help="forget the token (and go back to dry run)")
    sub.add_parser("page", help=argparse.SUPPRESS)  # what `open` starts in local mode
    syn = sub.add_parser("sync", help="one sync now")
    syn.add_argument("--trigger", default="", help=argparse.SUPPRESS)  # "mount": started by the plug-in trigger
    sub.add_parser("status", help="what is set up, and what it sees")
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
    {"setup": _setup, "sync": _sync, "status": _status, "open": _open, "uninstall": _uninstall, "token": _token}[a.cmd](a, computer)


def _serve(a) -> None:
    import uvicorn

    from .server import proxy

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

    digest = ""
    if cfg.server:
        token = computer.secret(UPLOAD)
        if a.new_token or not token:
            token = secrets.token_hex(32)
            computer.set_secret(UPLOAD, token)
            print("New upload token stored on this computer.")
        else:
            print("Keeping the existing upload token.")
        digest = _token_hash(token)
        del token

    if a.no_trigger:
        print("No trigger installed: run `kobo-hardcover-sync sync` with the Kobo plugged in.")
    else:
        command = _own_path()
        for line in computer.install_trigger(command, a.rebuild_app):
            print(line)
    print()
    if cfg.server:
        print(f"Server: {cfg.server}")
        print(f"This computer's hash (paste it at {cfg.server}/settings under Devices, unless it is there already):")
        print(digest)
    else:
        print("Local mode: everything happens on this computer.")
        print("Next: `kobo-hardcover-sync token` to store your Hardcover token, then plug in the Kobo.")
        print("`kobo-hardcover-sync open` shows your books; nothing goes to Hardcover until you go live under Settings.")


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
            print("Hardcover token removed. Syncing is back in dry run.")
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
        print(f"Stored. Hardcover knows you as @{who.get('username')}." if who.get("username") else "Stored.")
        assert computer.secret(HARDCOVER)
    finally:
        accounts.token_store = None
        con.close()


def _sync(a, computer) -> None:
    from .computer import runner

    out = runner.sync(computer, trigger=a.trigger)
    if out.message:
        if a.trigger:  # started by the plug-in trigger or the small app: tell the person there
            computer.notify(out.title, out.message)
        else:
            print(f"{out.title}: {out.message}")
    elif not a.trigger:
        print("Nothing new." if computer.find_kobo() else "No Kobo found: plug it in and tap Connect on the Kobo.")
    if not out.ok:
        sys.exit(1)


def _status(a, computer) -> None:
    from .computer import config, runner
    from .computer.platform import HARDCOVER, KOBO_DB, UPLOAD
    from .engine import collection

    cfg = config.load()
    print(f"Mode:    {'server, ' + cfg.server if cfg.server else cfg.mode or 'not set up'}")
    print(f"State:   {config.state_dir()}")
    if cfg.mode == "local":
        con = state.connect(os.path.join(config.state_dir(), "state.db"))
        row = con.execute("select hardcover_live, hardcover_user, kobo_collection from reader where name = 'me'").fetchone()
        books = con.execute("select count(*), sum(mode = 'on' or (mode = 'auto' and history = 0)) from book where reader = 'me'").fetchone()
        con.close()
        has = bool(computer.secret(HARDCOVER))
        place = f", kept in {computer.secret_place(HARDCOVER)}" if has else ""
        print(f"Token:   {'Hardcover token present' + place if has else 'no Hardcover token yet (kobo-hardcover-sync token)'}")
        print(f"Sending: {'live' if row and row[0] else 'dry run'}; {books[1] or 0} of {books[0]} books switched on")
        print(f"Collection on the Kobo: {(row[2] if row else '') or 'none'}")
    else:
        token = computer.secret(UPLOAD)
        print(f"Token:   {'present, hash ' + _token_hash(token) if token else 'none'}")
        del token
    mount = computer.find_kobo()
    if not mount:
        print("Kobo:    not found")
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
            print(f"Kobo:    {mount}{' (' + what + ')' if what else ''}, database version {version} ({tested})")
        except (OSError, sqlite3.Error, TypeError) as ex:
            print(f"Kobo:    {mount}, but its database could not be read ({ex})")
    try:
        with open(os.path.join(config.state_dir(), "last-message.txt")) as fh:
            lines = [line.strip() for line in fh if line.strip()]
        print(f"Last:    {lines[-1]}: {' '.join(lines[:-1])}")
    except (FileNotFoundError, IndexError):
        print("Last:    nothing synced yet")


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
    for line in computer.remove_trigger():
        print(line)
    if a.purge:
        computer.delete_secret(UPLOAD)
        computer.delete_secret(HARDCOVER)
        shutil.rmtree(config.state_dir(), ignore_errors=True)
        print("State and tokens removed." + (" Remove the device on the page under Settings, Devices." if server else ""))
    else:
        print(f"State and tokens kept ({config.state_dir()}); --purge removes them.")


if __name__ == "__main__":
    main()
