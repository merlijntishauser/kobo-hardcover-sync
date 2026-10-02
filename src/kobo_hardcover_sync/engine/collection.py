"""Keep ONE collection on a Kobo equal to a list of books.

This is the only code in kobo-hardcover-sync that writes to the device.

Rules:
  - It only ever touches the collection it created itself, remembered by
    its Shelf id in <state_dir>. A collection with the same name that it
    did not create is left alone, and it stops.
  - Before anything else, a gate: the database version and the tables it
    is about to write must be ones this code knows. Otherwise it stops and
    says what it found. Nothing is written, not even a backup.
  - Nothing is written when the collection already matches.
  - Before a write, the whole database is copied to <state_dir>/backups
    (the last 3 are kept).
  - One transaction. Rows look like the Kobo's own (Shelf: Type UserTag,
    _IsDeleted 0, _IsVisible 1; items: _IsDeleted 0). _IsSynced 0 tells the
    Kobo the row is new to it.
  - Books that are not on this Kobo are skipped. So are ids that are not
    Kobo book ids (sideloaded books have file paths as ids).
  - The collection is this tool's: its name is the one asked for, and it
    holds exactly the books asked for. A collection it made earlier under
    another name is taken off the Kobo again (remove_others).
  - After the write it looks again: the collection must hold what was
    asked for, on a Kobo that is still there.

<state_dir> keeps the layout of the shell script this replaced
(collection-id-<hash of the name>, backups/), so a collection made back
then is still "ours".

Seen working on a real Kobo: 2026-10-01, database version 222.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import os
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

# DbVersion.version values this code has been seen working against, with the
# Kobo software version of the device it was seen on.
KNOWN_VERSIONS = {222: "6.0.274403"}

# What the write statements below name. A database without one of these is
# refused, whatever its version.
NEEDED = {
    "Shelf": (
        "CreationDate",
        "Id",
        "InternalName",
        "LastModified",
        "Name",
        "Type",
        "_IsDeleted",
        "_IsVisible",
        "_IsSynced",
        "_SyncTime",
        "LastAccessed",
    ),
    "ShelfContent": ("ShelfName", "ContentId", "DateModified", "_IsDeleted", "_IsSynced"),
    "content": ("ContentID", "ContentType"),
}
WRITTEN = ("Shelf", "ShelfContent")
ID_OK = re.compile(r"^[A-Za-z0-9-]{8,64}$")  # Kobo book ids are uuids
SHELF_ID_OK = re.compile(r"^[0-9a-f-]{36}$")
BACKUPS_KEPT = 3
NAME_MAX = 60

UNTESTED_HOW = 'To try it anyway, see "The collection on the Kobo" in the README.'
IN_USE = "Close other programs that read the Kobo (Calibre, the Kobo desktop app) and plug it in again."

# For tests: called inside the transaction just before COMMIT, and right
# after it. A real interruption looks like one of these raising or dying.
_before_commit = None
_after_commit = None


class CollectionError(Exception):
    """The collection was not brought up to date. `backup` is the copy made
    before a write was attempted, or "" when it never came to a write."""

    def __init__(self, message: str, backup: str = ""):
        super().__init__(message)
        self.backup = backup


class UnsupportedKobo(CollectionError):
    """The gate: this database is not one the code knows how to write to."""

    def __init__(self, message: str, version: int | None = None):
        super().__init__(message)
        self.version = version


class NotOurs(CollectionError):
    """A collection of that name exists and was not made by this tool."""


class KoboGone(CollectionError):
    """The Kobo's database is not there (any more)."""


@dataclass(frozen=True)
class Result:
    action: str  # unchanged | not created | created | updated | removed | absent
    books: int = 0
    added: int = 0
    removed: int = 0
    backup: str = ""
    names: tuple = ()  # remove_others: the collections that were taken off

    @property
    def wrote(self) -> bool:
        return self.action in ("created", "updated", "removed")

    def line(self, name: str) -> str:
        """One line for the log and the notification."""
        if self.action == "unchanged":
            return f"collection '{name}': already up to date"
        if self.action == "not created":
            return f"collection '{name}': no books to put in it, not created"
        if self.action == "removed":
            return f"collection '{name}': removed"
        if self.action == "absent":
            return f"collection '{name}': nothing to remove"
        return f"collection '{name}': {self.books} books (+{self.added}, -{self.removed})"


# ---------- the gate ----------
def check(con: sqlite3.Connection, allow_untested: bool = False) -> int:
    """The database version, if this code may write to this database.
    Raises UnsupportedKobo otherwise. Reads only.

    allow_untested lets a version through that nobody has tried yet; it
    never lets through a database that lacks what the statements need."""
    nothing = "Nothing was written to the Kobo."
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    if "DbVersion" not in tables:
        raise UnsupportedKobo(f"This does not look like a Kobo database: it has no DbVersion table. {nothing}")
    rows = con.execute("select version from DbVersion").fetchall()
    if len(rows) != 1 or not isinstance(rows[0][0], int):
        raise UnsupportedKobo(f"The Kobo database does not say which version it is. {nothing}")
    version = rows[0][0]
    for table, needed in NEEDED.items():
        if table not in tables:
            raise UnsupportedKobo(f"Kobo database version {version} has no {table} table. {nothing}", version)
        cols = {r[1]: r for r in con.execute(f"pragma table_info({table})")}
        missing = [c for c in needed if c not in cols]
        if missing:
            raise UnsupportedKobo(f"Kobo database version {version}: the {table} table has no {', '.join(missing)}. {nothing}", version)
        if table in WRITTEN:
            # A column that must be filled in and that this code does not know about.
            unknown = [c for c, r in cols.items() if c not in needed and r[3] and r[4] is None]
            if unknown:
                raise UnsupportedKobo(
                    f"Kobo database version {version}: the {table} table needs {', '.join(unknown)}, which is new to "
                    f"kobo-hardcover-sync. {nothing}",
                    version,
                )
    triggers = [
        r[0] for r in con.execute("select name from sqlite_master where type='trigger' and lower(tbl_name) in ('shelf', 'shelfcontent')")
    ]
    if triggers:
        raise UnsupportedKobo(
            f"Kobo database version {version} has triggers on its collections ({', '.join(triggers)}), which is new to "
            f"kobo-hardcover-sync. {nothing}",
            version,
        )
    if version not in KNOWN_VERSIONS and not allow_untested:
        tested = ", ".join(f"{v}, Kobo software {fw}" for v, fw in sorted(KNOWN_VERSIONS.items()))
        raise UnsupportedKobo(
            f"This Kobo's software has not been tested with kobo-hardcover-sync yet (its database is version {version}; "
            f"tested: {tested}). {nothing} The collection on the Kobo stays as it is; syncing to Hardcover is not affected. "
            f"{UNTESTED_HOW}",
            version,
        )
    return version


# ---------- helpers ----------
def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > NAME_MAX or any(ord(ch) < 32 for ch in name):
        raise CollectionError(f"A collection name is 1 to {NAME_MAX} characters on one line.")
    return name


def _idfile(state_dir: str, name: str) -> str:
    return os.path.join(state_dir, "collection-id-" + hashlib.sha256(name.encode()).hexdigest()[:12])


def _own_id(state_dir: str, name: str) -> str:
    try:
        with open(_idfile(state_dir, name)) as fh:
            own = fh.read().strip()
    except FileNotFoundError:
        return ""
    if not SHELF_ID_OK.match(own):
        raise CollectionError("The remembered collection id is damaged; nothing was written to the Kobo.")
    return own


def _open(db_path: str) -> sqlite3.Connection:
    if not os.path.isfile(db_path):
        raise KoboGone("The Kobo was unplugged before the collection could be written. Nothing was written; plug it in again.")
    try:
        con = sqlite3.connect(f"file:{quote(db_path)}?mode=rw", uri=True, timeout=5, isolation_level=None)
        con.execute("select count(*) from sqlite_master").fetchone()
    except sqlite3.DatabaseError as ex:
        if _busy(ex):
            raise CollectionError(f"The Kobo's database is in use by another program; nothing was written. {IN_USE}") from ex
        raise CollectionError(f"The Kobo's database could not be opened ({ex}); nothing was written.") from ex
    return con


def _busy(ex: Exception) -> bool:
    return "locked" in str(ex) or "busy" in str(ex)


def _wanted(con: sqlite3.Connection, ids) -> None:
    """A temporary table `want` with the well-formed ids (it lives in the
    connection's temporary database, not in the Kobo's file)."""
    con.execute("create temp table if not exists want(id text primary key)")
    con.execute("delete from want")
    con.executemany("insert or ignore into want values (?)", [(i,) for i in ids if ID_OK.match(i or "")])


def _diff(con: sqlite3.Connection, name: str) -> tuple[int, int]:
    """(to add, to remove): wanted books on this Kobo that are not in the
    collection, and books in it that are not wanted."""
    add = con.execute(
        """select count(*) from want w join content c on c.ContentID = w.id and c.ContentType = 6
           where not exists (select 1 from ShelfContent s where s.ShelfName = ? and s.ContentId = w.id and s._IsDeleted = 0)""",
        (name,),
    ).fetchone()[0]
    remove = con.execute(
        "select count(*) from ShelfContent s where s.ShelfName = ? and s._IsDeleted = 0 and s.ContentId not in (select id from want)",
        (name,),
    ).fetchone()[0]
    return add, remove


def _members(con: sqlite3.Connection, name: str) -> int:
    return con.execute("select count(*) from ShelfContent where ShelfName = ? and _IsDeleted = 0", (name,)).fetchone()[0]


def _existing(con: sqlite3.Connection, name: str, own: str) -> str:
    """The id of the live collection of that name, "" if there is none.
    Raises NotOurs when there is one that this tool did not make."""
    row = con.execute("select Id from Shelf where Name = ? and _IsDeleted = 0 limit 1", (name,)).fetchone()
    existing = row[0] if row else ""
    if existing and existing != own:
        raise NotOurs(f"A collection named '{name}' already exists on this Kobo and was not made by kobo-hardcover-sync: left alone.")
    return existing


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _backup(con: sqlite3.Connection, state_dir: str) -> str:
    """The whole database, as it is now, gzipped under <state_dir>/backups."""
    d = os.path.join(state_dir, "backups")
    os.makedirs(d, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    plain = os.path.join(d, f"KoboReader-{stamp}.sqlite")
    # Two writes in the same second: number them on, never reusing a name.
    same = [re.fullmatch(rf"KoboReader-{stamp}(?:-(\d+))?\.sqlite\.gz", f) for f in os.listdir(d)]
    if any(same):
        n = max(int(m.group(1) or 1) for m in same if m) + 1
        plain = os.path.join(d, f"KoboReader-{stamp}-{n}.sqlite")
    try:
        dst = sqlite3.connect(plain)
        with contextlib.closing(dst):
            con.backup(dst)
        with open(plain, "rb") as fi, gzip.open(plain + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
    except (OSError, sqlite3.Error) as ex:
        with contextlib.suppress(OSError):
            os.unlink(plain + ".gz")
        raise CollectionError(f"No backup could be made ({ex}), so nothing was written to the Kobo.") from ex
    finally:
        with contextlib.suppress(OSError):
            os.unlink(plain)
    # Oldest first, by when they were written (names made in the same second do not sort by age).
    made = [os.path.join(d, f) for f in os.listdir(d) if f.startswith("KoboReader-") and f.endswith(".sqlite.gz")]
    for f in sorted(made, key=lambda f: (os.stat(f).st_mtime_ns, f))[:-BACKUPS_KEPT]:
        with contextlib.suppress(OSError):
            os.unlink(f)
    return plain + ".gz"


def _write(con: sqlite3.Connection, statements, backup: str, db_path: str, committed=None) -> None:
    """One transaction, flushed all the way to the device before it counts.
    committed: called once the transaction is on the Kobo, before anything
    that can still fail."""
    landed = False
    try:
        # On macOS an ordinary fsync may leave data in the drive's cache;
        # the Kobo is about to be unplugged, so ask for the real thing.
        con.execute("pragma synchronous = full")
        con.execute("pragma fullfsync = 1")
        con.execute("pragma checkpoint_fullfsync = 1")
        con.execute("begin immediate")
        try:
            statements()
            if _before_commit:
                _before_commit()
            con.execute("commit")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                con.execute("rollback")
            raise
        landed = True
        if committed:
            committed()
        con.execute("pragma wal_checkpoint(truncate)")
    except sqlite3.Error as ex:
        again = "Plug it in again: the next sync looks at the collection and writes it again if needed."
        if _busy(ex) and not landed:
            raise CollectionError(f"The Kobo's database is in use by another program; nothing was written. {IN_USE}", backup) from ex
        if not os.path.isfile(db_path):
            raise KoboGone(
                f"The Kobo was unplugged while the collection was being written. {again} The database as it was before is in {backup}.",
                backup,
            ) from ex
        if landed:
            raise CollectionError(
                f"The collection was written, but the Kobo did not confirm it ({ex}). {again} "
                f"The database as it was before is in {backup}.",
                backup,
            ) from ex
        raise CollectionError(
            f"Writing to the Kobo failed ({ex}); the change was rolled back. Plug the Kobo in again to try once more.", backup
        ) from ex
    if _after_commit:
        _after_commit()


def _reopen(db_path: str, backup: str) -> sqlite3.Connection:
    """The Kobo's database again, after a write."""
    try:
        return _open(db_path)
    except CollectionError as ex:
        raise KoboGone(
            "The Kobo was unplugged right after the collection was written. Plug it in again: the next sync looks at the "
            f"collection and writes it again if needed. The database as it was before is in {backup}.",
            backup,
        ) from ex


def _not_as_written(backup: str) -> CollectionError:
    return CollectionError(
        "The collection on the Kobo is not what was written. Plug the Kobo in again to let the next sync mend it; "
        f"the database as it was before is in {backup}.",
        backup,
    )


def _take_off(con: sqlite3.Connection, now: str, shelf_id: str, name: str) -> None:
    """Mark a collection and its items deleted, the way the Kobo does it
    itself (the books stay, of course)."""
    con.execute(
        "update ShelfContent set _IsDeleted = 1, _IsSynced = 0, DateModified = ? where ShelfName = ? and _IsDeleted = 0",
        (now, name),
    )
    con.execute("update Shelf set _IsDeleted = 1, _IsSynced = 0, LastModified = ? where Id = ?", (now, shelf_id))


def _verify(db_path: str, name: str, backup: str, ids=None) -> int:
    """After a write: the Kobo is still there and holds what was written.
    With ids, the collection must be live and equal to them; without, it
    must be gone. Returns the number of books in it."""
    with contextlib.closing(_reopen(db_path, backup)) as con:
        live = con.execute("select count(*) from Shelf where Name = ? and _IsDeleted = 0", (name,)).fetchone()[0]
        if ids is None:
            ok = live == 0 and _members(con, name) == 0
        else:
            _wanted(con, ids)
            ok = live == 1 and _diff(con, name) == (0, 0)
        if not ok:
            raise _not_as_written(backup)
        return _members(con, name)


# ---------- the three things it can do ----------
def status(db_path: str, name: str, state_dir: str) -> dict:
    """What is there, without changing anything. Give it a copy of the
    Kobo's database rather than the Kobo's own file."""
    name = _clean_name(name)
    con = _open(db_path)
    with contextlib.closing(con):
        version = con.execute("select version from DbVersion").fetchone()[0] if _has_table(con, "DbVersion") else None
        try:
            existing = _existing(con, name, _own_id(state_dir, name))
            ours = bool(existing)
        except NotOurs:
            existing, ours = "someone else's", False
        return {
            "version": version,
            "tested": version in KNOWN_VERSIONS,
            "present": bool(existing),
            "ours": ours,
            "books": _members(con, name) if existing else 0,
        }


def _has_table(con: sqlite3.Connection, table: str) -> bool:
    return bool(con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone())


def apply(db_path: str, name: str, ids, state_dir: str, *, preflight_db: str | None = None, allow_untested: bool = False) -> Result:
    """Make the collection `name` on the Kobo at db_path hold exactly the
    books in `ids` that are on this Kobo.

    preflight_db: a copy of the same database. With it, the gate and the
    comparison run on the copy, and the Kobo's own file is not opened at
    all when there is nothing to write."""
    name = _clean_name(name)
    ids = list(ids)
    os.makedirs(state_dir, exist_ok=True)
    own = _own_id(state_dir, name)

    if preflight_db:
        pre = _open(preflight_db)
        with contextlib.closing(pre):
            early = _nothing_to_write(pre, name, *_compare(pre, name, ids, own, allow_untested))
        if early:
            return early

    con = _open(db_path)
    with contextlib.closing(con):
        existing, to_add, to_remove = _compare(con, name, ids, own, allow_untested)
        early = _nothing_to_write(con, name, existing, to_add, to_remove)
        if early:
            return early
        backup = _backup(con, state_dir)
        shelf_id = existing or str(uuid.uuid4())
        now = _now()

        def statements():
            _wanted(con, ids)  # again, inside the transaction
            if not existing:
                con.execute(
                    """insert into Shelf (CreationDate, Id, InternalName, LastModified, Name, Type,
                                          _IsDeleted, _IsVisible, _IsSynced, _SyncTime, LastAccessed)
                       values (?, ?, ?, ?, ?, 'UserTag', 0, 1, 0, NULL, ?)""",
                    (now, shelf_id, name, now, name, now),
                )
            # A book that was in the collection before and left it: its row comes back.
            con.execute(
                """update ShelfContent set _IsDeleted = 0, _IsSynced = 0, DateModified = ?
                   where ShelfName = ? and _IsDeleted = 1
                     and ContentId in (select w.id from want w join content c on c.ContentID = w.id and c.ContentType = 6)""",
                (now, name),
            )
            con.execute(
                """insert into ShelfContent (ShelfName, ContentId, DateModified, _IsDeleted, _IsSynced)
                   select ?, w.id, ?, 0, 0 from want w join content c on c.ContentID = w.id and c.ContentType = 6
                   where not exists (select 1 from ShelfContent s where s.ShelfName = ? and s.ContentId = w.id)""",
                (name, now, name),
            )
            con.execute(
                """update ShelfContent set _IsDeleted = 1, _IsSynced = 0, DateModified = ?
                   where ShelfName = ? and _IsDeleted = 0 and ContentId not in (select id from want)""",
                (now, name),
            )
            con.execute("update Shelf set LastModified = ?, _IsSynced = 0 where Id = ?", (now, shelf_id))

        def remember():
            # Only once it is on the Kobo, and then at once: whatever fails
            # after this, the collection there is known to be this tool's.
            tmp = _idfile(state_dir, name) + ".tmp"
            with open(tmp, "w") as fh:
                fh.write(shelf_id)
            os.replace(tmp, _idfile(state_dir, name))

        _write(con, statements, backup, db_path, committed=remember)

    books = _verify(db_path, name, backup, ids)
    return Result("updated" if existing else "created", books, to_add, to_remove, backup)


def _compare(con: sqlite3.Connection, name: str, ids, own: str, allow_untested: bool) -> tuple[str, int, int]:
    """The gate, then: (id of our live collection or "", books to add, books
    to take out). Reads only."""
    check(con, allow_untested)
    existing = _existing(con, name, own)
    _wanted(con, ids)
    to_add, to_remove = _diff(con, name)
    return existing, to_add, to_remove


def _nothing_to_write(con: sqlite3.Connection, name: str, existing: str, to_add: int, to_remove: int) -> Result | None:
    if existing and not to_add and not to_remove:
        return Result("unchanged", _members(con, name))
    if not existing and not to_add:
        return Result("not created")
    return None


def remove(db_path: str, name: str, state_dir: str, *, allow_untested: bool = False) -> Result:
    """Take the collection off the Kobo again (its books stay, of course)."""
    name = _clean_name(name)
    own = _own_id(state_dir, name)
    con = _open(db_path)
    with contextlib.closing(con):
        check(con, allow_untested)
        existing = _existing(con, name, own)
        if not existing:
            return Result("absent")
        backup = _backup(con, state_dir)
        now = _now()

        _write(con, lambda: _take_off(con, now, existing, name), backup, db_path)
    with contextlib.suppress(FileNotFoundError):
        os.unlink(_idfile(state_dir, name))
    _verify(db_path, name, backup)
    return Result("removed", backup=backup)


def _remembered(state_dir: str) -> dict[str, str]:
    """Shelf id -> the file that remembers it, for every collection this
    tool ever made from this state folder."""
    out = {}
    try:
        names = os.listdir(state_dir)
    except OSError:
        return out
    for f in names:
        if f.startswith("collection-id-") and not f.endswith(".tmp"):
            try:
                with open(os.path.join(state_dir, f)) as fh:
                    shelf_id = fh.read().strip()
            except OSError:
                continue
            if SHELF_ID_OK.match(shelf_id):
                out[shelf_id] = os.path.join(state_dir, f)
    return out


def _ours_besides(con: sqlite3.Connection, keep: str, shelf_ids) -> list[tuple[str, str]]:
    """(shelf id, name) of the live collections with one of these ids,
    other than the one named `keep`."""
    ids = list(shelf_ids)
    if not ids or not _has_table(con, "Shelf"):
        return []
    rows = con.execute(f"select Id, Name from Shelf where _IsDeleted = 0 and Id in ({', '.join('?' * len(ids))})", ids).fetchall()
    return [(i, n) for i, n in rows if n != keep]


def remove_others(db_path: str, keep_name: str, state_dir: str, *, preflight_db: str | None = None, allow_untested: bool = False) -> Result:
    """Take every collection this tool made off the Kobo, except the one
    named keep_name ("" = all of them): the old collection after the name
    was changed or cleared. Collections are recognised by the Shelf id this
    tool remembered when it made them, never by name, so one that someone
    else made is not touched, whatever it is called."""
    keep = (keep_name or "").strip()
    remembered = _remembered(state_dir)
    if not remembered:
        return Result("absent")
    if preflight_db:
        pre = _open(preflight_db)
        with contextlib.closing(pre):
            if not _ours_besides(pre, keep, remembered):
                return Result("absent")
    con = _open(db_path)
    with contextlib.closing(con):
        others = _ours_besides(con, keep, remembered)
        if not others:
            return Result("absent")
        check(con, allow_untested)
        backup = _backup(con, state_dir)
        now = _now()

        def statements():
            for shelf_id, name in others:
                _take_off(con, now, shelf_id, name)

        _write(con, statements, backup, db_path)
    for shelf_id, _name in others:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(remembered[shelf_id])
    with contextlib.closing(_reopen(db_path, backup)) as con:
        if _ours_besides(con, keep, [i for i, _ in others]):
            raise _not_as_written(backup)
    return Result("removed", removed=len(others), backup=backup, names=tuple(n for _, n in others))
