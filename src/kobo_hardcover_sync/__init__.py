"""kobo-hardcover-sync: reading progress from a stock Kobo to Hardcover.

- engine: the Kobo database, the selection state, the plan, Hardcover and the
  two-way sync. Knows nothing about the page, the commands or the computer.
- server: what only server mode has (readers and their tokens, uploads, the
  stats endpoint).
- web: the page.
- computer: the tool on the computer the Kobo is plugged into.
- cli: the command.
- doctor: the check of everything a sync depends on, for the command and
  the page. logs: the log and its two levels.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("kobo-hardcover-sync")
except PackageNotFoundError:  # run from a checkout that was never installed
    __version__ = "0+unknown"

ISSUES = "https://github.com/merlijntishauser/kobo-hardcover-sync/issues"
