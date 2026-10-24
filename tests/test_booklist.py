"""The list of books in words: what the page draws and the Mac app will
draw from the tool's JSON. The page's own tests (test_web) hold how it
looks; these hold that the list says it without markup."""

from kobo_hardcover_sync import booklist
from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.engine.plan import quiet_for
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
