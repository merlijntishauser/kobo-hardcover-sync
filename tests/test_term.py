"""What the commands print: the page's status language in a terminal. The
state is never in the colour alone, and what is piped is plain text."""

import io
import os

import pytest

from kobo_hardcover_sync import cli, term
from kobo_hardcover_sync.computer import runner
from kobo_hardcover_sync.computer.platform import HARDCOVER
from kobo_hardcover_sync.engine import hardcover, state
from kobo_hardcover_sync.term import FAIL, NOTE, OK, WARN, Row, Screen
from tests.kobo_fixture import BOOKS
from tests.test_computer import FakeComputer
from tests.test_hardcover import FakeHC
from tests.test_local import LOCAL, TOKEN, catalogue, kobo, st


def printed(colour=False, unicode=True, width=60):
    out: list[str] = []
    return Screen(out.append, colour=colour, unicode=unicode, width=width), out


ROWS = [
    Row(OK, "Kobo", "Clara Colour, 9 books read"),
    Row(NOTE, "Sending", "Dry run"),
    Row(
        WARN, "Matches", "2 books need a match on the page, and that is a sentence long enough to be folded", "Choose the book in Details."
    ),
    Row(FAIL, "Hardcover", "Hardcover does not accept your token."),
]


def test_without_colour_the_state_is_a_word():
    screen, out = printed()
    screen.rows(ROWS)
    assert "".join(out) == (
        "  ok       Kobo       Clara Colour, 9 books read\n"
        "  note     Sending    Dry run\n"
        "  warning  Matches    2 books need a match on the page, and\n"
        "                      that is a sentence long enough to be\n"
        "                      folded\n"
        "                      To do: Choose the book in Details.\n"
        "  problem  Hardcover  Hardcover does not accept your token.\n"
    )
    assert "\x1b" not in "".join(out)


def test_with_colour_the_marks_also_differ_in_shape():
    screen, out = printed(colour=True)
    screen.rows(ROWS)
    text = "".join(out)
    marks = [line.split("\x1b[0m")[0].strip() for line in text.splitlines() if line.startswith("  \x1b")]
    assert marks == ["\x1b[32m●", "\x1b[90m○", "\x1b[33m▲", "\x1b[31m✗"]  # green, grey, amber, red: and four shapes
    assert "\x1b[2mChoose the book in Details.\x1b[0m" in text and "To do:" not in text  # what to do is the dimmer line
    assert "Clara Colour, 9 books read\n" in text  # the words themselves stay in the terminal's own ink
    # A terminal without UTF-8 gets marks it can show.
    plain, out = printed(colour=True, unicode=False)
    plain.rows(ROWS)
    assert [line[7] for line in "".join(out).splitlines() if line.startswith("  \x1b[")] == ["*", "-", "!", "x"]


def test_a_screen_is_what_its_stream_is(monkeypatch):
    class Terminal(io.StringIO):
        encoding = "UTF-8"

        def isatty(self):
            return True

    for name in ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "TERM"):
        monkeypatch.delenv(name, raising=False)
    assert Screen.of(Terminal()).colour and Screen.of(Terminal()).unicode
    assert not Screen.of(io.StringIO()).colour  # a pipe, a file
    monkeypatch.setenv("NO_COLOR", "1")
    assert not Screen.of(Terminal()).colour
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not Screen.of(Terminal()).colour
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert Screen.of(io.StringIO()).colour  # asked for, also into a pipe
    monkeypatch.setenv("NO_COLOR", "1")
    assert not Screen.of(io.StringIO()).colour  # and NO_COLOR has the last word

    class Latin(Terminal):
        encoding = "ISO-8859-1"

    assert not Screen.of(Latin()).unicode
    assert Screen(lambda s: None, width=400).width == term.MAX_WIDTH and Screen(lambda s: None, width=10).width == 40


def test_the_reading_line():
    screen, _ = printed()
    assert screen.reading_line(0) == "─" * 36
    assert screen.reading_line(50) == "━" * 18 + "─" * 18
    assert screen.reading_line(1).count("━") == 0 and screen.reading_line(3).count("━") == 1
    assert screen.reading_line(99) == "━" * 35 + "─"  # not full until it is finished
    assert screen.reading_line(100) == screen.reading_line(40, finished=True) == "━" * 36
    assert screen.reading_line(None) == "─" * 36 and screen.reading_line(250) == "━" * 36
    colour, _ = printed(colour=True)
    assert colour.reading_line(50).startswith("\x1b[36m━") and colour.reading_line(50, finished=True).startswith("\x1b[32m━")  # cyan, green
    ascii_only, _ = printed(unicode=False)
    assert ascii_only.reading_line(50) == "=" * 18 + "-" * 18


def test_counts_read_as_a_person_says_them():
    assert [term.plural(n, "book") for n in (0, 1, 2)] == ["0 books", "1 book", "2 books"]
    assert term.plural(1, "copy", "copies") == "1 copy" and term.plural(3, "copy", "copies") == "3 copies"


def test_the_first_help_page_is_written_for_a_reader(capsys):
    with pytest.raises(SystemExit) as ex:
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert ex.value.code == 0 and out.startswith("Kobo Hardcover Sync ") and "SUPPRESS" not in out and "\x1b" not in out
    assert "On the computer you plug the Kobo into\n  setup      Make this computer sync a plugged-in Kobo\n" in out
    assert "\nOn a server\n  serve      Run the server" in out and "  page " not in out
    for _, commands in cli.COMMANDS:  # every command it names is one the tool has
        for name, _ in commands:
            with pytest.raises(SystemExit) as known:
                cli.main([name, "--help"])
            assert known.value.code == 0
    capsys.readouterr()


def a_reader_with_books(home, live):
    kobo(home)
    mac = FakeComputer(home / "Volumes")
    mac.install_trigger("kobo-hardcover-sync")
    mac.set_secret(HARDCOVER, TOKEN)

    class OneRefused(FakeHC):
        def insert_user_book(self, obj):
            if obj["book_id"] == 102:
                raise hardcover.HardcoverError("Hardcover refused: this one, no", "refused")
            return super().insert_user_book(obj)

    hc = OneRefused(isbn=catalogue())
    runner.sync(mac, LOCAL, hardcover_client=hc)
    con = st(home)
    state.set_mode(con, "me", BOOKS[:3], "on")
    con.execute("update reader set hardcover_live = ?, kobo_collection = 'On Hardcover' where name = 'me'", (int(live),))
    con.execute("update book set status = 2, percent = 100, finished_at = '2026-09-21T20:00:00Z' where content_id = ?", (BOOKS[1],))
    con.commit()
    return mac, hc


def test_a_sync_by_hand_tells_its_steps_and_then_the_books(home, monkeypatch, capsys):
    mac, hc = a_reader_with_books(home, live=True)
    monkeypatch.setattr(hardcover, "Client", lambda token, **kw: hc)
    from kobo_hardcover_sync.computer import config

    config.save(config.Config())
    os.unlink(home / "state" / "agent.log")
    cli.main(["sync"], computer=mac)
    out = capsys.readouterr().out
    assert out.startswith(
        "\n"
        "  ok       Kobo        Kobo Clara Colour: nothing new since the last sync\n"
        "  warning  Hardcover   2 sent, 1 failed\n"
        "  ok       Collection  'On Hardcover': 3 books (+3, -0).\n"
        "\n"
        "Sent to Hardcover\n"
    )
    assert "  Made-up Book 0\n  " + "─" * 36 + "  mark Currently reading, 0%\n" in out  # its title, its reading line, what was sent
    assert "  Made-up Book 1\n  " + "━" * 36 + "  mark Read, finished 2026-09-21\n" in out  # finished: the line is full
    assert "\nNot sent\n  Made-up Book 2\n" in out and "Hardcover refused: this one, no\n" in out
    assert out.endswith("\nEject before unplugging.\n") and mac.told == []  # a run by hand notifies nobody
    # The titles were for the terminal: not in the log, not in what the small app would show.
    assert "Made-up" not in open(home / "state" / "agent.log").read()
    assert "Made-up" not in open(home / "state" / "last-message.txt").read()
    kept = [r[0] for r in st(home).execute("select detail from job")]
    assert kept and all("Made-up" not in d and "books" not in d for d in kept)  # nor kept with the run
    # Started by the plug-in trigger, the same sync says one thing, as a notification.
    cli.main(["sync", "--trigger", "mount"], computer=mac)
    assert capsys.readouterr().out == "" and len(mac.told) == 1 and "Made-up" not in mac.told[0][1]


def test_a_dry_run_says_what_would_be_sent_and_many_books_are_counted(home, monkeypatch, capsys):
    mac, hc = a_reader_with_books(home, live=False)
    monkeypatch.setattr(cli, "SHOWN_BOOKS", 2)
    steps = []
    out = runner.sync(mac, LOCAL, hardcover_client=hc, on_step=steps.append)
    assert [(s.state, s.what, s.text) for s in steps][1] == (NOTE, "Hardcover", "Dry run: 3 would be sent")
    assert [b["went"] for b in out.books] == ["planned"] * 3 and out.live is False and hc.calls == []
    screen, printed_ = printed(width=70)
    cli._books(screen, out.books, out.live)
    text = "".join(printed_)
    assert text.startswith("\nWould be sent to Hardcover (dry run)\n") and text.count("Made-up Book") == 2
    assert text.endswith("  and 1 more book; the page lists them all.\n")


def test_what_a_sync_has_to_say_when_it_cannot_run(home, capsys):
    mac = FakeComputer(home / "Volumes")
    with pytest.raises(SystemExit) as ex:
        cli.main(["sync"], computer=mac)
    assert ex.value.code == 1
    assert capsys.readouterr().out == "\n  problem  Sync        Not set up yet: run `kobo-hardcover-sync setup`.\n"
