"""Where the tool keeps its things on this computer, and what `setup` chose.

State folder: ~/Library/Application Support/kobo-hardcover-sync on macOS,
$XDG_DATA_HOME/kobo-hardcover-sync (~/.local/share/...) elsewhere;
KHS_HOME overrides both (tests, and anyone who wants it elsewhere).

Settings are a few lines of `key = "value"` in config.toml there:

    server = "https://kobo.example.org"   # server mode; absent = local mode
    eject_after_sync = false
    allow_untested_kobo = false
    verbose_log = false                   # true: book titles in agent.log
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass

APP = "kobo-hardcover-sync"


def state_dir() -> str:
    if os.environ.get("KHS_HOME"):
        return os.environ["KHS_HOME"]
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP}")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP)


@dataclass
class Config:
    server: str = ""  # "" = local mode
    eject_after_sync: bool = False
    allow_untested_kobo: bool = False
    verbose_log: bool = False

    set_up: bool = False  # has `setup` been run here?

    @property
    def path(self) -> str:
        return os.path.join(state_dir(), "config.toml")

    @property
    def mode(self) -> str:
        """ "server", "local", or "" when setup has not been run."""
        return ("server" if self.server else "local") if self.set_up else ""


def load() -> Config:
    c = Config()
    try:
        with open(c.path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return c
    c.set_up = True
    c.server = str(data.get("server") or "").rstrip("/")
    c.eject_after_sync = bool(data.get("eject_after_sync", False))
    c.allow_untested_kobo = bool(data.get("allow_untested_kobo", False))
    c.verbose_log = bool(data.get("verbose_log", False))
    return c


def save(c: Config) -> None:
    os.makedirs(state_dir(), mode=0o700, exist_ok=True)
    lines = []
    if c.server:
        lines.append("server = " + _quote(c.server.rstrip("/")))
    lines.append(f"eject_after_sync = {str(c.eject_after_sync).lower()}")
    lines.append(f"allow_untested_kobo = {str(c.allow_untested_kobo).lower()}")
    lines.append(f"verbose_log = {str(c.verbose_log).lower()}")
    tmp = c.path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, c.path)
    c.set_up = True


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
