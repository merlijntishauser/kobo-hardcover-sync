"""Server mode fails closed: the reader is believed only from the sign-in
proxy's address, and without that address configured nothing is served."""

import importlib

import pytest
from fastapi.routing import APIRoute

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.server import proxy
from tests import ELSEWHERE, PROXY, client_at
from tests.test_web import client

FORGED = {"Remote-User": "robin", "Remote-Email": "robin@example.org", "X-Forwarded-For": PROXY[0], "X-Real-IP": PROXY[0]}
NOT_THROUGH = "This page is only served through its sign-in proxy."


def test_parse_and_trusted():
    nets = proxy.parse(" 192.0.2.10, 10.1.0.0/16 ;2001:db8::/32,, ")
    assert [str(n) for n in nets] == ["192.0.2.10/32", "10.1.0.0/16", "2001:db8::/32"]
    for host, yes in (
        ("192.0.2.10", True),
        ("192.0.2.11", False),
        ("10.1.200.3", True),
        ("10.2.0.1", False),
        ("2001:db8::7", True),
        ("2001:db9::7", False),
        ("::ffff:192.0.2.10", True),
        ("testclient", False),
        ("", False),
        (None, False),
    ):
        assert proxy.trusted(host, nets) is yes, host
    assert proxy.parse("") == [] and proxy.parse(None) == [] and not proxy.trusted("192.0.2.10", [])
    with pytest.raises(proxy.BadSetting, match="'the-proxy' is not an address"):
        proxy.parse("192.0.2.10, the-proxy")


def test_a_forged_login_from_anywhere_but_the_proxy_gets_403_on_every_route(tmp_path, monkeypatch):
    through = client(tmp_path, monkeypatch)
    import kobo_hardcover_sync.web.app as web

    outside = client_at(web.app, ELSEWHERE)
    checked, left_open = [], set()
    for route in web.app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path.replace("{content_id:path}", "old").replace("{reader}", "robin")
        assert "{" not in path, path
        if path in web.OPEN_PATHS or path.startswith(web.OPEN_PREFIXES):
            left_open.add(route.path)
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = outside.request(method, path, headers=FORGED, data={"x": "1"}, follow_redirects=False)
            assert (r.status_code, r.text) == (403, NOT_THROUGH), (method, path, r.status_code)
            checked.append((method, path))
    # Every page and every form was refused; exactly these four routes are open (each with a key of its own, or no data).
    assert left_open == {"/healthz", "/upload", "/collection", "/api/stats/{reader}"}
    assert {
        ("GET", "/"),
        ("GET", "/settings"),
        ("GET", "/admin"),
        ("POST", "/sync"),
        ("POST", "/mode"),
        ("POST", "/signup"),
        ("POST", "/settings/token"),
        ("POST", "/admin/remove"),
        ("GET", "/cover/old"),
        ("GET", "/details/old"),
        ("POST", "/settings/stats/token"),
    } <= set(checked)
    # The same login through the proxy is served: the refusal is about the address, nothing else.
    assert through.get("/", headers={"Remote-User": "robin"}).status_code == 200
    assert outside.get("/", headers={"Remote-User": "robin"}).status_code == 403
    assert outside.get("/").status_code == 403  # also without a forged header


def test_what_anyone_may_reach_gives_nothing_away(tmp_path, monkeypatch):
    client(tmp_path, monkeypatch)
    import kobo_hardcover_sync.web.app as web

    outside = client_at(web.app, ELSEWHERE)
    assert outside.get("/healthz").text == "ok"
    assert outside.get("/static/kobo.css").status_code == 200
    # The three paths with a token of their own still want it, forged login or not.
    assert outside.put("/upload", headers=FORGED, content=b"x").status_code == 401
    assert outside.get("/collection", headers=FORGED).status_code == 401
    assert outside.get("/api/stats/robin", headers=FORGED).status_code == 401


def test_without_a_proxy_address_nothing_is_served_and_the_server_does_not_start(tmp_path, monkeypatch, capsys):
    c = client(tmp_path, monkeypatch)
    monkeypatch.delenv("KHS_TRUSTED_PROXIES")
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    for address in (PROXY, ELSEWHERE, ("127.0.0.1", 1)):
        nobody = client_at(web.app, address)
        assert nobody.get("/", headers={"Remote-User": "robin"}).status_code == 403
        assert nobody.get("/healthz").status_code == 200
    with pytest.raises(RuntimeError, match="Set KHS_TRUSTED_PROXIES"), client_at(web.app):
        pass  # the app refuses to start
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: pytest.fail("the server was started"))
    for value in (None, "", "the-proxy"):
        if value is None:
            monkeypatch.delenv("KHS_TRUSTED_PROXIES", raising=False)
        else:
            monkeypatch.setenv("KHS_TRUSTED_PROXIES", value)
        with pytest.raises(SystemExit) as ex:
            cli.main(["serve"])
        assert "not started" in str(ex.value.code) and "KHS_TRUSTED_PROXIES" in str(ex.value.code)
    assert c is not None
