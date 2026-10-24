"""The syncs this computer ran: one line of JSON each, in history.jsonl in
the state folder, the last hundred kept.

`kobo-hardcover-sync history` shows them, and the Mac app's window lists
them (`history --json`). A line holds what the notification said, never a
book: when, what started it, whether it went well, and the words.

A sync that found no Kobo after some other volume was mounted is not one:
it is not written down, nor is one that found another sync running.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from . import config

FILE = "history.jsonl"
KEPT = 100
STARTED_BY = {"mount": "Kobo plugged in", "app": "Sync now", "hand": "by hand"}  # how a trigger reads in a list

log = logging.getLogger(__name__)


def _path() -> str:
    return os.path.join(config.state_dir(), FILE)


def record(ok: bool, title: str, message: str, trigger: str = "", now=None) -> None:
    """Add a sync; never raises, a sync is not undone by its history."""
    line = {
        "at": (now or datetime.now()).astimezone().isoformat(timespec="seconds"),
        "trigger": trigger or "hand",
        "ok": ok,
        "title": title,
        "message": message,
    }
    try:
        kept = _lines()[-(KEPT - 1) :]
        tmp = _path() + ".tmp"
        with open(tmp, "w") as fh:
            fh.writelines(json.dumps(x) + "\n" for x in [*kept, line])
        os.replace(tmp, _path())
    except OSError as ex:
        log.warning("could not keep this sync in %s: %s", FILE, ex)


def syncs() -> list[dict]:
    """The syncs kept, newest first."""
    return list(reversed(_lines()))


def _lines() -> list[dict]:
    out = []
    try:
        with open(_path()) as fh:
            for raw in fh:
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue  # a line cut short: the rest still counts
                if isinstance(item, dict) and {"at", "trigger", "ok", "title", "message"} <= item.keys():
                    out.append(item)
    except FileNotFoundError:
        pass
    return out
