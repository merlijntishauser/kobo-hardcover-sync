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

import pytest

from lastread import cli, doctor
from lastread.computer import config, macos, runner, update
from lastread.engine import hardcover
from tests import said
from tests.test_app_answers import same_shape, sample
from tests.test_computer import FakeComputer, FakeMac, plug_in, register, server  # noqa: F401 (the fixture)
from tests.test_local import ORIGIN, local  # noqa: F401 (the fixture)

ROOT = pathlib.Path(__file__).resolve().parents[1]
MACOS = ROOT / "packaging" / "macos"
AGENT = "org.gargleblaster.kobo-hardcover-sync.agent"
APP_AGENT = "org.gargleblaster.kobo-hardcover-sync.app.agent"


@pytest.fixture
def the_app(home, monkeypatch):
    """Started by the app: KHS_APP says where it is."""
    app = home / "Applications" / "Lastread.app"
    app.mkdir(parents=True)
    monkeypatch.setenv("KHS_APP", str(app))
    return app


def tool(home):
    t = home / "bin" / "lastread"
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
    assert "ok Trigger Plugging in the Kobo starts a sync in Lastread.app" in out
    # Words for someone without a terminal.
    assert "Connect to Hardcover on the page, under Settings" in out and "`lastread" not in out
    assert fake.ran("osacompile") == [fake.ran("osacompile")[0]]  # only Homebrew's, before

    # Homebrew's setup again, now that the app is there: it leaves the trigger to the app.
    monkeypatch.delenv("KHS_APP")
    cli.main(["setup"], computer=mac)
    again = said(capsys)
    assert not os.path.exists(mac.plist) and len(fake.ran("osacompile")) == 1 and fake.loaded == {APP_AGENT}
    assert "ok Trigger Plugging in the Kobo starts a sync in Lastread.app" in again
    # Uninstalling from there cannot take the app's agent away, and says so.
    assert mac.remove_trigger() == [
        "The trigger of Lastread.app belongs to the app: choose Remove… in its Settings, or move it to the Bin."
    ]
    assert fake.loaded == {APP_AGENT}


def test_the_app_without_its_launch_agent(home, the_app):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    works, found = mac.trigger_state()
    assert not works and "Login Items" in found
    fake.loaded.add(APP_AGENT)
    assert mac.trigger_state() == (True, "Plugging in the Kobo starts a sync in Lastread.app (its launch agent is loaded).")
    # When macOS keeps the Kobo closed, the app is named, not the small one.
    words = mac.cannot_read(by_hand=False)
    assert "Lastread read the Kobo" in words and "Removable Volumes" in words and "KoboHardcoverSync.app" not in words


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
    assert gh.asked[0][2]["User-agent"].startswith("lastread/")
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


def test_check_now_asks_also_when_the_daily_look_is_off_and_keeps_the_answer(home, the_app, monkeypatch, capsys):
    os.makedirs(home / "state")
    config.save(config.Config(check_for_updates=False))  # someone who clicked asked, whatever the daily look says
    gh = GitHub("v0.13.0")
    found = update.now(gh, lambda: 1_000_000.0, current="0.12.1")
    # The link is built from the version, never taken from the answer.
    assert found == {
        "version": "0.12.1",
        "latest": "0.13.0",
        "newer": True,
        "link": "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v0.13.0",
        "problem": "",
    }
    assert update.kept() == {"checked": 1_000_000.0, "latest": "0.13.0"} and len(gh.asked) == 1
    gh.fail = OSError("no network")
    found = update.now(gh, lambda: 1_000_100.0, current="0.13.0")
    assert (found["latest"], found["newer"], found["link"]) == ("0.13.0", False, "") and "GitHub did not answer" in found["problem"]

    monkeypatch.setattr(update, "ask", lambda fetch=None: "99.0.0")  # newer than this tool, whichever it is
    mac = macos.MacOS(run=FakeMac(), home=str(home))
    cli.main(["update", "--json"], computer=mac)
    same_shape(json.loads(capsys.readouterr().out), sample("update.json"))
    cli.main(["update"], computer=mac)
    out = capsys.readouterr().out
    assert "99.0.0 is out" in out and "Download it there." in out


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
    assert "Lastread " in settings and "Looks for a newer version once a day" in settings and "is out" not in settings
    with open(os.path.join(config.state_dir(), "update.json"), "w") as fh:
        json.dump({"checked": 1, "latest": "99.0.0"}, fh)
    settings = inside.get("/settings").text
    assert (
        "Version 99.0.0 is out." in settings
        and 'href="https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v99.0.0"' in settings
    )
    r = inside.post("/settings/updates", data={"check": "0"}, headers=ORIGIN, follow_redirects=False)
    assert r.headers["location"] == "/settings?ok=updates_off#computer" and config.load().check_for_updates is False
    settings = inside.get("/settings").text
    assert "Does not look for a newer version" in settings and "is out" not in settings
    inside.post("/settings/updates", data={"check": "1"}, headers=ORIGIN)
    assert config.load().check_for_updates is True
    assert inside.post("/settings/updates", data={"check": "0"}).status_code == 403  # from another page: refused


# ---------- what the wrapper and the tool agree on ----------
def test_the_chain_is_built_from_doctors_groups_and_the_steps_of_a_sync():
    chain = (MACOS / "Chain.swift").read_text()
    for group in (doctor.COMPUTER, doctor.KOBO, doctor.HARDCOVER, "Also"):
        assert f'"{group}"' in chain, group
    checks = {what for whats in doctor.GROUPS.values() for what in whats}
    for what in ("Server", "Trigger", "Kobo", "Hardcover"):  # a link of its own, or the check that says a link is there
        assert what in checks and f'"{what}"' in chain, what
    steps = (ROOT / "src" / "lastread" / "computer" / "runner.py").read_text()
    for step in ("Kobo", "Collection", "Upload", "Hardcover", "Matches"):  # where linkOf puts them
        assert f'"{step}"' in steps and f'"{step}"' in chain, step


def test_the_wrapper_and_the_tool_use_the_same_names():
    swift = "".join(p.read_text() for p in sorted(MACOS.glob("*.swift")))
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
    for file in ("update.json", "config.toml", "agent.log"):
        assert f'"{file}"' in swift, file
    assert f'"{hardcover.NEW_TOKEN_URL}"' in swift  # where the app sends someone to make a token
    assert f'"{config.APP}"' in swift  # the state folder
    for args in (
        '"sync", "--trigger", "mount"',
        '"sync", "--trigger", "app", "--steps"',
        '"status", "--json"',
        '"doctor", "--json"',
        '"history", "--json"',
        '"books", "--json"',
        '"books", "--covers", "--json"',
        '"open", "--book"',
        '"token", "--json"',
        '"token", "--paste", "--json"',
        '"settings", "--set", "live=true", "--json"',
        '["book", id]',
        '"--large-cover", "--json"',
        '"--sync", sync, "--filter", filter',
        '"--expect"',
        '"setup", "--local"',
        '"setup", "--server"',
        '"open"',
    ):
        assert args in swift, args


def test_the_pictures_are_what_art_py_draws(tmp_path, monkeypatch):
    """The SVGs beside art.py are its drawing, not edited by hand (and the PNGs are made from them)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("art", MACOS / "art.py")
    art = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(art)
    monkeypatch.setattr(art, "HERE", tmp_path)
    art.icon_composer()
    flat = art.flat_icon()
    assert flat == (MACOS / "AppIcon.svg").read_text()
    assert art.volume_icon() == (MACOS / "VolumeIcon.svg").read_text()
    assert art.window(flat) == (MACOS / "dmg-background.svg").read_text()
    for size in (16, 32):  # drawn for their size
        assert art.small_icon(size) == (MACOS / f"AppIcon-{size}.svg").read_text()
        assert art.small_volume(size) == (MACOS / f"VolumeIcon-{size}.svg").read_text()
    for name in ("icon.json", "Assets/reader.svg", "Assets/sync.svg"):
        assert (tmp_path / "AppIcon.icon" / name).read_text() == (MACOS / "AppIcon.icon" / name).read_text(), name
    for layer in ("reader.svg", "sync.svg"):  # neither filters nor gradients: actool draws flat, macOS lights the layers
        assert (MACOS / "AppIcon.icon" / "Assets" / layer).read_text().count("filter") == 0
        assert (MACOS / "AppIcon.icon" / "Assets" / layer).read_text().count("Gradient") == 0


def test_the_icon_and_the_disk_window_are_packed():
    with open(MACOS / "Info.plist", "rb") as fh:
        info = plistlib.load(fh)
    assert info["CFBundleIconFile"] == info["CFBundleIconName"] == "AppIcon"  # .icns before macOS 26, Assets.car from it
    build, package = (MACOS / "build.sh").read_text(), (MACOS / "package.sh").read_text()
    assert '"$here/AppIcon.icon"' in build and "Assets.car" in build
    for size in (16, 32):
        assert (MACOS / f"AppIcon-{size}.png").is_file() and f'"$here/AppIcon-{size}.png"' in build
        assert (MACOS / f"VolumeIcon-{size}.png").is_file() and f'"$here/VolumeIcon-{size}.png"' in package
    for file in ("dmg-background.png", "dmg-background@2x.png", "dmg.DS_Store", "VolumeIcon.png"):
        assert (MACOS / file).is_file() and f'"$here/{file}"' in package, file
    # Where dmg-layout.sh puts the two icons is where the move mark in the window is drawn.
    assert '"Lastread.app": (170, 190), "Applications": (470, 190)' in (MACOS / "dmg-layout.sh").read_text()
    layout = (MACOS / "dmg.DS_Store").read_bytes().replace(b"\x00", b"")
    if b"Kobo Hardcover Sync.app" in layout and b"Lastread.app" not in layout:
        pytest.xfail("dmg.DS_Store still places Kobo Hardcover Sync.app: run packaging/macos/dmg-layout.sh on a Mac")
    assert b"Lastread.app" in layout
