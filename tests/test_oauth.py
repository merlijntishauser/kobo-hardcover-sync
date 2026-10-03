"""Signing in to Hardcover with OAuth (the device flow), and keeping the
connection alive. Hardcover here is a stand-in that does what its
documentation says: codes that wait for approval, tokens that are replaced
on every renewal, and a refresh token that ends the whole connection when
it is used twice."""

import fcntl
import io
import re
import threading
import time

import pytest

from kobo_hardcover_sync import cli, doctor, logs
from kobo_hardcover_sync.computer import config, macos, page, runner
from kobo_hardcover_sync.computer.platform import HARDCOVER
from kobo_hardcover_sync.engine import hardcover, oauth, state
from kobo_hardcover_sync.server import accounts
from tests import said
from tests.test_accounts import ANNA, client
from tests.test_computer import FakeComputer
from tests.test_hardcover import FakeHC
from tests.test_local import LOCAL, catalogue, kobo, st

WEEK = 7 * 24 * 3600


class Hardcover:
    """Hardcover's OAuth endpoints, as documented."""

    def __init__(self):
        self.posts, self.n = [], 0
        self.approved = self.denied = self.hurried = self.down = self.ended = False
        self.refresh, self.spent = None, set()

    def pair(self):
        self.n += 1
        self.access, self.refresh = f"hc_at_{self.n}", f"hc_rt_{self.n}"
        return {"access_token": self.access, "refresh_token": self.refresh, "expires_in": WEEK, "token_type": "Bearer"}

    def __call__(self, url, fields, opener=None):
        self.posts.append((url.rsplit("/", 1)[-1], dict(fields)))
        if self.down:
            return 0, {}
        if url == oauth.DEVICE_URL:
            return 200, {
                "device_code": "device-code-not-for-eyes",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://hardcover.app/link",
                "verification_uri_complete": "https://hardcover.app/link?code=ABCD-EFGH",
                "expires_in": 900,
                "interval": 5,
            }
        if url == oauth.REVOKE_URL:
            self.ended = True
            return 200, {}
        if fields["grant_type"] == "authorization_code":  # the browser sign-in: a code, and the PKCE verifier for it
            return (200, self.pair()) if fields["code"] == "a-code" and fields.get("code_verifier") else (400, {"error": "invalid_grant"})
        if fields["grant_type"] == oauth.DEVICE_GRANT:
            if self.denied:
                return 400, {"error": "access_denied"}
            if not self.approved:
                return 400, {"error": "slow_down" if self.hurried else "authorization_pending"}
            return 200, self.pair()
        given = fields["refresh_token"]
        if given in self.spent:  # used twice: taken for stolen, the whole connection goes
            self.ended = True
        if self.ended or given != self.refresh:
            return 400, {"error": "invalid_grant"}
        self.spent.add(given)
        return 200, self.pair()

    def asked(self, what):
        return [f for name, f in self.posts if name == what]


@pytest.fixture
def hc(monkeypatch):
    fake = Hardcover()
    monkeypatch.setattr(oauth, "_post", fake)
    monkeypatch.setenv("KHS_HARDCOVER_CLIENT_ID", "an-app-id")
    return fake


class Me:
    """hardcover.Client for whoami: knows the access tokens the stand-in gave out."""

    seen: list = []

    def __init__(self, token, **kw):
        self.token = hardcover.bare(token)
        Me.seen.append(self.token)

    def whoami(self):
        if not self.token.startswith("hc_at_"):
            raise hardcover.HardcoverError("Hardcover does not accept your token", "token")
        return {"id": 7, "username": "anna_reads"}


class Kept:
    """A place a token is kept in, and the lock around it."""

    def __init__(self, text=""):
        self.text, self.writes, self.inside = text, [], False
        self.read_inside = []

    def read(self):
        self.read_inside.append(self.inside)
        return self.text

    def write(self, text):
        assert self.inside
        self.text = text
        self.writes.append(text)

    def __enter__(self):
        self.inside = True

    def __exit__(self, *a):
        self.inside = False


# ---------- what is kept ----------
def test_a_connection_is_kept_as_one_word_every_store_can_hold():
    tokens = oauth.Tokens("hc_at_AbC-123_xyz", "hc_rt_Zz+9/==", 1_900_000_000)
    kept = tokens.pack()
    assert oauth.unpack(kept) == tokens and kept.startswith("oauth.")
    assert macos.SECRET_OK.match(kept)  # the Keychain helper takes it
    assert "hc_at_" not in kept and "hc_rt_" not in kept  # not readable at a glance in a listing
    for pasted in ("", "eyJhbGciOi.a-pasted-token.xyz", "Bearer abc", "oauth.not-base64!", "oauth.e30="):
        assert oauth.unpack(pasted) is None
    assert oauth.peek("pasted") == "pasted" and oauth.peek("") == ""
    assert oauth.peek(kept, now=1_800_000_000) == "hc_at_AbC-123_xyz" and oauth.peek(kept, now=1_900_000_001) == ""


# ---------- signing in ----------
def test_signing_in_asks_for_the_four_permissions_and_waits_for_approval(hc):
    device = oauth.start()
    assert hc.asked("device") == [{"client_id": "an-app-id", "scope": "read:me:content read:catalog read:library write:library"}]
    assert (device.user_code, device.link, device.link_with_code, device.interval) == (
        "ABCD-EFGH",
        "https://hardcover.app/link",
        "https://hardcover.app/link?code=ABCD-EFGH",
        5,
    )
    assert oauth.collect(device) == 5  # not approved yet: ask again in five seconds
    hc.hurried = True
    assert oauth.collect(device) == 10  # asked too often: slower
    hc.down = True
    assert oauth.collect(device) == 5  # no answer: the same question again later
    hc.down, hc.approved = False, True
    tokens = oauth.collect(device)
    assert (tokens.access, tokens.refresh) == ("hc_at_1", "hc_rt_1") and abs(tokens.expires - time.time() - WEEK) < 5
    assert hc.asked("token")[-1] == {"grant_type": oauth.DEVICE_GRANT, "device_code": "device-code-not-for-eyes", "client_id": "an-app-id"}


def test_a_sign_in_that_is_refused_or_runs_out_or_cannot_start(hc, monkeypatch):
    device = oauth.start()
    hc.denied = True
    with pytest.raises(oauth.OAuthError, match="refused on Hardcover") as ex:
        oauth.collect(device)
    assert ex.value.code == "access_denied"
    late = oauth.Device("d", "u", "l", "l", expires=time.monotonic() - 1, interval=5)
    posts = len(hc.posts)
    with pytest.raises(oauth.OAuthError, match="The code has run out"):
        oauth.collect(late)
    assert len(hc.posts) == posts  # not even asked
    hc.down = True
    with pytest.raises(oauth.OAuthError, match="could not be reached") as ex:
        oauth.start()
    assert ex.value.code == "unreachable"
    monkeypatch.delenv("KHS_HARDCOVER_CLIENT_ID")
    monkeypatch.setattr(oauth, "CLIENT_ID", "")
    assert not oauth.available()
    with pytest.raises(oauth.OAuthError) as ex:
        oauth.start()
    assert ex.value.code == "no_app"


# ---------- renewing ----------
def connection(hc, left):
    """A connection whose access token has `left` seconds to go."""
    hc.approved = True
    pair = hc.pair()
    return oauth.Tokens(pair["access_token"], pair["refresh_token"], int(time.time()) + left).pack()


def test_a_pasted_token_and_a_fresh_connection_are_used_as_they_are(hc):
    pasted = Kept("a-pasted-token")
    assert oauth.usable(pasted.read, pasted.write, pasted) == "a-pasted-token"
    fresh = Kept(connection(hc, left=3 * 24 * 3600))
    assert oauth.usable(fresh.read, fresh.write, fresh) == "hc_at_1"
    assert hc.asked("token") == [] and pasted.writes == fresh.writes == []
    assert pasted.read_inside == [True] and fresh.read_inside == [True]  # read under the lock, always


def test_a_connection_about_to_run_out_is_renewed_and_kept_before_it_is_used(hc):
    kept = Kept(connection(hc, left=3600))
    assert oauth.usable(kept.read, kept.write, kept) == "hc_at_2"
    assert hc.asked("token") == [{"grant_type": "refresh_token", "refresh_token": "hc_rt_1", "client_id": "an-app-id"}]
    assert [oauth.unpack(w).refresh for w in kept.writes] == ["hc_rt_2"] and kept.read_inside == [True]
    # Again right away: the new one is fresh, Hardcover is not asked.
    assert oauth.usable(kept.read, kept.write, kept) == "hc_at_2" and len(hc.asked("token")) == 1


def test_when_hardcover_does_not_answer_the_spent_token_is_not_sent_blindly(hc):
    kept = Kept(connection(hc, left=3600))
    hc.down = True
    assert oauth.usable(kept.read, kept.write, kept) == "hc_at_1"  # still good for an hour: used, and nothing kept anew
    assert kept.writes == []
    run_out = Kept(connection(hc, left=-60))
    with pytest.raises(hardcover.HardcoverError, match="could not be reached to renew") as ex:
        oauth.usable(run_out.read, run_out.write, run_out)
    assert ex.value.kind == "unreachable" and run_out.writes == []


def test_a_connection_hardcover_ended_says_connect_again(hc):
    kept = Kept(connection(hc, left=3600))
    hc.ended = True  # revoked on Hardcover's own page
    with pytest.raises(hardcover.HardcoverError, match="no longer accepts this connection. Connect again under Settings") as ex:
        oauth.usable(kept.read, kept.write, kept)
    assert ex.value.kind == "token" and ex.value.stops_the_run and kept.writes == []


def test_the_stand_in_ends_a_connection_whose_refresh_token_is_used_twice(hc):
    """The rule everything above is built around."""
    kept = connection(hc, left=3600)
    first = oauth.renew(oauth.unpack(kept).refresh)
    with pytest.raises(oauth.OAuthError):
        oauth.renew(oauth.unpack(kept).refresh)  # the old one again
    with pytest.raises(oauth.OAuthError):
        oauth.renew(first.refresh)  # and now the new one is dead too
    assert hc.ended


# ---------- on a server ----------
def connected(tmp_path, monkeypatch, hc):
    c, db = client(tmp_path, monkeypatch)
    monkeypatch.setattr(hardcover, "Client", Me)
    c.post("/signup", headers=ANNA)
    return c, db


def test_connecting_on_the_page(tmp_path, monkeypatch, hc):
    c, db = connected(tmp_path, monkeypatch, hc)
    page_ = c.get("/settings", headers=ANNA).text
    assert ">Connect to Hardcover</button>" in page_ and "<summary>Paste a token instead</summary>" in page_
    assert hc.posts == []  # looking at Settings asks Hardcover nothing

    r = c.post("/settings/connect", headers=ANNA)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert 'href="https://hardcover.app/link?code=ABCD-EFGH" target="_blank" rel="noopener noreferrer"' in r.text
    assert '<code class="code">ABCD-EFGH</code>' in r.text and 'data-poll="/settings/connect/check" data-every="5"' in r.text
    assert "device-code-not-for-eyes" not in r.text and ">Connect to Hardcover</button>" not in r.text
    assert '<code class="code">ABCD-EFGH</code>' in c.get("/settings", headers=ANNA).text  # it waits, also after a reload

    # Not approved yet: the button says so; the page's own question gets a short answer.
    r = c.post("/settings/connect/check", headers=ANNA)
    assert r.status_code == 200 and "Not approved on Hardcover yet." in r.text
    assert c.post("/settings/connect/check", headers={**ANNA, "X-Requested-With": "fetch"}).json() == {"done": False, "wait": 5}
    assert accounts.token_kind(db, "anna") == ""

    hc.approved = True
    r = c.post("/settings/connect/check", headers=ANNA, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings?ok=connected"
    assert accounts.token_kind(db, "anna") == "oauth" and accounts.token_for(db, "anna") == "hc_at_1" and Me.seen[-1] == "hc_at_1"
    raw = open(tmp_path / "state.db", "rb").read()
    assert b"hc_at_" not in raw and b"hc_rt_" not in raw and b"oauth." not in raw  # encrypted, like a pasted token
    done = c.get("/settings?ok=connected", headers=ANNA).text
    assert "Connected to Hardcover." in done and "Connected to Hardcover as @anna_reads" in done
    assert ">Disconnect</button>" in done and "hc_at_" not in done and "hc_rt_" not in done and "ABCD-EFGH" not in done
    assert ">Connect to Hardcover</button>" not in done and "<summary>Paste a token instead</summary>" in done

    # Disconnecting ends it at Hardcover too, and syncing is back in dry run.
    c.post("/settings/live", data={"live": "1"}, headers=ANNA)
    c.post("/settings/token/remove", headers=ANNA)
    assert hc.asked("revoke") == [{"token": "hc_rt_1", "token_type_hint": "refresh_token", "client_id": "an-app-id"}]
    assert accounts.token_kind(db, "anna") == "" and accounts.get(db, "anna")["hardcover_live"] == 0


def test_a_sign_in_that_fails_on_the_page_and_one_from_elsewhere(tmp_path, monkeypatch, hc):
    c, db = connected(tmp_path, monkeypatch, hc)
    assert c.post("/settings/connect", headers={"Remote-User": "Anna", "Origin": "https://evil.example"}).status_code == 403
    c.post("/settings/connect", headers=ANNA)
    hc.denied = True
    r = c.post("/settings/connect/check", headers=ANNA)
    assert r.status_code == 400 and "Connecting to Hardcover did not work." in r.text and "The sign-in was refused on Hardcover." in r.text
    assert ">Connect to Hardcover</button>" in r.text  # back to the start
    assert c.post("/settings/connect/check", headers=ANNA, follow_redirects=False).status_code == 303  # nothing waits any more
    # Cancelled by the reader.
    hc.denied = False
    c.post("/settings/connect", headers=ANNA)
    assert c.post("/settings/connect/cancel", headers=ANNA, follow_redirects=False).headers["location"] == "/settings"
    assert "ABCD-EFGH" not in c.get("/settings", headers=ANNA).text
    # Hardcover out of reach when starting.
    hc.down = True
    r = c.post("/settings/connect", headers=ANNA)
    assert r.status_code == 502 and "Hardcover could not be reached. Try again in a moment." in r.text
    # An installation without an app to connect through keeps the form it had.
    monkeypatch.delenv("KHS_HARDCOVER_CLIENT_ID")
    monkeypatch.setattr(oauth, "CLIENT_ID", "")
    plain = c.get("/settings", headers=ANNA).text
    assert "Connect to Hardcover" not in plain and '<button class="solid">Check and save</button>' in plain


def test_everything_that_wants_the_token_at_once_renews_it_once(tmp_path, monkeypatch, hc):
    c, db = connected(tmp_path, monkeypatch, hc)
    accounts.set_token(db, "anna", connection(hc, left=3600), "anna_reads")
    slow = hc.__call__

    def slowly(url, fields, opener=None):
        time.sleep(0.05)  # long enough for the others to arrive
        return slow(url, fields, opener)

    monkeypatch.setattr(oauth, "_post", slowly)
    got, errors = [], []

    def use():
        try:
            got.append(accounts.token_for(state.connect(str(tmp_path / "state.db")), "anna"))
        except Exception as ex:  # a replayed refresh token would show up here
            errors.append(ex)

    threads = [threading.Thread(target=use) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and got == ["hc_at_2"] * 8
    assert len(hc.asked("token")) == 1 and not hc.ended  # one renewal, the connection lives


def test_a_connection_that_ended_is_said_on_the_page_not_passed_over(tmp_path, monkeypatch, hc):
    c, db = connected(tmp_path, monkeypatch, hc)
    accounts.set_token(db, "anna", connection(hc, left=3600), "anna_reads")
    accounts.set_live(db, "anna", True)
    assert hc.asked("token") == []  # going live looks whether there is a token, and asks Hardcover nothing
    hc.ended = True
    started = []
    monkeypatch.setattr("kobo_hardcover_sync.engine.job.start", lambda *a, **kw: started.append(a))
    c.post("/sync", headers=ANNA)
    assert started == []  # there is nothing to start a run with
    failed = db.execute("select detail from job where reader = 'anna' and status = 'failed'").fetchall()
    assert len(failed) == 1 and "no longer accepts this connection. Connect again under Settings" in failed[0]["detail"]
    checked = c.post("/settings/check", headers=ANNA).text
    assert "stopped: Hardcover no longer accepts this connection. Connect again under Settings." in checked


def test_the_check_renews_nothing(tmp_path, monkeypatch, hc):
    c, db = connected(tmp_path, monkeypatch, hc)
    accounts.set_token(db, "anna", connection(hc, left=3600), "anna_reads")  # about to run out: a sync would renew
    r = c.post("/settings/check", headers=ANNA)
    assert "Hardcover is reachable and accepts the token: it is @anna_reads&#x27;s." in r.text and Me.seen[-1] == "hc_at_1"
    assert hc.asked("token") == []
    accounts.set_token(db, "anna", connection(hc, left=-60), "anna_reads")  # run out
    r = c.post("/settings/check", headers=ANNA)
    assert "The connection to Hardcover is renewed at the next sync; it was not asked about now." in r.text and hc.asked("token") == []


# ---------- the browser sign-in, back to this computer ----------
def test_the_browser_sign_in_is_on_and_can_be_switched_off(hc, monkeypatch):
    # On since Hardcover has the address registered (and ignores its port): seen working 2026-10-03.
    assert oauth.LOOPBACK_READY is True and oauth.loopback() is True
    monkeypatch.setenv("KHS_HARDCOVER_LOOPBACK", "0")
    assert oauth.loopback() is False  # back to the device flow
    monkeypatch.setenv("KHS_HARDCOVER_LOOPBACK", "1")
    assert oauth.loopback() is True
    monkeypatch.setenv("KHS_HARDCOVER_CLIENT_ID", "")
    monkeypatch.setattr(oauth, "CLIENT_ID", "")
    assert oauth.loopback() is False  # no app to sign in through, no sign-in


def test_the_browser_sign_in_sends_a_challenge_and_takes_only_its_own_answer(hc):
    import base64
    import hashlib
    import urllib.parse

    sign_in = oauth.browser_start(5555)
    url = urllib.parse.urlparse(sign_in.url)
    q = dict(urllib.parse.parse_qsl(url.query))
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://hardcover.app/oauth2/authorize"
    assert q["response_type"] == "code" and q["client_id"] == "an-app-id" and q["scope"] == " ".join(hardcover.SCOPES)
    assert q["redirect_uri"] == "http://127.0.0.1:5555/oauth/callback" and q["state"] == sign_in.state
    # PKCE: only the hash of the secret goes out; the secret goes with the code, to the token endpoint.
    assert q["code_challenge_method"] == "S256" and sign_in.verifier not in sign_in.url
    assert q["code_challenge"] == base64.urlsafe_b64encode(hashlib.sha256(sign_in.verifier.encode()).digest()).rstrip(b"=").decode()
    back = {"code": "a-code", "state": sign_in.state, "iss": "https://api.hardcover.app"}
    for wrong, code in (({"state": "someone-elses"}, "state"), ({"iss": "https://evil.example"}, "iss"), ({"code": ""}, "answer")):
        with pytest.raises(oauth.OAuthError) as ex:
            oauth.browser_finish(sign_in, {**back, **wrong})
        assert ex.value.code == code
    with pytest.raises(oauth.OAuthError, match="refused on Hardcover"):
        oauth.browser_finish(sign_in, {"error": "access_denied", "state": sign_in.state})
    assert hc.asked("token") == []  # none of those reached Hardcover
    tokens = oauth.browser_finish(sign_in, back)
    sent = hc.asked("token")[0]
    assert tokens.access == "hc_at_1" and sent["code_verifier"] == sign_in.verifier and sent["redirect_uri"] == sign_in.redirect_uri


# ---------- on your own computer ----------
def test_the_token_command_connects_at_a_terminal_and_still_takes_a_pasted_one(home, monkeypatch, capsys, hc):
    monkeypatch.setenv("KHS_HARDCOVER_LOOPBACK", "0")  # the device flow, as `token --code` gives it too
    mac = FakeComputer(home / "Volumes")
    cli.main(["setup", "--local", "--no-trigger"], computer=mac)
    capsys.readouterr()
    monkeypatch.setattr(hardcover, "Client", Me)
    waits = []

    def wait(seconds):
        waits.append(seconds)
        hc.approved = len(waits) >= 2  # approved while the tool waits

    monkeypatch.setattr(cli.time, "sleep", wait)
    terminal = io.StringIO()
    terminal.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", terminal)
    cli.main(["token"], computer=mac)
    out = said(capsys)
    assert (
        "Connect to Hardcover 1. Open this address (it is being opened for you) and approve: https://hardcover.app/link?code=ABCD-EFGH"
        in out
    )
    assert "2. Check that Hardcover shows this code: ABCD-EFGH" in out and out.endswith("ok Connected. Hardcover knows you as @anna_reads.")
    assert mac.opened == ["https://hardcover.app/link?code=ABCD-EFGH"] and waits == [5, 5]
    assert oauth.unpack(mac.secrets[HARDCOVER]).refresh == "hc_rt_1" and "hc_" not in out and "device-code" not in out
    # Disconnecting ends it at Hardcover.
    cli.main(["token", "--remove"], computer=mac)
    assert mac.secrets == {} and hc.asked("revoke") and "Disconnected from Hardcover." in said(capsys)
    # --paste, or a token piped in: as before.
    monkeypatch.setattr(hardcover, "Client", lambda token, **kw: type("C", (), {"whoami": lambda self: {"username": "sam"}})())
    monkeypatch.setattr("sys.stdin", io.StringIO("a-pasted-token\n"))
    cli.main(["token"], computer=mac)
    assert mac.secrets == {HARDCOVER: "a-pasted-token"} and said(capsys) == "ok Stored. Hardcover knows you as @sam."


def test_the_token_command_signs_in_through_the_browser_when_that_is_switched_on(home, monkeypatch, capsys, hc):
    import urllib.parse
    import urllib.request

    mac = FakeComputer(home / "Volumes")
    cli.main(["setup", "--local", "--no-trigger"], computer=mac)
    capsys.readouterr()
    monkeypatch.setattr(hardcover, "Client", Me)
    monkeypatch.setenv("KHS_HARDCOVER_LOOPBACK", "1")
    terminal = io.StringIO()
    terminal.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", terminal)

    def browser(url):  # the reader approves; Hardcover sends the browser back to the tool
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        back = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "a-code", "state": q["state"], "iss": "https://api.hardcover.app"})
        threading.Thread(target=lambda: urllib.request.urlopen(back, timeout=10).read(), daemon=True).start()

    monkeypatch.setattr(mac, "open_page", browser)
    cli.main(["token"], computer=mac)
    out = said(capsys)
    assert "Approve on Hardcover, in the browser that is being opened for you." in out and "token --code" in out
    assert out.endswith("ok Connected. Hardcover knows you as @anna_reads.") and "a-code" not in out
    assert oauth.unpack(mac.secrets[HARDCOVER]).refresh == "hc_rt_1" and hc.asked("device") == []
    # --code: the device flow, as without the switch.
    cli.main(["token", "--remove"], computer=mac)
    capsys.readouterr()
    monkeypatch.setattr(mac, "open_page", lambda url: setattr(hc, "approved", True))
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    cli.main(["token", "--code"], computer=mac)
    assert hc.asked("device") and "Check that Hardcover shows this code: ABCD-EFGH" in said(capsys)


def test_a_local_sync_renews_and_one_whose_connection_ended_says_so(home, hc):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, connection(hc, left=3600))
    seen = []

    class Books(FakeHC):
        pass

    real = runner.job.run

    def run(db_path, reader, live, client=None, token=""):
        seen.append(token)
        return real(db_path, reader, live, client=Books(isbn=catalogue()), token=token)

    runner.job.run, restore = run, real
    try:
        out = runner.sync(mac, LOCAL)
        assert out.ok and seen == ["hc_at_2"] and oauth.unpack(mac.secrets[HARDCOVER]).refresh == "hc_rt_2"
        hc.ended = True
        mac.set_secret(HARDCOVER, oauth.Tokens("hc_at_2", "hc_rt_2", int(time.time()) + 60).pack())
        steps = []
        out = runner.sync(mac, LOCAL, on_step=steps.append)
        assert out.ok and "Hardcover no longer accepts this connection. Connect again under Settings." in out.message
        assert [(s.state, s.what) for s in steps if s.what == "Hardcover"] == [("fail", "Hardcover")] and len(seen) == 1
        failed = st(home).execute("select detail from job where status = 'failed'").fetchall()
        assert len(failed) == 1 and "Connect again" in failed[0]["detail"]
    finally:
        runner.job.run = restore


def test_a_sync_and_the_page_cannot_renew_at_the_same_moment(home, hc):
    mac = FakeComputer(home / "Volumes")
    mac.set_secret(HARDCOVER, connection(hc, left=3600))
    sync_side, page_side = page.KeptToken(mac), page.KeptToken(mac)
    with sync_side.lock():
        with open(home / "state" / "hardcover.lock") as other:  # what another program would meet
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert sync_side.usable() == "hc_at_2" and page_side.usable() == "hc_at_2" and len(hc.asked("token")) == 1


def test_doctor_looks_at_a_connection_without_renewing_it(home, hc, monkeypatch):
    mac = FakeComputer(home / "Volumes")
    config.save(config.Config())
    monkeypatch.setattr(hardcover, "Client", Me)
    mac.set_secret(HARDCOVER, connection(hc, left=3600))
    found = {c.what: c for c in doctor.computer_checks(mac, LOCAL)}
    assert found["Token"].found.startswith("The connection to Hardcover is kept in ") and found["Hardcover"].state == "ok"
    assert Me.seen[-1] == "hc_at_1" and hc.asked("token") == [] and oauth.unpack(mac.secrets[HARDCOVER]).refresh == "hc_rt_1"
    mac.set_secret(HARDCOVER, connection(hc, left=-60))
    found = {c.what: c for c in doctor.computer_checks(mac, LOCAL)}
    assert found["Hardcover"].state == "note" and "renewed at the next sync" in found["Hardcover"].found and hc.asked("token") == []


def test_nothing_of_a_sign_in_reaches_the_log(home, hc, monkeypatch):
    logs.to_file(str(home / "state" / "agent.log"), verbose=True)
    monkeypatch.undo()  # the real _post, against an opener that plays Hardcover

    class Answer:
        status = 200

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    sent = []

    def opener(req, timeout):
        sent.append(req.data.decode())
        if req.full_url == oauth.DEVICE_URL:
            return Answer(b'{"device_code": "device-code-not-for-eyes", "user_code": "ABCD-EFGH", "expires_in": 900, "interval": 5}')
        return Answer(b'{"access_token": "hc_at_secret", "refresh_token": "hc_rt_secret", "expires_in": 604800}')

    import os

    os.environ["KHS_HARDCOVER_CLIENT_ID"] = "an-app-id"
    try:
        device = oauth.start(opener)
        tokens = oauth.collect(device, opener)
        oauth.renew(tokens.refresh, opener)
    finally:
        del os.environ["KHS_HARDCOVER_CLIENT_ID"]
        logs._start([], False)
    log = open(home / "state" / "agent.log").read()
    assert "client_id=an-app-id" in sent[0] and "refresh_token=hc_rt_secret" in sent[-1]  # it was sent
    assert re.findall(r"detail (oauth \w+: \d+)", log) == ["oauth device: 200", "oauth token: 200", "oauth token: 200"]
    for secret in ("hc_at_secret", "hc_rt_secret", "device-code-not-for-eyes", "ABCD-EFGH", "an-app-id"):
        assert secret not in log
