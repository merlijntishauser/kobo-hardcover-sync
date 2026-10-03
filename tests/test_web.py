import importlib
import json
import re

from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.server import accounts
from tests import client_at
from tests.test_core import MINE, OLD, make_kobo, matched


def client(tmp_path, monkeypatch):
    (tmp_path / "readers.yaml").write_text("readers:\n  robin:\n    identities: [robin, robin@example.org]\n")
    monkeypatch.setenv("KHS_DATA", str(tmp_path))
    monkeypatch.setenv("KHS_CONFIG", str(tmp_path / "readers.yaml"))
    monkeypatch.setenv("KHS_HOST", "kobo.example.org")
    import kobo_hardcover_sync.web.app as web

    importlib.reload(web)
    k = tmp_path / "k.sqlite"
    make_kobo(k, [OLD, MINE], [])
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "robin", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    matched(st, "old", "mine")
    return client_at(web.app)


def test_no_identity_gets_403(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.get("/").status_code == 403
    for path in ("/settings", "/admin", "/details/old", "/cover/old"):
        assert c.get(path).status_code == 403, path


def test_page_lists_books_for_mapped_user(tmp_path, monkeypatch):
    r = client(tmp_path, monkeypatch).get("/", headers={"Remote-Email": "Robin@example.org"})
    assert r.status_code == 200 and "Old Finished" in r.text and "Not connected to Hardcover yet" in r.text


def test_mode_post_and_cross_origin_refusal(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    bad = c.post("/mode", data={"ids": "old", "mode": "on"}, headers={**h, "Origin": "https://evil.example"})
    assert bad.status_code == 403
    ok = c.post("/mode", data={"ids": "old", "mode": "on"}, headers={**h, "Origin": "https://kobo.example.org"}, follow_redirects=False)
    assert ok.status_code == 303
    assert "mark Read, finished 2021-05-01" in c.get("/", headers=h).text


def test_the_first_run_says_what_to_do_until_the_reader_goes_live(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    page = c.get("/", headers=h).text
    # Dry run with books: above the list, what to do with them and the three steps.
    assert '<section class="firstrun" aria-labelledby="fr-h">' in page and "Pick the books that are yours" in page
    assert "Your Kobo sent 2 books." in page
    assert '<a href="/settings#hardcover">Connect in Settings</a>' in page  # step 1 not done: no token yet
    assert '<li class="here" aria-current="step"><span class="n">2</span><b>Pick your books</b>' in page
    before = int(re.search(r'<p class="tally"><strong>(\d+)</strong>', page).group(1))
    # Switching a book on counts at once, for the row redrawn in place.
    d = c.post(
        "/mode", data={"ids": "old", "mode": "on"}, headers={**h, "X-Requested-With": "fetch", "Origin": "https://kobo.example.org"}
    ).json()
    assert d["on"] == before + 1
    # Going live is the last step, so the first run is over.
    st = state.connect(str(tmp_path / "state.db"))
    st.execute("update reader set hardcover_live=1 where name='robin'")
    st.commit()
    assert "firstrun" not in c.get("/", headers=h).text


def test_sync_now_shows_the_sync_running_and_then_what_it_did(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    import kobo_hardcover_sync.web.app as web

    # While it runs: Syncing, what it is doing, a gauge that is that far; the page looks again by itself without JS.
    web.job.progress["robin"] = {"phase": "send", "done": 1, "total": 4}
    try:
        page = c.get("/", headers=h).text
        assert '<form class="syncnow" data-running="/sync/status">' in page and 'aria-busy="true"' in page
        assert "<span>Syncing</span>" in page and '<div class="bar syncbar" aria-hidden="true"><span style="--p:0.25">' in page
        assert '<noscript><meta http-equiv="refresh" content="3"></noscript>' in page
        d = c.get("/sync/status", headers=h).json()
        assert d == {"running": True, "text": "Checking 2 of 4", "part": 0.25}  # a dry run checks, a live one sends
        web.job.progress["robin"] = {"phase": "shelf", "done": 0, "total": 0}
        assert c.get("/sync/status", headers=h).json() == {"running": True, "text": "Reading your Hardcover shelf", "part": None}
    finally:
        web.job.progress.pop("robin", None)
    # Done: what it did, said once the list is back (kobo.js shows it after the reload it asked for).
    st = state.connect(str(tmp_path / "state.db"))
    st.execute(
        "insert into job (reader, started, finished, live, status, detail) values ('robin', '2026-10-03T20:26:14Z', '2026-10-03T20:26:21Z', 1, 'ok', ?)",
        (json.dumps({"sent": 1, "errors": 0}),),
    )
    st.commit()
    assert c.get("/sync/status", headers=h).json() == {"running": False, "kind": "ok", "text": "Done: 1 change sent to Hardcover."}
    page = c.get("/", headers=h).text
    assert "<span>Sync now</span>" in page and "refresh" not in page.split("</head>")[0]
    assert '<div class="syncdone" role="status" hidden>' in page and "Done: 1 change sent to Hardcover." in page


def test_row_mode_via_fetch_returns_json(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    r = c.post(
        "/mode",
        data={"ids": "old", "mode": "on"},
        headers={"Remote-User": "robin", "X-Requested-With": "fetch", "Origin": "https://kobo.example.org"},
    )
    d = r.json()
    assert r.status_code == 200 and d["syncs"] is True and d["action"] == "mark Read, finished 2021-05-01"
    # The row's redrawn pieces: a full line gauge, and what would be sent, as a mark and the words.
    assert 'class="bar done"' in d["book"] and "Finished 1 May 2021" in d["book"]
    assert d["status"].startswith('<div class="act next"><svg class="mk"') and d["status"].endswith(
        "<span>Would send: mark Read, finished 2021-05-01</span></div>"
    )
    # In the cell the change is drawn as a correction: nothing on the shelf yet, so only an insertion.
    assert '<span>Would send</span><span class="sr">: mark Read, finished 2021-05-01</span>' in d["hc"]
    assert (
        '<div class="fix" aria-hidden="true"><span class="swap"><ins>' in d["hc"]
        and "Read, finished 1 May 2021</ins>" in d["hc"]
        and "<s>" not in d["hc"]
    )


def test_pick_returns_to_the_row_with_filters(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    r = c.post(
        "/pick",
        data={"id": "mine", "choice": "80|300|Mine Now", "back": "f=reading&q=mine"},
        headers={"Remote-User": "robin", "Origin": "https://kobo.example.org"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/?f=reading&q=mine#b-mine"


def test_page_has_theme_switch_chips_and_static_assets(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    page = c.get("/?f=finished", headers=h).text
    assert 'data-set="auto"' in page and "kobo-theme" in page  # switch + pre-paint script
    assert 'aria-current="true">Finished<b>1</b>' in page  # active chip with its count
    assert "Needs a match<b>0</b>" in page
    assert "Mine Now" not in page  # filtered out
    css = c.get("/static/kobo.css")
    assert css.status_code == 200 and '[data-theme="dark"]' in css.text and "prefers-color-scheme: dark" in css.text
    assert c.get("/static/fonts/SchibstedGrotesk-latin.woff2").status_code == 200


def test_filters_never_leak_other_readers(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    st.execute(
        "insert into book (reader, device, content_id, title, author, history, mode, state, status, percent) "
        "values ('other', 'k2', 'x', 'Someone Elses Reread', 'Z', 1, 'on', 'rereading', 1, 5)"
    )
    st.commit()
    for f in ("all", "reading", "on"):
        assert "Someone Elses Reread" not in c.get(f"/?f={f}", headers={"Remote-User": "robin"}).text


def test_candidate_labels_are_shortened(tmp_path, monkeypatch):
    import json

    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    long_title = "A Very Long Title " * 12
    st.execute(
        "update book set mode='on', hc_book_id=null, hc_how='uncertain', hc_candidates=? where content_id='mine'",
        (json.dumps([{"book_id": 9, "title": long_title, "authors": ["An Author With A Remarkably Long Name Indeed"], "pages": 100}]),),
    )
    st.commit()
    page = c.get("/details/mine", headers={"Remote-User": "robin", "X-Requested-With": "fetch"}).text
    label = page.split('<select name="choice"')[1].split("</option>")[0].split(">")[-1]
    assert len(label) <= 60 + 2 + 30 and "…" in label
    assert long_title.strip() in page  # full title kept in the value, so picking still stores it


def test_up_to_date_links_to_the_book_on_hardcover(tmp_path, monkeypatch):
    import json

    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    st.execute(
        "update book set mode='on', hc_book_id=20640, last_sent=? where content_id='old'",
        (json.dumps({"status": "read", "user_book_id": 5}),),
    )
    st.commit()
    h = {"Remote-User": "robin"}
    assert "Up to date on Hardcover" in c.get("/?f=finished", headers=h).text
    d = c.get("/details/old", headers={**h, "X-Requested-With": "fetch"}).text
    assert '<a href="https://hardcover.app/id/book/20640" target="_blank" rel="noopener noreferrer">' in d


def test_hardcover_column_and_details(tmp_path, monkeypatch):
    import json

    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    st.execute(
        "update book set mode='on', hc_book_id=20640, hc_title='Old Finished', hc_format='Ebook', hc_format_id=4, hc_pages=300, last_sent=? where content_id='old'",
        (json.dumps({"status": "read", "user_book_id": 5, "finished": "2021-05-01", "at": "2026-09-30T10:00:00Z"}),),
    )
    st.execute(
        "update book set mode='on', hc_book_id=null, hc_how='uncertain', hc_candidates=? where content_id='mine'",
        (json.dumps([{"book_id": 9, "title": "Mine Now", "authors": ["C"], "pages": 100}]),),
    )
    st.commit()
    h = {"Remote-User": "robin"}
    page = c.get("/", headers=h).text
    # The cell: status with its mark, a quiet match line, a Details button; no forms in the row.
    assert re.search(r'<div class="act ok"><svg class="mk"[^>]*>.*?</svg><span>Up to date on Hardcover</span></div>', page)
    assert '<div class="sub">Old Finished, Ebook</div>' in page
    assert re.search(r'<div class="act warn"><svg class="mk"[^>]*>.*?</svg><span>Needs a Hardcover match</span></div>', page)
    assert '<ul class="legend" aria-label="What the marks mean">' in page  # every mark explained above the list
    assert page.count('class="details"') == 2 and "/pick" not in page.split("<dialog")[0]
    # The details fragment carries the facts and the actions.
    d = c.get("/details/old?back=f%3Dall", headers={**h, "X-Requested-With": "fetch"}).text
    assert "<h2>Old Finished</h2>" in d and 'href="https://hardcover.app/id/book/20640"' in d and "300 pages" in d
    assert "Read, 1 May 2021" in d and "Remove from Hardcover" in d and 'name="back" value="f=all"' in d
    d2 = c.get("/details/mine", headers={**h, "X-Requested-With": "fetch"}).text
    assert 'action="/pick"' in d2 and 'action="/research"' in d2 and "Needs a Hardcover match" in d2
    # Without JS: a page of its own, with a way back.
    full = c.get("/details/old", headers=h).text
    assert "<!doctype html>" in full and "Back to the list" in full
    assert c.get("/details/nope", headers=h).status_code == 404


def test_dialog_forms_answer_with_refreshed_details_and_row(tmp_path, monkeypatch):
    from kobo_hardcover_sync.engine import hardcover

    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    st.execute("update book set mode='on', hc_book_id=null, hc_how='none', hc_candidates='[]' where content_id='mine'")
    st.commit()
    h = {"Remote-User": "robin", "Origin": "https://kobo.example.org", "X-Requested-With": "fetch"}

    class Stub:
        def __init__(self, token, **kw):
            pass

        def search(self, q, n=3):
            return [{"book_id": 77, "title": "Mine Now", "authors": ["C"], "pages": 120, "slug": "m"}]

    monkeypatch.setattr(hardcover, "Client", Stub)
    monkeypatch.setattr(accounts, "token_for", lambda con, reader: "t")
    # Search Hardcover from the dialog: JSON with the refreshed dialog (now with a candidate) and the row.
    r = c.post("/research", data={"id": "mine", "q": "Mine Now", "back": "f=all"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert '<option value="77|120|Mine Now"' in d["details"] and "Needs a Hardcover match" in d["hc"]
    # A search that finds nothing: the dialog says so and keeps the search box.
    monkeypatch.setattr(Stub, "search", lambda self, q, n=3: [])
    r = c.post("/research", data={"id": "mine", "q": "nothing like it", "back": "f=all"}, headers=h)
    assert r.status_code == 200 and "Hardcover found nothing for this book." in r.json()["details"]
    assert 'action="/research"' in r.json()["details"] and 'action="/pick"' not in r.json()["details"]
    assert "Hardcover found nothing" in c.get("/details/mine", headers=h).text
    monkeypatch.setattr(
        Stub, "search", lambda self, q, n=3: [{"book_id": 77, "title": "Mine Now", "authors": ["C"], "pages": 120, "slug": "m"}]
    )
    c.post("/research", data={"id": "mine", "q": "Mine Now", "back": "f=all"}, headers=h)
    # Use the candidate: the row's status moves on, the dialog shows the match.
    r = c.post("/pick", data={"id": "mine", "choice": "77|120|Mine Now", "back": "f=all"}, headers=h)
    d = r.json()
    assert "Would send" in d["status"] and "Mine Now" in d["hc"]
    assert 'href="https://hardcover.app/id/book/77"' in d["details"]
    # Without the fetch header the same post redirects to the row, as before.
    r = c.post(
        "/research",
        data={"id": "mine", "q": "x", "back": "f=all"},
        headers={k: v for k, v in h.items() if k != "X-Requested-With"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].endswith("#b-mine")


def test_help_dialog_and_unread_wording(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    st = state.connect(str(tmp_path / "state.db"))
    st.execute("update book set mode='on', status=0, percent=0, finished_at='' where content_id='mine'")
    st.commit()
    page = c.get("/", headers={"Remote-User": "robin"}).text
    assert 'data-open="help"' in page and '<dialog id="help"' in page and "How Kobo Hardcover Sync works" in page
    assert "Unread on the Kobo, nothing to send yet" in page


def test_sync_now_and_refresh_keep_the_filtered_view(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin", "Origin": "https://kobo.example.org"}
    import kobo_hardcover_sync.web.app as web

    started = []
    monkeypatch.setattr(web.job, "start", lambda *a: started.append(a))
    page = c.get("/?f=on&q=mine&sort=title", headers=h).text
    # Sync now carries the view along; Refresh is a GET form with the same search, filter and sort.
    assert '<input type="hidden" name="back" value="f=on&amp;q=mine&amp;sort=title">' in page
    assert (
        '<form method="get" action="/"><input type="hidden" name="q" value="mine"><input type="hidden" name="f" value="on">'
        '<input type="hidden" name="sort" value="title"><button>Refresh</button></form>'
    ) in page
    r = c.post("/sync", data={"back": "f=on&q=mine&sort=title"}, headers=h, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?f=on&q=mine&sort=title" and len(started) == 1
    # Without a filter: the plain page, and a Refresh without parameters.
    assert c.post("/sync", headers=h, follow_redirects=False).headers["location"] == "/"
    assert '<form method="get" action="/"><button>Refresh</button></form>' in c.get("/", headers=h).text


def test_a_copy_that_does_not_speak_for_its_hardcover_book_says_so(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    st = state.connect(str(tmp_path / "state.db"))
    st.execute("update book set mode='on', hc_book_id=7")  # both are the same book on Hardcover; "mine" was read last
    st.commit()
    page = c.get("/", headers=h).text
    assert page.count("Hardcover follows the copy of this book you read last") == 1
    assert "mark Currently reading, 10%" in page and "mark Read, finished 2021-05-01" not in page
    assert "Hardcover follows the copy" in c.get("/details/old", headers=h).text
    assert "Hardcover follows the copy" not in c.get("/details/mine", headers=h).text


def test_set_all_shown_asks_first_without_js(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin", "Origin": "https://kobo.example.org"}
    assert '<input type="hidden" name="bulk" value="1">' in c.get("/", headers=h).text
    # No "confirmed": a page with the question, and nothing changed yet.
    r = c.post("/mode", data={"ids": "old,mine", "mode": "on", "back": "f=history", "bulk": "1"}, headers=h, follow_redirects=False)
    assert r.status_code == 200 and "Change sync to On for all books shown (2)?" in r.text
    assert '<input type="hidden" name="ids" value="old,mine">' in r.text and '<input type="hidden" name="confirmed" value="1">' in r.text
    assert '<a class="details" href="/?f=history">Cancel</a>' in r.text
    assert "mark Read, finished 2021-05-01" not in c.get("/", headers=h).text
    # Confirmed (the page's button, or kobo.js after its dialog): changed, back to the same view.
    r = c.post(
        "/mode",
        data={"ids": "old,mine", "mode": "on", "back": "f=history", "bulk": "1", "confirmed": "1"},
        headers=h,
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/?f=history"
    assert "mark Read, finished 2021-05-01" in c.get("/", headers=h).text
    assert c.post("/mode", data={"ids": "old", "mode": "nonsense", "bulk": "1"}, headers=h).status_code == 400


def test_a_rows_switches_have_a_button_when_there_is_no_javascript(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin", "Origin": "https://kobo.example.org"}
    page = c.get("/", headers=h).text
    forms = re.findall(r'<form method="post" action="/(mode|state)"[^>]*>(.*?)</form>', page, re.S)
    rows = [body for action, body in forms if "bulk" not in body]
    assert len(rows) == 4 and all("<noscript><button>Set</button></noscript>" in body for body in rows)  # two books, two switches each
    # ... and the form such a button sends is taken as it is: saved, and back to the list.
    r = c.post("/mode", data={"ids": "old", "mode": "on", "back": "f=history"}, headers=h, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/?f=history")
    r = c.post("/state", data={"id": "old", "state": "finished", "date": "2021-05-02", "back": ""}, headers=h, follow_redirects=False)
    assert r.status_code == 303


def test_the_list_says_what_it_is_to_someone_who_cannot_see_it(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin"}
    page = c.get("/", headers=h).text
    assert '<h2 class="pagehead">Books</h2>' in page
    assert '<table class="books" role="table" aria-label="Books">' in page and page.count('role="columnheader"') == 4
    assert (
        page.count('<tr id="b-') == page.count('role="row"') - 1 == 2 and page.count('role="cell"') == 8
    )  # laid out as cards on a phone, a table all the same
    assert '<meta name="theme-color" content="#c3e2ef" media="(prefers-color-scheme: light)">' in page
    alone = c.get("/details/old", headers=h).text
    assert '<main class="dpage"><h1 class="sr">Kobo Hardcover Sync</h1>' in alone


def test_pages_are_compressed_and_what_does_not_change_is_kept(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    h = {"Remote-User": "robin", "Accept-Encoding": "gzip"}
    page = c.get("/", headers=h)
    assert page.headers["content-encoding"] == "gzip" and "Old Finished" in page.text
    assert "content-encoding" not in c.get("/", headers={"Remote-User": "robin", "Accept-Encoding": "identity"}).headers
    css = c.get("/static/kobo.css?v=1", headers=h)
    assert css.headers["content-encoding"] == "gzip" and css.headers["cache-control"] == "max-age=31536000, immutable"
    font = c.get("/static/fonts/SchibstedGrotesk-latin.woff2", headers=h)  # compressed already: left alone, kept a week
    assert "content-encoding" not in font.headers and font.headers["cache-control"] == "max-age=604800" and len(font.content) > 20000
    assert c.get("/static/nothing.css", headers=h).status_code == 404


def test_every_text_the_page_asks_for_exists():
    """A text that is missing only shows when its branch runs: here, a book Hardcover found nothing for."""
    import pathlib
    import re

    from kobo_hardcover_sync.web.strings import T

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "kobo_hardcover_sync"
    asked = set()
    for path in src.rglob("*.py"):
        text = path.read_text()
        # T["name"], and T["one" if ... else "other"]. A name made at run time (T["ok_" + ok]) is not looked at.
        asked |= {name for _, name in re.findall(r"""\bT\[(["'])([a-z0-9_]+)\1\]""", text)}
        for one, other in re.findall(r"""\bT\[["']([a-z0-9_]+)["'] if [^\]]*? else ["']([a-z0-9_]+)["']\]""", text):
            asked |= {one, other}
    assert len(asked) > 150 and sorted(asked - set(T)) == []
