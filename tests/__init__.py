from fastapi.testclient import TestClient

# The address the tests' requests come from: the sign-in proxy, as far as the
# app is concerned (tests/conftest.py puts it in KHS_TRUSTED_PROXIES).
PROXY = ("192.0.2.10", 50000)
ELSEWHERE = ("203.0.113.5", 50000)


def said(capsys) -> str:
    """What a command printed, as one run of words: where a line was folded is the screen's business."""
    return " ".join(capsys.readouterr().out.split())


def client_at(app, address=PROXY) -> TestClient:
    """A test client whose requests reach the app from `address`."""

    async def from_address(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": address}
        await app(scope, receive, send)

    return TestClient(from_address)
