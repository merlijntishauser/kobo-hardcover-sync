"""The log, and the two levels a person chooses between.

  normal   what happened, in counts, and what went wrong. No book titles.
  verbose  also one line per book and one per request to Hardcover. Book
           titles are in it.

Never in it, at either level: a token, or anything a request carried.

On the computer the Kobo is plugged into the log is `agent.log` in the
tool's folder, kept to about a megabyte with one older file beside it.
Verbose there is `sync --verbose` for one run, `verbose_log = true` in
config.toml for every run. A server writes to standard error, where the
container's log picks it up; verbose there is KHS_LOG=verbose.

Modules log through `logging.getLogger(__name__)`: info for the normal
level, debug for what only verbose shows.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

ROOT = "kobo_hardcover_sync"
MAX_BYTES = 1_000_000
FORMAT = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")

for _level, _name in ((logging.DEBUG, "detail"), (logging.INFO, "info"), (logging.WARNING, "warning"), (logging.ERROR, "error")):
    logging.addLevelName(_level, _name)


def asked_verbose() -> bool:
    """KHS_LOG=verbose, the switch that works everywhere."""
    return os.environ.get("KHS_LOG", "").strip().lower() == "verbose"


def _start(handlers: list[logging.Handler], verbose: bool) -> None:
    log = logging.getLogger(ROOT)
    for old in list(log.handlers):
        log.removeHandler(old)
        old.close()
    for h in handlers:
        h.setFormatter(FORMAT)
        log.addHandler(h)
    log.setLevel(logging.DEBUG if verbose or asked_verbose() else logging.INFO)
    log.propagate = False


def to_file(path: str, verbose: bool = False, echo: bool = False) -> None:
    """Log to `path`. echo: also to standard error, for a run by hand."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    handlers: list[logging.Handler] = [RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=1, delay=True, encoding="utf-8")]
    if echo:
        handlers.append(logging.StreamHandler(sys.stderr))
    _start(handlers, verbose)


def to_stderr(verbose: bool = False) -> None:
    _start([logging.StreamHandler(sys.stderr)], verbose)
