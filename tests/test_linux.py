"""Desktop Linux: the seams, with the commands recorded where they need a
desktop (keyring, systemd, udisks), and for real where this machine can do
it (the private file, the whole tool against a folder that plays the Kobo,
the page as a process)."""

import os
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, linux, page, platform
from kobo_hardcover_sync.computer.platform import HARDCOVER, UPLOAD
from tests import said
from tests.kobo_fixture import BOOKS
from tests.test_computer import plug_in

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the Linux seams")
TOKEN = "eyJhbGciOi.made-up-hardcover-token.xyz"


class Desk:
    """subprocess.run and shutil.which for linux.Linux: a desktop that has
    the tools named in `tools`, a keyring that works or not, a user manager
    that works or not."""

    def __init__(self, tools=(), keyring_works=True, keyring_keeps=True, systemd_works=True):
        self.tools, self.keyring_works, self.systemd_works = set(tools), keyring_works, systemd_works
        self.keyring_keeps = keyring_keeps
        self.calls, self.keyring = [], {}

    def which(self, name):
        return "/usr/bin/" + name if name in self.tools else None

    def __call__(self, args, capture_output=True, text=True, input=None):
        self.calls.append((args, input))
        rc, out, err = 0, "", ""
        if args[0] == "secret-tool":
            key = tuple(a for a in args[2:] if a not in ("--label",) and not a.startswith("Kobo Hardcover Sync"))
            if not self.keyring_works:
                rc, err = 1, "secret-tool: Cannot autolaunch D-Bus without X11 $DISPLAY"
            elif args[1] == "store":
                if self.keyring_keeps:
                    self.keyring[key] = input
            elif args[1] == "lookup":
                rc, out = (0, self.keyring[key]) if key in self.keyring else (1, "")
            elif args[1] == "clear":
                self.keyring.pop(key, None)
        elif args[0] == "systemctl" and "enable" in args and not self.systemd_works:
            rc, err = 1, "Failed to connect to user scope bus via local transport: no medium found"
        elif args[0] == "findmnt":
            out = "/dev/sdb1\n"
        elif args[0] == "lsblk":
            out = "sdb\n"
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    def ran(self, tool):
        return [a for a, _ in self.calls if a[0] == tool]


def desk_computer(home, **kw):
    d = Desk(**kw)
    return linux.Linux(run=d, which=d.which, home=str(home), user="sam"), d


def test_this_platform_is_one_of_the_two():
    assert isinstance(platform.pick(), linux.Linux)


def test_the_kobo_is_found_where_the_desktop_mounts_it(home, monkeypatch):
    pc, _ = desk_computer(home)
    assert pc.volume_roots() == ["/run/media/sam", "/media/sam"] and pc.find_kobo() is None
    plug_in(home)
    monkeypatch.setattr(pc, "volume_roots", lambda: [str(home / "nothing"), str(home / "Volumes")])
    assert pc.find_kobo() == str(home / "Volumes" / "KOBOeReader")
    # Mounted by hand somewhere else: KHS_VOLUMES names more places to look.
    monkeypatch.setattr(pc, "volume_roots", lambda: ["/nonexistent"])
    assert pc.find_kobo() is None
    monkeypatch.setenv("KHS_VOLUMES", f"/also-nonexistent:{home / 'Volumes'}")
    assert pc.find_kobo() == str(home / "Volumes" / "KOBOeReader")


def test_without_a_keyring_the_secret_goes_to_a_private_file(home):
    for kw in ({}, {"tools": ("secret-tool",), "keyring_works": False}):  # no secret-tool at all; or one that cannot reach a keyring
        pc, desk = desk_computer(home, **kw)
        assert pc.secret(HARDCOVER) == ""
        pc.set_secret(HARDCOVER, TOKEN)
        path = home / "state" / "secrets.json"
        assert pc.secret(HARDCOVER) == TOKEN and stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE((home / "state").stat().st_mode) == 0o700
        assert pc.secret_place(HARDCOVER) == f"a private file on this computer ({path})"
        pc.set_secret(UPLOAD, "u" * 64)
        pc.delete_secret(HARDCOVER)
        assert pc.secret(HARDCOVER) == "" and pc.secret(UPLOAD) == "u" * 64  # the other one stays
        pc.delete_secret(UPLOAD)
        assert not path.exists()  # an empty file is not left lying around
        for args, _ in desk.calls:
            assert TOKEN not in " ".join(args)
    for bad in ("", "two\nlines"):
        with pytest.raises(ValueError):
            pc.set_secret(HARDCOVER, bad)


def test_a_keyring_that_says_yes_but_keeps_nothing_is_not_believed(home):
    """A locked or half-working keyring can accept a secret and not have it
    afterwards. The secret is read back before the keyring is trusted."""
    pc, desk = desk_computer(home, tools=("secret-tool",), keyring_keeps=False)
    pc.set_secret(HARDCOVER, TOKEN)
    assert desk.keyring == {} and pc.secret(HARDCOVER) == TOKEN
    assert "a private file" in pc.secret_place(HARDCOVER) and (home / "state" / "secrets.json").exists()


def test_with_a_keyring_the_secret_goes_there_on_standard_input(home):
    pc, desk = desk_computer(home, tools=("secret-tool",))
    pc.set_secret(HARDCOVER, TOKEN)
    assert desk.keyring == {("service", "kobo-hardcover-sync", "account", "hardcover"): TOKEN}
    assert pc.secret(HARDCOVER) == TOKEN and pc.secret_place(HARDCOVER) == "the desktop keyring"
    assert not (home / "state" / "secrets.json").exists()
    store = [(a, i) for a, i in desk.calls if a[:2] == ["secret-tool", "store"]]
    assert store[0][1] == TOKEN and all(TOKEN not in " ".join(a) for a, _ in desk.calls)  # never an argument
    # A token that was in the file before moves: one place only.
    file_only, _ = desk_computer(home)
    file_only.set_secret(UPLOAD, "u" * 64)
    pc.set_secret(UPLOAD, "u" * 64)
    assert not (home / "state" / "secrets.json").exists() and pc.secret(UPLOAD) == "u" * 64
    pc.delete_secret(HARDCOVER)
    assert pc.secret(HARDCOVER) == "" and ("service", "kobo-hardcover-sync", "account", "upload") in desk.keyring


def test_the_trigger_is_a_user_service_the_kobos_mount_wants(home, monkeypatch):
    monkeypatch.delenv("KHS_HOME")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "cfg"))
    pc, desk = desk_computer(home, tools=("systemctl",))
    assert pc.mount_units() == ["run-media-sam-KOBOeReader.mount", "media-sam-KOBOeReader.mount"]
    said = pc.install_trigger("/home/sam/.local/bin/kobo-hardcover-sync")
    unit = (home / "cfg" / "systemd" / "user" / "kobo-hardcover-sync.service").read_text()
    assert 'ExecStart="/home/sam/.local/bin/kobo-hardcover-sync" sync --trigger mount' in unit and "Type=oneshot" in unit
    assert "WantedBy=run-media-sam-KOBOeReader.mount media-sam-KOBOeReader.mount" in unit and "Environment" not in unit
    assert desk.ran("systemctl") == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "disable", "kobo-hardcover-sync.service"],
                                     ["systemctl", "--user", "enable", "kobo-hardcover-sync.service"]]  # fmt: skip
    assert "no administrator rights" in said[0] and all("sudo" not in " ".join(a) for a, _ in desk.calls)
    # A user name systemd has to escape, and a state folder that is not the default one.
    monkeypatch.setenv("KHS_HOME", "/srv/khs state")
    odd = linux.Linux(run=desk, which=desk.which, home=str(home), user="stim-py")
    odd.install_trigger("/usr/bin/kobo-hardcover-sync")
    unit = (home / "cfg" / "systemd" / "user" / "kobo-hardcover-sync.service").read_text()
    assert "WantedBy=run-media-stim\\x2dpy-KOBOeReader.mount media-stim\\x2dpy-KOBOeReader.mount" in unit
    assert 'Environment="KHS_HOME=/srv/khs state"' in unit
    assert (
        pc.remove_trigger() == ["User service removed."]
        and not (home / "cfg" / "systemd" / "user" / "kobo-hardcover-sync.service").exists()
    )
    # No user session to enable it in (ssh without lingering, a container): it says so, and what to do.
    headless, _ = desk_computer(home, tools=("systemctl",), systemd_works=False)
    said = headless.install_trigger("/usr/bin/kobo-hardcover-sync")
    assert "could not be enabled" in said[0] and "no medium found" in said[0] and "by hand" in said[1]
    bare, _ = desk_computer(home)
    assert "No systemd here" in bare.install_trigger("/usr/bin/kobo-hardcover-sync")[0]


def test_whether_plugging_in_starts_a_sync(home, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "cfg"))
    pc, desk = desk_computer(home, tools=("systemctl",))
    works, said = pc.trigger_state()
    assert not works and said.startswith("No trigger on this computer: plugging in the Kobo does nothing by itself.")
    tool = home / "kobo-hardcover-sync"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    pc.install_trigger(str(tool))
    calls = len(desk.calls)
    assert pc.trigger_state() == (True, f"Plugging in the Kobo starts a sync (user service enabled; it runs {tool}).")
    assert [a for a, _ in desk.calls[calls:]] == [
        ["systemctl", "--user", "is-enabled", "kobo-hardcover-sync.service"]
    ]  # asked, nothing changed
    bare = linux.Linux(run=desk, which=lambda name: None, home=str(home), user="sam")
    assert bare.trigger_state()[1].startswith("The user service is written but not enabled")
    tool.unlink()
    assert pc.trigger_state()[1].startswith(f"The trigger starts {tool} that is not there any more.")
    assert "Check how the Kobo is mounted" in pc.cannot_read(by_hand=True)


def test_mount_unit_names_are_the_ones_systemd_makes(home):
    if not os.path.exists("/usr/bin/systemd-escape"):
        pytest.skip("no systemd-escape to compare with")
    for path in (
        "/run/media/sam/KOBOeReader",
        "/media/stim-py/KOBOeReader",
        "/run/media/jörg/KOBOeReader",
        "/media/a.b/x y",
        "/media/.hidden/K",
    ):
        real = subprocess.run(["systemd-escape", "-p", "--suffix=mount", path], capture_output=True, text=True).stdout.strip()
        assert linux._mount_unit(path) == real, path


def test_notify_eject_and_open(home, capsys):
    pc, desk = desk_computer(home, tools=("notify-send", "udisksctl", "findmnt", "lsblk", "xdg-open"))
    pc.notify("Kobo synced", 'Collection "A"; $(rm -rf ~)')
    assert desk.ran("notify-send")[0][-2:] == ["Kobo synced", 'Collection "A"; $(rm -rf ~)']  # arguments, not a shell line
    assert pc.eject("/run/media/sam/KOBOeReader")
    assert desk.ran("udisksctl") == [["udisksctl", "unmount", "-b", "/dev/sdb1"], ["udisksctl", "power-off", "-b", "/dev/sdb"]]
    pc.open_page("http://127.0.0.1:4000/?k=abc")
    assert desk.ran("xdg-open") == [["xdg-open", "http://127.0.0.1:4000/?k=abc"]]
    # A desktop without these: nothing breaks; the link is at least printed.
    bare, quiet = desk_computer(home)
    bare.notify("t", "m")
    assert bare.eject("/run/media/sam/KOBOeReader") is False and quiet.calls == []
    bare.open_page("http://127.0.0.1:4000/?k=abc")
    assert capsys.readouterr().out == "http://127.0.0.1:4000/?k=abc\n"


def test_the_whole_tool_on_this_machine(home, monkeypatch, capsys):
    """No stand-in computer: the real Linux seams, a folder as the Kobo, the
    page as a real process. No Hardcover token, so nothing reaches out."""
    db = plug_in(home)
    monkeypatch.setenv("KHS_VOLUMES", str(home / "Volumes"))
    monkeypatch.delenv("KHS_TRUSTED_PROXIES")
    pc = platform.pick()
    monkeypatch.setattr(pc, "volume_roots", lambda: [])
    cli.main(["setup", "--local", "--no-trigger"], computer=pc)
    cli.main(["sync"], computer=pc)
    out = said(capsys)
    assert "Local mode" in out and "ok Kobo Kobo: 9 books updated note Hardcover Not connected yet: connect on the page" in out
    cli.main(["status"], computer=pc)
    status = said(capsys)
    assert "ok Mode Local mode" in status and "note Token Not connected to Hardcover yet" in status
    assert f"ok Kobo {home / 'Volumes' / 'KOBOeReader'}" in status
    assert os.path.getsize(db) > 0 and config.load().mode == "local"
    cli.main(["doctor"], computer=pc)  # ends well: no trigger and no token are a warning and a note, not problems
    seen = said(capsys)
    assert "warning Trigger No trigger on this computer" in seen and "note Hardcover Not connected to Hardcover yet" in seen
    assert "ok Database The Kobo's database can be read: 9 books on it." in seen
    assert seen.endswith("1 warning: its line says what to do.")

    link = page.link()  # starts the page, as `open` does
    try:
        with httpx.Client(follow_redirects=True) as browser:
            books = browser.get(link)
            assert books.status_code == 200 and "Made-up Book 3" in books.text and "Not connected to Hardcover yet" in books.text
            base = link.split("/?k=")[0]
            settings = browser.get(base + "/settings")
            assert settings.status_code == 200 and "This computer" in settings.text and "Not connected yet" in settings.text
            # A token straight into the secret store (as `token` would, after asking Hardcover): the page says where it is kept.
            if not os.path.exists("/usr/bin/secret-tool"):
                pc.set_secret(HARDCOVER, TOKEN)
                kept = browser.get(base + "/settings").text
                assert "Kept in a private file on this computer" in kept and TOKEN not in kept
                r = browser.post(
                    base + "/mode", data={"ids": BOOKS[0], "mode": "on"}, headers={"Origin": base, "X-Requested-With": "fetch"}
                )
                assert r.status_code == 200 and r.json()["syncs"] is True
            assert page.link().split("/?k=")[0] == base  # asked again: the same page, not a second one
    finally:
        os.kill(page.running()["pid"], 15)
        for _ in range(100):
            if not page.running():
                break
            time.sleep(0.05)
    assert page.running() is None
    pc.delete_secret(HARDCOVER)
