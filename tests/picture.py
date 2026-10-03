"""The picture of a sync at the top of the README: docs/img/sync.svg.

It is what the tool prints. A made-up shelf is synced for real (a folder
plays the Kobo, an in-memory Hardcover plays Hardcover), what
`kobo-hardcover-sync sync` writes to a terminal is caught with its
colours, and that is set as an SVG whose lines appear one after another.
A test makes the picture again and compares, so it cannot drift from the
tool.

    uv run python -m tests.picture      # writes docs/img/sync.svg
"""

import html
import io
import os
import pathlib
import re
import sqlite3
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PICTURE = ROOT / "docs" / "img" / "sync.svg"
COMMAND = "kobo-hardcover-sync sync"
# Three books of a made-up reader: title, author, how far before, how far now (100: finished).
SHELF = (
    ("Moby-Dick; or, The Whale", "Herman Melville", 35, 37),
    ("Middlemarch", "George Eliot", 96, 100),
    ("The Left Hand of Darkness", "Ursula K. Le Guin", 4, 16),
)
VERSION = "N36XXXXXXXX,4.9.77,6.0.274403,4.9.77,4.9.77,00000000-0000-0000-0000-000000000393\n"

# The terminal: the page's night colours.
PAPER, INK, FRAME = "#0f172a", "#e2e8f0", "#2a3a55"
COLOURS = {"32": "#34d399", "36": "#22d3ee", "33": "#fbbf24", "31": "#fb7185", "90": "#94a3b8"}
DIM = "#94a3b8"
CHAR, LINE, PAD, COLUMNS = 8.4, 20, 18, 80
FIRST, STEP, HOLD = 1.2, 0.45, 6.0  # seconds: before the first line, between lines, with everything shown


class Terminal(io.StringIO):
    encoding = "utf-8"


def printed() -> str:
    """What `sync` prints for the made-up shelf, colours included."""
    from kobo_hardcover_sync import cli, logs
    from kobo_hardcover_sync.computer import config, runner
    from kobo_hardcover_sync.computer.platform import HARDCOVER
    from kobo_hardcover_sync.engine import hardcover, state
    from kobo_hardcover_sync.server import accounts
    from tests.kobo_fixture import BOOKS, make
    from tests.test_computer import FakeComputer
    from tests.test_hardcover import FakeHC

    kept = {k: os.environ.get(k) for k in ("KHS_HOME", "FORCE_COLOR", "NO_COLOR", "TZ")}
    client, out = hardcover.Client, Terminal()
    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp)
        os.environ.update(KHS_HOME=str(home / "state"), FORCE_COLOR="1", TZ="UTC")
        os.environ.pop("NO_COLOR", None)
        try:
            db = home / "Volumes" / "KOBOeReader" / ".kobo" / "KoboReader.sqlite"
            db.parent.mkdir(parents=True)
            make(str(db))
            (db.parent / "version").write_text(VERSION)

            def on_the_kobo(now: bool) -> None:
                kobo = sqlite3.connect(db)
                for cid, (title, author, before, after) in zip(BOOKS, SHELF, strict=False):
                    percent = after if now else before
                    kobo.execute(
                        "update content set Title=?, Attribution=?, ___PercentRead=?, ReadStatus=?, LastTimeFinishedReading=? where ContentID=?",
                        (title, author, percent, 2 if percent == 100 else 1, "2026-09-21T20:00:00Z" if percent == 100 else "", cid),
                    )
                kobo.commit()
                kobo.close()

            mac = FakeComputer(home / "Volumes")
            mac.install_trigger("kobo-hardcover-sync")
            mac.set_secret(HARDCOVER, "a-made-up-token")
            fake = FakeHC(
                isbn={
                    f"97800000000{n:02d}": {"id": 10 + n, "book_id": 100 + n, "isbn_13": f"97800000000{n:02d}", "pages": 300, "title": t[0]}
                    for n, t in enumerate(SHELF)
                }
            )
            hardcover.Client = lambda token, **kw: fake
            config.save(config.Config())
            # Before: the shelf as it was, synced once, live, with a collection.
            on_the_kobo(now=False)
            runner.sync(mac)
            con = state.connect(str(home / "state" / "state.db"))
            state.set_mode(con, "me", list(BOOKS[: len(SHELF)]), "on")
            accounts.set_collection(con, "me", "On Hardcover")
            con.execute("update reader set hardcover_live = 1 where name = 'me'")
            con.commit()
            con.close()
            runner.sync(mac)
            # Then some reading, and the sync that is the picture.
            on_the_kobo(now=True)
            import contextlib

            with contextlib.redirect_stdout(out):
                cli.main(["sync"], computer=mac)
        finally:
            hardcover.Client = client
            logs._start([], False)  # the log went to a folder that is about to go
            for k, v in kept.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return out.getvalue()


def spans(line: str) -> str:
    """A printed line as SVG text: its colours, bold and dim kept."""
    out, codes = [], set()
    for part in re.split(r"(\x1b\[[0-9;]*m)", line):
        if part.startswith("\x1b["):
            codes = set() if part == "\x1b[0m" else codes | set(part[2:-1].split(";"))
        elif part:
            fill = next((COLOURS[c] for c in codes if c in COLOURS), DIM if "2" in codes else "")
            attrs = (f' fill="{fill}"' if fill else "") + (' font-weight="600"' if "1" in codes else "")
            out.append(f"<tspan{attrs}>{html.escape(part)}</tspan>")
    return "".join(out)


def svg(text: str) -> str:
    lines = [f"\x1b[90m$\x1b[0m {COMMAND}", *text.rstrip("\n").split("\n")]
    width, height = round(COLUMNS * CHAR + 2 * PAD), len(lines) * LINE + 2 * PAD + 26
    total = FIRST + STEP * len(lines) + HOLD
    rows, frames = [], []
    for i, line in enumerate(lines):
        at = 0 if i == 0 else (FIRST + STEP * i) / total * 100  # the command is there from the start
        frames.append(
            f"@keyframes l{i} {{ 0%, {max(at - 0.01, 0):.2f}% {{ opacity: 0 }} {at:.2f}%, 97% {{ opacity: 1 }} 100% {{ opacity: 0 }} }}"
        )
        y = PAD + 26 + i * LINE + 14
        rows.append(
            f'<text x="{PAD}" y="{y}" xml:space="preserve" style="animation: l{i} {total:.1f}s linear infinite">{spans(line)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
        f'aria-label="A terminal running {COMMAND}: three steps, then the books that went to Hardcover, each with a line showing how far it is read.">\n'
        "<style>\n"
        f"text {{ font: 14px ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace; fill: {INK}; }}\n"
        + "\n".join(frames)
        + "\n@media (prefers-reduced-motion: reduce) { text { animation: none !important; opacity: 1 } }\n"
        "</style>\n"
        f'<rect width="{width}" height="{height}" rx="10" fill="{PAPER}" stroke="{FRAME}"/>\n'
        f'<circle cx="{PAD + 4}" cy="18" r="5" fill="{FRAME}"/><circle cx="{PAD + 22}" cy="18" r="5" fill="{FRAME}"/><circle cx="{PAD + 40}" cy="18" r="5" fill="{FRAME}"/>\n'
        + "\n".join(rows)
        + "\n</svg>\n"
    )


def main() -> None:
    PICTURE.write_text(svg(printed()), encoding="utf-8")
    print(f"wrote {PICTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
