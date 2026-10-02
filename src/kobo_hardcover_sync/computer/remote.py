"""Server mode's half of a sync: send the small database, ask which books
belong in the collection. The upload token is the only credential."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse


class ServerError(Exception):
    """Something the person can act on; str() is the message."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class Server:
    def __init__(self, url: str, token: str, opener=None):
        self.url = url.rstrip("/")
        self.host = urlparse(self.url).hostname or self.url
        self._token = token
        self._open = opener or urllib.request.urlopen

    def _request(self, method: str, path: str, body: bytes | None = None, timeout: int = 60, content_type: str = ""):
        headers = {"Authorization": "Bearer " + self._token, "User-Agent": "kobo-hardcover-sync"}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.url + path, data=body, method=method, headers=headers)
        try:
            with self._open(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as ex:
            detail = ex.read()[:300].decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except ValueError:
                pass
            if ex.code == 401:
                raise ServerError(
                    f"{self.host} does not know this computer. Add its hash under Settings, Devices (run setup to see it).", 401
                ) from ex
            if ex.code == 413:
                raise ServerError(f"{self.host} refused the upload: too large.", 413) from ex
            raise ServerError(f"{self.host} answered {ex.code}: {str(detail)[:120]}", ex.code) from ex
        except (urllib.error.URLError, OSError) as ex:
            reason = getattr(ex, "reason", ex)
            raise ServerError(f"Could not reach {self.host} ({reason}).") from ex

    def upload(self, gz_path: str) -> dict:
        """Send the gzipped database. Returns what the server imported."""
        with open(gz_path, "rb") as fh:
            body = fh.read()
        _, raw = self._request("PUT", "/upload", body, timeout=120, content_type="application/gzip")
        try:
            return json.loads(raw)
        except ValueError as ex:
            raise ServerError(f"{self.host} gave an answer that is not from kobo-hardcover-sync.") from ex

    def collection(self) -> tuple[str, list[str]] | None:
        """(name, book ids) of the collection to keep on the Kobo, or None
        when the reader set no collection name."""
        status, raw = self._request("GET", "/collection")
        text = raw.decode("utf-8", "replace")
        if status == 204 or not text.strip():
            return None
        name, _, rest = text.partition("\n")
        return name.strip(), [i for i in rest.split("\n") if i.strip()]
