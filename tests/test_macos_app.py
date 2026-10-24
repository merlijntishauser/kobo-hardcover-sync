"""The signed Mac app (docs/macos-app.md), from the tool's side: the app owns
the trigger, a Mac keeps one trigger, and the app looks for a newer
version once a day. The wrapper itself only runs on a Mac; what it and the
tool must agree on is checked here against its files."""

import fcntl
import io
import json
import os
import pathlib
import plistlib
import re

import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, macos, runner, update
from tests import said
from tests.test_computer import FakeComputer, FakeMac, plug_in, register, server  # noqa: F401 (the fixture)
from tests.test_local import ORIGIN, local  # noqa: F401 (the fixture)

ROOT = pathlib.Path(__file__).resolve().parents[1]
MACOS = ROOT / "packaging" / "macos"
AGENT = "org.gargleblaster.kobo-hardcover-sync.agent"
APP_AGENT = "org.gargleblaster.kobo-hardcover-sync.app.agent"


@pytest.fixture
def the_app(home, monkeypatch):
    """Started by the app: KHS_APP says where it is."""
    app = home / "Applications" / "Kobo Hardcover Sync.app"
    app.mkdir(parents=True)
    monkeypatch.setenv("KHS_APP", str(app))
    return app


def tool(home):
    t = home / "bin" / "kobo-hardcover-sync"
    t.parent.mkdir(exist_ok=True)
    t.write_text("#!/bin/sh\n")
    t.chmod(0o755)
    return str(t)


# ---------- one trigger per Mac ----------
def test_only_a_real_app_counts(home, monkeypatch):
    assert macos.app_path() == ""
    monkeypatch.setenv("KHS_APP", str(home))  # a folder, but not an app
    assert macos.app_path() == "" and not macos.MacOS(run=FakeMac(), home=str(home)).in_app
    monkeypatch.setenv("KHS_APP", str(home / "Gone.app"))
    assert macos.app_path() == ""


def test_setting_up_the_app_takes_the_trigger_over_from_homebrew(home, the_app, monkeypatch, capsys):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    # Homebrew's installation came first: its small app and launch agent.
    monkeypatch.delenv("KHS_APP")
    mac.install_trigger(tool(home))
    assert os.path.isdir(mac.app) and os.path.isfile(mac.plist) and fake.loaded == {AGENT}
    monkeypatch.setenv("KHS_APP", str(the_app))
    fake.loaded.add(APP_AGENT)  # what the app registered before it ran setup

    cli.main(["setup", "--local"], computer=mac)
    out = said(capsys)
    assert not os.path.exists(mac.app) and not os.path.exists(mac.plist) and fake.loaded == {APP_AGENT}
    assert not os.path.exists(os.path.join(mac.state, "command"))
    assert "The trigger of the other installation (KoboHardcoverSync.app) is removed" in out
    assert "macOS asks whether it may use files on a removable volume" in out
    assert "ok Trigger Plugging in the Kobo starts a sync in Kobo Hardcover Sync.app" in out
    # Words for someone without a terminal.
    assert "Connect to Hardcover on the page, under Settings" in out and "`kobo-hardcover-sync" not in out
    assert fake.ran("osacompile") == [fake.ran("osacompile")[0]]  # only Homebrew's, before

    # Homebrew's setup again, now that the app is there: it leaves the trigger to the app.
    monkeypatch.delenv("KHS_APP")
    cli.main(["setup"], computer=mac)
    again = said(capsys)
    assert not os.path.exists(mac.plist) and len(fake.ran("osacompile")) == 1 and fake.loaded == {APP_AGENT}
    assert "ok Trigger Plugging in the Kobo starts a sync in Kobo Hardcover Sync.app" in again
    # Uninstalling from there cannot take the app's agent away, and says so.
    assert mac.remove_trigger() == ["The trigger of Kobo Hardcover Sync.app belongs to the app: move the app to the Bin to remove it."]
    assert fake.loaded == {APP_AGENT}


def test_the_app_without_its_launch_agent(home, the_app):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    works, found = mac.trigger_state()
    assert not works and "Login Items" in found
    fake.loaded.add(APP_AGENT)
    assert mac.trigger_state() == (True, "Plugging in the Kobo starts a sync in Kobo Hardcover Sync.app (its launch agent is loaded).")
    # When macOS keeps the Kobo closed, the app is named, not the small one.
    words = mac.cannot_read(by_hand=False)
    assert "Kobo Hardcover Sync read the Kobo" in words and "Removable Volumes" in words and "KoboHardcoverSync.app" not in words


# ---------- a newer version ----------
class GitHub:
    """urlopen for update.ask: answers with a tag, and counts."""

    def __init__(self, tag="v0.12.0", fail=None):
        self.tag, self.fail, self.asked = tag, fail, []

    def __call__(self, req, timeout):
        self.asked.append((req.full_url, timeout, dict(req.header_items())))
        if self.fail:
            raise self.fail
        return io.BytesIO(json.dumps({"tag_name": self.tag, "html_url": "https://example.org/elsewhere"}).encode())


def test_the_app_asks_once_a_day_and_only_the_app(home, the_app, monkeypatch):
    os.makedirs(home / "state")
    config.save(config.Config())
    gh, now = GitHub(), [1_000_000.0]
    update.now_and_then(gh, lambda: now[0])
    assert [a[:2] for a in gh.asked] == [("https://api.github.com/repos/merlijntishauser/kobo-hardcover-sync/releases/latest", 5)]
    assert gh.asked[0][2]["User-agent"].startswith("kobo-hardcover-sync/")
    assert update.newer("0.11.0") == {
        "version": "0.12.0",
        "link": "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v0.12.0",
    }
    assert update.newer("0.12.0.dev0") == update.newer("0.11.0") and update.newer("0.12.0") is None and update.newer("1.0.0") is None
    now[0] += 3600
    update.now_and_then(gh, lambda: now[0])
    assert len(gh.asked) == 1  # not again the same day
    now[0] += 24 * 3600
    gh.fail = OSError("no network")
    update.now_and_then(gh, lambda: now[0])
    assert len(gh.asked) == 2 and update.newer("0.11.0")["version"] == "0.12.0"  # a failure forgets nothing
    # Switched off: it does not ask, and says nothing.
    cfg = config.load()
    cfg.check_for_updates = False
    config.save(cfg)
    assert "check_for_updates = false" in open(cfg.path).read()
    now[0] += 24 * 3600
    update.now_and_then(gh, lambda: now[0])
    assert len(gh.asked) == 2 and update.newer("0.11.0") is None
    # Not the app (Homebrew, PyPI): never.
    cfg.check_for_updates = True
    config.save(cfg)
    assert "check_for_updates" not in open(cfg.path).read()
    monkeypatch.delenv("KHS_APP")
    update.now_and_then(gh, lambda: now[0])
    assert len(gh.asked) == 2 and update.newer("0.11.0") is None


@pytest.mark.parametrize("tag", ["0.12.0", "v0.12", "v0.12.0-rc1", "v0.12.0\n", "v99999.0.0", "", None, 12])
def test_only_a_plain_version_is_taken_from_the_answer(home, the_app, tag):
    os.makedirs(home / "state")
    config.save(config.Config())
    update.now_and_then(GitHub(tag), lambda: 1_000_000.0)
    assert update.kept()["latest"] == "" and update.newer("0.0.1") is None


def test_a_triggered_sync_in_the_app_asks_after_the_notification(home, the_app, monkeypatch):
    order = []
    mac = macos.MacOS(run=FakeMac(), home=str(home), volumes=str(home / "Volumes"))
    monkeypatch.setattr(update, "now_and_then", lambda: order.append("asked"))
    monkeypatch.setattr(mac, "notify", lambda title, message: order.append("notified"))
    monkeypatch.setattr(runner, "sync", lambda computer, **kw: runner.Outcome(ok=False, message="It went wrong."))
    with pytest.raises(SystemExit):  # a failed sync asks too
        cli.main(["sync", "--trigger", "mount"], computer=mac)
    assert order == ["notified", "asked"]
    monkeypatch.delenv("KHS_APP")  # Homebrew's trigger: never
    order.clear()
    with pytest.raises(SystemExit):
        cli.main(["sync", "--trigger", "mount"], computer=mac)
    assert order == ["notified"]


def test_sync_now_in_the_app_always_answers(home, server):  # noqa: F811
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    cfg = config.Config(server=server.url)
    clicked = runner.sync(mac, cfg, trigger="app")
    assert (clicked.ok, clicked.message) == (True, "No Kobo found: plug it in and tap Connect on the Kobo.")
    assert runner.sync(mac, cfg, trigger="mount") == runner.Outcome(True)  # some other volume: still nothing said

    plug_in(home)
    assert runner.sync(mac, cfg, trigger="app").message == "9 books updated."
    again = runner.sync(mac, cfg, trigger="app")
    assert (again.ok, again.message) == (True, "Nothing new since the last sync.")
    # The app's window shows the last news, not that nothing was new.
    assert open(home / "state" / "last-message.txt").read().startswith("Kobo synced\n9 books updated.\n")
    assert runner.sync(mac, cfg, trigger="mount").message == ""

    with open(home / "state" / "sync.lock", "w") as held:  # a sync the Kobo started is still running
        fcntl.flock(held, fcntl.LOCK_EX)
        busy = runner.sync(mac, cfg, trigger="app")
    assert (busy.ok, busy.message) == (True, "A sync is already running. It says so when it is done.")


def test_the_page_shows_the_version_and_the_setting_in_the_app(local, home, the_app, monkeypatch):  # noqa: F811
    web, mac, inside = local
    assert "Looks for a newer version" not in inside.get("/settings").text  # not the app: no such setting
    mac.in_app = True
    settings = inside.get("/settings").text
    assert "Kobo Hardcover Sync " in settings and "Looks for a newer version once a day" in settings and "is out" not in settings
    with open(os.path.join(config.state_dir(), "update.json"), "w") as fh:
        json.dump({"checked": 1, "latest": "99.0.0"}, fh)
    settings = inside.get("/settings").text
    assert (
        "Version 99.0.0 is out." in settings
        and 'href="https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v99.0.0"' in settings
    )
    r = inside.post("/settings/updates", data={"check": "0"}, headers=ORIGIN, follow_redirects=False)
    assert r.headers["location"] == "/settings?ok=updates_off" and config.load().check_for_updates is False
    settings = inside.get("/settings").text
    assert "Does not look for a newer version" in settings and "is out" not in settings
    inside.post("/settings/updates", data={"check": "1"}, headers=ORIGIN)
    assert config.load().check_for_updates is True
    assert inside.post("/settings/updates", data={"check": "0"}).status_code == 403  # from another page: refused


# ---------- what the wrapper and the tool agree on ----------
def test_the_wrapper_and_the_tool_use_the_same_names(home):
    swift = (MACOS / "KoboHardcoverSync.swift").read_text()
    with open(MACOS / "Info.plist", "rb") as fh:
        info = plistlib.load(fh)
    with open(MACOS / f"{APP_AGENT}.plist", "rb") as fh:
        agent = plistlib.load(fh)
    assert info["CFBundleIdentifier"] == macos.BUNDLE_ID + ".app" and info["CFBundleName"] == macos.SIGNED_APP[:-4]
    assert info["LSUIElement"] is True and info["NSRemovableVolumesUsageDescription"]
    assert agent["Label"] == macos.SIGNED_LABEL and agent["StartOnMount"] is True
    assert agent["EnvironmentVariables"] == {"KHS_TRIGGER": "mount"}
    assert agent["BundleProgram"] == f"Contents/MacOS/{macos.SIGNED_APP[:-4]}"
    for must in (f'"{macos.SIGNED_LABEL}.plist"', '"KHS_APP"', '"KHS_NOTIFY"', '"stdout"', '"NOTIFY|"', '"KHS_TRIGGER"', '"mount"'):
        assert must in swift, must
    for file in ("last-message.txt", "update.json", "config.toml"):
        assert f'"{file}"' in swift, file
    # The window reads the time of the last sync back as "d MMM yyyy, HH:mm".
    os.makedirs(config.state_dir())
    runner.remember(runner.Outcome(True, "Kobo synced", "11 books updated."))
    title, said, blank, stamp = (pathlib.Path(config.state_dir()) / "last-message.txt").read_text().splitlines()
    assert (title, said, blank) == ("Kobo synced", "11 books updated.", "")
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}", stamp)
    assert '"d MMM yyyy, HH:mm"' in swift and '"en_US_POSIX"' in swift
    assert f'"{config.APP}"' in swift  # the state folder
    for args in ('"sync", "--trigger", "mount"', '"sync", "--trigger", "app"', '"setup", "--local"', '"setup", "--server"', '"open"'):
        assert args in swift, args
