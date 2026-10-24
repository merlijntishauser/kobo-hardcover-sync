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
from tests.test_computer import FakeComputer, plug_in, register, server  # noqa: F401 (the fixture)

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
