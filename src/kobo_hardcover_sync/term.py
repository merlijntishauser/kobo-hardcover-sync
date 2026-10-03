"""What the commands print, in the page's language.

The page says status with a dot and plain words: green for fine, amber for
"needs you", red for "went wrong", grey for a note. The terminal does the
same, with the terminal's own colours (they follow the reader's theme), and
draws a book's progress as the page's reading line.

The state never hangs on colour alone. With colour the marks also differ in
shape; without colour (output that is piped or kept in a file, NO_COLOR, a
terminal that cannot) the state is a word. Without UTF-8 the marks are
plain characters.

No package is needed for this: a few escape codes and textwrap.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from dataclasses import dataclass

OK, NOTE, WARN, FAIL, NEXT = "ok", "note", "warn", "fail", "next"
WORDS = {OK: "ok", NOTE: "note", WARN: "warning", FAIL: "problem", NEXT: "next"}
MARKS = {OK: "●", NOTE: "○", WARN: "▲", FAIL: "✗", NEXT: "●"}
PLAIN_MARKS = {OK: "*", NOTE: "-", WARN: "!", FAIL: "x", NEXT: ">"}
# The terminal's own palette: green, grey, yellow, red; cyan is "your place" and "your choice", as on the page.
COLOURS = {OK: "32", NOTE: "90", WARN: "33", FAIL: "31", NEXT: "36"}
BOLD, DIM, CYAN, GREEN = "1", "2", "36", "32"
MAX_WIDTH = 96  # a line of words is not read comfortably beyond this
BAR = 36  # cells of a reading line


@dataclass(frozen=True)
class Row:
    """One line of status: a mark, what it is about, what was found, and
    under it what to do."""

    state: str
    what: str
    text: str
    todo: str = ""


class Screen:
    def __init__(self, write=None, colour: bool = False, unicode: bool = True, width: int = 80):
        self._write = write or sys.stdout.write
        self.colour, self.unicode, self.width = colour, unicode, max(40, min(width, MAX_WIDTH))

    @classmethod
    def of(cls, stream=None) -> Screen:
        """The screen a stream is: colour on a terminal that wants it, the
        marks its encoding can show, its width."""
        stream = stream or sys.stdout
        tty = hasattr(stream, "isatty") and stream.isatty()
        env = os.environ
        colour = tty and "NO_COLOR" not in env and env.get("TERM") != "dumb"
        if env.get("FORCE_COLOR") or env.get("CLICOLOR_FORCE"):
            colour = "NO_COLOR" not in env
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        width = shutil.get_terminal_size((80, 24)).columns if tty else 80
        return cls(stream.write, colour=bool(colour), unicode=encoding.startswith("utf"), width=width)

    # --- pieces
    def style(self, text: str, *codes: str) -> str:
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m" if self.colour and codes and text else text

    def mark(self, state: str) -> str:
        """The mark of a state; where there is no colour to say it, the word."""
        if not self.colour:
            return WORDS[state]
        return self.style((MARKS if self.unicode else PLAIN_MARKS)[state], COLOURS[state])

    @property
    def _mark_width(self) -> int:
        return 1 if self.colour else max(len(w) for w in WORDS.values())

    def line(self, text: str = "") -> None:
        self._write(text + "\n")

    def say(self, text: str, indent: int = 0, style: tuple = (), hang: int = 0) -> None:
        """A paragraph, wrapped to the screen. hang: how much further its
        later lines stand in, for a line that starts with a number."""
        parts = textwrap.wrap(text, self.width - indent, subsequent_indent=" " * hang, break_long_words=False, break_on_hyphens=False)
        for part in parts or [""]:
            self.line(" " * indent + self.style(part, *style))

    def heading(self, text: str) -> None:
        self.line(self.style(text, BOLD))

    def rows(self, rows: list[Row], label_width: int | None = None) -> None:
        """Status lines under each other: the marks in one column, the
        labels in the next, the words wrapped beside them."""
        if not rows:
            return
        marks = self._mark_width
        labels = label_width if label_width is not None else max(len(r.what) for r in rows)
        at = 2 + marks + 2 + (labels + 2 if labels else 0)
        room = max(self.width - at, 24)
        for r in rows:
            mark = self.mark(r.state) + " " * (marks - (1 if self.colour else len(WORDS[r.state])))
            label = f"{r.what:<{labels}}  " if labels else ""
            text = textwrap.wrap(r.text, room, break_long_words=False, break_on_hyphens=False) or [""]
            self.line(f"  {mark}  {label}{text[0]}")
            for more in text[1:]:
                self.line(" " * at + more)
            # What to do: dimmer than what was found; where nothing can be dimmed, it says what it is.
            todo = r.todo if self.colour or not r.todo else f"To do: {r.todo}"
            for part in textwrap.wrap(todo, room, break_long_words=False, break_on_hyphens=False):
                self.line(" " * at + self.style(part, DIM))

    def reading_line(self, percent, finished: bool = False) -> str:
        """The page's reading line: how far a book has been read, cyan on a
        quiet track, green and full when it is finished."""
        pct = 100 if finished else max(0, min(100, int(percent or 0)))
        done = BAR if pct >= 100 else min(BAR - 1, round(BAR * pct / 100)) if pct else 0
        full, rest = ("━", "─") if self.unicode else ("=", "-")
        return self.style(full * done, GREEN if finished else CYAN) + self.style(rest * (BAR - done), DIM)

    def book(self, title: str, percent, finished: bool, facts: str) -> None:
        """A book as a line of the reading log: its title, its reading line, a few facts."""
        self.say(title, indent=2, style=(BOLD,))
        self.line(f"  {self.reading_line(percent, finished)}  {self.style(facts, DIM)}")


def plural(n: int, one: str, many: str | None = None) -> str:
    """ "1 book", "3 books"."""
    return f"{n} {one if n == 1 else many or one + 's'}"
