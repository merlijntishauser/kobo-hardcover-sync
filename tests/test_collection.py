"""The one piece of code that writes to a Kobo, against a made-up database
with the Kobo's own table definitions (tests/kobo_fixture.py)."""

import gzip
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from kobo_hardcover_sync.engine import collection
from tests.kobo_fixture import BOOKS, SIDELOADED, make

NAME = "On Hardcover"


@pytest.fixture
def kobo(tmp_path):
    db = tmp_path / "kobo" / ".kobo" / "KoboReader.sqlite"
    db.parent.mkdir(parents=True)
    make(str(db))
    return str(db), str(tmp_path / "state")


def rows(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def everything(db):
    """Every row of every table, to compare a database before and after."""
    con = sqlite3.connect(db)
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def others(db, name=NAME):
    """Every collection and item that is not ours."""
    return rows(db, "select * from Shelf where Name != ? order by Id", name), rows(
        db, "select * from ShelfContent where ShelfName != ? order by 1, 2", name
    )


def members(db, deleted=0):
    return {r[0] for r in rows(db, "select ContentId from ShelfContent where ShelfName = ? and _IsDeleted = ?", NAME, deleted)}


def backups(state):
    d = os.path.join(state, "backups")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def stray_files(db):
    """SQLite's side files next to the Kobo's database; none should stay behind with anything in them."""
    return [f for f in (db + "-wal", db + "-journal") if os.path.exists(f) and os.path.getsize(f)]


# ---------- the rules ----------
def test_an_empty_list_creates_nothing(kobo):
    db, state = kobo
    before = everything(db)
    r = collection.apply(db, NAME, [], state)
    assert r.action == "not created" and not r.wrote and r.line(NAME) == f"collection '{NAME}': no books to put in it, not created"
    assert everything(db) == before and backups(state) == []


def test_create_then_the_same_list_again_writes_nothing(kobo):
    db, state = kobo
    before, untouched = everything(db), others(db)
    r = collection.apply(db, NAME, BOOKS[:3], state)
    assert (r.action, r.books, r.added, r.removed) == ("created", 3, 3, 0) and r.wrote
    assert r.line(NAME) == f"collection '{NAME}': 3 books (+3, -0)"
    # The shelf row looks like one the Kobo made itself; the items are marked as new to it.
    assert rows(
        db,
        "select Type, _IsDeleted, _IsVisible, _IsSynced, length(Id), Name = InternalName, _SyncTime is null from Shelf where Name = ?",
        NAME,
    ) == [("UserTag", 0, 1, 0, 36, 1, 1)]
    assert rows(db, "select _IsDeleted, _IsSynced, count(*) from ShelfContent where ShelfName = ? group by 1, 2", NAME) == [(0, 0, 3)]
    assert rows(db, "select CreationDate from Shelf where Name = ?", NAME)[0][0].endswith(".000Z")
    assert members(db) == set(BOOKS[:3]) and others(db) == untouched and not stray_files(db)
    # The backup is the database as it was before the write.
    assert len(backups(state)) == 1 and r.backup.endswith(backups(state)[0])
    restored = os.path.join(state, "restored.sqlite")
    with gzip.open(r.backup, "rb") as fi, open(restored, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    assert everything(restored) == before

    after = everything(db)
    again = collection.apply(db, NAME, BOOKS[:3], state)
    assert (again.action, again.books, again.wrote) == ("unchanged", 3, False) and again.line(NAME).endswith("already up to date")
    assert everything(db) == after and len(backups(state)) == 1  # nothing written, no new backup


def test_one_in_one_out_and_ids_that_are_not_books_here_are_skipped(kobo):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:3], state)
    untouched = others(db)
    wanted = [
        *BOOKS[1:4],
        "00000000-0000-0000-0000-notonthiskobo",
        "bad id'; drop table Shelf;--",
        SIDELOADED,
        BOOKS[0] + "!chapter1",
        "",
        None,
    ]
    r = collection.apply(db, NAME, wanted, state)
    assert (r.action, r.books, r.added, r.removed) == ("updated", 3, 1, 1)
    assert members(db) == set(BOOKS[1:4]) and members(db, deleted=1) == {BOOKS[0]}  # marked deleted, not dropped
    r = collection.apply(db, NAME, BOOKS[:4], state)
    assert (r.books, r.added, r.removed) == (4, 1, 0) and members(db, deleted=1) == set()  # its row came back
    assert rows(db, "select count(*) from ShelfContent where ShelfName = ?", NAME) == [(4,)]
    assert others(db) == untouched and rows(db, "select count(*) from Shelf") == [(5,)]


def test_a_collection_of_that_name_that_is_not_ours_is_left_alone(kobo):
    db, state = kobo
    before = everything(db)
    for theirs in ("Holiday", "Wishlist-like system shelf"):
        with pytest.raises(collection.NotOurs, match="left alone"):
            collection.apply(db, theirs, BOOKS[:2], state)
        with pytest.raises(collection.NotOurs):
            collection.remove(db, theirs, state)
    assert everything(db) == before and backups(state) == []
    # One the reader deleted on the Kobo is not in the way.
    assert collection.apply(db, "Old list", BOOKS[:1], state).action == "created"


def test_ours_stays_ours_only_through_the_remembered_id(kobo):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:2], state)
    idfile = os.path.join(state, "collection-id-" + hashlib.sha256(NAME.encode()).hexdigest()[:12])
    assert open(idfile).read() == rows(db, "select Id from Shelf where Name = ?", NAME)[0][0]
    os.rename(idfile, idfile + ".hidden")  # as on another computer
    with pytest.raises(collection.NotOurs):
        collection.apply(db, NAME, BOOKS[:3], state)
    os.rename(idfile + ".hidden", idfile)
    with open(idfile, "w") as fh:
        fh.write("not an id")
    with pytest.raises(collection.CollectionError, match="damaged"):
        collection.apply(db, NAME, BOOKS[:3], state)


def test_remove_and_create_again(kobo):
    db, state = kobo
    assert collection.remove(db, NAME, state).action == "absent" and backups(state) == []
    collection.apply(db, NAME, BOOKS[:3], state)
    first_id = rows(db, "select Id from Shelf where Name = ?", NAME)[0][0]
    untouched = others(db)
    r = collection.remove(db, NAME, state)
    assert r.action == "removed" and r.wrote and members(db) == set() and len(members(db, deleted=1)) == 3
    assert rows(db, "select _IsDeleted, _IsSynced from Shelf where Id = ?", first_id) == [(1, 0)]
    assert collection.remove(db, NAME, state).action == "absent"
    r = collection.apply(db, NAME, BOOKS[:2], state)  # a new collection, the two rows revived
    assert r.action == "created" and members(db) == set(BOOKS[:2])
    assert rows(db, "select count(*), count(distinct Id) from Shelf where Name = ?", NAME) == [(2, 2)]
    assert others(db) == untouched and not stray_files(db)


def test_only_the_last_three_backups_are_kept(kobo):
    db, state = kobo
    made = [collection.apply(db, NAME, BOOKS[:n], state).backup for n in range(1, 6)]  # five writes within a second or two
    assert len(set(made)) == 5
    assert all(b.startswith("KoboReader-") and b.endswith(".sqlite.gz") for b in backups(state))
    assert sorted(os.path.join(state, "backups", b) for b in backups(state)) == sorted(made[-3:])  # the newest three


def test_names(kobo):
    db, state = kobo
    assert collection.apply(db, 'Robin\'s "shelf"; drop table Shelf;--', BOOKS[:1], state).action == "created"
    assert rows(db, "select count(*) from Shelf") == [(5,)]
    for bad in ("", "   ", "two\nlines", "x" * 61, None):
        with pytest.raises(collection.CollectionError):
            collection.apply(db, bad, BOOKS[:1], state)


def test_status(kobo):
    db, state = kobo
    assert collection.status(db, NAME, state) == {"version": 222, "tested": True, "present": False, "ours": False, "books": 0}
    collection.apply(db, NAME, BOOKS[:3], state)
    assert collection.status(db, NAME, state) == {"version": 222, "tested": True, "present": True, "ours": True, "books": 3}
    assert collection.status(db, "Holiday", state)["ours"] is False and collection.status(db, "Holiday", state)["present"] is True


# ---------- the gate ----------
def altered(tmp_path, *statements, version=222):
    db = str(tmp_path / "other.sqlite")
    make(db, version=version)
    con = sqlite3.connect(db)
    for s in statements:
        con.execute(s)
    con.commit()
    con.close()
    return db


def refused(db, state, match, **kw):
    before = everything(db)
    for call in (lambda: collection.apply(db, NAME, BOOKS[:2], state, **kw), lambda: collection.remove(db, NAME, state, **kw)):
        with pytest.raises(collection.UnsupportedKobo, match=match) as ex:
            call()
        assert "Nothing was written" in str(ex.value)
    assert everything(db) == before and backups(state) == []
    return ex.value


def test_an_untested_database_version_is_refused_unless_asked_for(tmp_path):
    state = str(tmp_path / "state")
    db = altered(tmp_path, version=223)
    ex = refused(db, state, "version 223, which has not been tested")
    assert ex.version == 223 and "222 (Kobo software 6.0.274403)" in str(ex)
    assert collection.status(db, NAME, state)["tested"] is False
    assert collection.apply(db, NAME, BOOKS[:2], state, allow_untested=True).action == "created"


def test_a_database_that_lacks_what_is_written_is_refused_even_when_asked_for(tmp_path):
    state = str(tmp_path / "state")
    cases = [
        ("drop table DbVersion", "no DbVersion table"),
        ("delete from DbVersion", "does not say which version"),
        ("alter table ShelfContent rename column _IsSynced to Synced", "ShelfContent table has no _IsSynced"),
        ("alter table Shelf drop column LastAccessed", "Shelf table has no LastAccessed"),
        ("alter table content rename column ContentType to Kind", "content table has no ContentType"),
        ("alter table Shelf add column Owner TEXT NOT NULL DEFAULT ''", None),  # has a default: fine
        ("alter table ShelfContent rename to ShelfItems", "has no ShelfContent table"),
        ("create trigger shelf_watch after insert on Shelf begin select 1; end", "triggers on its collections"),
    ]
    for n, (statement, match) in enumerate(cases):
        d = tmp_path / str(n)
        d.mkdir()
        db = altered(d, statement)
        if match is None:
            assert collection.apply(db, NAME, BOOKS[:2], state + str(n)).action == "created"
        else:
            refused(db, state + str(n), match, allow_untested=True)


def test_a_new_column_that_must_be_filled_in_is_refused(tmp_path):
    state = str(tmp_path / "state")
    db = str(tmp_path / "other.sqlite")
    make(db)
    con = sqlite3.connect(db)
    con.executescript(
        "alter table ShelfContent rename to old; create table ShelfContent (ShelfName TEXT, ContentId TEXT, DateModified TEXT,"
        " _IsDeleted BOOL, _IsSynced BOOL, Position INT NOT NULL, PRIMARY KEY(ShelfName, ContentId)); drop table old;"
    )
    con.close()
    refused(db, state, "ShelfContent table needs Position", allow_untested=True)


def test_a_file_that_is_no_kobo_database(tmp_path):
    state = str(tmp_path / "state")
    junk = tmp_path / "KoboReader.sqlite"
    junk.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(collection.CollectionError, match="could not be opened"):
        collection.apply(str(junk), NAME, BOOKS[:1], state)
    with pytest.raises(collection.KoboGone):
        collection.apply(str(tmp_path / "nowhere.sqlite"), NAME, BOOKS[:1], state)
    assert backups(state) == []


# ---------- interruptions ----------
def test_a_failure_inside_the_write_changes_nothing(kobo, monkeypatch):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:2], state)
    before = everything(db)

    def boom():
        raise RuntimeError("the cable fell out")

    monkeypatch.setattr(collection, "_before_commit", boom)
    with pytest.raises(RuntimeError):
        collection.apply(db, NAME, BOOKS[:5], state)
    with pytest.raises(RuntimeError):
        collection.remove(db, NAME, state)
    assert everything(db) == before and not stray_files(db)
    monkeypatch.setattr(collection, "_before_commit", None)
    assert collection.apply(db, NAME, BOOKS[:5], state).books == 5  # and it works afterwards


def test_a_first_write_that_fails_does_not_remember_a_collection(kobo, monkeypatch):
    db, state = kobo
    before = everything(db)
    monkeypatch.setattr(collection, "_before_commit", lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        collection.apply(db, NAME, BOOKS[:2], state)
    assert everything(db) == before and not [f for f in os.listdir(state) if f.startswith("collection-id-")]
    assert len(backups(state)) == 1  # the backup was made before the attempt


def test_a_process_that_dies_in_the_middle_of_the_write_changes_nothing(kobo):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:2], state)
    before = everything(db)
    script = textwrap.dedent(f"""
        import os
        from kobo_hardcover_sync.engine import collection
        from tests.kobo_fixture import BOOKS
        collection._before_commit = lambda: os._exit(9)      # no rollback, no close: the process is simply gone
        collection.apply({db!r}, {NAME!r}, BOOKS[:6], {state!r})
    """)
    died = subprocess.run([sys.executable, "-c", script], cwd=os.path.dirname(os.path.dirname(__file__)))
    assert died.returncode == 9
    assert everything(db) == before  # SQLite undoes the half-written change
    assert members(db) == set(BOOKS[:2])
    assert collection.apply(db, NAME, BOOKS[:6], state).books == 6


def test_a_kobo_that_disappears_right_after_the_write_is_reported_with_the_backup(kobo, monkeypatch):
    db, state = kobo
    monkeypatch.setattr(collection, "_after_commit", lambda: os.rename(db, db + ".unplugged"))
    with pytest.raises(collection.KoboGone, match="disappeared right after the write") as ex:
        collection.apply(db, NAME, BOOKS[:2], state)
    assert ex.value.backup and os.path.exists(ex.value.backup) and ex.value.backup in str(ex.value)


def test_a_database_another_program_is_writing_to(kobo):
    db, state = kobo
    other = sqlite3.connect(db, isolation_level=None)
    other.execute("begin immediate")
    try:
        with pytest.raises(collection.CollectionError, match="in use by another program"):
            collection_apply_fast(db, state)
    finally:
        other.execute("rollback")
        other.close()
    assert members(db) == set()


def collection_apply_fast(db, state):
    """apply(), without waiting the full five seconds for the lock."""
    real = collection._open

    def quick(path):
        con = real(path)
        con.execute("pragma busy_timeout = 100")
        return con

    collection._open = quick
    try:
        return collection.apply(db, NAME, BOOKS[:2], state)
    finally:
        collection._open = real


# ---------- the Kobo's own file is opened as little as possible ----------
def test_with_a_copy_to_look_at_the_kobos_file_is_not_opened_when_nothing_changes(kobo, tmp_path, monkeypatch):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:3], state)
    copy = str(tmp_path / "copy.sqlite")
    shutil.copy(db, copy)
    opened = []
    real = collection._open
    monkeypatch.setattr(collection, "_open", lambda path: opened.append(path) or real(path))
    r = collection.apply(db, NAME, BOOKS[:3], state, preflight_db=copy)
    assert r.action == "unchanged" and opened == [copy]
    opened.clear()
    r = collection.apply(db, NAME, BOOKS[:4], state, preflight_db=copy)  # something to write: now it is
    assert r.action == "updated" and opened[0] == copy and db in opened and members(db) == set(BOOKS[:4])
    # An untested version is refused on the copy; the Kobo's file is never opened.
    opened.clear()
    con = sqlite3.connect(copy)
    con.execute("update DbVersion set version = 300")
    con.commit()
    con.close()
    with pytest.raises(collection.UnsupportedKobo):
        collection.apply(db, NAME, BOOKS[:5], state, preflight_db=copy)
    assert opened == [copy]


# ---------- the name was changed or cleared ----------
def test_a_collection_made_under_another_name_is_taken_off_again(kobo):
    db, state = kobo
    collection.apply(db, "Old name", BOOKS[:3], state)
    untouched = others(db, "Old name")
    assert collection.remove_others(db, "Old name", state).action == "absent"  # the wanted one is the only one: nothing to do
    assert len(backups(state)) == 1
    gone = collection.remove_others(db, NAME, state)  # the reader now wants it called NAME
    assert (gone.action, gone.removed, gone.names, gone.wrote) == ("removed", 1, ("Old name",), True)
    assert rows(db, "select _IsDeleted, _IsSynced from Shelf where Name = 'Old name'") == [(1, 0)]
    assert rows(db, "select count(*) from ShelfContent where ShelfName = 'Old name' and _IsDeleted = 0") == [(0,)]
    assert others(db, "Old name") == untouched and not stray_files(db)
    assert not [f for f in os.listdir(state) if f.startswith("collection-id-")]  # forgotten, so it is not looked for again
    assert collection.remove_others(db, NAME, state).action == "absent" and len(backups(state)) == 2
    assert collection.apply(db, NAME, BOOKS[:3], state).action == "created"


def test_a_cleared_name_takes_every_collection_of_ours_off_and_nobody_elses(kobo):
    db, state = kobo
    collection.apply(db, "First", BOOKS[:2], state)
    collection.apply(db, "Second", BOOKS[2:4], state)
    theirs = (
        rows(db, "select * from Shelf where Name in ('Holiday', 'To lend', 'Wishlist-like system shelf') order by Id"),
        rows(db, "select * from ShelfContent where ShelfName in ('Holiday', 'To lend') order by 1, 2"),
    )
    gone = collection.remove_others(db, "", state)
    assert gone.removed == 2 and set(gone.names) == {"First", "Second"}
    assert rows(db, "select count(*) from Shelf where Name in ('First', 'Second') and _IsDeleted = 0") == [(0,)]
    assert theirs == (
        rows(db, "select * from Shelf where Name in ('Holiday', 'To lend', 'Wishlist-like system shelf') order by Id"),
        rows(db, "select * from ShelfContent where ShelfName in ('Holiday', 'To lend') order by 1, 2"),
    )
    assert collection.remove_others(db, "", state).action == "absent"
    assert collection.remove_others(db, "", os.path.join(state, "never-used")).action == "absent"


def test_ours_is_known_by_its_id_not_by_its_name(kobo):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:2], state)
    con = sqlite3.connect(db)  # the reader renames it on the Kobo itself
    con.execute("update Shelf set Name = 'Renamed on the Kobo', InternalName = 'Renamed on the Kobo' where Name = ?", (NAME,))
    con.execute("update ShelfContent set ShelfName = 'Renamed on the Kobo' where ShelfName = ?", (NAME,))
    con.commit()
    con.close()
    gone = collection.remove_others(db, NAME, state)  # still ours, and not the name that is wanted
    assert gone.names == ("Renamed on the Kobo",)
    assert collection.apply(db, NAME, BOOKS[:2], state).action == "created" and members(db) == set(BOOKS[:2])
    # A collection that merely has a name we once used is not ours.
    assert collection.remove_others(db, "", os.path.join(state, "elsewhere")).action == "absent"
    assert rows(db, "select count(*) from Shelf where Name = 'Holiday' and _IsDeleted = 0") == [(1,)]


def test_removing_the_old_collection_obeys_the_gate_and_looks_at_the_copy_first(kobo, tmp_path, monkeypatch):
    db, state = kobo
    collection.apply(db, "Old name", BOOKS[:2], state)
    copy = str(tmp_path / "copy.sqlite")
    shutil.copy(db, copy)
    opened = []
    real = collection._open
    monkeypatch.setattr(collection, "_open", lambda path: opened.append(path) or real(path))
    assert collection.remove_others(db, "Old name", state, preflight_db=copy).action == "absent" and opened == [copy]
    monkeypatch.setattr(collection, "_open", real)
    con = sqlite3.connect(db)
    con.execute("update DbVersion set version = 300")
    con.commit()
    con.close()
    before, n = everything(db), len(backups(state))
    with pytest.raises(collection.UnsupportedKobo, match="version 300"):
        collection.remove_others(db, NAME, state)
    assert everything(db) == before and len(backups(state)) == n
    monkeypatch.setattr(collection, "_before_commit", lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        collection.remove_others(db, NAME, state, allow_untested=True)
    assert everything(db) == before and [f for f in os.listdir(state) if f.startswith("collection-id-")]  # still remembered


def test_a_book_added_by_hand_on_the_kobo_is_taken_out_again(kobo):
    db, state = kobo
    collection.apply(db, NAME, BOOKS[:2], state)
    con = sqlite3.connect(db)
    con.execute("insert into ShelfContent values (?, ?, '2026-10-01T10:00:00.000Z', 0, 0)", (NAME, BOOKS[6]))
    con.commit()
    con.close()
    r = collection.apply(db, NAME, BOOKS[:2], state)
    assert (r.action, r.added, r.removed) == ("updated", 0, 1) and members(db) == set(BOOKS[:2])
    assert rows(db, "select count(*) from content where ContentID = ?", BOOKS[6]) == [(1,)]  # the book itself stays, of course
