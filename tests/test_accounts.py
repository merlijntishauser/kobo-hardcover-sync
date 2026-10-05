"""Readers manage themselves: sign-up, settings, devices, the
encrypted Hardcover token, and the admin page."""

import gzip
import hashlib
import importlib
import os
import re
import sqlite3
import urllib.error

import pytest
from cryptography.fernet import Fernet

from kobo_hardcover_sync import doctor
from kobo_hardcover_sync.engine import hardcover, kobo_db, state
from kobo_hardcover_sync.server import accounts
from tests import ELSEWHERE, client_at
from tests.test_core import MINE, OLD, make_kobo

ORIGIN = {"Origin": "https://kobo.example.org"}
ROBIN = {"Remote-User": "robin", **ORIGIN}
ANNA = {"Remote-User": "Anna", "Remote-Email": "anna@example.org", "Remote-Name": "Anna B", **ORIGIN}
SECRET = "hc-secret-token-value"


def client(tmp_path, monkeypatch, key=True, env_token=""):
    """An installation from before readers managed themselves: one reader and one device in yaml."""
    (tmp_path / "readers.yaml").write_text(
        "readers:\n  robin:\n    hardcover_live: true\n    kobo_collection: Robin\n    identities: [robin, Robin@Example.org]\n"
    )
    (tmp_path / "devices.yaml").write_text(
        f"devices:\n  - token_sha256: {hashlib.sha256(b'old-token').hexdigest()}\n    reader: robin\n    device: kobo-robin\n"
    )
    monkeypatch.setenv("KHS_DATA", str(tmp_path))
    monkeypatch.setenv("KHS_CONFIG", str(tmp_path / "readers.yaml"))
    monkeypatch.setenv("KHS_HOST", "kobo.example.org")
    monkeypatch.setenv("KHS_INTERVAL", "0")
    if key:
        monkeypatch.setenv("KHS_SECRET_KEY", Fernet.generate_key().decode())
    else:
        monkeypatch.delenv("KHS_SECRET_KEY", raising=False)
    if env_token:
        monkeypatch.setenv("HARDCOVER_TOKEN_ROBIN", env_token)
    else:
        monkeypatch.delenv("HARDCOVER_TOKEN_ROBIN", raising=False)
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, MINE], [])
    c = client_at(web.app)
    c.get("/", headers=ROBIN)  # first request: the yaml is taken over
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "robin", "kobo-robin", kobo_db.read_books(kobo_db.open_db(str(k))))
    return c, st


class Hardcover:
    """Stands in for hardcover.Client: accepts one token."""

    seen: list = []

    def __init__(self, token, **kw):
        self.token = hardcover.bare(token)
        Hardcover.seen.append(self.token)

    def whoami(self):
        if self.token != SECRET:
            raise hardcover.HardcoverError("Hardcover does not accept your token. Make a new one", "token")
        return {"id": 7, "username": "anna_reads"}


def test_yaml_is_taken_over_once_and_first_reader_is_admin(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    me = accounts.get(st, "robin")
    assert me["is_admin"] == 1 and me["hardcover_live"] == 1 and me["kobo_collection"] == "Robin"
    assert accounts.logins(me) == ["robin", "robin@example.org"]
    assert [d["device"] for d in accounts.devices(st, "robin")] == ["kobo-robin"]
    # The files are not read again: a later edit changes nothing.
    (tmp_path / "readers.yaml").write_text("readers:\n  intruder:\n    admin: true\n    identities: [intruder]\n")
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    c = client_at(web.app)
    assert "Welcome to Kobo Hardcover Sync" in c.get("/", headers={"Remote-User": "intruder"}).text
    assert accounts.get(st, "intruder") is None


def test_header_shows_who_is_signed_in_and_admin_link_only_for_admins(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    page = c.get("/", headers=ROBIN).text
    assert "Signed in as</span> <b>robin</b>" in page
    # The navigation: Books (here), Settings, Admin, in that order.
    assert re.findall(r'<a href="(/[a-z]*)"( aria-current="page")?><svg', page) == [
        ("/", ' aria-current="page"'),
        ("/settings", ""),
        ("/admin", ""),
    ]
    c.post("/signup", headers=ANNA)
    page = c.get("/settings", headers=ANNA).text
    assert "Signed in as</span> <b>Anna B</b>" in page and 'href="/admin"' not in page
    assert re.findall(r'<a href="(/[a-z]*)"( aria-current="page")?><svg', page) == [("/", ""), ("/settings", ' aria-current="page"')]


def test_sign_up_creates_a_reader_in_dry_run(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    r = c.get("/", headers=ANNA)
    assert r.status_code == 200 and "Welcome to Kobo Hardcover Sync" in r.text and "signed in as Anna" in r.text
    assert "Old Finished" not in r.text and accounts.get(st, "anna") is None  # looking creates nothing
    assert c.post("/signup", headers={**ANNA, "Origin": "https://evil.example"}).status_code == 403
    r = c.post("/signup", headers=ANNA, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings?ok=signed_up"
    anna = accounts.get(st, "anna")
    assert anna["display_name"] == "Anna B" and anna["is_admin"] == 0 and anna["hardcover_live"] == 0
    assert accounts.logins(anna) == ["anna", "anna@example.org"]
    # Signing up twice keeps the one reader; her page starts with what to do, not with someone's books.
    c.post("/signup", headers=ANNA)
    assert len(accounts.all_readers(st)) == 2
    page = c.get("/", headers={"Remote-Email": "ANNA@example.org"}).text
    assert "Nothing from your Kobo yet" in page and "Old Finished" not in page
    # A second login with the same user name gets its own reader.
    c.post("/signup", headers={"Remote-User": "anna!", "Remote-Email": "other@example.org", **ORIGIN})
    assert accounts.get(st, "anna-2") is not None
    assert c.post("/signup", headers=ORIGIN).status_code == 403  # no login, no reader


def test_first_reader_of_an_empty_installation_becomes_admin(tmp_path):
    st = state.connect(str(tmp_path / "state.db"))
    accounts.bootstrap(st, str(tmp_path / "none.yaml"), str(tmp_path / "none2.yaml"))
    assert accounts.get(st, accounts.sign_up(st, "first", "", ""))["is_admin"] == 1
    assert accounts.get(st, accounts.sign_up(st, "second", "", ""))["is_admin"] == 0


def test_profile_collection_and_cross_origin(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    assert c.post("/settings/profile", data={"display_name": "X"}, headers={**ROBIN, "Origin": "https://evil.example"}).status_code == 403
    r = c.post("/settings/profile", data={"display_name": "  Robin   T "}, headers=ROBIN, follow_redirects=False)
    assert r.status_code == 303 and accounts.get(st, "robin")["display_name"] == "Robin T"
    assert "Name saved." in c.get(r.headers["location"], headers=ROBIN).text
    r = c.post("/settings/profile", data={"display_name": " "}, headers=ROBIN)
    assert r.status_code == 400 and "Enter a name." in r.text
    c.post("/settings/collection", data={"collection": "Mine"}, headers=ROBIN)
    assert accounts.get(st, "robin")["kobo_collection"] == "Mine"
    c.post("/settings/collection", data={"collection": ""}, headers=ROBIN)
    assert accounts.get(st, "robin")["kobo_collection"] is None


def test_devices_add_upload_remove(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    c.post("/signup", headers=ANNA)
    digest = hashlib.sha256(b"anna-token").hexdigest()
    for bad, text in (
        ({"device": "kobo anna", "hash": digest}, "A device name is"),
        ({"device": "kobo-anna", "hash": "abc"}, "The hash is 64 characters"),
        ({"device": "kobo-anna", "hash": hashlib.sha256(b"old-token").hexdigest()}, "already in use"),
    ):
        r = c.post("/settings/devices/add", data=bad, headers=ANNA)
        assert r.status_code == 400 and text in r.text
    r = c.post("/settings/devices/add", data={"device": "kobo-anna", "hash": digest.upper()}, headers=ANNA, follow_redirects=False)
    assert r.status_code == 303
    page = c.get("/settings", headers=ANNA).text
    assert "kobo-anna" in page and digest[:8] in page and "kobo-robin" not in page
    # The token of that hash uploads for anna, into her own books.
    k = tmp_path / "anna.sqlite"
    make_kobo(k, [MINE], [])
    up = c.put(
        "/upload", content=gzip.compress(k.read_bytes()), headers={"Authorization": "Bearer anna-token", "Content-Type": "application/gzip"}
    )
    assert up.status_code == 200 and up.json()["reader"] == "anna" and up.json()["device"] == "kobo-anna"
    assert "Mine Now" in c.get("/", headers=ANNA).text and "Old Finished" not in c.get("/", headers=ANNA).text
    # Someone else cannot remove it; she can, and then the token is refused.
    c.post("/settings/devices/remove", data={"hash": digest}, headers=ROBIN)
    assert len(accounts.devices(st, "anna")) == 1
    c.post("/settings/devices/remove", data={"hash": digest}, headers=ANNA)
    assert accounts.devices(st, "anna") == []
    assert c.put("/upload", content=b"x", headers={"Authorization": "Bearer anna-token"}).status_code == 401
    assert "Mine Now" in c.get("/", headers=ANNA).text  # what was uploaded stays


def test_token_is_checked_encrypted_and_never_shown(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    monkeypatch.setattr(hardcover, "Client", Hardcover)
    c.post("/signup", headers=ANNA)
    r = c.post("/settings/live", data={"live": "1"}, headers=ANNA)
    assert r.status_code == 400 and "Connect to Hardcover first." in r.text
    r = c.post("/settings/token", data={"token": "wrong"}, headers=ANNA)
    assert r.status_code == 400 and "The token was not stored." in r.text and "Hardcover does not accept your token" in r.text
    assert accounts.token_state(st, "anna") == "none"  # a refused token is not stored
    r = c.post("/settings/token", data={"token": f"Bearer {SECRET} "}, headers=ANNA, follow_redirects=False)
    assert r.status_code == 303
    assert accounts.token_for(st, "anna") == SECRET and accounts.token_state(st, "anna") == "stored"
    raw = open(tmp_path / "state.db", "rb").read()
    assert SECRET.encode() not in raw  # not in the database in the clear
    page = c.get("/settings", headers=ANNA).text
    assert "Connected to Hardcover as @anna_reads" in page and SECRET not in page
    assert SECRET not in c.get("/admin", headers=ROBIN).text
    # Another key cannot read it: the reader is told to enter it again.
    monkeypatch.setenv("KHS_SECRET_KEY", Fernet.generate_key().decode())
    assert accounts.token_for(st, "anna") == "" and accounts.token_state(st, "anna") == "unreadable"


def test_live_and_remove_token(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    monkeypatch.setattr(hardcover, "Client", Hardcover)
    c.post("/signup", headers=ANNA)
    c.post("/settings/token", data={"token": SECRET}, headers=ANNA)
    assert c.post("/settings/live", data={"live": "1"}, headers=ANNA, follow_redirects=False).status_code == 303
    assert accounts.get(st, "anna")["hardcover_live"] == 1
    c.post("/settings/token/remove", headers=ANNA)
    anna = accounts.get(st, "anna")
    assert anna["hardcover_token_enc"] is None and anna["hardcover_live"] == 0  # no token: back to dry run
    assert "Not connected yet" in c.get("/settings", headers=ANNA).text


def test_the_check_card_on_the_server(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    monkeypatch.setattr(hardcover, "Client", Hardcover)
    c.post("/signup", headers=ANNA)
    Hardcover.seen.clear()
    page = c.get("/settings", headers=ANNA).text
    assert 'id="check"' in page and ">Check now</button>" in page and 'class="checks"' not in page
    assert "/settings/token/test" not in page and Hardcover.seen == []  # looking at the page asks Hardcover nothing

    # No token, no computer yet: what is missing, and what to do about it.
    r = c.post("/settings/check", headers=ANNA)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and ">Check again</button>" in r.text
    assert "<b>Hardcover</b> Not connected to Hardcover yet, so nothing is sent to it." in r.text
    assert "To do: Add one under Hardcover, above." in r.text
    assert "<b>Computers</b> No computer uploads your Kobo yet." in r.text
    assert "Run <code>kobo-hardcover-sync setup --server &lt;this address&gt;</code> on the computer" in r.text
    assert "run <code>kobo-hardcover-sync doctor</code> there" in r.text  # the Kobo's half is on the computer
    assert '<span class="sr">warning: </span>' in r.text and "1 warning: its line says what to do." in r.text
    assert Hardcover.seen == []

    # With a token: Hardcover is asked once, and the page shows whose it is and not the token.
    c.post("/settings/token", data={"token": SECRET}, headers=ANNA)
    c.post("/settings/devices/add", data={"device": "kobo-anna", "hash": "a" * 64}, headers=ANNA)
    Hardcover.seen.clear()
    before = "\n".join(st.iterdump())
    r = c.post("/settings/check", headers=ANNA)
    assert Hardcover.seen == [SECRET] and SECRET not in r.text
    assert "<b>Hardcover</b> Hardcover is reachable and accepts the token: it is @anna_reads&#x27;s." in r.text
    assert "<b>Computer</b> kobo-anna: no upload yet." in r.text and '<span class="sr">ok: </span>' in r.text
    assert "\n".join(st.iterdump()) == before  # it changed nothing
    # Robin has books and a computer that uploaded.
    r = c.post("/settings/check", headers=ROBIN)
    assert "<b>Books</b> 0 of 2 books are switched on." in r.text and "<b>Computer</b> kobo-robin: last upload" in r.text
    # A token Hardcover no longer accepts is a problem, said in Hardcover's words.
    monkeypatch.setattr(
        Hardcover, "whoami", lambda self: (_ for _ in ()).throw(hardcover.HardcoverError("Hardcover does not accept your token", "token"))
    )
    r = c.post("/settings/check", headers=ANNA)
    assert '<span class="sr">problem: </span><b>Hardcover</b> Hardcover does not accept your token.' in r.text
    assert '<div class="found" role="status"><div class="act err">' in r.text and "1 problem: its line says what to do." in r.text
    # Another site cannot press the button.
    assert c.post("/settings/check", headers={"Remote-User": "Anna", "Origin": "https://evil.example"}).status_code == 403


def test_the_server_half_of_the_check(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    said = lambda checks: {x.what: (x.state, x.found) for x in checks}  # noqa: E731
    unreadable = said(doctor.server_checks(st, "robin", "unreadable", "", True, []))
    assert unreadable["Token"] == ("fail", "The stored Hardcover token cannot be read any more.") and "Hardcover" not in unreadable
    no_key = said(doctor.server_checks(st, "robin", "none", "", False, []))
    assert no_key["Token"] == ("fail", "Tokens cannot be stored: the server has no KHS_SECRET_KEY.")
    assert said(doctor.server_checks(st, "robin", "env", "t", False, [], client=Hardcover(SECRET)))["Hardcover"][0] == "ok"
    assert said(doctor.server_checks(st, "robin", "none", "", True, []))["Kobo"] == ("note", doctor.ON_THE_COMPUTER)


def test_without_a_key_tokens_cannot_be_stored_and_env_keeps_working(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch, key=False, env_token="Bearer legacy-token")
    monkeypatch.setattr(hardcover, "Client", Hardcover)
    assert accounts.token_for(st, "robin") == "Bearer legacy-token" and accounts.token_state(st, "robin") == "env"
    r = c.post("/settings/token", data={"token": SECRET}, headers=ROBIN)
    assert r.status_code == 400 and "KHS_SECRET_KEY" in r.text
    page = c.get("/settings", headers=ROBIN).text
    assert "Token set on the server by the admin" in page and 'name="token"' not in page
    monkeypatch.setenv("KHS_SECRET_KEY", "not-a-key")  # an invalid key counts as none
    assert not accounts.can_store_tokens()


def test_env_token_moves_into_the_database_once(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch, key=True, env_token="Bearer legacy-token")
    assert accounts.token_state(st, "robin") == "stored" and accounts.token_for(st, "robin") == "legacy-token"
    assert b"legacy-token" not in open(tmp_path / "state.db", "rb").read()
    # Removed on the page stays removed, also after a restart with the variable still set.
    c.post("/settings/token/remove", headers=ROBIN)
    accounts.bootstrap(st, str(tmp_path / "readers.yaml"), str(tmp_path / "devices.yaml"))
    assert accounts.token_for(st, "robin") == ""


def test_admin_says_the_servers_version_and_which_version_uploaded_last(tmp_path, monkeypatch):
    from kobo_hardcover_sync import __version__
    from kobo_hardcover_sync.computer import remote

    c, st = client(tmp_path, monkeypatch)
    c.post("/signup", headers=ANNA)
    c.post("/settings/devices/add", data={"device": "kobo-anna", "hash": hashlib.sha256(b"anna-token").hexdigest()}, headers=ANNA)
    page = c.get("/admin", headers=ROBIN).text
    assert f"<dt>Version</dt><dd>{__version__}</dd>" in page and "This server" in page
    assert "Last upload from" not in page  # no upload yet: nothing to say
    k = tmp_path / "anna.sqlite"
    make_kobo(k, [MINE], [])
    body = gzip.compress(k.read_bytes())

    def upload(agent):
        h = {"Authorization": "Bearer anna-token", "Content-Type": "application/gzip", "User-Agent": agent}
        assert c.put("/upload", content=body, headers=h).status_code == 200

    upload("kobo-hardcover-sync")  # a computer from before 0.7.1 says no version
    assert "Last upload from a version before 0.7.1, which does not say its version" in c.get("/admin", headers=ROBIN).text
    upload("kobo-hardcover-sync/0.7.9")
    assert f"Last upload from version 0.7.9; this server runs {__version__}" in c.get("/admin", headers=ROBIN).text
    upload(f"kobo-hardcover-sync/{__version__}")
    assert f"Last upload from version {__version__}, the same as this server" in c.get("/admin", headers=ROBIN).text
    # And a computer of this version does say it.
    seen = []

    def network(req, timeout):  # what the tool sends, and then no server
        seen.append(req.get_header("User-agent"))
        raise urllib.error.URLError("no server here")

    with pytest.raises(remote.ServerError):
        remote.Server("https://kobo.example.org", "t", opener=network).upload(str(k))
    assert seen == [f"kobo-hardcover-sync/{__version__}"]


def test_admin_page_is_for_admins_and_shows_counts_only(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    c.post("/signup", headers=ANNA)
    assert c.get("/admin", headers=ANNA).status_code == 403
    assert c.post("/admin/role", data={"name": "anna", "admin": "1"}, headers=ANNA).status_code == 403
    assert c.post("/admin/remove", data={"name": "robin"}, headers=ANNA).status_code == 403
    assert (
        c.post("/admin/role", data={"name": "anna", "admin": "1"}, headers={**ROBIN, "Origin": "https://evil.example"}).status_code == 403
    )
    state.set_mode(st, "robin", ["old"], "on")
    st.execute(
        "insert into job (reader, started, finished, live, status, detail) values ('robin','2026-10-01T08:00:00Z','2026-10-01T08:00:05Z',1,'failed',?)",
        ('{"fatal": "request failed: HTTP Error 401: Unauthorized"}',),
    )
    st.commit()
    page = c.get("/admin", headers=ROBIN).text
    assert "1 of 2 syncing" in page and "0 of 0 syncing" in page and "anna@example.org" in page
    assert "Old Finished" not in page and "Mine Now" not in page  # counts, never books
    assert "HTTP Error 401" in page and "1 device<" in page and "0 devices" in page and "Database" in page
    assert "The only admin" in page and 'action="/admin/remove"' in page  # anna can be removed, robin not


def test_admin_roles_and_the_last_admin(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    c.post("/signup", headers=ANNA)
    r = c.post("/admin/role", data={"name": "robin", "admin": "0"}, headers=ROBIN)
    assert r.status_code == 400 and "only admin" in r.text and accounts.get(st, "robin")["is_admin"] == 1
    r = c.post("/admin/remove", data={"name": "robin"}, headers=ROBIN)
    assert r.status_code == 400 and accounts.get(st, "robin") is not None
    assert c.post("/admin/role", data={"name": "anna", "admin": "1"}, headers=ROBIN, follow_redirects=False).status_code == 303
    assert c.get("/admin", headers=ANNA).status_code == 200
    # With two admins one may step down, and lands on Settings.
    r = c.post("/admin/role", data={"name": "robin", "admin": "0"}, headers=ROBIN, follow_redirects=False)
    assert r.headers["location"] == "/settings?ok=role" and c.get("/admin", headers=ROBIN).status_code == 403
    assert c.post("/admin/role", data={"name": "nobody", "admin": "1"}, headers=ANNA).status_code == 400


def test_removing_a_reader_deletes_their_data_only(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    c.post("/signup", headers=ANNA)
    digest = hashlib.sha256(b"anna-token").hexdigest()
    c.post("/settings/devices/add", data={"device": "kobo-anna", "hash": digest}, headers=ANNA)
    k = tmp_path / "anna.sqlite"
    make_kobo(k, [MINE], [])
    c.put(
        "/upload", content=gzip.compress(k.read_bytes()), headers={"Authorization": "Bearer anna-token", "Content-Type": "application/gzip"}
    )
    assert os.path.isdir(tmp_path / "snapshots" / "anna")
    r = c.post("/admin/remove", data={"name": "anna"}, headers=ROBIN, follow_redirects=False)
    assert r.status_code == 303
    con = sqlite3.connect(tmp_path / "state.db")
    for table in ("reader", "book", "device", "device_token", "import"):
        if table == "reader":
            assert con.execute("select count(*) from reader where name='anna'").fetchone()[0] == 0
        else:
            assert con.execute(f"select count(*) from {table} where reader='anna'").fetchone()[0] == 0, table
    assert not os.path.exists(tmp_path / "snapshots" / "anna")
    assert con.execute("select count(*) from book where reader='robin'").fetchone()[0] == 2
    assert c.put("/upload", content=b"x", headers={"Authorization": "Bearer anna-token"}).status_code == 401
    assert "Welcome to Kobo Hardcover Sync" in c.get("/", headers=ANNA).text  # she can start again, empty


def test_stats_and_collection_follow_the_reader_table(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    state.set_mode(st, "robin", ["mine"], "on")
    assert c.get("/collection", headers={"Authorization": "Bearer old-token"}).text == "Robin\nmine\n"


def test_stats_are_off_until_the_reader_makes_a_token(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    h = {**ROBIN, **ORIGIN}
    # Off: the same 401 for a reader without a token, an unknown reader, and any token.
    for path, headers in (("/api/stats/robin", {}), ("/api/stats/nobody", {}), ("/api/stats/robin", {"Authorization": "Bearer guess"})):
        r = c.get(path, headers=headers)
        assert r.status_code == 401 and r.json() == {"error": "a stats token is needed"} and r.headers["www-authenticate"] == "Bearer"
    page = c.get("/settings", headers=ROBIN).text
    assert "Off: nobody can read your stats" in page and "Make a stats token" in page
    # The reader makes a token: shown once, on that page only.
    made = c.post("/settings/stats/token", headers=h, follow_redirects=False)
    shown_at = made.headers["location"]
    assert made.status_code == 303 and shown_at.startswith("/settings?ok=stats_on&show=") and shown_at.endswith("#stats")
    # Someone else following that link sees nothing, and does not use it up.
    c.post("/signup", headers={**ANNA, **ORIGIN})
    assert "secret" not in c.get(shown_at, headers=ANNA).text
    r = c.get(shown_at, headers=ROBIN)
    token = re.search(r'<code class="secret">([^<]+)</code>', r.text).group(1)
    assert r.status_code == 200 and len(token) >= 40 and r.headers["cache-control"] == "no-store" and "Stats token made" in r.text
    # Reloading or restoring that page shows nothing more, and makes no new token.
    again = c.get(shown_at, headers=ROBIN)
    assert again.status_code == 200 and token not in again.text and "Stats token made" not in again.text
    assert (
        token not in c.get("/settings", headers=ROBIN).text
        and "On: readable with your stats token" in c.get("/settings", headers=ROBIN).text
    )
    assert token.encode() not in open(tmp_path / "state.db", "rb").read()  # only its hash is kept
    ok = c.get("/api/stats/robin", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json()["reader"] == "robin" and "minutes_today" in ok.json()
    # It is this reader's key only, and only as a bearer token.
    assert c.get("/api/stats/anna-b", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert c.get("/api/stats/robin", headers={"Authorization": token}).status_code == 401
    assert c.get(f"/api/stats/robin?token={token}").status_code == 401
    # A new token replaces the old one; turning it off closes the door.
    new = re.search(r'<code class="secret">([^<]+)</code>', c.post("/settings/stats/token", headers=h).text).group(1)
    assert new != token and c.get("/api/stats/robin", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert c.get("/api/stats/robin", headers={"Authorization": f"Bearer {new}"}).status_code == 200
    assert c.post("/settings/stats/off", headers=h, follow_redirects=False).headers["location"] == "/settings?ok=stats_off"
    assert c.get("/api/stats/robin", headers={"Authorization": f"Bearer {new}"}).status_code == 401
    # Another site cannot make someone a token.
    assert c.post("/settings/stats/token", headers={**ROBIN, "Origin": "https://evil.example"}).status_code == 403


def test_each_reader_downloads_their_own_reading_and_nobody_else_does(tmp_path, monkeypatch):
    c, st = client(tmp_path, monkeypatch)
    assert 'action="/settings/export"' in c.get("/settings", headers=ROBIN).text
    r = c.get("/settings/export", headers=ROBIN)
    assert r.status_code == 200 and r.headers["content-type"] == "application/json" and r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="kobo-reading-')
    data = r.json()
    assert data["reader"] == "robin" and sorted(b["kobo_id"] for b in data["books"]) == ["mine", "old"]
    assert "reader" not in data["summary"] and SECRET not in r.text
    c.post("/signup", headers={**ANNA, **ORIGIN})
    assert c.get("/settings/export", headers=ANNA).json()["books"] == []  # her own, still empty
    assert c.get("/settings/export", headers={"Remote-User": "stranger"}).status_code == 403
    import kobo_hardcover_sync.web.app as web

    around = client_at(web.app, ELSEWHERE).get("/settings/export", headers=ROBIN)  # past the proxy: the header is not believed
    assert around.status_code == 403 and "mine" not in around.text
