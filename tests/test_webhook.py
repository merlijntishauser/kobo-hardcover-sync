"""The webhook: after a sync that read the Kobo, a POST to an address of
the reader's own. Not tied to any service, so it is tested against a real
little HTTP server on this computer: what arrives, with which headers, and
that a redirect is never followed with the token."""

import io
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.computer import config, runner, webhook
from kobo_hardcover_sync.computer.platform import WEBHOOK
from tests import said
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer
from tests.test_local import LOCAL, kobo

HOOK_TOKEN = "hook-token-made-up-123"


class Receiver:
    """An API of the reader's own: keeps what it is sent, answers `status`."""

    def __init__(self):
        self.got, self.status, self.location = [], 200, ""
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                receiver.got.append((self.path, dict(self.headers), json.loads(body)))
                self.send_response(receiver.status)
                if receiver.location:
                    self.send_header("Location", receiver.location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def api():
    r = Receiver()
    yield r
    r.server.shutdown()


def test_which_addresses_it_takes():
    assert webhook.problem("https://tracker.example.org/api/kobo") == ""
    for local in ("http://127.0.0.1:8000/hook", "http://localhost/hook", "http://[::1]:9/x"):
        assert webhook.problem(local) == "", local
    assert "Only https" in webhook.problem("http://tracker.example.org/hook")
    assert "Only https" in webhook.problem("http://198.51.100.5/hook")  # any other machine is across a network
    assert "--token" in webhook.problem("https://me:secret@tracker.example.org/hook")
    for wrong in ("ftp://example.org/x", "tracker.example.org/hook", "", "https://"):
        assert "not a web address" in webhook.problem(wrong), wrong


def test_a_redirect_is_not_followed_with_the_token(api):
    api.status, api.location = 302, api.url + "/elsewhere"
    with pytest.raises(webhook.WebhookError, match="answered with a redirect \\(302\\)"):
        webhook.post(api.url + "/hook", HOOK_TOKEN, {"a": 1})
    assert [path for path, _, _ in api.got] == ["/hook"]  # never /elsewhere
    api.status, api.location = 500, ""
    with pytest.raises(webhook.WebhookError, match="127.0.0.1 answered 500"):
        webhook.post(api.url + "/hook", "", {"a": 1})
    api.server.shutdown()
    api.server.server_close()
    with pytest.raises(webhook.WebhookError, match="could not reach 127.0.0.1"):
        webhook.post(api.url + "/hook", "", {"a": 1})


def test_set_up_tested_then_every_sync_that_reads_the_kobo(home, api, monkeypatch, capsys):
    db = kobo(home)
    mac = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    first = runner.sync(mac, LOCAL)  # no webhook yet: nothing is sent
    assert first.ok and api.got == []

    # A test that is refused stores nothing.
    api.status = 401
    monkeypatch.setattr("sys.stdin", io.StringIO(f"Bearer {HOOK_TOKEN}\n"))
    with pytest.raises(SystemExit, match="the test was not taken: 127.0.0.1 answered 401. Nothing was stored."):
        cli.main(["webhook", api.url + "/kobo", "--token"], computer=mac)
    assert config.load().webhook_url == "" and WEBHOOK not in mac.secrets

    api.status, api.got = 200, []
    monkeypatch.setattr("sys.stdin", io.StringIO(f"Bearer {HOOK_TOKEN}\n"))
    cli.main(["webhook", api.url + "/kobo", "--token"], computer=mac)
    assert "ok Test 127.0.0.1 answered 200" in said(capsys)
    path, headers, test = api.got[0]
    assert path == "/kobo" and headers["Authorization"] == f"Bearer {HOOK_TOKEN}" and headers["Content-Type"] == "application/json"
    assert headers["User-Agent"].startswith("kobo-hardcover-sync/")
    assert (test["event"], test["format"], test["first_sync"], test["changed"]) == ("test", 1, False, [])
    assert config.load().webhook_url == api.url + "/kobo" and mac.secrets[WEBHOOK] == HOOK_TOKEN
    assert HOOK_TOKEN not in open(config.load().path).read()
    cli.main(["status"], computer=mac)
    assert f"ok Webhook POST to {api.url}/kobo after a sync that reads the Kobo" in said(capsys)

    # Reading on the Kobo: one book further. The next sync sends that book, and the book being read.
    con = sqlite3.connect(db)
    con.execute("update content set ___PercentRead = 55, DateLastRead = '2026-10-06T08:00:00Z' where ContentID = ?", (BOOKS[3],))
    con.execute("insert into Event values (3, '2026-10-06T07:00:00', '2026-10-06T08:00:00', 1, ?)", (BOOKS[3],))
    con.commit()
    con.close()
    api.got = []
    synced = runner.sync(mac, config.load())
    assert synced.ok and "Webhook" not in synced.message  # a webhook that worked is not news
    ((_, headers, event),) = api.got
    assert event["event"] == "sync" and event["first_sync"] is False and headers["Authorization"] == f"Bearer {HOOK_TOKEN}"
    assert [b["kobo_id"] for b in event["changed"]] == [BOOKS[3]] and event["changed"][0]["percent"] == 55
    assert event["reading"]["title"] == "Made-up Book 3" and event["summary"]["current_title"] == "Made-up Book 3"
    assert "reader" not in event["summary"] and event["device"].startswith("kobo")

    # Plugged in again with nothing new: nothing is sent.
    api.got = []
    assert runner.sync(mac, config.load()).ok and api.got == []

    # The API is down: said, and the sync is still done.
    con = sqlite3.connect(db)
    con.execute("update content set ___PercentRead = 60 where ContentID = ?", (BOOKS[3],))
    con.commit()
    con.close()
    api.status = 503
    down = runner.sync(mac, config.load())
    assert down.ok and "Webhook not sent: 127.0.0.1 answered 503." in down.message

    # A new address does not take the old one's token along; --remove forgets both.
    api.status, api.got = 200, []
    cli.main(["webhook", api.url + "/other"], computer=mac)
    assert "Authorization" not in api.got[0][1] and WEBHOOK not in mac.secrets
    cli.main(["webhook", "--remove"], computer=mac)
    assert config.load().webhook_url == "" and "No webhook any more" in said(capsys)
    with pytest.raises(SystemExit, match="no webhook yet"):
        cli.main(["webhook", "--test"], computer=mac)


def test_only_where_it_can_do_no_harm(home):
    mac = FakeComputer(home / "Volumes")
    with pytest.raises(SystemExit, match="run setup first"):
        cli.main(["webhook", "https://tracker.example.org/x"], computer=mac)
    config.save(LOCAL)
    with pytest.raises(SystemExit, match="Only https"):
        cli.main(["webhook", "http://tracker.example.org/x"], computer=mac)
    config.save(config.Config(server="https://kobo.example.org"))
    with pytest.raises(SystemExit, match="the webhook is for local mode"):
        cli.main(["webhook", "https://tracker.example.org/x"], computer=mac)
    assert not os.path.exists(home / "state" / "state.db")
