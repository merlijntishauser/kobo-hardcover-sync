import json
import sqlite3

import pytest

from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.engine.plan import action


def matched(st, *cids):
    for n, c in enumerate(cids, 1):  # each its own book on Hardcover
        st.execute("update book set hc_how='isbn', hc_book_id=?, hc_pages=300 where content_id=?", (n, c))
    st.commit()


def make_kobo(path, books, events, with_user=False):
    c = sqlite3.connect(path)
    c.execute("""create table content (ContentID text, ContentType int, Title text, Attribution text, ISBN text,
                 ___PercentRead int, ReadStatus int, DateLastRead text, TimeSpentReading int,
                 LastTimeFinishedReading text)""")
    c.execute("create table Event (EventType int, FirstOccurrence text, LastOccurrence text, EventCount int, ContentID text)")
    if with_user:
        c.execute("create table user (UserID text, AuthToken text)")
    for b in books:
        c.execute("insert into content values (?,6,?,?,?,?,?,?,?,?)", (tuple(b) + ("",))[:9])
    c.execute("insert into content values ('chapter-1',9,'ch','','',0,0,'',0,'')")  # not a book
    for cid, first in events:
        c.execute("insert into Event values (3,?,?,1,?)", (first, first, cid))
    c.commit()
    c.close()


OLD = ("old", "Old Finished", "A", "111", 100, 2, "2021-05-01T10:00:00Z", 36000)
FAMILY = ("fam", "Family Reading", "B", "222", 40, 1, "2026-09-20T10:00:00Z", 7200)
MINE = ("mine", "Mine Now", "C", "333", 10, 1, "2026-09-29T10:00:00Z", 600)
UNTOUCHED = ("never", "Never Opened", "D", "444", 0, 0, "", 0)


def test_refuses_tokens_and_non_kobo(tmp_path):
    p = tmp_path / "k.sqlite"
    make_kobo(p, [OLD], [], with_user=True)
    with pytest.raises(kobo_db.ContainsKoboTokens):
        kobo_db.open_db(str(p))
    kobo_db.open_db(str(p), allow_user_table=True)  # explicit local import is allowed
    junk = tmp_path / "junk.sqlite"
    sqlite3.connect(junk).execute("create table x (a)").connection.commit()
    with pytest.raises(kobo_db.NotAKoboDatabase):
        kobo_db.open_db(str(junk))


def test_reads_books_and_device_events(tmp_path):
    p = tmp_path / "k.sqlite"
    make_kobo(p, [OLD, MINE, UNTOUCHED], [("mine", "2026-09-29T09:00:00.000")])
    books = {b.content_id: b for b in kobo_db.read_books(kobo_db.open_db(str(p)))}
    assert set(books) == {"old", "mine", "never"}  # chapter rows excluded
    assert books["mine"].first_event.startswith("2026-09-29")
    assert books["old"].first_event == ""


def test_history_off_then_new_books_auto(tmp_path):
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, FAMILY, MINE, UNTOUCHED], [("mine", "2026-09-05T09:00:00")])
    st = state.connect(str(tmp_path / "state.db"))
    r = state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    assert r["first_import"] and r["new_auto"] == 0
    rows = {x["content_id"]: x for x in st.execute("select * from book")}
    assert "never" not in rows  # untouched books are not tracked
    assert all(x["history"] == 1 and x["mode"] == "off" for x in rows.values())
    assert not any(state.syncs(x) for x in rows.values())

    # A book first opened on this device after the first import -> new, auto-on.
    k2 = tmp_path / "k2.sqlite"
    newbook = ("new", "New Book", "E", "555", 3, 1, "2099-01-01T10:00:00Z", 300)
    make_kobo(k2, [OLD, FAMILY, MINE, newbook], [("mine", "2026-09-05T09:00:00"), ("new", "2099-01-01T09:00:00")])
    r2 = state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k2))))
    assert r2["new_auto"] == 1
    new = st.execute("select * from book where content_id='new'").fetchone()
    assert new["history"] == 0 and new["mode"] == "auto" and state.syncs(new)
    assert new["first_seen_reading"]  # start date known for new books


def test_modes_and_dry_run_actions(tmp_path):
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, MINE], [])
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    assert state.set_mode(st, "robin", ["old", "mine"], "on") == 2
    matched(st, "old", "mine")
    rows = {x["content_id"]: x for x in st.execute("select * from book")}
    assert action(rows["old"]) == "mark Read, finished 2021-05-01"
    assert action(rows["mine"]) == "mark Currently reading, 10%"  # history: no start date
    st.execute("update book set last_sent=? where content_id='mine'", (json.dumps({"status": "reading", "progress": 10}),))
    st.commit()
    assert action(st.execute("select * from book where content_id='mine'").fetchone()) == ""
    with pytest.raises(ValueError):
        state.set_mode(st, "robin", ["old"], "maybe")
    assert state.set_mode(st, "someone-else", ["old"], "off") == 0  # readers only touch their own rows


REOPENED = ("reo", "Reopened After Finishing", "F", "666", 46, 1, "2026-09-28T10:00:00Z", 9000, "2024-07-30T20:00:00Z")


def test_finished_rule_and_state_override(tmp_path):
    k = tmp_path / "k.sqlite"
    make_kobo(k, [REOPENED, MINE], [])
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    state.set_mode(st, "robin", ["reo", "mine"], "on")
    matched(st, "reo", "mine")

    def get(cid):
        return st.execute("select * from book where content_id=?", (cid,)).fetchone()

    # Reopened at 46%, but finished before: still Read on the old date.
    assert action(get("reo")) == "mark Read, finished 2024-07-30"
    # A real re-read.
    state.set_state(st, "robin", "reo", "rereading", "2026-09-28")
    assert action(get("reo")) == "start a re-read, 46%, started 2026-09-28"
    # Pin an unfinished book as finished with a date.
    state.set_state(st, "robin", "mine", "finished", "2026-09-30")
    assert action(get("mine")) == "mark Read, finished 2026-09-30"
    with pytest.raises(ValueError):
        state.set_state(st, "robin", "mine", "finished", "30-09-2026")
    with pytest.raises(ValueError):
        state.set_state(st, "robin", "mine", "done")


def test_old_state_db_gets_new_columns(tmp_path):
    p = str(tmp_path / "state.db")
    c = sqlite3.connect(p)
    c.executescript(state.SCHEMA.replace("  finished_at text, state text not null default 'kobo', state_date text,\n", ""))
    c.close()
    cols = {r[1] for r in state.connect(p).execute("pragma table_info(book)")}
    assert {"finished_at", "state", "state_date"} <= cols


def test_today_and_shown_times_follow_the_time_zone_setting_else_the_computer(monkeypatch):
    from datetime import datetime

    from kobo_hardcover_sync.web import fmt

    monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # 14 hours ahead of UTC
    ahead = state.local_day()
    monkeypatch.setenv("TZ", "Pacific/Pago_Pago")  # 11 hours behind: never the same date
    assert state.local_day() < ahead
    monkeypatch.delenv("TZ")
    import zoneinfo

    def no_zone_by_name(name):
        raise AssertionError(f"a time zone was built in: {name}")

    with monkeypatch.context() as m:  # without the setting no zone is named: the computer's own is used
        m.setattr(zoneinfo, "ZoneInfo", no_zone_by_name)
        assert state.local_day() == datetime.now().astimezone().strftime("%Y-%m-%d")
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert fmt.fmt_dt("2026-09-30T10:24:00Z") == "30 Sep 2026, 19:24"
    monkeypatch.delenv("TZ")
    assert state.local_tz() is None and fmt.fmt_dt("2026-09-30T10:24:00Z")
