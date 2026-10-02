"""A made-up KoboReader.sqlite for tests: the Kobo's own table definitions
(as read from a device on Kobo software 6.0.274403, database version 222)
with invented books and collections. No real reading data.

    python tests/kobo_fixture.py out.sqlite     # a file to look at or try things on
"""

import sqlite3
import sys
import uuid

DB_VERSION = 222

# Verbatim from the device (sqlite_master), whitespace included.
KOBO_SCHEMA = """
CREATE TABLE DbVersion( version INTEGER NOT NULL, PRIMARY KEY(version));
CREATE TABLE Shelf (
	CreationDate	TEXT,
	Id		TEXT,
	InternalName	TEXT,
	LastModified	TEXT,
	Name		TEXT,
	Type		TEXT,
	_IsDeleted	BOOL,
	_IsVisible	BOOL,
	_IsSynced	BOOL, _SyncTime TEXT, LastAccessed TEXT,
	PRIMARY KEY(Id)
);
CREATE INDEX shelf_id_index ON shelf (Id);
CREATE INDEX shelf_name_index ON shelf (Name);
CREATE INDEX shelf_creationdate_index ON shelf (CreationDate);
CREATE TABLE ShelfContent (
	ShelfName	TEXT,
	ContentId	TEXT,
	DateModified	TEXT,
	_IsDeleted	BOOL,
	_IsSynced	BOOL,
	PRIMARY KEY(ShelfName, ContentId)
);
CREATE INDEX shelfcontent_datemodified_index ON ShelfContent (DateModified);
"""
# The device's content table has 113 columns; these are the ones anything here reads.
CONTENT = """
CREATE TABLE content (
	ContentID TEXT NOT NULL, ContentType TEXT NOT NULL, MimeType TEXT NOT NULL, Title TEXT, Attribution TEXT,
	ISBN TEXT, ___PercentRead INT, ReadStatus INT, DateLastRead TEXT, TimeSpentReading INT,
	LastTimeFinishedReading TEXT, ImageId TEXT, Language TEXT,
	PRIMARY KEY(ContentID)
);
CREATE TABLE Event (EventType INT, FirstOccurrence TEXT, LastOccurrence TEXT, EventCount INT, ContentID TEXT);
"""


def book_id(n: int) -> str:
    """The id of made-up book n, shaped like a Kobo store id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kobo-hardcover-sync/test-book/{n}"))


BOOKS = [book_id(n) for n in range(8)]
SIDELOADED = "file:///mnt/onboard/A Sideloaded Book.epub"
T = "2026-09-0{}T10:00:00.000Z"


def make(path: str, version: int | None = DB_VERSION, wal: bool = True) -> None:
    con = sqlite3.connect(path)
    con.executescript(KOBO_SCHEMA + CONTENT)
    if version is not None:
        con.execute("insert into DbVersion values (?)", (version,))
    for n, cid in enumerate(BOOKS):
        con.execute(
            "insert into content values (?, '6', 'application/x-kobo-epub+zip', ?, 'An Author', ?, ?, 1, ?, ?, '', '', 'en')",
            (cid, f"Made-up Book {n}", f"97800000000{n:02d}", 10 * n, f"2026-09-{20 - n:02d}T10:00:00Z", 600 * (n + 1)),
        )
    con.execute(
        "insert into content values (?, '6', 'application/epub+zip', 'A Sideloaded Book', 'Someone', '', 5, 1, '', 60, '', '', 'en')",
        (SIDELOADED,),
    )
    con.execute(
        "insert into content values (?, '9', 'application/xhtml+xml', 'a chapter', '', '', 0, 0, '', 0, '', '', '')",
        (BOOKS[0] + "!chapter1",),
    )
    # Collections the tool must never touch: the Kobo's own, two of the reader's, one the reader deleted.
    shelves = [
        ("Wishlist-like system shelf", "SystemTag", 0, 1, T.format(1)),
        ("Holiday", "UserTag", 0, 1, T.format(2)),
        ("To lend", "UserTag", 0, 0, None),
        ("Old list", "UserTag", 1, 0, None),
    ]
    for name, typ, deleted, synced, sync_time in shelves:
        con.execute(
            "insert into Shelf values (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (T.format(1), str(uuid.uuid5(uuid.NAMESPACE_URL, name)), name, T.format(3), name, typ, deleted, synced, sync_time, T.format(3)),
        )
    for name, cid, deleted, synced in (
        ("Holiday", BOOKS[0], 0, 1),
        ("Holiday", BOOKS[5], 0, 1),
        ("Holiday", BOOKS[6], 1, 0),
        ("To lend", BOOKS[1], 0, 0),
        ("Old list", BOOKS[2], 1, 0),
    ):
        con.execute("insert into ShelfContent values (?, ?, ?, ?, ?)", (name, cid, T.format(4), deleted, synced))
    con.commit()
    if wal:  # the Kobo's database is in WAL mode
        con.execute("pragma journal_mode = wal")
    con.close()


if __name__ == "__main__":
    make(sys.argv[1])
