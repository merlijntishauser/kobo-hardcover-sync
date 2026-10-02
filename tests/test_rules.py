"""The sync rules that had no test of their own. docs/sync-rules.md is the
list of all rules; each one there names the test that pins it."""

import pytest

from kobo_hardcover_sync.engine import hardcover, job, kobo_db, plan, state
from kobo_hardcover_sync.engine.plan import action
from tests.test_core import MINE, OLD, UNTOUCHED, make_kobo
from tests.test_hardcover import BLIND, OLD_ED, READING, FakeHC, row, run, sent, setup

MINE_HIT = {"Mine": [{"book_id": 81, "title": "Mine Now", "authors": ["C"], "pages": 100, "slug": "m"}]}  # what a search for MINE finds


def imported(tmp_path, books, events=(), name="k.sqlite", device="kobo1"):
    k = tmp_path / name
    make_kobo(k, books, list(events))
    st = state.connect(str(tmp_path / "state.db"))
    return st, state.import_books(st, "alice", device, kobo_db.read_books(kobo_db.open_db(str(k))))


# ---------- which books ----------
def test_a_book_gone_from_the_kobo_stays_as_it_was(tmp_path):
    st = setup(tmp_path, [OLD, MINE])
    fake = FakeHC(isbn=OLD_ED, search=MINE_HIT)
    run(tmp_path, fake)
    before = dict(row(st, "mine"))
    fake.calls.clear()
    _, r = imported(tmp_path, [OLD], name="later.sqlite")  # "mine" was deleted from the Kobo
    assert r["changed"] == 0
    after = dict(row(st, "mine"))
    assert after == before and state.syncs(row(st, "mine"))  # still listed, still on, nothing forgotten
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == []  # and nothing is sent or taken off Hardcover for it


def test_importing_the_same_kobo_twice_changes_nothing(tmp_path):
    st, first = imported(tmp_path, [OLD, MINE, UNTOUCHED], [("mine", "2026-09-05T09:00:00")])
    assert (first["tracked_added"], first["changed"]) == (2, 0)
    snapshot = [tuple(r) for r in st.execute("select * from book order by content_id")]
    _, again = imported(tmp_path, [OLD, MINE, UNTOUCHED], [("mine", "2026-09-05T09:00:00")], name="again.sqlite")
    assert (again["tracked_added"], again["changed"], again["new_auto"], again["minutes_read"]) == (0, 0, 0, 0)
    assert [tuple(r) for r in st.execute("select * from book order by content_id")] == snapshot
    assert st.execute("select count(*) from reading_day").fetchone()[0] == 0  # no minutes counted twice


def test_the_start_date_is_the_day_the_book_was_first_seen_being_read(tmp_path):
    opened = ("opn", "Only Opened", "E", "555", 0, 0, "2026-09-28T10:00:00Z", 40)
    st, _ = imported(tmp_path, [MINE, opened])  # MINE is at 10% already: when it was started is not known
    imported(tmp_path, [MINE, opened], name="same.sqlite")
    assert plan.desired(row(st, "mine")) == {"status": "reading", "progress": 10}  # no start date, also not after a second import
    imported(tmp_path, [MINE, ("opn", "Only Opened", "E", "555", 4, 1, "2026-10-02T10:00:00Z", 900)], name="later.sqlite")
    assert plan.desired(row(st, "opn")) == {"status": "reading", "progress": 4, "started": state.now()[:10]}
    imported(tmp_path, [MINE, ("opn", "Only Opened", "E", "555", 9, 1, "2026-10-03T10:00:00Z", 1900)], name="still.sqlite")
    assert row(st, "opn")["first_seen_reading"][:10] == state.now()[:10] and "started" not in plan.desired(row(st, "mine"))


def test_the_same_book_on_two_kobos_is_two_rows(tmp_path):
    st, _ = imported(tmp_path, [OLD, MINE], device="kobo1")
    imported(tmp_path, [OLD], name="other.sqlite", device="kobo2")
    assert st.execute("select count(*) from book where content_id='old'").fetchone()[0] == 2
    assert st.execute("select count(*) from device").fetchone()[0] == 2  # each Kobo has its own history line


# ---------- matching ----------
def test_a_match_the_reader_chose_is_kept(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    job.pick(st, "alice", "rd", 4242, "Blindness (the other one)", 250)
    run(tmp_path, fake)
    r = row(st, "rd")
    assert (r["hc_how"], r["hc_book_id"]) == ("manual", 4242)  # not looked up again, not replaced by the search result
    assert [c for c in fake.calls if c[0] == "insert_ub"][0][1]["book_id"] == 4242


def test_an_unmatched_book_is_never_sent(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC()  # Hardcover knows nothing like it
    r = run(tmp_path, fake)
    assert (r["sent"], r["uncertain"]) == (0, 1) and fake.calls == [] and row(st, "rd")["hc_how"] == "none"
    assert action(row(st, "rd")) == "needs a Hardcover match"
    assert run(tmp_path, fake)["uncertain"] == 0 and fake.calls == []  # asked once; it waits for the reader


# ---------- progress ----------
def test_progress_is_the_kobos_number_also_when_it_went_down(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    run(tmp_path, fake)
    fake.calls.clear()
    st.execute("update book set percent = 30 where content_id = 'rd'")
    st.commit()
    assert action(row(st, "rd")) == "progress 46% to 30%"
    run(tmp_path, fake)
    assert [c[0] for c in fake.calls] == ["update_read"] and fake.calls[0][2]["progress_pages"] == 90
    assert sent(st, "rd")["progress"] == 30


def test_progress_is_pages_of_the_edition_rounded_and_within_the_book():
    assert [hardcover.pages_for(p, 300) for p in (0, 1, 46, 99, 100)] == [0, 3, 138, 297, 300]
    assert hardcover.pages_for(33, 10) == 3 and hardcover.pages_for(67, 10) == 7  # to the nearest page
    assert hardcover.pages_for(140, 300) == 300 and hardcover.pages_for(-5, 300) == 0  # never outside the book
    assert hardcover.pages_for(50, None) is None and hardcover.pages_for(50, 0) is None  # no page count, no progress


def test_without_a_page_count_the_status_is_sent_and_no_progress(tmp_path):
    setup(tmp_path, [READING])
    fake = FakeHC(search={"Blindness": [{"book_id": 80, "title": "Blindness", "authors": ["Jose Saramago"], "pages": None, "slug": "b"}]})
    run(tmp_path, fake)
    assert [c[0] for c in fake.calls] == ["insert_ub"] and fake.calls[0][1]["status_id"] == 2
    assert all("progress_pages" not in c[-1] for c in fake.calls if isinstance(c[-1], dict))


def test_a_book_with_progress_is_being_read_whatever_the_kobo_calls_it(tmp_path):
    odd = ("odd", "Unread But Halfway", "H", "888", 12, 0, "2026-09-29T10:00:00Z", 900)  # the Kobo says unread, at 12%
    st = setup(tmp_path, [odd])
    assert plan.desired(row(st, "odd")) == {"status": "reading", "progress": 12}
    assert not state.being_read(0, 0) and not state.being_read(0, None) and not state.being_read(2, 100)


def test_the_finish_date_is_the_kobos_utc_date(tmp_path):
    late = ("late", "Finished After Midnight", "G", "777", 100, 2, "2026-09-30T22:30:00Z", 9000, "2026-09-30T22:30:00Z")
    st = setup(tmp_path, [late])  # 00:30 on 1 October, two hours east of UTC
    assert plan.desired(row(st, "late")) == {"status": "read", "finished": "2026-09-30"}


def test_progress_set_on_hardcover_is_not_taken_over(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    run(tmp_path, fake)
    ub = sent(st, "rd")["user_book_id"]
    fake.reader_sets(ub, read={"progress_pages": 7})  # edited on hardcover.app
    fake.calls.clear()
    r = run(tmp_path, fake)
    assert r["adopted"] == 0 and row(st, "rd")["percent"] == 46 and fake.calls == []  # the Kobo's number stays the truth here
    st.execute("update book set percent = 50 where content_id = 'rd'")
    st.commit()
    run(tmp_path, fake)
    assert fake.calls[0][2]["progress_pages"] == 150  # and goes out again when the Kobo moves


# ---------- several Kobo books, one Hardcover book ----------
SAMPLE = ("smp", "Old Finished (sample)", "A", "111", 12, 1, "2026-09-01T10:00:00Z", 300)  # ISBN 111, as OLD: one book on Hardcover


def test_of_two_copies_of_one_hardcover_book_the_one_read_last_speaks(tmp_path):
    st = setup(tmp_path, [OLD, SAMPLE])
    assert {k: v["content_id"] for k, v in plan.quiet_for(st, "alice").items()} == {}  # not matched yet: nothing known
    fake = FakeHC(isbn=OLD_ED)
    assert run(tmp_path, fake)["sent"] == 1
    assert [c[0] for c in fake.calls].count("insert_ub") == 1 and len(fake.books) == 1  # one shelf entry
    assert next(iter(fake.books.values()))["status_id"] == 2  # the sample was read last: Currently reading
    assert {k: v["content_id"] for k, v in plan.quiet_for(st, "alice").items()} == {("kobo1", "old"): "smp"}
    assert row(st, "old")["last_sent"] == row(st, "smp")["last_sent"]  # what Hardcover has is known once, for both
    fake.calls.clear()
    r = run(tmp_path, fake)
    assert (r["sent"], r["adopted"]) == (0, 0) and fake.calls == []  # it settles: the copies do not fight over the entry
    assert (row(st, "old")["state"], row(st, "smp")["state"]) == ("kobo", "kobo")  # and the other copy is no "edit on Hardcover"
    assert run(tmp_path, fake, live=False)["planned"] == 0


def test_the_other_copy_takes_over_once_it_is_read_later(tmp_path):
    st = setup(tmp_path, [OLD, SAMPLE])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    st.execute("update book set last_read = '2026-10-01T08:00:00Z', finished_at = '2026-10-01T08:00:00Z' where content_id = 'old'")
    st.commit()
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 1
    assert "insert_ub" not in [c[0] for c in fake.calls] and len(fake.books) == 1  # the same shelf entry
    ub = next(iter(fake.books.values()))
    assert ub["status_id"] == 3 and len(ub["user_book_reads"]) == 1 and ub["user_book_reads"][0]["finished_at"] == "2026-10-01"
    assert list(plan.quiet_for(st, "alice")) == [("kobo1", "smp")]
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == []


def test_a_copy_that_is_switched_off_or_unread_does_not_speak(tmp_path):
    unread = ("new", "Old Finished (new edition)", "A", "111", 0, 0, "2026-10-01T10:00:00Z", 30)  # opened last, nothing read
    st = setup(tmp_path, [OLD, SAMPLE, unread])
    state.set_mode(st, "alice", ["smp"], "off")
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    assert next(iter(fake.books.values()))["status_id"] == 3  # OLD speaks: the sample is off, the new edition has nothing to say
    assert list(plan.quiet_for(st, "alice")) == [("kobo1", "new")]


def test_the_same_book_on_two_kobos_follows_the_kobo_it_was_read_on_last(tmp_path):
    st, _ = imported(tmp_path, [READING], device="kobo1")
    in_a_drawer = ("rd", "Blindness", "José Saramago", "978000", 20, 1, "2026-08-01T10:00:00Z", 400)
    imported(tmp_path, [in_a_drawer], name="drawer.sqlite", device="kobo2")
    state.set_mode(st, "alice", ["rd"], "on")
    fake = FakeHC(search=BLIND)
    assert run(tmp_path, fake)["sent"] == 1 and len(fake.books) == 1
    assert next(iter(fake.books.values()))["user_book_reads"][0]["progress_pages"] == 138  # 46%, not the drawer's 20%
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == []
    assert list(plan.quiet_for(st, "alice")) == [("kobo2", "rd")]


def test_a_book_taken_off_the_shelf_on_hardcover_switches_every_copy_off(tmp_path):
    st = setup(tmp_path, [OLD, SAMPLE])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    fake.books.clear()  # removed on hardcover.app
    fake.calls.clear()
    r = run(tmp_path, fake)
    assert (r["removed"], r["sent"]) == (1, 0) and fake.calls == [] and not fake.books  # the other copy does not add it again
    assert [row(st, c)["mode"] for c in ("old", "smp")] == ["off", "off"]
    assert row(st, "old")["hc_book_id"] == 70  # the match is kept for when it is switched on again


def test_a_copy_that_never_spoke_goes_off_with_the_book_too(tmp_path):
    st = setup(tmp_path, [OLD, SAMPLE])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    st.execute("update book set last_sent = null where content_id = 'old'")  # as a copy matched before copies shared a record
    st.commit()
    fake.books.clear()
    fake.calls.clear()
    assert run(tmp_path, fake)["removed"] == 1 and fake.calls == [] and not fake.books
    assert [row(st, c)["mode"] for c in ("old", "smp")] == ["off", "off"]


def test_an_edit_on_hardcover_is_taken_over_by_the_copy_that_speaks(tmp_path):
    st = setup(tmp_path, [OLD, SAMPLE])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    ub = sent(st, "smp")["user_book_id"]
    fake.reader_sets(ub, status_id=3, read={"finished_at": "2026-09-15"})  # marked Read on hardcover.app
    fake.calls.clear()
    r = run(tmp_path, fake)
    assert (r["adopted"], r["sent"]) == (1, 0) and fake.calls == []  # one edit, taken over once
    assert (row(st, "smp")["state"], row(st, "smp")["state_date"]) == ("finished", "2026-09-15")
    assert row(st, "old")["state"] == "kobo"  # the quiet copy keeps what its Kobo says, for when it is read again
    assert row(st, "old")["last_sent"] == row(st, "smp")["last_sent"]
    assert run(tmp_path, fake)["adopted"] == 0


def test_a_book_matched_by_hand_to_a_book_already_synced_joins_it(tmp_path):
    st = setup(tmp_path, [OLD, ("odd", "Oud en klaar", "A", "", 100, 2, "2020-01-01T10:00:00Z", 500)])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    assert row(st, "odd")["hc_how"] == "none" and row(st, "odd")["last_sent"] is None
    job.pick(st, "alice", "odd", 70, "Old Finished", 400)  # the reader says: this is that book
    assert row(st, "odd")["last_sent"] == row(st, "old")["last_sent"]
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == [] and len(fake.books) == 1
    job.pick(st, "alice", "odd", 71, "Another book", 200)  # no, it is another one after all
    assert row(st, "odd")["last_sent"] is None and row(st, "old")["last_sent"]
    run(tmp_path, fake)
    assert len(fake.books) == 2  # its own shelf entry, and the first book's entry is left as it was


# ---------- when things go wrong ----------
class Flaky(FakeHC):
    """Hardcover that fails for one book, once."""

    def __init__(self, fail_book, **kw):
        super().__init__(**kw)
        self.fail_book, self.failed = fail_book, 0

    def insert_user_book(self, obj):
        if obj["book_id"] == self.fail_book and not self.failed:
            self.failed += 1
            raise hardcover.HardcoverError("Hardcover refused: this book cannot be added right now")
        return super().insert_user_book(obj)


def test_one_failing_book_does_not_stop_the_others_and_is_tried_again(tmp_path):
    st = setup(tmp_path, [OLD, READING])
    fake = Flaky(80, isbn=OLD_ED, search=BLIND)
    r = run(tmp_path, fake)
    assert (r["status"], r["sent"], r["errors"]) == ("errors", 1, 1)
    assert (
        "cannot be added" in row(st, "rd")["hc_error"] and row(st, "rd")["last_sent"] is None
    )  # shown on the page, nothing recorded as sent
    assert row(st, "old")["hc_error"] is None and sent(st, "old")["status"] == "read"
    r = run(tmp_path, fake)
    assert (r["status"], r["sent"], r["errors"]) == ("ok", 1, 0) and row(st, "rd")["hc_error"] is None
    assert len(fake.books) == 2


def test_hardcover_out_of_reach_fails_the_run_and_loses_nothing(tmp_path):
    st = setup(tmp_path, [OLD, READING])

    class Down(FakeHC):
        def shelf(self):
            raise hardcover.HardcoverError(
                "Hardcover could not be reached (timed out). Nothing is lost: the next sync carries on", "unreachable"
            )

    r = run(tmp_path, Down(isbn=OLD_ED, search=BLIND))
    assert r["status"] == "failed" and "timed out" in r["fatal"]
    assert st.execute("select status from job order by started desc limit 1").fetchone()[0] == "failed"
    assert all(row(st, c)["last_sent"] is None for c in ("old", "rd"))
    fake = FakeHC(isbn=OLD_ED, search=BLIND)
    assert run(tmp_path, fake)["sent"] == 2  # the next sync sends what was waiting


class Killed(BaseException):
    """The process died: not an error anything catches."""


def test_a_run_cut_off_after_hardcover_took_the_book_does_not_add_it_twice(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    real_reads = fake.reads

    def dies(ub):
        raise Killed

    fake.reads = dies  # Hardcover has the book; the process dies before that is written down here
    with pytest.raises(Killed):
        run(tmp_path, fake)
    assert len(fake.books) == 1 and row(st, "rd")["last_sent"] is None
    fake.reads = real_reads
    r = run(tmp_path, fake)  # the next run finds it on the shelf and carries on from there
    assert r["sent"] == 1 and [c[0] for c in fake.calls].count("insert_ub") == 1 and len(fake.books) == 1
    assert len(next(iter(fake.books.values()))["user_book_reads"]) == 1
    assert sent(st, "rd")["progress"] == 46


def test_trouble_that_is_the_same_for_every_book_stops_the_run_at_the_first_one(tmp_path):
    st = setup(tmp_path, [OLD, READING, MINE])
    catalogue = {
        "isbn": OLD_ED,
        "search": {**BLIND, **MINE_HIT},
    }
    for kind in ("unreachable", "rate", "token", "scope"):
        tried = []

        class Down(FakeHC):
            def insert_user_book(self, obj, kind=kind, tried=tried):
                tried.append(obj["book_id"])
                raise hardcover.HardcoverError(
                    "Hardcover could not be reached (timed out). Nothing is lost: the next sync carries on", kind
                )

        r = run(tmp_path, Down(**catalogue))
        assert (r["status"], r["sent"], r["errors"]) == ("failed", 0, 0) and "could not be reached" in r["fatal"], kind
        assert len(tried) == 1, kind  # not once per book, each with its own wait
        assert all(row(st, c)["hc_error"] is None and row(st, c)["last_sent"] is None for c in ("old", "rd", "mine"))
    assert run(tmp_path, FakeHC(**catalogue))["sent"] == 3  # nothing was lost


def test_a_shelf_without_any_of_our_books_switches_nothing_off(tmp_path):
    st = setup(tmp_path, [OLD, READING, MINE])
    fake = FakeHC(isbn=OLD_ED, search={**BLIND, **MINE_HIT})
    assert run(tmp_path, fake)["sent"] == 3
    mine, fake.books = fake.books, {}  # the shelf of another account, or one the token may not read
    fake.calls.clear()
    r = run(tmp_path, fake)
    assert r["status"] == "failed" and "None of the 3 books" in r["fatal"] and "Nothing was switched off" in r["fatal"]
    assert [row(st, c)["mode"] for c in ("old", "rd", "mine")] == ["on", "on", "on"] and fake.calls == []
    assert all(row(st, c)["last_sent"] for c in ("old", "rd", "mine"))
    fake.books = {k: v for k, v in mine.items() if v["book_id"] != 81}  # one of three taken off: that is the reader
    r = run(tmp_path, fake)
    assert (r["status"], r["removed"]) == ("ok", 1) and [row(st, c)["mode"] for c in ("old", "rd", "mine")] == ["on", "on", "off"]
    state.set_mode(st, "alice", ["old", "rd"], "off")  # and a reader who switched them off here may empty the shelf
    fake.books = {}
    assert run(tmp_path, fake)["status"] == "ok"
