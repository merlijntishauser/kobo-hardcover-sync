"""The log: two levels, and what is never in either."""

import json
import logging
import os

import pytest

from kobo_hardcover_sync import cli, logs
from kobo_hardcover_sync.computer import config, runner
from kobo_hardcover_sync.computer.platform import HARDCOVER
from kobo_hardcover_sync.engine import hardcover, state
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer
from tests.test_hardcover import FakeHC
from tests.test_local import LOCAL, TOKEN, catalogue, kobo, st


@pytest.fixture(autouse=True)
def no_handlers_left():
    yield
    logs._start([], False)


def log_of(home):
    with open(home / "state" / "agent.log") as fh:
        return fh.read()


def a_live_sync(home, **kw):
    """Three books go to Hardcover; one of them is refused."""
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, TOKEN)

    class OneRefused(FakeHC):
        def insert_user_book(self, obj):
            if obj["book_id"] == 102:
                raise hardcover.HardcoverError("Hardcover refused: this one, no", "refused")
            return super().insert_user_book(obj)

    hc = OneRefused(isbn=catalogue())
    runner.sync(mac, LOCAL, hardcover_client=hc)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:3], "on")
    con.execute("update reader set hardcover_live = 1 where name = 'me'")
    con.commit()
    os.unlink(home / "state" / "agent.log")
    return runner.sync(mac, kw.pop("cfg", LOCAL), hardcover_client=hc, **kw)


def test_the_normal_log_has_counts_and_no_titles(home, capsys):
    out = a_live_sync(home)
    assert out.message == "2 sent to Hardcover. 1 failed."
    log = log_of(home)
    assert "Made-up" not in log and TOKEN not in log  # no book, no token
    assert " info hardcover (live) for me: " not in log and " error hardcover (live) for me: {'status': 'errors'," in log
    assert "'sent': 2" in log and " warning a book could not be sent (refused); its row on the page says why" in log
    assert " info said: Kobo synced: 2 sent to Hardcover. 1 failed." in log
    assert all(line[:4].isdigit() and line[19] == " " for line in log.splitlines())  # every line starts with when
    assert capsys.readouterr().err == ""  # and nothing is printed


def test_the_verbose_log_names_the_books_and_still_no_token(home, capsys):
    a_live_sync(home, verbose=True)
    log = log_of(home)
    assert " detail sent 'Made-up Book 0': mark " in log and " detail not sent 'Made-up Book 2': Hardcover refused: this one, no" in log
    assert " detail sync started (by hand), Kobo: " in log and "Kobo Clara Colour, software 6.0.274403" in log
    assert TOKEN not in log
    assert capsys.readouterr().err == log  # a run by hand shows it as it goes


def test_verbose_for_every_run_is_a_setting(home, capsys, monkeypatch):
    cfg = config.Config(verbose_log=True)
    config.save(cfg)
    assert "verbose_log = true" in open(config.Config().path).read() and config.load().verbose_log is True
    a_live_sync(home, cfg=config.load(), trigger="mount")
    assert " detail sent 'Made-up Book 0'" in log_of(home) and capsys.readouterr().err == ""  # in the file only
    # And the switch that works everywhere, the server included.
    monkeypatch.setenv("KHS_LOG", "verbose")
    logs.to_stderr()
    logging.getLogger("kobo_hardcover_sync.engine.job").debug("a line per book")
    assert capsys.readouterr().err.endswith(" detail a line per book\n")
    monkeypatch.delenv("KHS_LOG")
    logs.to_stderr()
    logging.getLogger("kobo_hardcover_sync.engine.job").debug("a line per book")
    assert capsys.readouterr().err == ""


def test_a_request_to_hardcover_is_logged_without_what_it_carried(home):
    class Answer:
        status, headers = 200, {}

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(self.body).encode()

    def opener(req, timeout):
        asked = json.loads(req.data)["query"]
        if "me {" in asked:
            return Answer({"data": {"me": [{"id": 7, "username": "sam"}]}})
        return Answer({"data": {"search": {"results": {"hits": []}}}})

    logs.to_file(str(home / "state" / "agent.log"), verbose=True)
    client = hardcover.Client(TOKEN, opener=opener, sleep=lambda s: None)
    client.whoami()
    client.search("A Very Private Title")
    log = log_of(home)
    assert " detail hardcover me: 200 in " in log and " detail hardcover search: 200 in " in log
    assert TOKEN not in log and "Bearer" not in log and "Private" not in log


def test_the_log_does_not_grow_without_end(home, monkeypatch):
    monkeypatch.setattr(logs, "MAX_BYTES", 2000)
    path = str(home / "state" / "agent.log")
    logs.to_file(path)
    for n in range(200):
        logging.getLogger("kobo_hardcover_sync.computer.runner").info("line %s of a long life", n)
    assert sorted(os.listdir(home / "state")) == ["agent.log", "agent.log.1"]
    assert os.path.getsize(path) <= 2000 and "line 199 of a long life" in open(path).read()


def test_something_nobody_expected_is_said_and_written_down(home, monkeypatch, capsys):
    kobo(home)
    mac = FakeComputer(home / "Volumes")

    def broken(*a, **kw):
        raise RuntimeError("a bug")

    monkeypatch.setattr(runner, "_sync_here", broken)
    out = runner.sync(mac, LOCAL)
    assert (out.ok, out.title) == (False, "Kobo sync failed")
    assert out.message.startswith("Something went wrong that this tool did not expect (RuntimeError). The details are in ")
    assert str(home / "state" / "agent.log") in out.message and out.message.endswith("/kobo-hardcover-sync/issues")
    log = log_of(home)
    assert " error sync stopped by something unexpected" in log and "Traceback" in log and "RuntimeError: a bug" in log
    assert open(home / "state" / "last-message.txt").read().startswith("Kobo sync failed\nSomething went wrong")
    # The command ends with status 1 and the same words.
    config.save(config.Config())
    with pytest.raises(SystemExit) as ex:
        cli.main(["sync"], computer=mac)
    assert ex.value.code == 1 and "Kobo sync failed: Something went wrong" in capsys.readouterr().out
