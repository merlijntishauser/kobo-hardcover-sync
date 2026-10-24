"""The list of books in words: what the page draws and the Mac app will
draw from the tool's JSON. The page's own tests (test_web) hold how it
looks; these hold that the list says it without markup."""

import html
import re

from kobo_hardcover_sync import booklist
from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.engine.plan import quiet_for
from kobo_hardcover_sync.web import app
from tests.test_core import FAMILY, MINE, OLD, UNTOUCHED, make_kobo, matched


def shelf(tmp_path):
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, FAMILY, MINE, UNTOUCHED], [])
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    matched(st, "old", "mine")
    state.set_mode(st, "robin", ["old", "mine"], "on")
    return st


def test_the_status_and_the_correction_are_words_not_markup(tmp_path):
    st = shelf(tmp_path)
    quiet = quiet_for(st, "robin")
    rows = booklist.query_rows(st, "robin", "", "all", "last_read")
    said = [booklist.hc_status(r, False, quiet) for r in rows]
    assert {kind for kind, _ in said} <= {"ok", "next", "wait", "warn", "err", "none"}
    fixes = [booklist.correction(r) for r in rows]
    assert any(fixes)  # a matched book the next sync puts on the shelf
    for text in [t for _, t in said] + [w for fix in fixes if fix for w in fix]:
        assert "<" not in text and "&" not in text
    live = [booklist.hc_status(r, True, quiet)[1] for r in rows]
    assert booklist.marked(st, "robin", True, quiet) == sum(t.startswith("Next sync") for t in live)


def test_set_all_takes_the_books_the_filter_counts(tmp_path):
    st = shelf(tmp_path)
    counts = booklist.filter_counts(st, "robin", "")
    for f in booklist.FILTERS:
        assert len(booklist.ids(st, "robin", "", f)) == counts[f], f
    assert booklist.ids(st, "robin", "mine", "all") == ["mine"]  # the search too
    assert [k for _, keys in booklist.FILTER_GROUPS for k in keys] == list(booklist.FILTERS)  # every filter has its place


def test_details_in_words_say_what_the_pages_details_say(tmp_path):
    st = shelf(tmp_path)
    st.execute(
        "update book set hc_title='Old, the book', hc_format='Ebook', hc_edition_by='hardcover',"
        ' last_sent=\'{"user_book_id": 7, "status": "read", "finished": "2021-05-01", "at": "2026-10-01T08:00:00Z"}\''
        " where content_id='old'"
    )
    st.execute(
        "update book set hc_how='uncertain', hc_candidates=? where content_id='fam'",
        ('[{"book_id": 9, "title": "Family", "authors": ["B"]}]',),
    )
    st.execute("update book set mode='on' where content_id='fam'")
    st.commit()
    quiet = quiet_for(st, "robin")
    for r in booklist.query_rows(st, "robin", "", "all", "last_read"):
        said = booklist.details(r)
        page = html.unescape(re.sub(r"<[^>]+>", " ", app.details_fragment(r, booklist.hc_status(r, False, quiet), "")))
        page = re.sub(r"\s+", " ", page)
        for label, value in said["kobo"] + said["hardcover"]:
            assert label in page, label
            for part in re.split(r" \(|\)$", value):  # what the page sets apart in grey stands in brackets here
                assert part.strip() in page, (label, part)
        words, kept = booklist.edition(r)
        assert html.unescape(words) in html.unescape(app.edition_line(r)) and kept == (r["content_id"] == "old")
    assert booklist.edition(st.execute("select * from reader_book where content_id='old'").fetchone()) == ("Old, the book, Ebook", True)
    fam = booklist.details(st.execute("select * from reader_book where content_id='fam'").fetchone())
    assert fam["candidates"] == [{"title": "Family", "author": "B"}] and not fam["on_shelf"] and fam["link"] == ""
    old = booklist.details(st.execute("select * from reader_book where content_id='old'").fetchone())
    assert old["on_shelf"] and old["link"] == "https://hardcover.app/id/book/1"
