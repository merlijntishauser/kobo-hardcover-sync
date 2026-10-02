"""`doctor`: everything a sync depends on, looked at and not touched. Local
mode here; the server's half is in test_accounts, the computer's half of
server mode in test_computer, the Check card in test_local and
test_accounts."""

import errno
import hashlib
import os
import sqlite3

import pytest

from kobo_hardcover_sync import cli, doctor
from kobo_hardcover_sync.computer import config, runner
from kobo_hardcover_sync.computer.platform import HARDCOVER
from kobo_hardcover_sync.engine import collection, hardcover, state
from kobo_hardcover_sync.server import accounts
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer
from tests.test_hardcover import FakeHC
from tests.test_local import LOCAL, TOKEN, catalogue, kobo, st


class Whose(FakeHC):
    def whoami(self):
        return {"id": 1, "username": "sam"}


def found(checks, what):
    """The one check about `what`."""
    (c,) = [c for c in checks if c.what == what]
    return c


def tree(folder):
    """Every file under a folder with a hash of what is in it."""
    out = {}
    for base, _dirs, files in os.walk(folder):
        for f in files:
            with open(os.path.join(base, f), "rb") as fh:
                out[os.path.join(base, f)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def synced(home, live=True, name="On Hardcover"):
    """A computer in local mode that has synced: three books on, a collection on the Kobo."""
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.install_trigger("kobo-hardcover-sync")
    mac.set_secret(HARDCOVER, TOKEN)
    hc = Whose(isbn=catalogue())
    runner.sync(mac, LOCAL, hardcover_client=hc)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:3], "on")
    accounts.set_collection(con, "me", name)
    con.execute("update reader set hardcover_live = ? where name = 'me'", (int(live),))
    con.commit()
    con.close()
    runner.sync(mac, LOCAL, hardcover_client=hc)
    return mac, hc


def test_everything_in_order_and_nothing_touched(home):
    mac, hc = synced(home)
    calls, before = len(hc.calls), {**tree(home / "state"), **tree(home / "Volumes")}
    checks = doctor.computer_checks(mac, LOCAL, client=hc)
    assert {**tree(home / "state"), **tree(home / "Volumes")} == before  # not a byte, on the Kobo or here
    assert len(hc.calls) == calls and os.listdir(home / "scratch") == []  # nothing sent, no copy left behind
    assert [(c.what, c.state) for c in checks] == [
        ("Setup", "ok"),
        ("Trigger", "ok"),
        ("Folder", "ok"),
        ("Token", "ok"),
        ("Hardcover", "ok"),
        ("Books", "ok"),
        ("Sending", "ok"),
        ("Last run", "ok"),
        ("Kobo", "ok"),
        ("Database", "ok"),
        ("Kobo software", "ok"),
        ("Collection", "ok"),
        ("Backups", "ok"),
        ("Last sync", "ok"),
        ("Log", "ok"),
    ]
    assert all(not c.todo for c in checks) and doctor.problems(checks) == 0
    assert doctor.summary(checks) == "Everything a sync depends on is in order."
    assert found(checks, "Hardcover").found == "Hardcover is reachable and accepts the token: it is @sam's."
    assert found(checks, "Kobo").found.endswith("KOBOeReader (Kobo Clara Colour, software 6.0.274403).")
    assert found(checks, "Database").found == "The Kobo's database can be read: 9 books on it."
    assert found(checks, "Kobo software").found == "Database version 222 is one this tool was tested with (Kobo software 6.0.274403)."
    assert found(checks, "Books").found == "3 of 9 books are switched on."
    assert found(checks, "Collection").found == "'On Hardcover' is on the Kobo, with 3 books."
    assert found(checks, "Backups").found.startswith("1 copy of the Kobo's database from before a write")
    assert found(checks, "Last sync").found.endswith(
        ": Kobo synced: 3 sent to Hardcover. Collection 'On Hardcover': 3 books (+3, -0). Eject before unplugging."
    )
    text = doctor.report(checks)
    assert "ok       Kobo: Found at" in text and text.endswith("\n\nEverything a sync depends on is in order.")
    assert TOKEN not in text and "Made-up Book" not in text  # no token, no book


def test_not_set_up_is_a_problem_and_the_command_says_so(home, capsys):
    mac = FakeComputer(home / "Volumes")
    checks = doctor.computer_checks(mac)
    assert [(c.what, c.state, c.todo) for c in checks] == [("Setup", "fail", "Run `kobo-hardcover-sync setup`.")]
    with pytest.raises(SystemExit) as ex:
        cli.main(["doctor"], computer=mac)
    out = capsys.readouterr().out
    assert ex.value.code == 1 and out.startswith("kobo-hardcover-sync ") and ", Python 3." in out.splitlines()[0]
    assert "problem  Setup: This computer is not set up yet.\n         To do: Run `kobo-hardcover-sync setup`." in out
    assert out.endswith("1 problem: its line says what to do.\n")
    assert not os.path.exists(home / "state")  # looking made nothing


def test_the_command_ends_well_when_nothing_stops_syncing(home, capsys, monkeypatch):
    mac, hc = synced(home, live=False)
    config.save(config.Config())
    monkeypatch.setattr(hardcover, "Client", lambda token, **kw: hc)
    cli.main(["doctor"], computer=mac)  # no SystemExit: a dry run is a note, not a problem
    out = capsys.readouterr().out
    assert "note     Sending: Dry run: the page shows what would be sent, and nothing goes to Hardcover." in out
    assert "         To do: Go live under Settings when the plan looks right." in out and TOKEN not in out


def test_set_up_and_nothing_else_yet(home):
    config.save(config.Config())
    checks = doctor.computer_checks(FakeComputer(home / "Volumes"))
    assert doctor.problems(checks) == 0
    assert (found(checks, "Trigger").state, found(checks, "Hardcover").state) == ("warn", "note")
    assert found(checks, "Trigger").todo == "Until then, run `kobo-hardcover-sync sync` with the Kobo plugged in."
    assert found(checks, "Hardcover").todo == "`kobo-hardcover-sync token`, or Settings on the page."
    assert found(checks, "Books").found == "No books yet: nothing was read from a Kobo so far."
    assert found(checks, "Kobo").todo == "Plug it in, tap Connect on the Kobo, and run this check again."
    assert found(checks, "Backups").state == "note" and found(checks, "Last sync").state == "note"
    assert sorted(os.listdir(home / "state")) == ["config.toml"]  # no database made by looking


@pytest.mark.parametrize(
    "kind, state_, said",
    [
        ("token", "fail", "Hardcover does not accept your token."),
        ("scope", "fail", "Your Hardcover token may not do this."),
        ("unreachable", "warn", "Hardcover could not be reached (timed out). Nothing is lost: the next sync carries on."),
        ("rate", "warn", "Today's number of requests to Hardcover is used up."),
    ],
)
def test_what_hardcover_says_about_the_token(kind, state_, said):
    class Says:
        def whoami(self):
            raise hardcover.HardcoverError(said.rstrip("."), kind)

    c = doctor.hardcover_check(TOKEN, "there", client=Says())
    assert (c.state, c.found) == (state_, said)
    none = doctor.hardcover_check("", "Add one there.")
    assert (none.state, none.todo) == ("note", "Add one there.")


def test_books_that_wait_for_a_match_or_failed_and_a_run_that_stopped(home):
    mac, hc = synced(home)
    con = st(home)
    con.execute("update book set hc_book_id = null, hc_how = 'uncertain' where content_id = ?", (BOOKS[0],))
    con.execute("update book set hc_error = 'Hardcover refused: no' where content_id in (?, ?)", (BOOKS[1], BOOKS[2]))
    con.execute(
        "insert into job (reader, started, finished, live, status, detail) values ('me', '2099-01-01T10:00:00Z', null, 1, 'failed', ?)",
        ('{"fatal": "Hardcover does not accept your token"}',),
    )
    con.commit()
    checks = doctor.computer_checks(mac, LOCAL, client=hc)
    assert found(checks, "Matches").found == "1 book switched on has no Hardcover match yet and cannot sync."
    assert found(checks, "Errors").found == "2 books could not be sent at the last sync."
    assert found(checks, "Last run").state == "warn" and "stopped: Hardcover does not accept your token." in found(checks, "Last run").found
    assert doctor.problems(checks) == 0 and doctor.summary(checks) == "3 warnings: their lines say what to do."


def test_a_kobo_whose_software_was_not_tested(home):
    mac, hc = synced(home, name="")
    db = sqlite3.connect(home / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite")
    db.execute("update DbVersion set version = 223")
    db.commit()
    db.close()
    c = found(doctor.computer_checks(mac, LOCAL, client=hc), "Kobo software")
    assert c.state == "warn" and "has not been tested with kobo-hardcover-sync yet (its database is version 223)" in c.found
    assert "syncing to Hardcover is not affected" in c.found and c.todo == collection.UNTESTED_HOW
    allowed = found(doctor.computer_checks(mac, config.Config(set_up=True, allow_untested_kobo=True), client=hc), "Kobo software")
    assert allowed.state == "note" and "allow_untested_kobo lets the collection be written anyway" in allowed.found
    # A database that lacks what the write needs: no setting lets that through.
    db = sqlite3.connect(home / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite")
    db.execute("alter table Shelf drop column LastAccessed")
    db.commit()
    db.close()
    lacks = found(doctor.computer_checks(mac, config.Config(set_up=True, allow_untested_kobo=True), client=hc), "Kobo software")
    assert lacks.state == "warn" and "the Shelf table has no LastAccessed" in lacks.found


def test_the_collection_wanted_and_what_is_on_the_kobo(home):
    mac, hc = synced(home, name="")
    assert found(doctor.computer_checks(mac, LOCAL, client=hc), "Collection").found == (
        "No collection is wanted, so nothing is ever written to the Kobo."
    )
    con = st(home)
    accounts.set_collection(con, "me", "Not there yet")
    assert found(doctor.computer_checks(mac, LOCAL, client=hc), "Collection").found.startswith("'Not there yet' is not on the Kobo yet")
    # A collection of the reader's own with the wanted name.
    accounts.set_collection(con, "me", "Mine")
    db = str(home / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite")
    k = sqlite3.connect(db)
    k.execute(
        "insert into Shelf (CreationDate, Id, InternalName, LastModified, Name, Type, _IsDeleted, _IsVisible, _IsSynced) "
        "values ('2026-01-01', 'aaaaaaaa-0000-0000-0000-000000000000', 'Mine', '2026-01-01', 'Mine', 'UserTag', 0, 1, 1)"
    )
    k.commit()
    k.close()
    theirs = found(doctor.computer_checks(mac, LOCAL, client=hc), "Collection")
    assert theirs.state == "warn" and "was not made by this tool, so it is left alone" in theirs.found
    assert theirs.todo == "Choose another name under Settings, or remove that collection on the Kobo."


@pytest.mark.parametrize(
    "error, said",
    [
        (PermissionError(errno.EPERM, "Operation not permitted"), "This computer does not let the tool read the Kobo."),
        (OSError(errno.ENXIO, "Device not configured"), "The Kobo was unplugged during the sync. Nothing on it was changed. Plug it in again."),
        (OSError(errno.ENOSPC, "No space left on device"), "The Kobo's database could not be read (No space left on device). Plug the Kobo in again; `kobo-hardcover-sync doctor` shows more."),
    ],
)  # fmt: skip
def test_a_kobo_that_cannot_be_read(home, monkeypatch, error, said):
    mac, hc = synced(home)

    def refuse(db, folder):
        raise error

    monkeypatch.setattr(runner, "copy_database", refuse)
    checks = doctor.computer_checks(mac, LOCAL, client=hc, by_hand=False)
    assert (found(checks, "Database").state, found(checks, "Database").found) == ("fail", said)
    assert doctor.problems(checks) == 1 and "Collection" not in [c.what for c in checks]
    # The sync says the same thing.
    monkeypatch.setattr(runner, "fingerprint", lambda db: (_ for _ in ()).throw(error))
    out = runner.sync(mac, LOCAL, hardcover_client=hc, trigger="mount")
    assert (out.ok, out.message) == (False, said)


def test_a_file_on_the_kobo_that_is_not_its_database(home):
    mac, hc = synced(home)
    with open(home / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite", "wb") as fh:
        fh.write(b"not sqlite" * 500)
    c = found(doctor.computer_checks(mac, LOCAL, client=hc), "Database")
    assert c.state == "fail" and c.found.startswith(
        "The Kobo's database could not be read: it is damaged, or the Kobo was still writing it."
    )
    out = runner.sync(mac, LOCAL, hardcover_client=hc)
    assert (out.ok, out.title, out.message) == (False, "Kobo sync failed", c.found)
