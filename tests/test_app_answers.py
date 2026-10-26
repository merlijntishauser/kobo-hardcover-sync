"""What the Mac app's window reads from the tool (docs/plans/2026-10-24-mac-app-window-design.md):
the JSON answers of status, doctor, history and settings, the steps of a
sync, and the history behind them. The samples in packaging/macos/samples
are what the app is built against; each answer here has their shape."""

import fcntl
import json
import os
import pathlib
from datetime import datetime, timedelta

import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, history, runner
from kobo_hardcover_sync.computer.platform import UPLOAD
from kobo_hardcover_sync.engine import state
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer, plug_in, register, server  # noqa: F401 (the fixture)
from tests.test_local import LOCAL, kobo

SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "packaging" / "macos" / "samples"


def sample(name: str):
    return json.loads((SAMPLES / name).read_text())


def same_shape(found, wanted, where="answer") -> None:
    """The same keys at every level, and values of the same kind; None
    stands in for anything (a Kobo not plugged in, no sync yet)."""
    if found is None or wanted is None:
        return
    assert type(found) is type(wanted), f"{where}: {type(found).__name__}, the sample has {type(wanted).__name__}"
    if isinstance(wanted, dict):
        assert found.keys() == wanted.keys(), f"{where}: {sorted(found)} against {sorted(wanted)}"
        for key in wanted:
            same_shape(found[key], wanted[key], f"{where}.{key}")
    elif isinstance(wanted, list) and found and wanted:
        for item in found:
            same_shape(item, wanted[0], f"{where}[]")


def answer(capsys, *argv, computer, exits=None) -> dict:
    if exits is None:
        cli.main(list(argv), computer=computer)
    else:
        with pytest.raises(SystemExit) as ended:
            cli.main(list(argv), computer=computer)
        assert ended.value.code == exits
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def mac(home, server):  # noqa: F811
    """A computer in server mode with the Kobo plugged in."""
    plug_in(home)
    computer = FakeComputer(home / "Volumes")
    register(server, computer)
    config.save(config.Config(server=server.url))
    return computer


# ---------- the history ----------
def test_every_sync_is_kept_but_not_a_volume_that_was_no_kobo(home, server):  # noqa: F811
    computer = FakeComputer(home / "Volumes")
    register(server, computer)
    cfg = config.Config(server=server.url)
    runner.sync(computer, cfg, trigger="mount")  # some other volume
    runner.sync(computer, cfg, trigger="app")  # clicked, no Kobo: an answer, but no sync
    assert history.syncs() == []

    plug_in(home)
    runner.sync(computer, cfg, trigger="mount")
    runner.sync(computer, cfg, trigger="app")  # nothing new
    with open(home / "state" / "sync.lock", "w") as held:  # another sync is running: this one is not one
        fcntl.flock(held, fcntl.LOCK_EX)
        runner.sync(computer, cfg, trigger="app")
    newest, first = history.syncs()
    assert (first["trigger"], first["ok"], first["title"], first["message"]) == ("mount", True, "Kobo synced", "9 books updated.")
    assert (newest["trigger"], newest["ok"], newest["message"]) == ("app", True, "")  # kept as it was: nothing to tell
    assert datetime.fromisoformat(newest["at"]).tzinfo is not None
    assert "Made-up" not in (home / "state" / history.FILE).read_text()  # what the notification said, never a book


def test_the_last_hundred_are_kept_and_a_broken_line_is_skipped(home):
    os.makedirs(config.state_dir())
    start = datetime(2026, 10, 1, 8, 0)
    for n in range(history.KEPT + 5):
        history.record(True, "Kobo synced", f"{n} books updated.", "mount", now=start + timedelta(minutes=n))
    kept = history.syncs()
    assert len(kept) == history.KEPT
    assert (kept[0]["message"], kept[-1]["message"]) == (f"{history.KEPT + 4} books updated.", "5 books updated.")
    with open(home / "state" / history.FILE, "a") as fh:
        fh.write('{"at": "2026-10-')  # cut short, as by a full disk
    assert len(history.syncs()) == history.KEPT


# ---------- the answers ----------
def test_status_answers_at_once_with_the_last_sync(mac, home, capsys):
    found = answer(capsys, "status", "--json", computer=mac)
    same_shape(found, sample("status.json"))
    assert (found["mode"], found["last_sync"], found["kobo"]) == ("server", None, str(home / "Volumes" / "KOBOeReader"))
    # Before there was a history: the last thing a sync said.
    (home / "state" / "last-message.txt").write_text("Kobo synced\n11 books updated.\n\n24 Oct 2026, 10:22\n")
    last = answer(capsys, "status", "--json", computer=mac)["last_sync"]
    assert (last["title"], last["message"], last["at"][:16]) == ("Kobo synced", "11 books updated.", "2026-10-24T10:22")
    runner.sync(mac, config.load(), trigger="mount")
    last = answer(capsys, "status", "--json", computer=mac)["last_sync"]
    same_shape(last, sample("status.json")["last_sync"])
    assert (last["trigger"], last["message"]) == ("mount", "9 books updated.")


def test_status_says_when_a_sync_started_elsewhere_is_running(mac, home, capsys):
    assert answer(capsys, "status", "--json", computer=mac)["syncing"] == ""
    seen = []  # what the window would see halfway through a sync the Kobo started
    runner.sync(mac, config.load(), trigger="mount", on_step=lambda row: seen.append(runner.running()))
    assert seen and set(seen) == {"mount"}
    assert runner.running() == "" and not (home / "state" / runner.RUNNING).exists()

    # Only the lock counts: a marker left by a sync that was killed says nothing.
    (home / "state" / runner.RUNNING).write_text("mount")
    assert answer(capsys, "status", "--json", computer=mac)["syncing"] == ""
    with open(home / "state" / runner.LOCK, "w") as held:  # a sync, in another process, that has not written its marker yet
        fcntl.flock(held, fcntl.LOCK_EX)
        (home / "state" / runner.RUNNING).unlink()
        assert answer(capsys, "status", "--json", computer=mac)["syncing"] == "hand"
        cli.main(["status"], computer=mac)
        assert "A sync is running now" in capsys.readouterr().out


def test_status_in_local_mode_counts_the_books_for_the_overview(home, capsys):
    computer = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    assert answer(capsys, "status", "--json", computer=computer)["books"] is None  # nothing read from a Kobo yet
    kobo(home)
    runner.sync(computer, LOCAL)
    found = answer(capsys, "status", "--json", computer=computer)
    same_shape(found, sample("status-local.json"))
    assert found["books"] == {"total": 9, "on": 0, "next": 0, "needs_match": 0, "live": False, "user": "", "collection": ""}
    con = state.connect(str(home / "state" / "state.db"))
    state.set_mode(con, "me", BOOKS[:3], "on")
    con.close()
    books = answer(capsys, "status", "--json", computer=computer)["books"]
    assert (books["on"], books["next"]) == (3, 3)  # not matched yet: the next sync looks them up


def test_books_answers_every_book_with_its_row_and_details(home, capsys, monkeypatch):
    from kobo_hardcover_sync.web import covers

    computer = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    assert answer(capsys, "books", "--json", computer=computer)["books"] == []  # nothing read from a Kobo yet
    kobo(home)
    runner.sync(computer, LOCAL)
    con = state.connect(str(home / "state" / "state.db"))
    state.set_mode(con, "me", BOOKS[:3], "on")
    con.execute("update book set image_id = 'cover-' || substr(content_id, -1) where content_id in (?, ?)", BOOKS[:2])
    con.commit()
    con.close()
    found = answer(capsys, "books", "--json", computer=computer)
    same_shape(found, sample("books.json"))
    books = found["books"]
    assert len(books) == 9 and all(b["cover"] == "" for b in books)  # none fetched yet
    on = [b for b in books if b["syncs"]]
    assert len(on) == 3 and all("on" in b["filters"] and b["status"]["kind"] == "next" for b in on)
    for each in found["sorts"]:
        assert sorted(each["order"]) == list(range(9)), each["key"]
    newest = found["sorts"][0]
    assert newest["key"] == "last_read" and newest["order"] == list(range(9))  # the list itself comes newest read first
    assert [k for k, _ in found["words"]["legend"]] == ["next", "wait", "ok", "stet", "warn", "err", "none"]

    fetched = []
    monkeypatch.setattr(covers, "download", lambda image_id, size="thumb": fetched.append(image_id) or b"\xff\xd8jpeg")
    with_covers = answer(capsys, "books", "--covers", "--json", computer=computer)["books"]
    assert sorted(fetched) == sorted({f"cover-{c[-1]}" for c in BOOKS[:2]})  # only the books with a cover on Kobo
    assert [os.path.exists(b["cover"]) for b in with_covers if b["cover"]] == [True] * len(fetched)
    answer(capsys, "books", "--covers", "--json", computer=computer)
    assert len(fetched) == len(set(BOOKS[:2]))  # kept: not fetched again

    cli.main(["books"], computer=computer)
    assert "Made-up" in capsys.readouterr().out  # in a terminal: the titles, each with its status line

    config.save(config.Config(server="https://kobo.example.org"))
    with pytest.raises(SystemExit, match="no upload token: run setup again"):  # server mode asks the server, with this computer's token
        cli.main(["books", "--json"], computer=computer)


def test_book_changes_what_the_page_changes_and_answers_the_book(home, capsys, monkeypatch):
    from kobo_hardcover_sync.computer.platform import HARDCOVER
    from kobo_hardcover_sync.engine import hardcover
    from tests.test_hardcover import FakeHC
    from tests.test_local import TOKEN

    computer = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    kobo(home)
    runner.sync(computer, LOCAL)
    one, two = BOOKS[:2]
    hits = [{"book_id": 77, "title": "Made-up Book 0", "pages": 210, "authors": ["Someone"], "also": ["x"]}]
    hc = FakeHC(search={"Made-up": hits})
    real = hardcover.Client

    def client(token, **kw):
        real(token)  # refuses no token as Hardcover's client does
        return hc

    monkeypatch.setattr(hardcover, "Client", client)

    found = answer(capsys, "book", one, "--sync", "on", "--json", computer=computer)
    same_shape(found, sample("book.json"))
    assert found["book"]["syncs"] and "on" in found["book"]["filters"] and found["books"]["on"] == 1

    changed = answer(capsys, "book", one, "--state", "finished", "--date", "2026-10-01", "--json", computer=computer)["book"]
    assert (changed["state"], changed["state_date"]) == ("finished", "2026-10-01")
    with pytest.raises(SystemExit, match="date must be YYYY-MM-DD"):
        cli.main(["book", one, "--state", "finished", "--date", "1 Oct"], computer=computer)
    assert answer(capsys, "book", one, "--state", "want", "--date", "2026-10-01", "--json", computer=computer)["book"]["state_date"] == ""

    # A match: looked for on Hardcover, then one of what it found is taken.
    with pytest.raises(SystemExit, match="Not connected to Hardcover"):
        cli.main(["book", one, "--search", "Made-up Book"], computer=computer)
    computer.set_secret(HARDCOVER, TOKEN)
    looked = answer(capsys, "book", one, "--search", "Made-up Book", "--json", computer=computer)["book"]
    assert looked["details"]["candidates"] == [{"id": 77, "title": "Made-up Book 0", "author": "Someone"}]
    with pytest.raises(SystemExit, match="not one of the books it could be"):
        cli.main(["book", one, "--pick", "78"], computer=computer)
    picked = answer(capsys, "book", one, "--pick", "77", "--json", computer=computer)["book"]
    assert picked["details"]["link"] == "https://hardcover.app/id/book/77" and picked["details"]["candidates"] == []
    with pytest.raises(SystemExit, match="has its match already"):
        cli.main(["book", one, "--search", "Made-up"], computer=computer)

    # Off the shelf: Hardcover is asked to delete it, and the book stops syncing.
    con = state.connect(str(home / "state" / "state.db"))
    con.execute("update book set last_sent=? where content_id=?", (json.dumps({"user_book_id": 501, "status": "read"}), one))
    con.commit()
    gone = answer(capsys, "book", one, "--remove", "--json", computer=computer)["book"]
    assert ("delete_ub", 501) in hc.calls and not gone["syncs"] and not gone["details"]["on_shelf"]

    with pytest.raises(SystemExit, match="no book with the id"):
        cli.main(["book", "nothing-like-it", "--json"], computer=computer)

    # Set all, through the page's filter and search; only while the list holds what was counted.
    with pytest.raises(SystemExit, match="holds 9 books now, not 8: nothing was changed"):
        cli.main(["books", "--sync", "on", "--filter", "all", "--expect", "8"], computer=computer)
    assert sum(b["syncs"] for b in answer(capsys, "books", "--json", computer=computer)["books"]) == 0
    every = answer(capsys, "books", "--sync", "on", "--filter", "all", "--expect", "9", "--json", computer=computer)["books"]
    assert all(b["syncs"] for b in every)
    answer(capsys, "books", "--sync", "off", "--filter", "all", "--search", "Made-up Book 1", "--json", computer=computer)
    off = {b["id"] for b in answer(capsys, "books", "--json", computer=computer)["books"] if not b["syncs"]}
    assert two in off and one not in off
    with pytest.raises(SystemExit, match="--filter is one of"):
        cli.main(["books", "--sync", "on", "--filter", "mine"], computer=computer)


def test_the_first_run_and_going_live_in_local_mode(home, capsys):
    from kobo_hardcover_sync.computer.platform import HARDCOVER
    from tests.test_local import TOKEN

    computer = FakeComputer(home / "Volumes")
    computer.in_app = True
    config.save(LOCAL)
    kobo(home)
    said = runner.sync(computer, LOCAL).message
    assert said.endswith("Not connected to Hardcover yet: connect in the app.")  # the app's words, where there is no page to go to
    first = answer(capsys, "books", "--json", computer=computer)["first_run"]
    assert (first["on"], first["connected"], first["steps"]) == (0, False, ["Connect to Hardcover", "Pick your books", "Go live"])
    assert "Your Kobo sent 9 books" in first["text"]

    found = answer(capsys, "settings", "--json", computer=computer)
    same_shape(found, sample("settings.json"))
    assert found["live"] is False
    with pytest.raises(SystemExit, match="connect to Hardcover first"):
        cli.main(["settings", "--set", "live=true"], computer=computer)
    computer.set_secret(HARDCOVER, TOKEN)
    assert answer(capsys, "books", "--json", computer=computer)["first_run"]["connected"] is True
    assert answer(capsys, "settings", "--set", "live=true", "--json", computer=computer)["live"] is True
    assert answer(capsys, "books", "--json", computer=computer)["first_run"] is None  # going live ends it
    assert answer(capsys, "status", "--json", computer=computer)["books"]["live"] is True
    assert answer(capsys, "settings", "--set", "live=false", "--json", computer=computer)["live"] is False


def test_in_server_mode_the_books_come_from_the_server_for_this_computers_reader(mac, home, server, capsys, monkeypatch):  # noqa: F811
    from cryptography.fernet import Fernet

    from kobo_hardcover_sync.engine import hardcover
    from kobo_hardcover_sync.server import accounts
    from kobo_hardcover_sync.web import covers
    from tests.test_hardcover import FakeHC

    runner.sync(mac, config.load())  # the Kobo's books, sent to the server for sam
    found = answer(capsys, "books", "--json", computer=mac)
    same_shape(found, sample("books.json"))
    assert len(found["books"]) == 9 and found["first_run"]["connected"] is False and not found["live"]
    one, two = BOOKS[:2]

    # Covers: the server's, kept on this computer; fetched once, and only with --covers.
    srv = state.connect(os.path.join(server.data, "state.db"))
    srv.execute("update book set image_id = 'cover-' || substr(content_id, -1) where content_id in (?, ?)", (one, two))
    srv.commit()
    fetched = []
    monkeypatch.setattr(covers, "download", lambda image_id, size="thumb": fetched.append(image_id) or b"\xff\xd8jpeg")
    assert all(b["cover"] == "" for b in answer(capsys, "books", "--json", computer=mac)["books"])
    shown = [b["cover"] for b in answer(capsys, "books", "--covers", "--json", computer=mac)["books"] if b["cover"]]
    assert len(shown) == 2 and all(c.startswith(str(home / "state" / "server-covers")) and os.path.exists(c) for c in shown)
    assert len([b for b in answer(capsys, "books", "--covers", "--json", computer=mac)["books"] if b["cover"]]) == 2
    assert len(fetched) == 2  # kept: not asked for again

    # Changes, as in local mode, made on the server.
    changed = answer(capsys, "book", one, "--sync", "on", "--state", "finished", "--date", "2026-10-01", "--json", computer=mac)
    same_shape(changed, sample("book.json"))
    assert changed["book"]["syncs"] and changed["book"]["state_date"] == "2026-10-01" and changed["books"]["on"] == 1
    assert changed["book"]["cover"].startswith(str(home / "state" / "server-covers"))
    assert srv.execute("select mode from book where reader='sam' and content_id=?", (one,)).fetchone()[0] == "on"
    with pytest.raises(SystemExit, match="date must be YYYY-MM-DD"):
        cli.main(["book", one, "--state", "finished", "--date", "1 Oct"], computer=mac)
    with pytest.raises(SystemExit, match="no book with the id"):
        cli.main(["book", "nothing-like-it", "--json"], computer=mac)
    with pytest.raises(SystemExit, match="holds 9 books now, not 8: nothing was changed"):
        cli.main(["books", "--sync", "on", "--filter", "all", "--expect", "8"], computer=mac)
    assert all(
        b["syncs"] for b in answer(capsys, "books", "--sync", "on", "--filter", "all", "--expect", "9", "--json", computer=mac)["books"]
    )

    # A match and going live need sam's Hardcover connection, which is on the server.
    with pytest.raises(SystemExit, match="Connect to Hardcover first"):
        cli.main(["settings", "--set", "live=true"], computer=mac)
    monkeypatch.setenv("KHS_SECRET_KEY", Fernet.generate_key().decode())
    accounts.set_token(srv, "sam", "hc-token", "sam")
    srv.execute("update book set hc_book_id=null, hc_how='none' where reader='sam' and content_id=?", (two,))
    srv.commit()
    hits = [{"book_id": 77, "title": "Made-up Book 1", "pages": 210, "authors": ["Someone"], "also": []}]
    monkeypatch.setattr(hardcover, "Client", lambda token, **kw: FakeHC(search={"Made-up": hits}))
    looked = answer(capsys, "book", two, "--search", "Made-up Book", "--json", computer=mac)["book"]
    assert looked["details"]["candidates"] == [{"id": 77, "title": "Made-up Book 1", "author": "Someone"}]
    assert (
        answer(capsys, "book", two, "--pick", "77", "--json", computer=mac)["book"]["details"]["link"] == "https://hardcover.app/id/book/77"
    )
    aside = answer(capsys, "book", two, "--not-now", "--json", computer=mac)  # the tip is put aside on the server
    assert aside["tip"] is None or aside["tip"]["id"] != two
    assert srv.execute("select count(*) from tip_aside where reader='sam' and content_id=?", (two,)).fetchone()[0] == 1
    went = answer(capsys, "settings", "--set", "live=true", "--json", computer=mac)
    assert (went["live"], went["hardcover_connected"], went["hardcover_user"]) == (True, True, "sam")
    assert answer(capsys, "books", "--json", computer=mac)["first_run"] is None  # going live ends it
    srv.close()

    # Only this computer's token opens them: never the proxy's headers, and not a token the server does not know.
    assert server.page.get("/api/app/books").status_code == 401
    mac.set_secret(UPLOAD, "u" * 64)
    with pytest.raises(SystemExit, match="does not know this computer"):
        cli.main(["books", "--json"], computer=mac)


def test_open_at_a_book_lands_on_its_row(home, monkeypatch):
    from kobo_hardcover_sync.computer import page

    computer = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    monkeypatch.setattr(page, "link", lambda: "http://127.0.0.1:5000/?k=key")
    cli.main(["open", "--book", "file:///mnt/onboard/a b.epub"], computer=computer)
    assert computer.opened == [
        "http://127.0.0.1:5000/?k=key&at=file%3A%2F%2F%2Fmnt%2Fonboard%2Fa%20b.epub#b-file%3A%2F%2F%2Fmnt%2Fonboard%2Fa%20b.epub"
    ]


def test_doctor_answers_with_its_checks_and_says_when_something_stops_a_sync(mac, home, capsys):
    found = answer(capsys, "doctor", "--json", computer=mac, exits=None)
    same_shape(found, sample("doctor.json"))
    assert found["problems"] == 0 and {c["group"] for c in found["checks"]} >= {"This computer", "Your Kobo"}
    os.remove(home / "state" / "config.toml")
    broken = answer(capsys, "doctor", "--json", computer=mac, exits=1)
    assert broken["problems"] == 1 and broken["checks"][0]["what"] == "Setup" and broken["checks"][0]["state"] == "fail"


def test_history_answers_newest_first_and_reads_in_a_terminal(mac, home, capsys):
    assert answer(capsys, "history", "--json", computer=mac) == {"schema": 1, "syncs": []}
    runner.sync(mac, config.load(), trigger="mount")
    runner.sync(mac, config.load(), trigger="app")
    found = answer(capsys, "history", "--json", computer=mac)
    same_shape(found, sample("history.json"))
    assert [s["trigger"] for s in found["syncs"]] == ["app", "mount"]
    cli.main(["history"], computer=mac)
    text = capsys.readouterr().out
    assert "Sync now. Nothing new." in text and "Kobo plugged in. Kobo synced: 9 books updated." in text


def test_settings_answer_and_change_one_at_a_time(mac, home, capsys):
    found = answer(capsys, "settings", "--json", computer=mac)
    same_shape(found, sample("settings.json"))
    assert found["upload_token_hash"] == cli._token_hash("t" * 64) and found["settings"]["eject_after_sync"] is False
    changed = answer(capsys, "settings", "--set", "eject_after_sync=true", "--set", "verbose_log=TRUE", "--json", computer=mac)
    assert changed["settings"]["eject_after_sync"] is True and changed["settings"]["verbose_log"] is True
    assert config.load().eject_after_sync and config.load().server  # the rest stays as it was
    for wrong, said in (
        ("server=https://elsewhere.example", "cannot be set here"),
        ("eject_after_sync=yes", "true or false, not 'yes'"),
        ("eject_after_sync", "true or false, not ''"),
    ):
        with pytest.raises(SystemExit) as refused:
            cli.main(["settings", "--set", wrong], computer=mac)
        assert said in str(refused.value.code)
    assert config.load().server and config.load().eject_after_sync
    os.remove(home / "state" / "config.toml")
    with pytest.raises(SystemExit, match="not set up yet"):
        cli.main(["settings", "--set", "eject_after_sync=true"], computer=mac)


def test_a_sync_with_steps_says_each_step_then_the_outcome(mac, home, capsys):
    cli.main(["sync", "--trigger", "app", "--steps"], computer=mac)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    wanted = [json.loads(line) for line in (SAMPLES / "steps.jsonl").read_text().splitlines()]
    for line in lines[:-1]:
        same_shape(line, wanted[0], "step")
    same_shape(lines[-1], wanted[-1], "done")
    assert [line["step"] for line in lines[:-1]][:1] == ["Kobo"] and lines[-1]["done"] == {
        "ok": True,
        "title": "Kobo synced",
        "message": "9 books updated.",
    }
    assert "Made-up Book" not in json.dumps(lines)  # no book named: the window shows steps, not titles


# ---------- what Settings changes ----------
def test_setup_with_check_asks_the_server_first_and_changes_nothing_when_it_does_not_answer(home, server, capsys):  # noqa: F811
    computer = FakeComputer(home / "Volumes")
    config.save(config.Config())  # local mode, about to switch
    for wrong, why in (
        (server.url + "/not-here", "answered 404"),  # a typo in the path: something answers, but not as the tool would
        ("http://127.0.0.1:9", "Could not reach"),
    ):
        with pytest.raises(SystemExit) as refused:
            cli.main(["setup", "--server", wrong, "--check", "--no-trigger"], computer=computer)
        assert why in str(refused.value) and str(refused.value).endswith("Nothing was changed.")
        assert config.load().mode == "local" and not computer.secret(UPLOAD)

    cli.main(["setup", "--server", server.url, "--check", "--no-trigger"], computer=computer)
    assert config.load().server == server.url
    assert "Paste this computer's hash" in capsys.readouterr().out  # the server does not know it yet

    register(server, computer, computer.secret(UPLOAD))
    cli.main(["setup", "--server", server.url, "--check", "--no-trigger"], computer=computer)
    assert "knows this computer already" in capsys.readouterr().out
    cli.main(["setup", "--new-token", "--check", "--no-trigger"], computer=computer)
    assert "Paste this computer's hash" in capsys.readouterr().out  # a new token is a new device to the server
