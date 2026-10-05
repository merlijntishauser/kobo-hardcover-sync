"""`export`: the reader's reading as JSON, for a database or dashboard of
their own. It has to work without Hardcover, hold the whole shelf and not
only what syncs, and never hold a token."""

import json
import os
import stat

import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, runner
from kobo_hardcover_sync.computer.platform import HARDCOVER
from kobo_hardcover_sync.engine import export, kobo_db, state
from tests import said
from tests.test_computer import FakeComputer
from tests.test_core import FAMILY, MINE, OLD, UNTOUCHED, make_kobo
from tests.test_local import LOCAL, TOKEN, kobo, st


def test_the_whole_shelf_without_hardcover(home, capsys):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    with pytest.raises(SystemExit, match="run setup first"):
        cli.main(["export"], computer=mac)
    config.save(LOCAL)
    with pytest.raises(SystemExit, match="nothing to export yet"):
        cli.main(["export"], computer=mac)
    assert not os.path.exists(home / "state" / "state.db")  # asking made no empty state

    runner.sync(mac, LOCAL)  # never connected to Hardcover: the books are imported all the same
    cli.main(["export"], computer=mac)
    data = json.loads(capsys.readouterr().out)
    assert (data["format"], data["reader"]) == (export.FORMAT, "me") and data["tool"].startswith("kobo-hardcover-sync ")
    assert len(data["books"]) == 9 and len(data["devices"]) == 1
    assert {b["syncs"] for b in data["books"]} == {False} and {b["hardcover"] for b in data["books"]} == {None}
    assert set(data["summary"]) == {
        "minutes_today",
        "minutes_week",
        "minutes_month",
        "finished_this_year",
        "current_title",
        "current_author",
        "current_percent",
        "last_upload",
    }

    out = home / "reading.json"
    mac.set_secret(HARDCOVER, TOKEN)
    cli.main(["export", "--output", str(out)], computer=mac)
    assert said(capsys) == f"ok Export 9 books written to {out}"
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600 and json.loads(out.read_text())["books"] == data["books"]
    assert TOKEN not in out.read_text() and [p for p in os.listdir(home) if p.endswith(".tmp")] == []


def test_what_a_book_says(tmp_path):
    con = state.connect(str(tmp_path / "state.db"))
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, FAMILY, MINE, UNTOUCHED], [("mine", "2026-09-28T09:00:00")])
    state.import_books(con, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    state.set_mode(con, "alice", ["mine"], "on")
    con.execute("update book set hc_how='isbn', hc_book_id=7, hc_edition_id=70, hc_title='Mine Now', last_sent='x' where content_id='mine'")
    state.set_state(con, "alice", "old", "finished", "2021-05-01")
    con.execute("insert into reading_day values ('alice', 'kobo1', '2026-09-29', 1200)")
    con.commit()

    data = export.reading(con, "alice")
    books = {b["kobo_id"]: b for b in data["books"]}
    assert set(books) == {"old", "fam", "mine"}  # never opened by anyone: not in the state, so not here
    mine, fam, old = books["mine"], books["fam"], books["old"]
    assert (mine["status"], mine["percent"], mine["syncs"], mine["opened_on_this_kobo"]) == ("reading", 10, True, True)
    assert mine["hardcover"] == {"book_id": 7, "edition_id": 70, "title": "Mine Now", "matched_by": "isbn", "last_sent": "x"}
    assert (fam["opened_on_this_kobo"], fam["syncs"], fam["hardcover"]) == (False, False, None)  # someone else on the account
    assert (old["status"], old["state"], old["state_date"], old["isbn"]) == ("finished", "finished", "2021-05-01", "111")
    assert data["reading_days"] == [{"day": "2026-09-29", "device": "kobo1", "seconds": 1200}]
    assert export.reading(con, "bob") == {"devices": [], "books": [], "reading_days": []}


def test_on_the_server_one_reader_at_a_time(home, monkeypatch, capsys):
    monkeypatch.setenv("KHS_DATA", str(home / "data"))
    with pytest.raises(SystemExit, match="nothing to export yet"):
        cli.main(["export", "--reader", "alice"])
    os.makedirs(home / "data")
    con = state.connect(str(home / "data" / "state.db"))
    k = home / "k.sqlite"
    make_kobo(k, [MINE], [("mine", "2026-09-28T09:00:00")])
    state.import_books(con, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    con.execute("insert into reader (name, created) values ('alice', 'now')")
    con.commit()
    with pytest.raises(SystemExit, match="no reader called bob"):
        cli.main(["export", "--reader", "bob"])
    cli.main(["export", "--reader", "alice"])
    assert [b["title"] for b in json.loads(capsys.readouterr().out)["books"]] == ["Mine Now"]


def test_a_computer_that_sends_to_a_server_says_where_the_books_are(home):
    config.save(config.Config(server="https://kobo.example.org"))
    with pytest.raises(SystemExit, match="your books are on https://kobo.example.org; export there"):
        cli.main(["export"], computer=FakeComputer(home / "Volumes"))


def test_every_sync_keeps_the_file_up_to_date(home, capsys):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    runner.sync(mac, LOCAL)
    out = home / "reading.json"
    with pytest.raises(SystemExit, match="--every-sync needs --output FILE"):
        cli.main(["export", "--every-sync"], computer=mac)
    cli.main(["export", "--output", str(out), "--every-sync"], computer=mac)
    assert "ok Every sync Written again after every sync." in said(capsys)
    assert config.load().export_to == str(out)

    out.unlink()
    st(home).execute("update book set percent = 3").connection.commit()  # the Kobo is read again, and differs
    os.unlink(home / "state" / "last-import.sha256")
    synced = runner.sync(mac, config.load())
    assert synced.ok and "Export" not in synced.message  # a file that was written is not news
    assert len(json.loads(out.read_text())["books"]) == 9 and stat.S_IMODE(os.stat(out).st_mode) == 0o600
    cli.main(["status"], computer=mac)
    assert f"ok Export Written to {out} after every sync" in said(capsys)

    # A folder that went away: said, and the sync is still done.
    cfg = config.load()
    cfg.export_to = str(home / "gone" / "reading.json")
    config.save(cfg)
    broken = runner.sync(mac, config.load())
    assert broken.ok and "Export not written (No such file or directory)." in broken.message
    assert os.listdir(home / "scratch") == []

    cli.main(["export", "--stop"], computer=mac)
    assert "No longer written after a sync" in said(capsys) and config.load().export_to == "" and out.exists()
    config.save(config.Config(server="https://kobo.example.org"))
    with pytest.raises(SystemExit, match="--every-sync is for local mode"):
        cli.main(["export", "--output", str(out), "--every-sync"], computer=mac)
