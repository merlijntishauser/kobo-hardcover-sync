"""The Mac app: is there a newer version? (docs/macos-app.md)

The app has no package manager to say so, so after a sync it asks GitHub,
at most once a day. It only says; the app installs a version when the
reader chooses to (packaging/macos/Update.swift). Homebrew and
PyPI installations do not ask: they have their own way of telling.

What keeps it small:

- one GET to GitHub's API for the latest release, five seconds at most;
  nothing is sent but the request itself;
- only the tag is used, and only when it is `v` and three numbers; the
  link that is shown is built from that version, never taken from the
  answer;
- the answer is kept in update.json in the state folder, where the page
  and the app's window read it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request

from .. import __version__
from . import config, macos

LATEST = "https://api.github.com/repos/merlijntishauser/kobo-hardcover-sync/releases/latest"
RELEASE = "https://github.com/merlijntishauser/kobo-hardcover-sync/releases/tag/v{version}"
EVERY = 24 * 3600
TIMEOUT = 5
TAG = re.compile(r"v(\d{1,4})\.(\d{1,4})\.(\d{1,4})")  # whole, with fullmatch: no newline after it either
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(.*)")

log = logging.getLogger(__name__)


def _path() -> str:
    return os.path.join(config.state_dir(), "update.json")


def _order(version: str) -> tuple[int, int, int, int] | None:
    """For comparing: 0.11.0.dev0 comes before 0.11.0."""
    m = VERSION.fullmatch(version)
    if not m:
        return None
    return int(m[1]), int(m[2]), int(m[3]), 0 if m[4] else 1


def wanted() -> bool:
    """Whether this installation asks at all: only the app, and only when not switched off."""
    return bool(macos.app_path()) and config.load().check_for_updates


def kept() -> dict:
    try:
        with open(_path()) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def newer(current: str = __version__) -> dict | None:
    """{"version", "link"} for a release newer than this one, from what
    the last check found; None when there is none, or nothing is known."""
    if not wanted():
        return None
    latest, mine = str(kept().get("latest") or ""), _order(current)
    found = _order(latest)
    if not (found and mine and TAG.fullmatch("v" + latest) and found > mine):
        return None
    return {"version": latest, "link": RELEASE.format(version=latest)}


def ask(fetch=None) -> str:
    """The newest release's version from GitHub, or "" when the answer is
    not one."""
    req = urllib.request.Request(
        LATEST,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"kobo-hardcover-sync/{__version__}"},
    )
    with (fetch or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
        tag = str(json.load(r).get("tag_name") or "")
    m = TAG.fullmatch(tag)
    return ".".join(m.groups()) if m else ""


def now_and_then(fetch=None, clock=time.time) -> None:
    """Ask, if this installation asks and the last time was a day ago.
    Never raises: a failure only waits for the next day."""
    if not wanted():
        return
    if clock() - float(kept().get("checked") or 0) < EVERY:
        return
    _ask_and_keep(fetch, clock)


def now(fetch=None, clock=time.time, current: str = __version__) -> dict:
    """Ask now, because someone asked (`update`, Check now in the app),
    also when the daily look is switched off. What GitHub said, and
    whether it is newer than this version; "problem" when it did not say."""
    latest, problem = _ask_and_keep(fetch, clock)
    found, mine = _order(latest), _order(current)
    newer = bool(found and mine and found > mine)
    return {
        "version": current,
        "latest": latest,
        "newer": newer,
        "link": RELEASE.format(version=latest) if newer else "",
        "problem": problem,
    }


def _ask_and_keep(fetch, clock) -> tuple[str, str]:
    """(the newest version GitHub knows, or the last one known; why there is
    no answer). The answer is kept in update.json for the page and the app."""
    data = {"checked": clock(), "latest": kept().get("latest") or ""}
    problem = ""
    try:
        data["latest"] = ask(fetch) or data["latest"]
    except Exception as ex:  # noqa: BLE001 (any failure: no answer this time)
        log.info("no answer about a newer version: %s", ex)
        problem = f"GitHub did not answer ({getattr(ex, 'reason', ex)})."
    _keep(data)
    return data["latest"], problem


def _keep(data: dict) -> None:
    tmp = _path() + ".tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, _path())
    except OSError as ex:
        log.info("could not keep the answer about a newer version: %s", ex)
