"""Local mode: the whole sync on the reader's own computer, and the page
that is started for the occasion. A folder plays the Kobo, an in-memory
Hardcover plays Hardcover, and the computer's seams are the stand-ins from
test_computer."""

import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, macos, page, runner
from kobo_hardcover_sync.computer.platform import HARDCOVER, UPLOAD
from kobo_hardcover_sync.engine import hardcover, job, kobo_db, state
from kobo_hardcover_sync.server import accounts
from tests import client_at, said
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer, FakeMac, members, plug_in
from tests.test_hardcover import FakeHC

VERSION = "N36XXXXXXXX,4.9.77,6.0.274403,4.9.77,4.9.77,00000000-0000-0000-0000-000000000393\n"
TOKEN = "eyJhbGciOi.made-up-hardcover-token.xyz"
LOCAL = config.Config(set_up=True)  # local mode: set up, no server


def catalogue():
    """Hardcover knows the eight store books by ISBN."""
    return {
        f"97800000000{n:02d}": {
            "id": 10 + n,
            "book_id": 100 + n,
            "isbn_13": f"97800000000{n:02d}",
            "pages": 300,
            "title": f"Made-up Book {n}",
        }
        for n in range(8)
    }


def kobo(home):
    db = plug_in(home)
    with open(os.path.join(os.path.dirname(db), "version"), "w") as fh:
        fh.write(VERSION)
    return db


def st(home):
    return state.connect(str(home / "state" / "state.db"))


def writes(fake):
    return [c for c in fake.calls if c[0] in ("insert_ub", "update_ub", "insert_read", "update_read", "delete_ub")]


# ---------- the Kobo's own description ----------
def test_what_the_kobo_says_about_itself(home):
    db = kobo(home)
    mount = os.path.dirname(os.path.dirname(db))
    d = kobo_db.device(mount)
    assert (d.serial, d.software, d.model) == ("N36XXXXXXXX", "6.0.274403", "Kobo Clara Colour")
    assert d.name.startswith("kobo-") and len(d.name) == 13 and "N36" not in d.name  # stable, and not the serial
    assert kobo_db.device(mount).name == d.name
    with open(os.path.join(mount, ".kobo", "version"), "w") as fh:
        fh.write("SN123,4.9.77,7.1.0,4.9.77,4.9.77,00000000-0000-0000-0000-000000000999\n")
    other = kobo_db.device(mount)
    assert (other.software, other.model) == ("7.1.0", "model 999") and other.name != d.name
    for text in ("", "just-a-serial\n", "a,b\n"):
        with open(os.path.join(mount, ".kobo", "version"), "w") as fh:
            fh.write(text)
        assert kobo_db.device(mount).software == ""
    os.unlink(os.path.join(mount, ".kobo", "version"))
    assert kobo_db.device(mount) == kobo_db.Device() and kobo_db.Device().name == "kobo"


# ---------- a sync on this computer ----------
def test_plug_in_dry_run_live_collection_and_then_nothing(home):
    db = kobo(home)
    mac = FakeComputer(home / "Volumes")
    hc = FakeHC(isbn=catalogue())

    # No token yet: the books are imported, nothing else.
    first = runner.sync(mac, LOCAL)
    assert (first.ok, first.message) == (True, "9 books updated. No Hardcover token yet: add one on the page.")
    con = st(home)
    assert tuple(con.execute("select count(*), count(distinct device) from book where reader = 'me'").fetchone()) == (9, 1)
    assert con.execute("select device from device").fetchone()[0] == kobo_db.device(str(home / "Volumes" / "KOBOeReader")).name
    assert tuple(con.execute("select is_admin, hardcover_live from reader where name = 'me'").fetchone()) == (0, 0)
    assert os.listdir(home / "scratch") == [] and not os.path.exists(home / "state" / "snapshots")
    assert runner.sync(mac, LOCAL).message == ""  # plugged in again: nothing new, nothing said

    # A token, and three books switched on: still a dry run until the reader goes live.
    mac.set_secret(HARDCOVER, TOKEN)
    state.set_mode(con, "me", BOOKS[:3], "on")
    dry = runner.sync(mac, LOCAL, hardcover_client=hc)
    assert dry.message == "3 would be sent to Hardcover (dry run)." and writes(hc) == []
    accounts.set_collection(con, "me", "On Hardcover")
    con.execute("update reader set hardcover_live = 1 where name = 'me'")
    con.commit()

    live = runner.sync(mac, LOCAL, hardcover_client=hc)
    assert live.message == "3 sent to Hardcover. Collection 'On Hardcover': 3 books (+3, -0). Eject before unplugging."
    assert len(hc.books) == 3 and members(db, "On Hardcover") == set(BOOKS[:3])
    assert open(home / "state" / "last-message.txt").read().startswith("Kobo synced\n3 sent to Hardcover.")

    # Again, twice: nothing is sent, nothing is written, nothing is said.
    sent, on_kobo = len(writes(hc)), open(db, "rb").read()
    for _ in range(2):
        again = runner.sync(mac, LOCAL, hardcover_client=hc)
        assert (again.ok, again.message) == (True, "")
    assert len(writes(hc)) == sent and open(db, "rb").read() == on_kobo and os.listdir(home / "scratch") == []

    # The token is in the computer's secret store and nowhere else.
    for name in os.listdir(home / "state"):
        path = home / "state" / name
        if path.is_file():
            assert TOKEN.encode() not in path.read_bytes(), name
    assert mac.secrets == {HARDCOVER: TOKEN} and mac.ejected == []


def test_a_new_collection_name_replaces_the_old_collection_and_a_cleared_one_removes_it(home):
    db = kobo(home)
    mac = FakeComputer(home / "Volumes")
    runner.sync(mac, LOCAL)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:2], "on")
    accounts.set_collection(con, "me", "First name")
    assert runner.sync(mac, LOCAL).message == "Collection 'First name': 2 books (+2, -0). Eject before unplugging."
    accounts.set_collection(con, "me", "Second name")
    out = runner.sync(mac, LOCAL)
    assert out.message == "Collection 'First name' removed. Collection 'Second name': 2 books (+2, -0). Eject before unplugging."
    assert members(db, "First name") == set() and members(db, "Second name") == set(BOOKS[:2])
    assert runner.sync(mac, LOCAL).message == ""
    accounts.set_collection(con, "me", "")
    assert runner.sync(mac, LOCAL).message == "Collection 'Second name' removed. Eject before unplugging."
    assert members(db, "Second name") == set() and members(db, "Holiday") == {BOOKS[0], BOOKS[5]}  # the reader's own: untouched
    assert runner.sync(mac, LOCAL).message == ""


def test_without_a_kobo_only_the_hardcover_half_runs(home):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, TOKEN)
    hc = FakeHC(isbn=catalogue())
    runner.sync(mac, LOCAL, hardcover_client=hc)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:1], "on")
    con.execute("update reader set hardcover_live = 1, kobo_collection = 'On Hardcover' where name = 'me'")
    con.commit()
    shutil.rmtree(home / "Volumes" / "KOBOeReader")  # unplugged
    assert runner.sync(mac, LOCAL, hardcover_client=hc, trigger="mount") == runner.Outcome(True)  # some other volume: nothing
    assert writes(hc) == []
    out = runner.sync(mac, LOCAL, hardcover_client=hc)  # asked for: Hardcover gets what was waiting
    assert out.message == "1 sent to Hardcover." and len(hc.books) == 1
    assert runner.sync(mac, config.Config()).message == "Not set up yet: run `kobo-hardcover-sync setup`."


def test_a_kobo_unplugged_halfway(home, monkeypatch):
    db = kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, TOKEN)
    hc = FakeHC(isbn=catalogue())
    runner.sync(mac, LOCAL, hardcover_client=hc)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:2], "on")
    con.execute("update reader set hardcover_live = 1, kobo_collection = 'On Hardcover' where name = 'me'")
    con.commit()
    real = job.run

    def unplugged_during_the_hardcover_half(*a, **kw):
        os.rename(home / "Volumes" / "KOBOeReader", home / "unplugged")
        return real(*a, **kw)

    monkeypatch.setattr(job, "run", unplugged_during_the_hardcover_half)
    out = runner.sync(mac, LOCAL, hardcover_client=hc)
    assert out.ok and out.message == (
        "2 sent to Hardcover. Collection not updated: The Kobo was unplugged before the collection could be written."
    )
    assert "Eject" not in out.message and os.listdir(home / "scratch") == []
    # Plugged in again: Hardcover already has them, the collection catches up.
    monkeypatch.setattr(job, "run", real)
    os.rename(home / "unplugged", home / "Volumes" / "KOBOeReader")
    out = runner.sync(mac, LOCAL, hardcover_client=hc)
    assert out.message == "Collection 'On Hardcover': 2 books (+2, -0). Eject before unplugging." and members(db, "On Hardcover") == set(
        BOOKS[:2]
    )


def test_hardcover_trouble_is_said_and_the_books_are_still_imported(home):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, TOKEN)

    class Down(FakeHC):
        def editions_by_isbn(self, isbns):
            raise hardcover.HardcoverError(
                "Hardcover could not be reached (timed out). Nothing is lost: the next sync carries on", "unreachable"
            )

    assert runner.sync(mac, LOCAL, hardcover_client=FakeHC()).message == "9 books updated."
    st(home).execute("update book set mode = 'on' where reader = 'me'").connection.commit()
    out = runner.sync(mac, LOCAL, hardcover_client=Down())
    assert out.ok and out.message == "Hardcover could not be reached (timed out). Nothing is lost: the next sync carries on."
    assert st(home).execute("select count(*) from book where reader = 'me'").fetchone()[0] == 9


# ---------- the page, in local mode ----------
PORT = 45678
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = {"Origin": BASE}


@pytest.fixture
def local(home, monkeypatch):
    """The app in local mode, with the stand-in computer. Yields (web, computer, a client that came through `open`)."""
    monkeypatch.setenv("KHS_MODE", "local")
    monkeypatch.setenv("KHS_PAGE_PORT", str(PORT))
    monkeypatch.setenv("KHS_DATA", str(home / "state"))
    monkeypatch.setenv("KHS_HOST", "127.0.0.1")
    monkeypatch.delenv("KHS_TRUSTED_PROXIES")
    os.makedirs(home / "state")
    config.save(config.Config())
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    mac = FakeComputer(home / "Volumes")
    web.local._computer = mac
    c = visitor(web)
    assert c.get(f"/?k={page.new_key()}", follow_redirects=False).status_code == 303
    yield web, mac, c
    accounts.token_store = None


def visitor(web, address=("127.0.0.1", 50001), base=BASE):
    c = client_at(web.app, address)
    c.base_url = base
    return c


def test_the_page_wants_the_key_from_open(local):
    web, mac, inside = local
    stranger = visitor(web)  # another program on this computer: it can reach the port, and nothing more
    for path in ("/", "/settings", "/static/kobo.css", "/cover/x"):
        r = stranger.get(path)
        assert (r.status_code, "kobo-hardcover-sync open" in r.text) == (403, True), path
    assert stranger.get("/?k=guessed").status_code == 403
    assert stranger.get("/healthz").text == "ok"

    key = page.new_key()
    r = stranger.get(f"/settings?ok=profile&k={key}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings?ok=profile"  # the key leaves the address bar
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and key not in cookie
    assert stranger.get("/settings").status_code == 200
    # A key works once, and not after a minute.
    assert visitor(web).get(f"/?k={key}").status_code == 403
    old = page.new_key()
    past = time.time() - 61
    os.utime(os.path.join(config.state_dir(), "page-keys", os.listdir(os.path.join(config.state_dir(), "page-keys"))[0]), (past, past))
    assert visitor(web).get(f"/?k={old}").status_code == 403 and os.listdir(os.path.join(config.state_dir(), "page-keys")) == []
    # With the cookie, the page is the usual one, for the one built-in reader.
    home_page = inside.get("/")
    assert (
        home_page.status_code == 200
        and "Add your Hardcover token under Settings" in home_page.text
        and "On this computer:" in home_page.text
    )
    assert 'href="/admin"' not in home_page.text


def test_only_from_this_computer_to_its_own_address_and_from_its_own_pages(local):
    web, mac, inside = local
    session = inside.cookies.get(page.COOKIE)
    # Not from another computer, even with the cookie.
    lan = visitor(web, address=("10.0.0.50", 50001))
    lan.cookies.set(page.COOKIE, session)
    assert lan.get("/").status_code == 403 and "only for the person at this computer" in lan.get("/").text
    # Not under another name: a website cannot point a name of its own at this port and be answered.
    for host in ("evil.example", f"localhost:{PORT}", "127.0.0.1:1", "127.0.0.1"):
        r = inside.get("/", headers={"Host": host})
        assert r.status_code == 403, host
    # A change must come from this page: other websites, and other local servers (another port), are refused.
    for origin in (None, "https://evil.example", "http://127.0.0.1:9999", f"http://localhost:{PORT}", "null"):
        r = inside.post(
            "/settings/profile", data={"display_name": "Mallory"}, headers={"Origin": origin} if origin else {}, follow_redirects=False
        )
        assert r.status_code == 403, origin
    assert inside.post("/settings/profile", data={"display_name": "Sam"}, headers=ORIGIN, follow_redirects=False).status_code == 303
    assert "Sam" in inside.get("/settings").text and "Mallory" not in inside.get("/settings").text


def test_what_local_mode_does_not_have(local):
    web, mac, inside = local
    for method, path in (("PUT", "/upload"), ("GET", "/collection"), ("GET", "/api/stats/me"), ("POST", "/signup"), ("GET", "/admin"),
                         ("POST", "/admin/role"), ("POST", "/settings/devices/add"), ("POST", "/settings/stats/token")):  # fmt: skip
        r = inside.request(method, path, headers=ORIGIN)
        assert (r.status_code, r.text) == (404, "Not there in local mode."), path
    settings = inside.get("/settings").text
    assert "This computer" in settings and "Devices" not in settings and "stats" not in settings.lower() and "Logins" not in settings
    assert accounts.get(st_of(web), "me")["is_admin"] == 0


def st_of(web):
    return state.connect(os.path.join(web.DATA, "state.db"))


def test_the_token_goes_to_the_secret_store_from_the_page(local, monkeypatch):
    web, mac, inside = local

    class Stub:
        def __init__(self, token, **kw):
            assert token == TOKEN

        def whoami(self):
            return {"id": 1, "username": "sam"}

    monkeypatch.setattr(hardcover, "Client", Stub)
    assert "No token yet" in inside.get("/settings").text
    r = inside.post("/settings/token", data={"token": "Bearer " + TOKEN}, headers=ORIGIN)
    assert r.status_code == 200 and "Connected to Hardcover as @sam" in r.text and TOKEN not in r.text
    assert mac.secrets == {HARDCOVER: TOKEN}
    assert TOKEN.encode() not in open(os.path.join(web.DATA, "state.db"), "rb").read()
    assert tuple(st_of(web).execute("select hardcover_token_enc, hardcover_user from reader").fetchone()) == (None, "sam")
    # Live, eject, and back.
    assert (
        inside.post("/settings/live", data={"live": "1"}, headers=ORIGIN, follow_redirects=False).headers["location"] == "/settings?ok=live"
    )
    assert (
        inside.post("/settings/eject", data={"eject": "1"}, headers=ORIGIN, follow_redirects=False).headers["location"]
        == "/settings?ok=eject_on"
    )
    assert config.load().eject_after_sync is True and "The Kobo is ejected after a sync" in inside.get("/settings").text
    inside.post("/settings/eject", data={"eject": "0"}, headers=ORIGIN)
    assert config.load().eject_after_sync is False
    inside.post("/settings/token/remove", headers=ORIGIN)
    assert mac.secrets == {} and st_of(web).execute("select hardcover_live from reader").fetchone()[0] == 0


def test_the_check_card_in_local_mode_looks_at_the_kobo_too(local, monkeypatch):
    web, mac, inside = local
    kobo(web_home(web))
    mac.set_secret(HARDCOVER, TOKEN)

    class Stub:
        def __init__(self, token, **kw):
            assert token == TOKEN

        def whoami(self):
            return {"id": 1, "username": "sam"}

    monkeypatch.setattr(hardcover, "Client", Stub)
    page_before = inside.get("/settings").text
    assert ">Check now</button>" in page_before and "with the Kobo plugged in, the Kobo too" in page_before
    r = inside.post("/settings/check", headers=ORIGIN)
    assert r.status_code == 200 and TOKEN not in r.text
    for line in (
        "<b>Setup</b> Local mode: everything happens on this computer.",
        "<b>Hardcover</b> Hardcover is reachable and accepts the token: it is @sam&#x27;s.",
        "<b>Kobo</b> Found at ",
        "<b>Database</b> The Kobo&#x27;s database can be read: 9 books on it.",
        "<b>Kobo software</b> Database version 222 is one this tool was tested with (Kobo software 6.0.274403).",
        "<b>Trigger</b> No trigger on this computer.",
        "run <code>kobo-hardcover-sync sync</code> with the Kobo plugged in",
    ):
        assert line in r.text, line
    assert inside.post("/settings/check").status_code == 403  # not without the page's own Origin


def test_sync_now_on_the_page_is_the_whole_sync(local, monkeypatch):
    web, mac, inside = local
    asked = []
    monkeypatch.setattr(web.runner, "sync", lambda computer, *a, **kw: asked.append(computer))
    r = inside.post("/sync", data={"back": "f=on"}, headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?f=on"
    for _ in range(50):
        if asked:
            break
        time.sleep(0.02)
    assert asked == [mac]


def test_books_show_up_on_the_local_page_after_a_sync(local):
    web, mac, inside = local
    kobo(web_home(web))
    runner.sync(mac, config.load())
    books = inside.get("/").text
    assert "Made-up Book 3" in books and "Kobo read" in books and "No Hardcover token yet" in books
    assert (
        inside.post("/mode", data={"ids": BOOKS[0], "mode": "on"}, headers={**ORIGIN, "X-Requested-With": "fetch"}).json()["syncs"] is True
    )


def web_home(web):
    import pathlib

    return pathlib.Path(web.DATA).parent


def test_local_mode_cannot_be_started_half_open(home, monkeypatch):
    monkeypatch.setenv("KHS_MODE", "local")
    monkeypatch.setenv("KHS_DATA", str(home / "state"))
    monkeypatch.delenv("KHS_PAGE_PORT", raising=False)
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    with pytest.raises(RuntimeError, match="kobo-hardcover-sync open"), client_at(web.app):
        pass
    accounts.token_store = None
    # And the server mode of the same code is untouched by all this.
    monkeypatch.delenv("KHS_MODE")
    importlib.reload(web)
    assert web.local is None and accounts.token_store is None


def test_the_real_page_process(home):
    """`open` starts the page as a process of its own: loopback only, a file
    that says where it is, and the same gate."""
    env = {**os.environ, "KHS_HOME": str(home / "state")}
    env.pop("KHS_TRUSTED_PROXIES", None)
    os.makedirs(home / "state")
    config.save(config.Config())
    proc = subprocess.Popen(
        [sys.executable, "-m", "kobo_hardcover_sync", "page"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        info = None
        for _ in range(150):
            info = page.running()
            if info:
                break
            assert proc.poll() is None, proc.stderr.read().decode()[-600:]
            time.sleep(0.1)
        assert info and info["pid"] == proc.pid and oct(os.stat(home / "state" / "page.json").st_mode)[-3:] == "600"
        url = f"http://127.0.0.1:{info['port']}"
        listening = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout if shutil.which("ss") else ""
        if listening:
            assert f"127.0.0.1:{info['port']}" in listening and f"0.0.0.0:{info['port']}" not in listening
        assert httpx.get(url + "/healthz").text == "ok" and httpx.get(url + "/").status_code == 403
        with httpx.Client(follow_redirects=True) as browser:
            r = browser.get(f"{url}/?k={page.new_key()}")
            assert r.status_code == 200 and "Kobo Hardcover Sync" in r.text and str(r.url) == url + "/"
            assert browser.get(url + "/static/kobo.css").status_code == 200
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert page.running() is None and not os.path.exists(home / "state" / "page.json")


def test_the_page_stops_by_itself_when_nobody_uses_it(home):
    env = {**os.environ, "KHS_HOME": str(home / "state"), "KHS_PAGE_IDLE_SECONDS": "1"}
    os.makedirs(home / "state")
    config.save(config.Config())
    proc = subprocess.Popen(
        [sys.executable, "-m", "kobo_hardcover_sync", "page"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(150):
            if page.running():
                break
            time.sleep(0.1)
        assert page.running()
        assert proc.wait(timeout=15) == 0  # nobody came: it went away
    finally:
        if proc.poll() is None:
            proc.kill()
    assert page.running() is None and not os.path.exists(home / "state" / "page.json")


def test_open_reuses_the_running_page_or_starts_one(home, monkeypatch):
    os.makedirs(home / "state")
    started = []
    monkeypatch.setattr(page, "start", lambda: started.append(1) or {"port": 4000, "pid": os.getpid()})
    assert page.running() is None
    first = page.link()
    assert first.startswith("http://127.0.0.1:4000/?k=") and started == [1]
    with open(home / "state" / "page.json", "w") as fh:
        fh.write(f'{{"port": 4001, "pid": {os.getpid()}}}')
    assert page.link().startswith("http://127.0.0.1:4001/?k=") and started == [1]  # found it, did not start another
    with open(home / "state" / "page.json", "w") as fh:
        fh.write('{"port": 4002, "pid": 999999999}')  # a page that is gone
    assert page.running() is None and page.link().startswith("http://127.0.0.1:4000/") and started == [1, 1]


# ---------- the commands ----------
def test_setup_token_status_open_in_local_mode(home, monkeypatch, capsys):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    with pytest.raises(SystemExit, match="--server or --local, not both"):
        cli.main(["setup", "--local", "--server", "https://kobo.example.org"], computer=mac)
    with pytest.raises(SystemExit, match="run setup first"):
        cli.main(["token"], computer=mac)
    cli.main(["setup"], computer=mac)  # no server anywhere: local mode
    out = said(capsys)
    assert "ok Mode Local mode: everything happens on this computer." in out and mac.triggers and UPLOAD not in mac.secrets
    assert "ok Trigger Plugging in the Kobo starts a sync." in out and "Next 1. `kobo-hardcover-sync token` connects to Hardcover." in out
    assert config.load().mode == "local"

    class Stub(FakeHC):
        def __init__(self, token, **kw):
            if token != TOKEN:
                raise hardcover.HardcoverError("Hardcover does not accept your token", "token")
            super().__init__(isbn=catalogue())

        def whoami(self):
            return {"username": "sam"}

    monkeypatch.setattr(hardcover, "Client", Stub)
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("wrong-token\n"))
    with pytest.raises(SystemExit, match="does not accept your token. Nothing was stored"):
        cli.main(["token"], computer=mac)
    assert mac.secrets == {}
    monkeypatch.setattr("sys.stdin", io.StringIO(f"Bearer {TOKEN}\n"))
    cli.main(["token"], computer=mac)
    assert said(capsys) == "ok Stored. Hardcover knows you as @sam."
    assert mac.secrets == {HARDCOVER: TOKEN} and accounts.token_store is None

    cli.main(["sync"], computer=mac)  # the real engine, with the stub for Hardcover: matching fails softly
    capsys.readouterr()
    cli.main(["status"], computer=mac)
    status = said(capsys)
    assert "ok Mode Local mode: everything on this computer" in status and "ok Token Hardcover token present" in status
    assert "note Sending Dry run; 0 of 9 books switched on" in status
    assert "(Kobo Clara Colour, software 6.0.274403), database version 222 (tested)" in status and TOKEN not in status
    monkeypatch.setattr(page, "link", lambda: "http://127.0.0.1:4000/?k=abc")
    cli.main(["open"], computer=mac)
    assert mac.opened == ["http://127.0.0.1:4000/?k=abc"]

    cli.main(["token", "--remove"], computer=mac)
    assert mac.secrets == {} and "back in dry run" in said(capsys)
    # Switching to a server and back keeps the two apart.
    cli.main(["setup", "--server", "https://kobo.example.org"], computer=mac)
    assert config.load().mode == "server" and UPLOAD in mac.secrets
    with pytest.raises(SystemExit, match="set on the server's page"):
        cli.main(["token"], computer=mac)
    cli.main(["setup", "--local"], computer=mac)
    assert config.load().mode == "local"
    installed = len(mac.triggers)
    cli.main(["setup", "--no-trigger"], computer=mac)  # only the settings
    assert len(mac.triggers) == installed and "note Trigger No trigger installed" in said(capsys)
    mac.set_secret(HARDCOVER, TOKEN)
    cli.main(["uninstall", "--purge"], computer=mac)
    assert mac.secrets == {} and not os.path.exists(home / "state")


def test_setup_in_local_mode_on_a_mac_makes_no_upload_token(home, capsys):
    fake = FakeMac()
    mac = macos.MacOS(run=fake, home=str(home), volumes=str(home / "Volumes"))
    cli.main(["setup", "--local"], computer=mac)
    assert fake.keychain == {} and len(fake.ran("osacompile")) == 1 and "Local mode" in capsys.readouterr().out
    assert os.path.exists(home / "Library/LaunchAgents/org.gargleblaster.kobo-hardcover-sync.agent.plist")
    mac.set_secret(HARDCOVER, TOKEN)  # a Hardcover token is made of characters the Keychain helper takes
    assert fake.keychain == {("kobo-hardcover-sync", "hardcover"): TOKEN}


def test_the_state_database_never_holds_the_token(home):
    """Also not by another road: the server's encrypted column stays empty in local mode."""
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, TOKEN)
    runner.sync(mac, LOCAL, hardcover_client=FakeHC(isbn=catalogue()))
    con = sqlite3.connect(home / "state" / "state.db")
    assert con.execute("select hardcover_token_enc from reader").fetchall() == [(None,)]
