"""One sync, start to finish (docs/local-mode.md, "A sync, step by step").

Both modes copy the Kobo's database to a temporary folder first and keep
the collection on the Kobo at the end. In between, server mode sends the
server only what it reads; local mode imports the books here and runs the
same engine the server runs, with the Hardcover token from this computer's
secret store."""

from __future__ import annotations

import errno
import fcntl
import getpass
import gzip
import hashlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime

from .. import ISSUES, logs
from ..engine import collection, hardcover, job, kobo_db, state
from ..server import accounts
from ..term import FAIL, NOTE, OK, WARN, Row, plural
from . import config, page, remote
from .platform import KOBO_DB, UPLOAD, Computer

NAME = "Kobo Hardcover Sync"
FAILED = "Kobo sync failed"
LOG_FILE = "agent.log"
log = logging.getLogger(__name__)

# What reading a file says when the device under it went away.
GONE = (errno.ENOENT, errno.ENODEV, errno.ENXIO, errno.EIO, errno.ENOTDIR, errno.ESTALE)
DAMAGED = (
    "The Kobo's database could not be read: it is damaged, or the Kobo was still writing it. Unplug the Kobo, let it "
    "start, and plug it in again. If it stays, `kobo-hardcover-sync doctor` shows more."
)


@dataclass
class Outcome:
    """What a sync has to say. title and message are the notification. The
    rest is for someone watching a run by hand: the steps were told as they
    happened (on_step), and these come at the end."""

    ok: bool
    title: str = NAME
    message: str = ""  # "" = nothing worth telling
    about: str = "Sync"  # what a failure is about: the label of its line
    books: list = field(default_factory=list)  # what went, or would go, to Hardcover (job.run)
    live: bool = False
    closing: str = ""  # the last word: eject, or safe to unplug


def unreadable(computer: Computer, ex: OSError, by_hand: bool) -> str:
    """Why the Kobo's database could not be read or copied, and what to do
    about it. Nothing has been written to the Kobo at that point."""
    if isinstance(ex, PermissionError):
        return computer.cannot_read(by_hand)
    if ex.errno in GONE:
        return "The Kobo was unplugged during the sync. Nothing on it was changed. Plug it in again."
    return f"The Kobo's database could not be read ({ex.strerror or ex}). Plug the Kobo in again; `kobo-hardcover-sync doctor` shows more."


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


def sync(
    computer: Computer,
    cfg: config.Config | None = None,
    opener=None,
    trigger: str = "",
    hardcover_client=None,
    verbose: bool = False,
    on_step=None,
) -> Outcome:
    """trigger "mount": started because some volume was mounted, so without
    a Kobo there is nothing to do. verbose: this run logs every book, and
    shows the log while it runs. on_step: called with a term.Row as each
    step finishes, for a terminal that is watching. opener and
    hardcover_client let tests stand in for the network."""
    step = on_step or (lambda row: None)
    cfg = cfg or config.load()
    state_dir = config.state_dir()
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    logs.to_file(os.path.join(state_dir, LOG_FILE), verbose=verbose or cfg.verbose_log, echo=verbose)
    if not cfg.server and not cfg.set_up:
        return Outcome(False, message="Not set up yet: run `kobo-hardcover-sync setup`.")
    mount = computer.find_kobo()
    if not mount and (cfg.server or trigger == "mount"):
        step(Row(NOTE, "Kobo", "No Kobo found: plug it in and tap Connect on the Kobo."))
        return Outcome(True)  # every volume that mounts starts us; most are not a Kobo
    lock = open(os.path.join(state_dir, "sync.lock"), "w")  # noqa: SIM115 (held until the end)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            step(Row(NOTE, "Sync", "Another sync is running; it carries on."))
            return Outcome(True)  # a sync is already running; it wins
        log.debug("sync started (%s), Kobo: %s", f"by {trigger}" if trigger else "by hand", _describe(mount))
        try:
            if cfg.server:
                out = _sync_to_server(computer, cfg, mount, state_dir, opener, by_hand=not trigger, step=step)
            else:
                out = _sync_here(computer, cfg, mount, state_dir, hardcover_client, by_hand=not trigger, step=step)
        except Exception as ex:  # nothing this tool knows what to say about
            log.exception("sync stopped by something unexpected")
            out = Outcome(
                False,
                FAILED,
                f"Something went wrong that this tool did not expect ({ex.__class__.__name__}). The details are in "
                f"{os.path.join(state_dir, LOG_FILE)}. Please report it: {ISSUES}",
            )
        if out.message:
            log.log(logging.INFO if out.ok else logging.ERROR, "said: %s: %s", out.title, out.message)
        return remember(out)
    finally:
        lock.close()


def _describe(mount: str | None) -> str:
    if not mount:
        return "none"
    dev = kobo_db.device(mount)
    return ", ".join(x for x in (mount, dev.model, f"software {dev.software}" if dev.software else "") if x)


def _model(mount: str) -> str:
    return kobo_db.device(mount).model or "Kobo"


def _finish(computer: Computer, cfg: config.Config, mount: str | None, said: list[str], wrote: bool) -> Outcome:
    closing = ""
    if mount and (said or wrote) and cfg.eject_after_sync:
        closing = "Ejected: safe to unplug." if computer.eject(mount) else "Could not eject; eject before unplugging."
    elif wrote:
        closing = "Eject before unplugging."
    return Outcome(True, "Kobo synced", " ".join([*said, closing] if closing else said), closing=closing)


def _collection_step(step, name: str, told: list[str]) -> None:
    """The collection's line for a terminal, from what the notification says about it."""
    if not told:
        step(
            Row(OK, "Collection", f"'{name}' is up to date")
            if name
            else Row(NOTE, "Collection", "None wanted: nothing is written to the Kobo")
        )
        return
    text = " ".join(t.removeprefix("Collection ") for t in told)
    step(Row(WARN if "not updated" in text else OK, "Collection", text[:1].upper() + text[1:]))


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
            log.info("collections removed: %s", ", ".join(gone.names))
            said += [f"Collection '{n}' removed." for n in gone.names]
        if name:
            r = collection.apply(db, name, ids, where, preflight_db=None if wrote else copy, allow_untested=cfg.allow_untested_kobo)
            log.info(r.line(name))
            if r.wrote:
                wrote = True
                said.append(f"Collection {r.line(name).removeprefix('collection ')}.")
    except collection.CollectionError as ex:
        log.warning("collection not updated: %s", ex)
        said.append(f"Collection not updated: {str(ex).split('. ')[0].rstrip('.')}.")
    return wrote


def _sync_here(
    computer: Computer, cfg: config.Config, mount: str | None, state_dir: str, client=None, by_hand: bool = False, step=lambda row: None
) -> Outcome:
    """Local mode: the books are imported here and the engine runs here."""
    db_path = os.path.join(state_dir, "state.db")
    con = state.connect(db_path)
    reader = accounts.local_reader(con, getpass.getuser())
    said, wrote, imported = [], False, False
    books, live = [], False
    hash_file = os.path.join(state_dir, "last-import.sha256")
    with tempfile.TemporaryDirectory(prefix="khs-") as tmp:
        copy = db = None
        if not mount:
            step(Row(NOTE, "Kobo", "Not plugged in: only Hardcover is brought up to date"))
        else:
            db = os.path.join(mount, KOBO_DB)
            try:
                seen = fingerprint(db)
                copy = copy_database(db, tmp)
            except OSError as ex:
                log.error("cannot read the Kobo's database: %s", ex)
                return Outcome(False, message=unreadable(computer, ex, by_hand), about="Kobo")
            try:
                with open(hash_file) as fh:
                    unchanged = fh.read().strip() == seen
            except FileNotFoundError:
                unchanged = False
            if unchanged:
                log.info("unchanged since last import, import skipped")
                step(Row(OK, "Kobo", f"{_model(mount)}: nothing new since the last sync"))
            else:
                try:
                    kobo = kobo_db.open_db(copy, allow_user_table=True)  # the copy never leaves this folder
                    try:
                        on_kobo = kobo_db.read_books(kobo)
                    finally:
                        kobo.close()
                except kobo_db.NotAKoboDatabase as ex:
                    log.error("not a Kobo database: %s", ex)
                    return Outcome(False, FAILED, DAMAGED, about="Kobo")
                result = state.import_books(con, reader["name"], kobo_db.device(mount).name, on_kobo, source="usb")
                with open(hash_file, "w") as fh:
                    fh.write(seen + "\n")
                log.info("imported: %s", result)
                imported = True
                n = int(result.get("changed", 0)) + int(result.get("tracked_added", 0))
                if n:
                    said.append(f"{plural(n, 'book')} updated.")
                step(Row(OK, "Kobo", f"{_model(mount)}: {plural(n, 'book')} updated" if n else f"{_model(mount)}: read, nothing changed"))

        # Hardcover: the same run as on the server. Dry run until the reader goes live.
        ended = False
        try:
            token = page.KeptToken(computer).usable()  # an OAuth connection is renewed here when it is about to run out
        except hardcover.HardcoverError as ex:
            token, ended = "", True
            job.could_not_start(db_path, reader["name"], bool(reader["hardcover_live"]), str(ex))
            said.append(f"{ex}.")
            step(Row(FAIL, "Hardcover", said[-1]))
        if ended:
            pass  # said above: the connection to Hardcover cannot be used
        elif token or client:
            live = bool(reader["hardcover_live"])
            r = job.run(db_path, reader["name"], live, client=client, token=token)
            books = r.get("books", [])
            if r.get("status") == "failed":
                said.append(f"{r.get('fatal', 'The sync to Hardcover failed')}.")
                step(Row(FAIL, "Hardcover", said[-1]))
            elif live:
                said += [
                    f"{r[k]} {text}"
                    for k, text in (("sent", "sent to Hardcover."), ("adopted", "taken over from Hardcover."), ("errors", "failed."))
                    if r.get(k)
                ]
                did = [f"{r[k]} {text}" for k, text in (("sent", "sent"), ("adopted", "taken over"), ("errors", "failed")) if r.get(k)]
                step(Row(WARN if r.get("errors") else OK, "Hardcover", ", ".join(did) if did else "Up to date: nothing to send"))
            elif r.get("planned"):
                said.append(f"{r['planned']} would be sent to Hardcover (dry run).")
                step(Row(NOTE, "Hardcover", f"Dry run: {r['planned']} would be sent"))
            else:
                step(Row(NOTE, "Hardcover", "Dry run: nothing to send"))
            if r.get("uncertain"):
                said.append(f"{r['uncertain']} need a match on the page.")
                step(
                    Row(
                        WARN,
                        "Matches",
                        f"{plural(r['uncertain'], 'book')} {'needs' if r['uncertain'] == 1 else 'need'} a match on the page",
                    )
                )
        else:
            if imported:
                said.append("No Hardcover token yet: add one on the page.")
            step(Row(NOTE, "Hardcover", "No token yet: add one on the page"))

        name = (reader["kobo_collection"] or "").strip()
        if mount:
            ids = [
                b["content_id"]
                for b in con.execute("select * from book where reader=? order by last_read desc", (reader["name"],))
                if state.syncs(b)
            ]
            before = len(said)
            wrote = _keep_collection(db, copy, name, ids, state_dir, cfg, said)
            _collection_step(step, name, said[before:])
            if wrote:
                try:
                    with open(hash_file, "w") as fh:  # our own write is not a reason to import again
                        fh.write(fingerprint(db) + "\n")
                except OSError:
                    pass
    con.close()
    out = _finish(computer, cfg, mount, said, wrote)
    out.books, out.live = books, live
    return out


def _sync_to_server(
    computer: Computer, cfg: config.Config, mount: str, state_dir: str, opener, by_hand: bool = False, step=lambda row: None
) -> Outcome:
    db = os.path.join(mount, KOBO_DB)
    token = computer.secret(UPLOAD)
    if not token:
        log.error("no upload token in the secret store")
        return Outcome(False, message="No upload token on this computer; run `kobo-hardcover-sync setup` again.", about="Setup")
    server = remote.Server(cfg.server, token, opener)
    hash_file = os.path.join(state_dir, "last-upload.sha256")
    try:
        seen = fingerprint(db)
    except OSError as ex:
        log.error("cannot read the Kobo's database: %s", ex)
        return Outcome(False, message=unreadable(computer, ex, by_hand), about="Kobo")
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
            log.error("cannot copy the Kobo's database: %s", ex)
            return Outcome(False, message=unreadable(computer, ex, by_hand), about="Kobo")
        step(Row(OK, "Kobo", _model(mount)))
        if unchanged:
            log.info("unchanged since last upload, upload skipped")
            step(Row(OK, "Upload", f"Nothing new for {server.host} since the last upload"))
        else:
            try:
                small = os.path.join(tmp, "upload.sqlite")
                kobo_db.export_for_upload(copy, small)
                with open(small, "rb") as fi, gzip.open(small + ".gz", "wb", compresslevel=9) as fo:
                    shutil.copyfileobj(fi, fo)
                result = server.upload(small + ".gz")
            except kobo_db.NotAKoboDatabase as ex:
                log.error("not a Kobo database: %s", ex)
                return Outcome(False, FAILED, DAMAGED, about="Kobo")
            except remote.ServerError as ex:
                log.error("upload failed: %s", ex)
                return Outcome(False, FAILED, str(ex), about="Upload")
            with open(hash_file, "w") as fh:
                fh.write(seen + "\n")
            log.info("uploaded: %s", result)
            n = int(result.get("changed", 0)) + int(result.get("tracked_added", 0))
            said.append(f"{plural(n, 'book')} updated.")
            step(Row(OK, "Upload", f"Sent to {server.host}: {plural(n, 'book')} updated"))

        # The collection on the Kobo: checked on every plug-in.
        wrote = False
        try:
            wanted = server.collection() or ("", [])  # no name set on the server: no collection wanted
        except remote.ServerError as ex:
            log.warning("collection request failed: %s", ex)
            wanted = None  # not known: leave the Kobo as it is
            step(Row(WARN, "Collection", f"Left as it is: {server.host} could not be asked which books belong in it"))
        if wanted is not None:
            before = len(said)
            wrote = _keep_collection(db, copy, wanted[0], wanted[1], state_dir, cfg, said)
            _collection_step(step, wanted[0], said[before:])
            if wrote:
                with open(hash_file, "w") as fh:  # our own write is not a reason to upload again
                    fh.write(fingerprint(db) + "\n")

    return _finish(computer, cfg, mount, said, wrote)
