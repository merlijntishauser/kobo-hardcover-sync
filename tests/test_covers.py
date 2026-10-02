import os
import time

from kobo_hardcover_sync.engine import kobo_db, state
from kobo_hardcover_sync.web import covers
from tests.test_core import make_kobo
from tests.test_web import client


def test_cover_is_fetched_once_and_cached(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(covers, "download", lambda i, size="thumb": calls.append(i) or b"\xff\xd8jpeg")
    p = covers.cover_path(str(tmp_path), "abc-123")
    assert p and open(p, "rb").read() == b"\xff\xd8jpeg"
    assert covers.cover_path(str(tmp_path), "abc-123") == p and calls == ["abc-123"]


def test_missing_cover_is_remembered_and_retried_after_a_week(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(covers, "download", lambda i, size="thumb": calls.append(i))  # returns None
    assert covers.cover_path(str(tmp_path), "gone") is None
    assert covers.cover_path(str(tmp_path), "gone") is None and len(calls) == 1
    marker = tmp_path / "covers" / "gone.none"
    old = time.time() - 8 * 86400
    os.utime(marker, (old, old))
    covers.cover_path(str(tmp_path), "gone")
    assert len(calls) == 2


def test_bad_image_ids_never_reach_the_network_or_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(covers, "download", lambda i, size="thumb": (_ for _ in ()).throw(AssertionError("fetched " + i)))
    for bad in ("", "../etc/passwd", "a/b", "x" * 81, "id?x=1", "http://evil"):
        assert covers.cover_path(str(tmp_path), bad) is None


def test_parser_reads_image_id_when_present(tmp_path):
    k = tmp_path / "k.sqlite"
    make_kobo(k, [("a", "T", "A", "1", 1, 1, "2026-01-01T00:00:00Z", 60)], [])
    assert kobo_db.read_books(kobo_db.open_db(str(k)))[0].image_id == ""  # old fixture has no ImageId column
    import sqlite3

    c = sqlite3.connect(k)
    c.execute("alter table content add column ImageId text")
    c.execute("update content set ImageId='img-1'")
    c.commit()
    assert kobo_db.read_books(kobo_db.open_db(str(k)))[0].image_id == "img-1"


def test_cover_route_serves_own_books_only(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    monkeypatch.setattr(covers, "download", lambda i, size="thumb": b"\xff\xd8" + size.encode())
    st = state.connect(str(tmp_path / "state.db"))
    st.execute("update book set image_id='img-mine' where content_id='mine'")
    st.execute(
        "insert into book (reader, device, content_id, title, history, mode, state, image_id) values ('other','k2','theirs','X',1,'on','kobo','img-theirs')"
    )
    st.commit()
    h = {"Remote-User": "robin"}
    r = c.get("/cover/mine", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and "max-age" in r.headers["cache-control"]
    assert c.get("/cover/old", headers=h).status_code == 404  # book without an image id
    assert c.get("/cover/theirs", headers=h).status_code == 404  # another reader's book
    assert c.get("/cover/mine", headers={"Remote-User": "stranger"}).status_code == 403
    page = c.get("/", headers=h).text
    assert '<img class="cover" src="/cover/mine"' in page and '<span class="cover"></span>' in page
    assert 'href="/cover/mine?size=large"' in page and '<dialog id="lightbox"' in page
    # The large version is its own cached file; an unknown size is no cover.
    assert c.get("/cover/mine?size=large", headers=h).content == b"\xff\xd8large"
    assert r.content == b"\xff\xd8thumb"
    assert sorted(f.name for f in (tmp_path / "covers").iterdir()) == ["img-mine.jpg", "img-mine.large.jpg"]
    assert c.get("/cover/mine?size=huge", headers=h).status_code == 404


def test_cdn_url_per_size():
    assert covers.CDN.format(id="x", size=covers.SIZES["thumb"]).endswith("/x/240/360/85/False/image.jpg")
    assert covers.CDN.format(id="x", size=covers.SIZES["large"]).endswith("/x/1200/1800/90/False/image.jpg")
