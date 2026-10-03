"""Signing in to Hardcover with OAuth, by the device flow (RFC 8628).

Hardcover asks an app that other people install not to take a pasted token
(docs/hardcover-api.md). This tool is such an app, and it runs in two
places it cannot tell apart from the outside: a reader's own computer, and
a household's own server at an address only they know. The device flow
fits both: the tool shows a link and a short code, the reader approves on
hardcover.app, and the tool collects the tokens. No address to come back
to, and no secret that would have to ship in public code.

What Hardcover hands out (their OAuth page, 2026-09-24):
- an access token, good for a week, used exactly like a pasted token;
- a refresh token, good for six months, **replaced on every use**. One that
  is used twice is taken for stolen, and Hardcover then revokes the whole
  connection: the reader has to connect again.

So renewing is the delicate part, and `usable` is the one place that does
it: under a lock the caller provides, reading the newest tokens inside
that lock, and saving the new pair before handing anything back. A renewal
that fails without an answer is not sent again as long as the access token
still works: it may have arrived, and sending it twice is the one thing
that must not happen.

The app is registered at Hardcover by this project; its id is public (the
flow has no secret). KHS_HARDCOVER_CLIENT_ID names another app, for a fork
or for someone who wants their own.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import hardcover

# The app "Kobo Hardcover Sync" at Hardcover (type: mobile, desktop or CLI; device flow only).
CLIENT_ID = ""
DEVICE_URL = os.environ.get("HARDCOVER_OAUTH_DEVICE", "https://api.hardcover.app/oauth2/device")
TOKEN_URL = os.environ.get("HARDCOVER_OAUTH_TOKEN", "https://api.hardcover.app/oauth2/token")
REVOKE_URL = os.environ.get("HARDCOVER_OAUTH_REVOKE", "https://api.hardcover.app/oauth2/revoke")
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

RENEW_BEFORE = 24 * 3600  # an access token is renewed when it has less than a day left
PREFIX = "oauth."  # how a kept OAuth connection is told from a pasted token
log = logging.getLogger(__name__)


def client_id() -> str:
    return (os.environ.get("KHS_HARDCOVER_CLIENT_ID") or CLIENT_ID).strip()


def available() -> bool:
    """Can a reader connect with OAuth? Only with an app to connect through."""
    return bool(client_id())


class OAuthError(Exception):
    """A step of signing in or renewing did not work. `code`: Hardcover's
    own word for it (access_denied, expired_token, invalid_grant, ...), or
    "unreachable" when there was no usable answer."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str
    expires: int  # when the access token stops working, in seconds since 1970

    def pack(self) -> str:
        """As one word that every place a token is kept in can hold (the
        Keychain helper takes letters, digits and a few signs)."""
        raw = json.dumps({"a": self.access, "r": self.refresh, "e": self.expires}, separators=(",", ":"))
        return PREFIX + base64.b64encode(raw.encode()).decode()


def unpack(kept: str) -> Tokens | None:
    """The OAuth connection in what is kept, or None: nothing kept, a
    pasted token, or something this code did not write."""
    if not (kept or "").startswith(PREFIX):
        return None
    try:
        d = json.loads(base64.b64decode(kept[len(PREFIX) :]))
        return Tokens(str(d["a"]), str(d["r"]), int(d["e"]))
    except (ValueError, KeyError, TypeError):
        return None


@dataclass(frozen=True)
class Device:
    """A sign-in that waits for the reader: where to go, what to enter
    there, and how to ask whether they have."""

    device_code: str  # for asking; never shown
    user_code: str
    link: str  # where the reader enters the code
    link_with_code: str  # the same, with the code filled in
    expires: float  # time.monotonic() after which this sign-in is over
    interval: int  # seconds to leave between two questions


def _post(url: str, fields: dict, opener=None) -> tuple[int, dict]:
    """One form post. (status, what was answered); status 0: no answer."""
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": hardcover.USER_AGENT},
    )
    try:
        with (opener or urllib.request.urlopen)(req, timeout=30) as r:
            status, raw = int(getattr(r, "status", 200) or 200), r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:  # no name, no route, refused, reset, timed out
        log.debug("oauth %s: no answer (%s)", url.rsplit("/", 1)[-1], getattr(e, "reason", None) or e.__class__.__name__)
        return 0, {}
    try:
        said = json.loads(raw)
    except ValueError:
        said = {}
    log.debug("oauth %s: %s", url.rsplit("/", 1)[-1], status)  # what was asked and how it went; never what was sent or came back
    return status, said if isinstance(said, dict) else {}


def _tokens(said: dict) -> Tokens:
    access, refresh = said.get("access_token"), said.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
        raise OAuthError("Hardcover gave an answer this tool does not understand (no tokens in it)", "answer")
    try:
        lasts = int(said.get("expires_in") or 0)
    except (TypeError, ValueError):
        lasts = 0
    return Tokens(access, refresh, int(time.time()) + (lasts if lasts > 0 else 7 * 24 * 3600))


def start(opener=None) -> Device:
    """Ask Hardcover for a code the reader can approve."""
    if not available():
        raise OAuthError("This installation has no Hardcover app to connect through", "no_app")
    status, said = _post(DEVICE_URL, {"client_id": client_id(), "scope": " ".join(hardcover.SCOPES)}, opener)
    if status != 200 or not said.get("device_code") or not said.get("user_code"):
        if status == 0:
            raise OAuthError("Hardcover could not be reached. Try again in a moment", "unreachable")
        raise OAuthError(f"Hardcover did not start the sign-in ({said.get('error') or f'error {status}'})", str(said.get("error") or ""))
    link = str(said.get("verification_uri") or "https://hardcover.app/link")
    return Device(
        device_code=str(said["device_code"]),
        user_code=str(said["user_code"]),
        link=link,
        link_with_code=str(said.get("verification_uri_complete") or link),
        expires=time.monotonic() + int(said.get("expires_in") or 900),
        interval=max(1, int(said.get("interval") or 5)),
    )


SLOWER = 5  # seconds added to the interval when Hardcover says it is asked too often


def collect(device: Device, opener=None) -> Tokens | int:
    """Ask once whether the reader has approved. The tokens when they have;
    otherwise the seconds to wait before asking again. Raises OAuthError
    when this sign-in is over: refused, or run out."""
    if time.monotonic() > device.expires:
        raise OAuthError("The code has run out. Start again", "expired_token")
    status, said = _post(TOKEN_URL, {"grant_type": DEVICE_GRANT, "device_code": device.device_code, "client_id": client_id()}, opener)
    if status == 200:
        return _tokens(said)
    error = str(said.get("error") or "")
    if error == "authorization_pending" or status == 0:  # not yet; or no answer, which asking again mends
        return device.interval
    if error == "slow_down":
        return device.interval + SLOWER
    if error == "access_denied":
        raise OAuthError("The sign-in was refused on Hardcover", error)
    if error == "expired_token":
        raise OAuthError("The code has run out. Start again", error)
    raise OAuthError(f"Hardcover did not finish the sign-in ({error or f'error {status}'})", error)


def renew(refresh: str, opener=None) -> Tokens:
    """A new pair of tokens for a refresh token. That token is spent by
    this, whatever comes back."""
    status, said = _post(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id()}, opener)
    if status == 200:
        return _tokens(said)
    if status == 0 or status >= 500:
        raise OAuthError("Hardcover could not be reached", "unreachable")
    raise OAuthError(f"Hardcover did not renew the connection ({said.get('error') or f'error {status}'})", str(said.get("error") or "gone"))


def revoke(kept: str, opener=None) -> None:
    """Tell Hardcover the connection is over, so that it does not stay
    listed as a session there. Best effort: what is kept here goes anyway."""
    tokens = unpack(kept)
    if tokens is not None and available():
        _post(REVOKE_URL, {"token": tokens.refresh, "token_type_hint": "refresh_token", "client_id": client_id()}, opener)


CONNECT_AGAIN = "Hardcover no longer accepts this connection. Connect again under Settings"


def peek(kept: str, now=None) -> str:
    """The token in what is kept, without renewing anything: for a check
    that must change nothing. "" when an OAuth access token has run out
    (the next sync renews it)."""
    tokens = unpack(kept)
    if tokens is None:
        return kept or ""
    return tokens.access if tokens.expires > (now or time.time()) else ""


def usable(read, write, lock, opener=None, now=None) -> str:
    """The token to send to Hardcover: a pasted one as it is; an OAuth
    access token, renewed first when it is about to run out.

    read() gives what is kept, write(text) keeps something new, and `lock`
    is held around both: everything that can use this reader's tokens must
    come through the same lock, in this process and in any other.

    Raises hardcover.HardcoverError when there is a connection and it
    cannot be used: Hardcover ended it, or it has run out and Hardcover
    cannot be reached to renew it."""
    with lock:
        kept = read() or ""
        tokens = unpack(kept)
        if tokens is None:
            return kept
        left = tokens.expires - (now or time.time())
        if left > RENEW_BEFORE:
            return tokens.access
        try:
            new = renew(tokens.refresh, opener)
        except OAuthError as ex:
            if ex.code == "unreachable":
                if left > 0:
                    return tokens.access  # still good; the next use tries again
                raise hardcover.HardcoverError(
                    f"Hardcover could not be reached to renew the connection. {hardcover.NOTHING_LOST}", "unreachable"
                ) from ex
            log.error("the Hardcover connection could not be renewed: %s", ex.code or "refused")
            raise hardcover.HardcoverError(CONNECT_AGAIN, "token") from ex
        write(new.pack())  # before anything else can go wrong: the old refresh token is spent
        log.info("the Hardcover connection was renewed")
        return new.access
