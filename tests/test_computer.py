"""The tool on the computer the Kobo is plugged into, in server mode: a
temporary folder plays the mounted Kobo, a real server on the loopback
address plays the server, and macOS is a recording of the commands it would
have been given."""

import gzip
import hashlib
import importlib
import os
import plistlib
import shutil
import socket
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from kobo_hardcover_sync import cli, doctor
from kobo_hardcover_sync.computer import config, macos, remote, runner
from kobo_hardcover_sync.computer.platform import UPLOAD, Computer
from kobo_hardcover_sync.engine import collection, kobo_db
from tests import said
from tests.kobo_fixture import BOOKS, make

SAM = {"Remote-User": "sam"}
COLLECTION = "On Hardcover"


# ---------- stand-ins ----------
class FakeComputer(Computer):
    """The seams, in memory. The Kobo is a folder under <tmp>/Volumes."""

    def __init__(self, volumes):
        self.volumes = str(volumes)
        self.secrets, self.told, self.ejected, self.opened, self.triggers = {}, [], [], [], []

    def volume_roots(self):
        return [self.volumes]

    def eject(self, mount):
        self.ejected.append(mount)
        return True

    def secret(self, name):
        return self.secrets.get(name, "")

    def set_secret(self, name, value):
        self.secrets[name] = value

    def delete_secret(self, name):
        self.secrets.pop(name, None)

    def notify(self, title, message):
        self.told.append((title, message))

    def open_page(self, url):
        self.opened.append(url)

    def install_trigger(self, command, rebuild=False):
        self.triggers.append((command, rebuild))
        return ["trigger installed"]

    def remove_trigger(self):
        self.triggers.clear()
        return ["trigger removed"]

    def trigger_state(self):
        if self.triggers:
            return True, "Plugging in the Kobo starts a sync."
        return False, "No trigger on this computer."

    def cannot_read(self, by_hand):
        return "This computer does not let " + ("this terminal" if by_hand else "the tool") + " read the Kobo."


def plug_in(tmp_path, **kw):
    """A Kobo on <tmp>/Volumes/KOBOeReader, with the things that must never leave it."""
    db = tmp_path / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "Volumes" / "Macintosh HD").mkdir(exist_ok=True)
    make(str(db), **kw)
    con = sqlite3.connect(db)
    con.executescript(
        """create table user (UserID text, AuthToken text, RefreshToken text);
           insert into user values ('u-1', 'KOBO-AUTH-TOKEN-SECRET', 'KOBO-REFRESH-TOKEN-SECRET');
           create table content_keys (volumeId text, elementId text, elementKey blob);
           insert into content_keys values ('v', 'e', 'DRM-CONTENT-KEY-SECRET');
           create table Reviews (ContentID text, Body text);
           insert into Reviews values ('x', 'A PRIVATE REVIEW');"""
    )
    con.execute("insert into Event values (3, '2026-09-10T08:00:00Z', '2026-09-12T08:00:00Z', 4, ?)", (BOOKS[0],))
    con.execute("insert into Event values (3, '2026-09-11T08:00:00Z', '2026-09-11T08:00:00Z', 1, 'not-a-book')")
    con.commit()
    con.close()
    return str(db)


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The real server on a loopback port, with one reader (sam) signed up."""
    import uvicorn

    data = tmp_path / "server"
    data.mkdir()
    monkeypatch.setenv("KHS_DATA", str(data))
    monkeypatch.setenv("KHS_CONFIG", str(data / "readers.yaml"))
    monkeypatch.setenv("KHS_HOST", "127.0.0.1")
    monkeypatch.setenv("KHS_INTERVAL", "0")
    monkeypatch.setenv("KHS_TRUSTED_PROXIES", "127.0.0.1")
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(web.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}"
    page = httpx.Client(base_url=url, headers=SAM)
    assert page.post("/signup").status_code in (200, 303)
    yield SimpleNamespace(url=url, page=page, data=str(data))
    page.close()
    srv.should_exit = True
    thread.join(timeout=5)


def register(server, computer, token="t" * 64):
    """This computer's upload token, and its hash on the reader's Settings page."""
    computer.set_secret(UPLOAD, token)
    r = server.page.post("/settings/devices/add", data={"device": "kobo-sam", "hash": hashlib.sha256(token.encode()).hexdigest()})
    assert r.status_code in (200, 303), r.text[:200]


def snapshots(server):
    d = os.path.join(server.data, "snapshots", "sam", "kobo-sam")
    return sorted(os.path.join(d, f) for f in os.listdir(d)) if os.path.isdir(d) else []


def uploads(server):
    """How many uploads the server took in (snapshots are named by the second, so they cannot be counted in a fast test)."""
    con = sqlite3.connect(os.path.join(server.data, "state.db"))
    try:
        return con.execute("select count(*) from import where reader = 'sam'").fetchone()[0]
    finally:
        con.close()


def members(db, name=COLLECTION):
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("select ContentId from ShelfContent where ShelfName = ? and _IsDeleted = 0", (name,))}
    finally:
        con.close()


# ---------- what leaves the computer ----------
def test_the_upload_holds_only_what_the_server_reads(tmp_path):
    db = plug_in(tmp_path)
    out = str(tmp_path / "upload.sqlite")
    assert kobo_db.export_for_upload(db, out) == 9  # the eight store books and the sideloaded one
    con = sqlite3.connect(out)
    assert {r[0] for r in con.execute("select name from sqlite_master")} == kobo_db.UPLOAD_TABLES == {"content", "Event"}
    assert [r[1] for r in con.execute("pragma table_info(content)")] == [c for c, _ in kobo_db.UPLOAD_CONTENT]
    assert con.execute("select count(*) from content where ContentType != 6").fetchone()[0] == 0  # no chapters
    assert con.execute("select ContentID from Event").fetchall() == [(BOOKS[0],)]  # events of books only
    con.close()
    raw = open(out, "rb").read()
    for private in (
        b"KOBO-AUTH-TOKEN-SECRET",
        b"KOBO-REFRESH-TOKEN-SECRET",
        b"DRM-CONTENT-KEY-SECRET",
        b"A PRIVATE REVIEW",
        b"Holiday",
        b"MimeType",
    ):
        assert private not in raw, private
    # And the server reads exactly the same books from it as from the Kobo's own file.
    assert kobo_db.read_books(kobo_db.open_db(out)) == kobo_db.read_books(kobo_db.open_db(db, allow_user_table=True))
    with pytest.raises(kobo_db.NotAKoboDatabase):
        junk = tmp_path / "junk.sqlite"
        junk.write_bytes(b"not sqlite" * 50)
        kobo_db.export_for_upload(str(junk), str(tmp_path / "x.sqlite"))


# ---------- a sync, start to finish ----------
def test_plug_in_upload_then_collection_then_nothing(home, server):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    cfg = config.Config(server=server.url)

    first = runner.sync(mac, cfg)
    assert (first.ok, first.title, first.message) == (True, "Kobo synced", "9 books updated.")
    assert "Made-up Book 3" in server.page.get("/").text
    # What arrived on the server is the small database, not the Kobo's.
    assert len(snapshots(server)) == 1 and uploads(server) == 1
    with gzip.open(snapshots(server)[0]) as fh:
        arrived = fh.read()
    assert b"SECRET" not in arrived and b"PRIVATE" not in arrived and len(arrived) < 40_000
    assert members(db) == set()  # no collection name on the server yet: nothing written
    assert os.listdir(home / "scratch") == []  # the copy of the Kobo's database is gone

    # The reader names a collection and switches three books on.
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    server.page.post("/mode", data={"ids": ",".join(BOOKS[:3]), "mode": "on"})
    second = runner.sync(mac, cfg)
    assert second.message == f"Collection '{COLLECTION}': 3 books (+3, -0). Eject before unplugging."
    assert members(db) == set(BOOKS[:3])
    assert uploads(server) == 1  # the Kobo had not changed: no second upload
    assert open(home / "state" / "last-message.txt").read().startswith(f"Kobo synced\nCollection '{COLLECTION}'")

    # Plugged in again with nothing new: no upload, nothing written, nothing said.
    before = open(db, "rb").read()
    third = runner.sync(mac, cfg)
    assert (third.ok, third.message) == (True, "") and uploads(server) == 1
    assert open(db, "rb").read() == before and os.listdir(home / "scratch") == []
    log = open(home / "state" / "agent.log").read()
    assert "upload skipped" in log and "already up to date" in log and "t" * 64 not in log

    # A book read further on the Kobo: uploaded again, and one more switched on lands in the collection.
    con = sqlite3.connect(db)
    con.execute("update content set ___PercentRead = 99 where ContentID = ?", (BOOKS[4],))
    con.commit()
    con.close()
    server.page.post("/mode", data={"ids": BOOKS[4], "mode": "on"})
    fourth = runner.sync(mac, cfg)
    assert fourth.message == f"1 book updated. Collection '{COLLECTION}': 4 books (+1, -0). Eject before unplugging."
    assert uploads(server) == 2 and mac.ejected == []


def test_in_server_mode_a_cleared_name_removes_the_collection_but_a_server_out_of_reach_does_not(home, server):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    cfg = config.Config(server=server.url)
    runner.sync(mac, cfg)
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    server.page.post("/mode", data={"ids": BOOKS[0], "mode": "on"})
    runner.sync(mac, cfg)
    assert members(db) == {BOOKS[0]}
    # The server cannot be asked: the Kobo is left as it is.
    out = runner.sync(mac, config.Config(server="http://127.0.0.1:9"))
    assert members(db) == {BOOKS[0]} and "Collection" not in out.message
    server.page.post("/settings/collection", data={"collection": "Another name"})
    out = runner.sync(mac, cfg)
    assert out.message == f"Collection '{COLLECTION}' removed. Collection 'Another name': 1 book (+1, -0). Eject before unplugging."
    server.page.post("/settings/collection", data={"collection": ""})
    assert runner.sync(mac, cfg).message == "Collection 'Another name' removed. Eject before unplugging."
    assert members(db, "Another name") == set() and runner.sync(mac, cfg).message == ""


def test_eject_after_sync_when_asked(home, server):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    out = runner.sync(mac, config.Config(server=server.url, eject_after_sync=True))
    assert out.message == "9 books updated. Ejected: safe to unplug." and mac.ejected == [os.path.dirname(os.path.dirname(db))]


def test_a_computer_the_server_does_not_know(home, server):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(UPLOAD, "u" * 64)  # never added under Settings, Devices
    before = open(db, "rb").read()
    out = runner.sync(mac, config.Config(server=server.url))
    assert (out.ok, out.title) == (False, "Kobo sync failed")
    assert out.message == "127.0.0.1 does not know this computer. Add its hash under Settings, Devices (run setup to see it)."
    assert open(db, "rb").read() == before and snapshots(server) == [] and "u" * 64 not in open(home / "state" / "agent.log").read()
    mac.delete_secret(UPLOAD)
    assert "No upload token" in runner.sync(mac, config.Config(server=server.url)).message


def test_no_kobo_no_server_no_setup(home):
    mac = FakeComputer(home / "Volumes")
    (home / "Volumes" / "A USB stick").mkdir(parents=True)
    nowhere = config.Config(server="http://127.0.0.1:9")  # nothing listens there
    assert runner.sync(mac, nowhere) == runner.Outcome(True)  # some other volume was mounted: quiet, and no call to the server
    plug_in(home)
    mac.set_secret(UPLOAD, "t" * 64)
    out = runner.sync(mac, nowhere)
    assert not out.ok and out.message.startswith("Could not reach 127.0.0.1")
    assert runner.sync(mac, config.Config()).message == "Not set up yet: run `kobo-hardcover-sync setup`."


def test_a_second_sync_at_the_same_time_leaves_quietly(home, server):
    import fcntl

    plug_in(home)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    os.makedirs(home / "state")
    with open(home / "state" / "sync.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert runner.sync(mac, config.Config(server=server.url)) == runner.Outcome(True)
        assert snapshots(server) == []
    assert runner.sync(mac, config.Config(server=server.url)).message == "9 books updated."


def test_an_untested_kobo_still_syncs_but_its_collection_is_left_alone(home, server):
    db = plug_in(home, version=300)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    out = runner.sync(mac, config.Config(server=server.url))
    assert out.ok and out.message == (
        "9 books updated. Collection not updated: This Kobo's software has not been tested with kobo-hardcover-sync yet "
        "(its database is version 300; tested: 222, Kobo software 6.0.274403)."
    )
    assert "Eject" not in out.message and members(db) == set()
    server.page.post("/mode", data={"ids": BOOKS[0], "mode": "on"})
    out = runner.sync(mac, config.Config(server=server.url, allow_untested_kobo=True))
    assert out.message.startswith(f"Collection '{COLLECTION}': 1 book (") and members(db) == {BOOKS[0]}


def test_doctor_on_a_computer_that_uploads_to_a_server(home, server, capsys):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    cfg = config.Config(server=server.url)
    config.save(cfg)  # as setup leaves it
    state_of = lambda checks: {c.what: c.state for c in checks}  # noqa: E731

    # No upload token: nothing to ask the server with.
    checks = doctor.computer_checks(mac, cfg)
    assert state_of(checks)["Upload token"] == "fail" and "Server" not in state_of(checks) and doctor.problems(checks) == 1
    # A token the server was never told about.
    mac.set_secret(UPLOAD, "u" * 64)
    checks = doctor.computer_checks(mac, cfg)
    unknown = next(c for c in checks if c.what == "Server")
    assert (
        unknown.state == "fail"
        and unknown.found == "127.0.0.1 does not know this computer. Add its hash under Settings, Devices (run setup to see it)."
    )
    assert next(c for c in checks if c.what == "Collection").found == "Which collection is wanted is not known: the server did not say."
    # Known to the server, synced, a collection on the Kobo.
    register(server, mac)
    mac.install_trigger("kobo-hardcover-sync")
    runner.sync(mac, cfg)
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    server.page.post("/mode", data={"ids": BOOKS[0], "mode": "on"})
    runner.sync(mac, cfg)
    before, taken = open(db, "rb").read(), uploads(server)
    checks = doctor.computer_checks(mac, cfg)
    assert open(db, "rb").read() == before and uploads(server) == taken  # looked, and nothing else
    assert state_of(checks) == {
        "Setup": "ok", "Trigger": "ok", "Folder": "ok", "Upload token": "ok", "Server": "ok", "Hardcover": "note", "Kobo": "ok",
        "Database": "ok", "Kobo software": "ok", "Collection": "ok", "Backups": "ok", "Last sync": "ok", "Log": "ok",
    }  # fmt: skip
    said = {c.what: c.found for c in checks}
    digest = hashlib.sha256(b"t" * 64).hexdigest()
    assert said["Upload token"].endswith(f"its hash starts with {digest[:8]}.") and digest not in doctor.report(checks)
    assert said["Server"] == "127.0.0.1 is reachable and knows this computer."
    assert said["Hardcover"] == f"Your Hardcover token and your books are checked on the server: {server.url}/settings, Check."
    assert said["Collection"] == f"'{COLLECTION}' is on the Kobo, with 1 book."
    assert "t" * 64 not in doctor.report(checks)
    # A server that is not there.
    away = next(c for c in doctor.computer_checks(mac, config.Config(server="http://127.0.0.1:9", set_up=True)) if c.what == "Server")
    assert away.state == "fail" and away.found.startswith("Could not reach 127.0.0.1")


def test_whether_plugging_in_starts_a_sync_on_a_mac(home):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    assert mac.trigger_state() == (
        False,
        "No trigger on this Mac: plugging in the Kobo does nothing by itself. Run `kobo-hardcover-sync setup` again.",
    )
    tool = home / "bin" / "kobo-hardcover-sync"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    mac.install_trigger(str(tool))
    calls = len(fake.calls)
    works, said = mac.trigger_state()
    assert works and said == f"Plugging in the Kobo starts a sync (launch agent loaded; it runs {tool})."
    assert [a[1] for a, _ in fake.calls[calls:]] == ["print"]  # it asked launchctl, and changed nothing
    # The tool was uninstalled (or moved) after setup: the trigger starts nothing.
    tool.unlink()
    works, said = mac.trigger_state()
    assert not works and said == f"The trigger starts {tool} that is not there any more. Run `kobo-hardcover-sync setup` again."
    # What to do when macOS keeps the Kobo closed depends on who asked.
    assert "Give KoboHardcoverSync.app Full Disk Access" in mac.cannot_read(by_hand=False)
    assert "this terminal" in mac.cannot_read(by_hand=True) and "Removable Volumes" in mac.cannot_read(by_hand=True)


def test_the_server_client_says_what_a_person_can_act_on():
    class Answer:
        def __init__(self, status, body):
            self.status, self._body = status, body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = []

    def opener(req, timeout):
        seen.append((req.get_method(), req.full_url, dict(req.header_items())))
        return Answer(200, b"Shelf\nid-1\nid-2\n") if req.full_url.endswith("/collection") else Answer(200, b"<html>a login page</html>")

    s = remote.Server("https://kobo.example.org/", "tok", opener)
    assert s.collection() == ("Shelf", ["id-1", "id-2"])
    assert seen[0][2]["Authorization"] == "Bearer tok" and seen[0][1] == "https://kobo.example.org/collection"
    with pytest.raises(remote.ServerError, match="not from kobo-hardcover-sync"):
        s.upload(__file__)
    assert remote.Server("https://x.example", "t", lambda req, timeout: Answer(204, b"")).collection() is None


# ---------- macOS, as a recording ----------
class FakeMac:
    """subprocess.run for macos.MacOS: keeps a Keychain, builds a pretend app, records every command."""

    def __init__(self):
        self.calls, self.keychain = [], {}

    def __call__(self, args, capture_output=True, text=True, input=None):
        self.calls.append((args, input))
        tool, rc, out = os.path.basename(args[0]), 0, ""
        if tool == "security":
            if args[1] == "-i":
                words = input.split()
                assert words[0] == "add-generic-password"
                self.keychain[(words[words.index("-s") + 1], words[words.index("-a") + 1])] = words[words.index("-w") + 1]
            else:
                key = (args[args.index("-s") + 1], args[args.index("-a") + 1])
                if args[1] == "find-generic-password":
                    rc, out = (0, self.keychain[key] + "\n") if key in self.keychain else (44, "")
                elif args[1] == "delete-generic-password":
                    self.keychain.pop(key, None)
        elif tool == "osacompile":
            os.makedirs(os.path.join(args[2], "Contents", "MacOS"))
            with open(os.path.join(args[2], "Contents", "Info.plist"), "w") as fh:
                fh.write("plist")
        return SimpleNamespace(returncode=rc, stdout=out, stderr="")

    def ran(self, tool):
        return [a for a, _ in self.calls if os.path.basename(a[0]) == tool]


def test_a_secret_never_appears_on_a_command_line(home):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home))
    secret = "a1b2c3" * 10 + ".AbC-_~+/="
    mac.set_secret(UPLOAD, secret)
    assert mac.secret(UPLOAD) == secret
    for args, _ in fake.calls:
        assert not any(secret in a for a in args), args
    assert [i for _, i in fake.calls if i] == [f"add-generic-password -U -s kobo-hardcover-sync -a upload -w {secret}\n"]
    for bad in ("two words", 'quo"te', "semi;colon", "new\nline", "", "back\\slash"):
        with pytest.raises(ValueError):
            mac.set_secret(UPLOAD, bad)
    mac.delete_secret(UPLOAD)
    assert mac.secret(UPLOAD) == ""


def test_setup_on_a_mac_builds_the_app_once_and_loads_the_trigger(home, capsys):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    cli.main(["setup", "--server", "https://kobo.example.org/"], computer=mac)
    out = said(capsys)
    token = fake.keychain[("kobo-hardcover-sync", "upload")]
    assert len(token) == 64 and token not in out and hashlib.sha256(token.encode()).hexdigest() in out
    assert "New upload token" in out and "Full Disk Access" in out and "https://kobo.example.org/settings" in out
    state = home / "state"
    assert config.load().server == "https://kobo.example.org"
    script = open(state / "KoboHardcoverSync.applescript").read()
    assert f'property stateDir : "{state}/"' in script and 'toolLine("sync --trigger mount")' in script and "KHS_HOME='" in script
    assert open(state / "command").read().strip().endswith("kobo-hardcover-sync") or os.path.isabs(open(state / "command").read().strip())
    assert len(fake.ran("osacompile")) == 1 and fake.ran("codesign")[0][1:5] == ["--force", "--deep", "--sign", "-"]
    assert [
        "/usr/libexec/PlistBuddy",
        "-c",
        "Set :CFBundleIdentifier org.gargleblaster.kobo-hardcover-sync",
        str(state / "KoboHardcoverSync.app/Contents/Info.plist"),
    ] in fake.ran("PlistBuddy")
    with open(home / "Library/LaunchAgents/org.gargleblaster.kobo-hardcover-sync.agent.plist", "rb") as fh:
        plist = plistlib.load(fh)
    assert plist["StartOnMount"] is True and plist["EnvironmentVariables"] == {"KHS_TRIGGER": "mount"}
    assert plist["ProgramArguments"] == [str(state / "KoboHardcoverSync.app/Contents/MacOS/applet")]
    assert [a[1] for a in fake.ran("launchctl")] == ["bootout", "bootstrap", "print"]  # loaded, and then looked at
    assert "ok Mode Server mode: this computer uploads to https://kobo.example.org." in out and "Next 1. Paste this computer's hash" in out

    # Again: same token, same hash, the app is not rebuilt (its permission stays).
    cli.main(["setup"], computer=mac)
    again = said(capsys)
    assert "Keeping the existing upload token" in again and hashlib.sha256(token.encode()).hexdigest() in again and "kept" in again
    assert len(fake.ran("osacompile")) == 1 and fake.keychain[("kobo-hardcover-sync", "upload")] == token
    # On purpose: a new app, a new token.
    cli.main(["setup", "--rebuild-app", "--new-token"], computer=mac)
    assert len(fake.ran("osacompile")) == 2 and fake.keychain[("kobo-hardcover-sync", "upload")] != token
    for args, _ in fake.calls:
        assert token not in " ".join(args)


def test_notifications_and_the_other_seams_on_a_mac(home, monkeypatch, capsys):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    assert mac.find_kobo() is None
    plug_in(home)
    assert mac.find_kobo() == str(home / "Volumes" / "KOBOeReader")
    monkeypatch.setenv("KHS_NOTIFY", "stdout")  # started by the small app: it shows the notification itself
    mac.notify("Kobo synced", "Collection 'A|B':\n3 books")
    assert capsys.readouterr().out == "NOTIFY|Kobo synced|Collection 'A/B': 3 books\n" and fake.ran("osascript") == []
    monkeypatch.delenv("KHS_NOTIFY")
    mac.notify('Ti"tle', 'say "hi"; do shell script "rm -rf ~"')
    call = fake.ran("osascript")[0]
    assert call[-2:] == ['Ti"tle', 'say "hi"; do shell script "rm -rf ~"'] and "rm -rf" not in " ".join(call[:-2])  # text, never script
    assert mac.eject("/Volumes/KOBOeReader") and fake.ran("diskutil")[0] == ["/usr/sbin/diskutil", "eject", "/Volumes/KOBOeReader"]
    mac.open_page("https://kobo.example.org")
    assert fake.ran("open")[0] == ["/usr/bin/open", "https://kobo.example.org"]


# ---------- the command ----------
def test_the_commands_around_a_sync(home, server, capsys):
    db = plug_in(home)
    mac = FakeComputer(home / "Volumes")
    with pytest.raises(SystemExit, match="starts with https://"):
        cli.main(["setup", "--server", "kobo.example.org"], computer=mac)
    cli.main(["setup", "--server", server.url], computer=mac)
    digest = hashlib.sha256(mac.secrets[UPLOAD].encode()).hexdigest()
    assert digest in capsys.readouterr().out and mac.triggers and mac.triggers[0][1] is False
    server.page.post("/settings/devices/add", data={"device": "kobo-sam", "hash": digest})

    cli.main(["sync"], computer=mac)  # in a terminal: each step, printed
    assert capsys.readouterr().out == (
        "\n"
        "  ok       Kobo        Kobo\n"
        "  ok       Upload      Sent to 127.0.0.1: 9 books updated\n"
        "  note     Collection  None wanted: nothing is written to the Kobo\n"
    )
    assert mac.told == []
    cli.main(["sync"], computer=mac)
    assert "ok Upload Nothing new for 127.0.0.1 since the last upload" in said(capsys)
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    server.page.post("/mode", data={"ids": BOOKS[0], "mode": "on"})
    cli.main(["sync", "--trigger", "mount"], computer=mac)  # from the plug-in trigger: a notification
    assert capsys.readouterr().out == "" and mac.told == [
        ("Kobo synced", f"Collection '{COLLECTION}': 1 book (+1, -0). Eject before unplugging.")
    ]
    assert members(db) == {BOOKS[0]}

    cli.main(["status"], computer=mac)
    status = said(capsys)
    assert f"ok Mode Server mode: uploads to {server.url}" in status and f"its hash is {digest}" in status
    assert "database version 222 (tested)" in status
    assert "Collection 'On Hardcover'" in status and mac.secrets[UPLOAD] not in status
    cli.main(["open"], computer=mac)
    assert mac.opened == [server.url]

    shutil.rmtree(home / "Volumes" / "KOBOeReader")
    cli.main(["sync"], computer=mac)
    assert "note Kobo No Kobo found: plug it in and tap Connect on the Kobo." in said(capsys)
    cli.main(["sync", "--trigger", "mount"], computer=mac)  # some other volume: silent
    assert capsys.readouterr().out == "" and len(mac.told) == 1
    cli.main(["uninstall"], computer=mac)
    assert os.path.isdir(home / "state") and UPLOAD in mac.secrets and mac.triggers == []
    cli.main(["uninstall", "--purge"], computer=mac)
    assert not os.path.exists(home / "state") and UPLOAD not in mac.secrets


def test_the_collection_module_is_what_writes(home, server, monkeypatch):
    """The tool does not have its own way of writing to the Kobo."""
    plug_in(home)
    mac = FakeComputer(home / "Volumes")
    register(server, mac)
    runner.sync(mac, config.Config(server=server.url))  # the books reach the server
    server.page.post("/settings/collection", data={"collection": COLLECTION})
    server.page.post("/mode", data={"ids": BOOKS[0], "mode": "on"})
    asked = []
    real = collection.apply
    monkeypatch.setattr(collection, "apply", lambda *a, **kw: asked.append((a, kw)) or real(*a, **kw))
    runner.sync(mac, config.Config(server=server.url))
    (db, name, ids, state), kw = asked[0]
    assert name == COLLECTION and ids == [BOOKS[0]] and state == str(home / "state" / "collection")
    assert kw["preflight_db"].startswith(str(home / "scratch")) and kw["allow_untested"] is False  # the gate ran on the copy first


def test_on_a_platform_without_seams_the_tool_says_so(monkeypatch):
    monkeypatch.setattr("sys.platform", "sunos5")
    for cmd in (["status"], ["sync"], ["setup", "--server", "https://kobo.example.org"]):
        with pytest.raises(SystemExit, match="runs on macOS and on desktop Linux"):
            cli.main(cmd)
