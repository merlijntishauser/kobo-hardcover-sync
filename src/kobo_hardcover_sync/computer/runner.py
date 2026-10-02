"""One sync, start to finish (docs/local-mode.md, "A sync, step by step").

Both modes copy the Kobo's database to a temporary folder first and keep
the collection on the Kobo at the end. In between, server mode sends the
server only what it reads; local mode imports the books here and runs the
same engine the server runs, with the Hardcover token from this computer's
secret store."""

from __future__ import annotations

import fcntl
import getpass
import gzip
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime

from ..engine import collection, job, kobo_db, state
from ..server import accounts
from . import config, remote
from .platform import HARDCOVER, KOBO_DB, UPLOAD, Computer

NAME = "Kobo Hardcover Sync"


@dataclass
class Outcome:
    ok: bool
    title: str = NAME
    message: str = ""  # "" = nothing worth telling


def log(text: str) -> None:
    os.makedirs(config.state_dir(), mode=0o700, exist_ok=True)
    with open(os.path.join(config.state_dir(), "agent.log"), "a") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")


def remember(out: Outcome) -> Outcome:
    """Keep the last thing told, for the small app that shows it on a click."""
    if out.message:
        with open(os.path.join(config.state_dir(), "last-message.txt"), "w") as fh:
            fh.write(f"{out.title}\n{out.message}\n\n{datetime.now():%-d %b %Y, %H:%M}\n")
    return out


def fingerprint(db: str) -> str:
    """SHA-256 of the Kobo's database as it is on the device (with its
    write-ahead log, if the Kobo left one)."""
    h = hashlib.sha256()
    wal = db + "-wal"
    for path in [db] + ([wal] if os.path.exists(wal) and os.path.getsize(wal) else []):
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
    return h.hexdigest()


def copy_database(db: str, folder: str) -> str:
    """A private copy to read from (with the write-ahead log, if the Kobo
    left one). The caller deletes the folder."""
    dst = os.path.join(folder, "KoboReader.sqlite")
    shutil.copyfile(db, dst)
    if os.path.exists(db + "-wal") and os.path.getsize(db + "-wal"):
        shutil.copyfile(db + "-wal", dst + "-wal")
    return dst


def sync(computer: Computer, cfg: config.Config | None = None, opener=None, trigger: str = "", hardcover_client=None) -> Outcome:
    """trigger "mount": started because some volume was mounted, so without
    a Kobo there is nothing to do. opener and hardcover_client let tests
    stand in for the network."""
    cfg = cfg or config.load()
    state_dir = config.state_dir()
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    if not cfg.server and not cfg.set_up:
        return Outcome(False, message="Not set up yet: run `kobo-hardcover-sync setup`.")
    mount = computer.find_kobo()
    if not mount and (cfg.server or trigger == "mount"):
        return Outcome(True)  # every volume that mounts starts us; most are not a Kobo
    lock = open(os.path.join(state_dir, "sync.lock"), "w")  # noqa: SIM115 (held until the end)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return Outcome(True)  # a sync is already running; it wins
        if cfg.server:
            return remember(_sync_to_server(computer, cfg, mount, state_dir, opener))
        return remember(_sync_here(computer, cfg, mount, state_dir, hardcover_client))
    finally:
        lock.close()


def _finish(computer: Computer, cfg: config.Config, mount: str | None, said: list[str], wrote: bool) -> Outcome:
    if mount and (said or wrote) and cfg.eject_after_sync:
        said.append("Ejected: safe to unplug." if computer.eject(mount) else "Could not eject; eject before unplugging.")
    elif wrote:
        said.append("Eject before unplugging.")
    return Outcome(True, "Kobo synced", " ".join(said))


def _keep_collection(db: str, copy: str, name: str, ids: list[str], state_dir: str, cfg: config.Config, said: list[str]) -> bool:
    """The collection on the Kobo, through the one module that writes to it:
    the one named `name` holds exactly `ids`; one made earlier under another
    name goes ("" = no collection wanted at all). True when it wrote."""
    where = os.path.join(state_dir, "collection")
    wrote = False
    try:
        gone = collection.remove_others(db, name, where, preflight_db=copy, allow_untested=cfg.allow_untested_kobo)
        if gone.wrote:
            wrote = True
            log(f"collections removed: {', '.join(gone.names)}")
            said += [f"Collection '{n}' removed." for n in gone.names]
        if name:
            r = collection.apply(db, name, ids, where, preflight_db=None if wrote else copy, allow_untested=cfg.allow_untested_kobo)
            log(r.line(name))
            if r.wrote:
                wrote = True
                said.append(f"Collection {r.line(name).removeprefix('collection ')}.")
    except collection.CollectionError as ex:
        log(f"collection not updated: {ex}")
        said.append(f"Collection not updated: {str(ex).split('. ')[0].rstrip('.')}.")
    return wrote


def _sync_here(computer: Computer, cfg: config.Config, mount: str | None, state_dir: str, client=None) -> Outcome:
    """Local mode: the books are imported here and the engine runs here."""
    db_path = os.path.join(state_dir, "state.db")
    con = state.connect(db_path)
    reader = accounts.local_reader(con, getpass.getuser())
    said, wrote, imported = [], False, False
    hash_file = os.path.join(state_dir, "last-import.sha256")
    with tempfile.TemporaryDirectory(prefix="khs-") as tmp:
        copy = db = None
        if mount:
            db = os.path.join(mount, KOBO_DB)
            try:
                seen = fingerprint(db)
                copy = copy_database(db, tmp)
            except OSError as ex:
                log(f"cannot read the Kobo's database: {ex}")
                return Outcome(False, message="Could not read the Kobo's database. Does the app have Full Disk Access?")
            try:
                with open(hash_file) as fh:
                    unchanged = fh.read().strip() == seen
            except FileNotFoundError:
                unchanged = False
            if unchanged:
                log("unchanged since last import, import skipped")
            else:
                try:
                    kobo = kobo_db.open_db(copy, allow_user_table=True)  # the copy never leaves this folder
                    try:
                        books = kobo_db.read_books(kobo)
                    finally:
                        kobo.close()
                except kobo_db.NotAKoboDatabase as ex:
                    log(f"not a Kobo database: {ex}")
                    return Outcome(False, "Kobo sync failed", "The Kobo's database could not be read.")
                result = state.import_books(con, reader["name"], kobo_db.device(mount).name, books, source="usb")
                with open(hash_file, "w") as fh:
                    fh.write(seen + "\n")
                log(f"imported: {result}")
                imported = True
                n = int(result.get("changed", 0)) + int(result.get("tracked_added", 0))
                if n:
                    said.append(f"{n} book(s) updated.")

        # Hardcover: the same run as on the server. Dry run until the reader goes live.
        token = computer.secret(HARDCOVER)
        if token or client:
            live = bool(reader["hardcover_live"])
            r = job.run(db_path, reader["name"], live, client=client, token=token)
            log(f"hardcover: {r}")
            if r.get("status") == "failed":
                said.append(f"{r.get('fatal', 'The sync to Hardcover failed')}.")
            elif live:
                said += [
                    f"{r[k]} {text}"
                    for k, text in (("sent", "sent to Hardcover."), ("adopted", "taken over from Hardcover."), ("errors", "failed."))
                    if r.get(k)
                ]
            elif r.get("planned"):
                said.append(f"{r['planned']} would be sent to Hardcover (dry run).")
            if r.get("uncertain"):
                said.append(f"{r['uncertain']} need a match on the page.")
        elif imported:
            said.append("No Hardcover token yet: add one on the page.")

        name = (reader["kobo_collection"] or "").strip()
        if mount:
            ids = [
                b["content_id"]
                for b in con.execute("select * from book where reader=? order by last_read desc", (reader["name"],))
                if state.syncs(b)
            ]
            wrote = _keep_collection(db, copy, name, ids, state_dir, cfg, said)
            if wrote:
                try:
                    with open(hash_file, "w") as fh:  # our own write is not a reason to import again
                        fh.write(fingerprint(db) + "\n")
                except OSError:
                    pass
    con.close()
    return _finish(computer, cfg, mount, said, wrote)


def _sync_to_server(computer: Computer, cfg: config.Config, mount: str, state_dir: str, opener) -> Outcome:
    db = os.path.join(mount, KOBO_DB)
    token = computer.secret(UPLOAD)
    if not token:
        log("no upload token in the secret store")
        return Outcome(False, message="No upload token on this computer; run `kobo-hardcover-sync setup` again.")
    server = remote.Server(cfg.server, token, opener)
    hash_file = os.path.join(state_dir, "last-upload.sha256")
    try:
        seen = fingerprint(db)
    except OSError as ex:
        log(f"cannot read the Kobo's database: {ex}")
        return Outcome(False, message="Could not read the Kobo's database. Does the app have Full Disk Access?")
    try:
        with open(hash_file) as fh:
            unchanged = fh.read().strip() == seen
    except FileNotFoundError:
        unchanged = False

    said = []
    with tempfile.TemporaryDirectory(prefix="khs-") as tmp:
        try:
            copy = copy_database(db, tmp)
        except OSError as ex:
            log(f"copy failed: {ex}")
            return Outcome(False, message="Could not copy the Kobo's database. Does the app have Full Disk Access?")
        if unchanged:
            log("unchanged since last upload, upload skipped")
        else:
            try:
                small = os.path.join(tmp, "upload.sqlite")
                kobo_db.export_for_upload(copy, small)
                with open(small, "rb") as fi, gzip.open(small + ".gz", "wb", compresslevel=9) as fo:
                    shutil.copyfileobj(fi, fo)
                result = server.upload(small + ".gz")
            except kobo_db.NotAKoboDatabase as ex:
                log(f"not a Kobo database: {ex}")
                return Outcome(False, "Kobo sync failed", "The Kobo's database could not be read.")
            except remote.ServerError as ex:
                log(f"upload failed: {ex}")
                return Outcome(False, "Kobo sync failed", str(ex))
            with open(hash_file, "w") as fh:
                fh.write(seen + "\n")
            log(f"uploaded: {result}")
            said.append(f"{int(result.get('changed', 0)) + int(result.get('tracked_added', 0))} book(s) updated.")

        # The collection on the Kobo: checked on every plug-in.
        wrote = False
        try:
            wanted = server.collection() or ("", [])  # no name set on the server: no collection wanted
        except remote.ServerError as ex:
            log(f"collection request failed: {ex}")
            wanted = None  # not known: leave the Kobo as it is
        if wanted is not None:
            wrote = _keep_collection(db, copy, wanted[0], wanted[1], state_dir, cfg, said)
            if wrote:
                with open(hash_file, "w") as fh:  # our own write is not a reason to upload again
                    fh.write(fingerprint(db) + "\n")

    return _finish(computer, cfg, mount, said, wrote)
