from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.server.stats import stats
from tests.test_core import make_kobo


def book(cid, secs, pct=10, status=1, finished=""):
    return (cid, f"Title {cid}", "Author", "999", pct, status, "2026-09-30T08:00:00Z", secs, finished)


def test_minutes_only_count_books_opened_on_this_device(tmp_path):
    st = state.connect(str(tmp_path / "state.db"))
    k1 = tmp_path / "a.sqlite"
    make_kobo(k1, [book("mine", 600), book("family", 600)], [("mine", "2026-09-05T09:00:00")])
    state.import_books(st, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k1))))
    k2 = tmp_path / "b.sqlite"
    # 30 min more on my book, 45 min more on a family book read on another Kobo
    make_kobo(k2, [book("mine", 600 + 1800, 20), book("family", 600 + 2700, 50)], [("mine", "2026-09-05T09:00:00")])
    r = state.import_books(st, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k2))))
    assert r["minutes_read"] == 30
    s = stats(st, "alice", today=state.local_day())
    assert s["minutes_today"] == 30 and s["minutes_week"] == 30
    assert s["current_title"] == "Title mine" and s["current_percent"] == 20


def test_finished_this_year_counts_synced_books_only(tmp_path):
    st = state.connect(str(tmp_path / "state.db"))
    k = tmp_path / "a.sqlite"
    make_kobo(
        k,
        [
            book("a", 100, 100, 2, "2026-03-01T10:00:00Z"),
            book("b", 100, 100, 2, "2025-03-01T10:00:00Z"),
            book("c", 100, 100, 2, "2026-04-01T10:00:00Z"),
        ],
        [],
    )
    state.import_books(st, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    state.set_mode(st, "alice", ["a", "b"], "on")
    assert stats(st, "alice", today="2026-09-30")["finished_this_year"] == 1  # c is off, b is 2025
