"""The tip (tip.py): one book from the reader's own shelf, by the first rule
that finds one, the same all day, put aside for a month with Not now."""

from datetime import date, timedelta

from lastread import tip
from lastread.computer import config, runner
from lastread.engine import state
from tests.kobo_fixture import BOOKS
from tests.test_app_answers import answer
from tests.test_computer import FakeComputer
from tests.test_local import LOCAL, kobo

TODAY = date(2026, 10, 26)


def shelf(home):
    """Local mode after a first sync: Made-up Book n is 10n% read, read last in September 2026."""
    computer = FakeComputer(home / "Volumes")
    config.save(LOCAL)
    kobo(home)
    runner.sync(computer, LOCAL)
    return computer, state.connect(str(home / "state" / "state.db"))


def unopened(con, *ids):
    """Never opened, as a real Kobo has it: no status, no percentage, no time read, but a last read date all the same."""
    for cid in ids:
        con.execute("update book set percent=0, status=0, seconds_read=0, last_read='2024-01-01T10:00:00Z' where content_id=?", (cid,))
    con.commit()


def test_left_off_then_wanted_then_never_opened(home):
    _, con = shelf(home)
    assert tip.pick(con, "me", TODAY) is None  # everything was read last month: nothing to suggest yet

    unopened(con, BOOKS[6])
    assert tip.pick(con, "me", TODAY) == {"id": BOOKS[6], "rule": "never_opened", "text": "On your Kobo, never opened."}
    con.execute("update book set seconds_read=60 where content_id=?", (BOOKS[6],))  # a minute in: opened after all
    con.commit()
    assert tip.pick(con, "me", TODAY) is None
    unopened(con, BOOKS[6])

    unopened(con, BOOKS[5])
    state.set_state(con, "me", BOOKS[5], "want")
    assert tip.pick(con, "me", TODAY)["id"] == BOOKS[5]  # Want to read goes before never opened
    assert tip.pick(con, "me", TODAY)["text"] == "On your Want to read, and already on your Kobo."

    con.execute("update book set last_read='2025-03-11T21:14:00Z' where content_id=?", (BOOKS[3],))
    con.commit()
    left = tip.pick(con, "me", TODAY)
    assert left == {"id": BOOKS[3], "rule": "left_off", "text": "You stopped at 30% in March 2025. Pick it up again?"}
    assert tip.pick(con, "me", date(2025, 6, 1))["rule"] == "wanted"  # less than half a year after: not left off yet

    # A book the reader settled is not suggested, however it stands.
    state.set_state(con, "me", BOOKS[3], "dnf")
    assert tip.pick(con, "me", TODAY)["rule"] == "wanted"
    state.set_state(con, "me", BOOKS[3], "kobo")
    con.execute("update book set percent=95 where content_id=?", (BOOKS[3],))  # nearly done: not "left off"
    con.commit()
    assert tip.pick(con, "me", TODAY)["rule"] == "wanted"


def test_the_same_tip_all_day_and_not_now_for_a_month(home):
    _, con = shelf(home)
    unopened(con, BOOKS[6], BOOKS[7])
    today = {tip.pick(con, "me", TODAY)["id"] for _ in range(3)}
    tomorrow = tip.pick(con, "me", TODAY + timedelta(days=1))["id"]
    assert len(today) == 1 and tomorrow != next(iter(today))  # two candidates: one a day, in turn

    shown = tip.pick(con, "me", TODAY)["id"]
    tip.put_aside(con, "me", shown, TODAY)
    other = tip.pick(con, "me", TODAY)["id"]
    assert other != shown
    tip.put_aside(con, "me", other, TODAY)
    assert tip.pick(con, "me", TODAY) is None
    assert tip.pick(con, "me", TODAY + timedelta(days=30)) is not None  # a month later it may come back


def test_books_carries_the_tip_and_not_now_puts_it_aside(home, capsys):
    computer, con = shelf(home)
    assert answer(capsys, "books", "--json", computer=computer)["tip"] is None
    unopened(con, BOOKS[6], BOOKS[7])
    con.close()
    shown = answer(capsys, "books", "--json", computer=computer)["tip"]
    assert shown["rule"] == "never_opened" and shown["id"] in (BOOKS[6], BOOKS[7])
    after = answer(capsys, "book", shown["id"], "--not-now", "--json", computer=computer)
    assert after["tip"]["id"] != shown["id"] and after["tip"]["rule"] == "never_opened"  # the answer has the next one
    assert answer(capsys, "books", "--json", computer=computer)["tip"] == after["tip"]
