"""The page in local mode: started when asked for, on the loopback address,
for the one person at this computer (docs/local-mode.md).

It has no login, so three things stand in for one:

- It only answers requests that come from this computer, to its own address
  and port (the Host header), and for anything that changes something, from
  its own pages (the Origin header, port included). That keeps other
  websites out, and other local web servers too: cookies do not tell ports
  apart, so the Origin check has to.
- A session cookie that only this run of the page knows.
- The cookie is handed out in exchange for a one-time key. `open` makes the
  key as a file in the state folder, which only this user can write to, and
  puts it in the link it opens. The page deletes the file when it takes the
  key. So nothing that is worth stealing is ever written down.

The page stops by itself after half an hour without a request.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time

from . import config
from .platform import HARDCOVER, Computer

IDLE_SECONDS = 30 * 60
KEY_SECONDS = 60
COOKIE = "khs"
HOST = "127.0.0.1"


def _info_path() -> str:
    return os.path.join(config.state_dir(), "page.json")


def _keys_dir() -> str:
    return os.path.join(config.state_dir(), "page-keys")


# ---------- one-time keys ----------
def new_key() -> str:
    """A key for one visit, valid for a minute."""
    os.makedirs(_keys_dir(), mode=0o700, exist_ok=True)
    key = secrets.token_urlsafe(32)
    with open(os.path.join(_keys_dir(), hashlib.sha256(key.encode()).hexdigest()), "w"):
        pass
    return key


def take_key(key: str) -> bool:
    """True once for a fresh key; the key is gone afterwards."""
    path = os.path.join(_keys_dir(), hashlib.sha256((key or "").encode()).hexdigest())
    try:
        fresh = time.time() - os.path.getmtime(path) <= KEY_SECONDS
        os.unlink(path)
    except OSError:
        return False
    return fresh


# ---------- what the app needs to know in local mode ----------
class KeptToken:
    """The Hardcover token, kept in the computer's secret store."""

    def __init__(self, source):
        self._source = source  # a Computer, or something that has one (.computer)

    @property
    def computer(self) -> Computer:
        return getattr(self._source, "computer", self._source)

    def get(self) -> str:
        return self.computer.secret(HARDCOVER)

    def set(self, token: str) -> None:
        self.computer.set_secret(HARDCOVER, token)

    def delete(self) -> None:
        self.computer.delete_secret(HARDCOVER)


class Local:
    """One run of the local page."""

    def __init__(self, port: int, computer: Computer | None = None):
        self.port = port
        self.session = secrets.token_urlsafe(32)
        self.last_seen = time.monotonic()
        self._computer = computer
        try:
            self.user = getpass.getuser()
        except (KeyError, OSError):
            self.user = "me"

    @property
    def computer(self) -> Computer:
        if self._computer is None:
            from .platform import pick

            self._computer = pick()
        return self._computer

    @property
    def origin(self) -> str:
        return f"http://{HOST}:{self.port}"

    def has_session(self, cookie: str | None) -> bool:
        return hmac.compare_digest(cookie or "", self.session)


# ---------- starting and finding it ----------
def running() -> dict | None:
    """{"port", "pid"} of the page that is up, or None."""
    try:
        with open(_info_path()) as fh:
            info = json.load(fh)
        os.kill(int(info["pid"]), 0)
        return {"port": int(info["port"]), "pid": int(info["pid"])}
    except (OSError, ValueError, KeyError):
        return None


def start(timeout: float = 15.0) -> dict:
    """Start the page as a process of its own and wait until it answers."""
    log = open(os.path.join(config.state_dir(), "page.log"), "a")  # noqa: SIM115 (handed to the child)
    try:
        os.unlink(_info_path())
    except OSError:
        pass
    subprocess.Popen(
        [sys.executable, "-m", "kobo_hardcover_sync", "page"],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    log.close()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = running()
        if info:
            return info
        time.sleep(0.1)
    raise RuntimeError(f"The page did not start; see {os.path.join(config.state_dir(), 'page.log')}.")


def link() -> str:
    """A link that opens the page for this visit, starting it if need be."""
    info = running() or start()
    return f"http://{HOST}:{info['port']}/?k={new_key()}"


def serve() -> None:
    """Run the page (the `page` command). Listens on the loopback address
    only; there is no option to change that."""
    import socket
    import threading

    import uvicorn

    os.makedirs(config.state_dir(), mode=0o700, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, 0))
    port = sock.getsockname()[1]
    os.environ["KHS_MODE"] = "local"
    os.environ["KHS_PAGE_PORT"] = str(port)
    os.environ["KHS_DATA"] = config.state_dir()
    os.environ["KHS_HOST"] = HOST
    from ..web import app as web

    server = uvicorn.Server(uvicorn.Config(web.app, log_level="warning", proxy_headers=False))

    idle = float(os.environ.get("KHS_PAGE_IDLE_SECONDS") or IDLE_SECONDS)  # the variable is for tests

    def watch():
        while not server.should_exit:
            time.sleep(min(5.0, idle / 2))
            if time.monotonic() - web.local.last_seen > idle:
                server.should_exit = True

    def announce():
        while not server.started and not server.should_exit:
            time.sleep(0.05)
        tmp = _info_path() + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            json.dump({"port": port, "pid": os.getpid()}, fh)
        os.replace(tmp, _info_path())

    def forget():
        try:
            os.unlink(_info_path())
        except OSError:
            pass

    # On the way down, also when stopped by a signal: uvicorn shuts the app
    # down first and only then lets the signal end the process.
    web.app.add_event_handler("shutdown", forget)
    threading.Thread(target=watch, daemon=True).start()
    threading.Thread(target=announce, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        forget()
