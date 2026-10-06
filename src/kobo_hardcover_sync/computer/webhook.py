"""Local mode: a POST to an address of the reader's own after every sync
that read the Kobo, for a tracker, a database or an automation of theirs.
Not tied to any service: the body is the JSON in docs/webhook.md, and the
only credential is an optional Bearer token.

The address is a setting (config.toml, `webhook_url`); the token is a
secret, kept where the Hardcover token is. What keeps the token where it
belongs:

- https only, except to this computer itself (an API on localhost);
- no user:password in the address, where it would sit in a settings file;
- redirects are not followed, so the token never goes to another address
  than the one the reader gave.

One try per sync, ten seconds at most. A POST that fails is said in the
sync's notification and not repeated: the next sync sends its own changes,
and `reading` and `summary` are always the whole present state.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .. import __version__

TIMEOUT = 10


class WebhookError(Exception):
    """Something the person can act on; str() is the message."""


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def problem(url: str) -> str:
    """Why this address cannot be used, or "" when it can."""
    u = urlparse(url.strip())
    if u.scheme not in ("https", "http") or not u.hostname:
        return "That is not a web address: it should start with https://."
    if u.username or u.password:
        return "Leave the user name and password out of the address; give a token with --token instead."
    if u.scheme == "http" and not _loopback(u.hostname):
        return "Only https: over plain http the token and your reading would cross the network readable. (http is fine to this computer itself.)"
    return ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirected to {newurl}; not followed", headers, fp)


def host(url: str) -> str:
    return urlparse(url).hostname or url


def post(url: str, token: str, body: dict, opener=None) -> int:
    """POST body as JSON. Returns the status; raises WebhookError for
    anything that is not a 2xx answer."""
    where = host(url)
    headers = {"Content-Type": "application/json", "User-Agent": f"kobo-hardcover-sync/{__version__}"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers=headers)
    send = opener or urllib.request.build_opener(_NoRedirect).open
    try:
        with send(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as ex:
        if 300 <= ex.code < 400:
            raise WebhookError(f"{where} answered with a redirect ({ex.code}); give the address it redirects to") from ex
        raise WebhookError(f"{where} answered {ex.code}") from ex
    except (urllib.error.URLError, OSError) as ex:
        raise WebhookError(f"could not reach {where} ({getattr(ex, 'reason', ex)})") from ex
