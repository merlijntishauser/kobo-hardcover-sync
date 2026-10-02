import copy
import json

from kobo_hardcover_sync.engine import hardcover, job, kobo_db, state
from kobo_hardcover_sync.engine.plan import action
from tests.test_core import OLD, make_kobo


class FakeHC:
    """A small in-memory Hardcover: a shelf that behaves like the real one
    (a new shelf book gets a read entry by itself), plus a catalogue."""

    def __init__(self, isbn=None, search=None, catalog=None):
        self.isbn, self.search_res, self.catalog = isbn or {}, search or {}, catalog or {}
        self.calls, self.next_id, self.books = [], 100, {}

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _edition(self, eid):
        for eds in self.catalog.values():
            for e in eds:
                if e["id"] == eid:
                    return {
                        "id": eid,
                        "pages": e.get("pages"),
                        "reading_format_id": e.get("reading_format_id"),
                        "edition_format": e.get("edition_format"),
                        "isbn_13": e.get("isbn_13"),
                    }
        return {"id": eid, "pages": None, "reading_format_id": None, "edition_format": None, "isbn_13": None} if eid else None

    # lookups
    def editions_by_isbn(self, isbns):
        return {i: self.isbn[i] for i in isbns if i in self.isbn}

    def search(self, text, n=3):
        return self.search_res.get(text.split(" ")[0], [])

    def shelf(self):
        out = copy.deepcopy(list(self.books.values()))
        for u in out:
            u["edition"] = self._edition(u["edition_id"])
        return out

    def editions_for_books(self, book_ids, isbns):
        return {b: self.catalog[b] for b in book_ids if b in self.catalog}

    def reads(self, ub_id):
        return copy.deepcopy(self.books[ub_id]["user_book_reads"])

    # writes
    def insert_user_book(self, obj):
        self.calls.append(("insert_ub", obj))
        ub = self._id()
        self.books[ub] = {
            "id": ub,
            "book_id": obj["book_id"],
            "status_id": obj["status_id"],
            "edition_id": obj.get("edition_id"),
            "user_book_reads": [
                {
                    "id": self._id(),
                    "started_at": None,
                    "progress_pages": None,
                    "edition_id": None,
                    "finished_at": "2026-09-30" if obj["status_id"] == 3 else None,
                }
            ],
        }
        return ub

    def update_user_book(self, i, obj):
        self.calls.append(("update_ub", i, obj))
        self.books[i].update(obj)

    def insert_read(self, ub, r):
        self.calls.append(("insert_read", ub, r))
        rid = self._id()
        self.books[ub]["user_book_reads"].append({"id": rid, "started_at": None, "finished_at": None, "progress_pages": None, **r})
        return rid

    def update_read(self, i, r):
        self.calls.append(("update_read", i, r))
        for u in self.books.values():
            for x in u["user_book_reads"]:
                if x["id"] == i:
                    x.update(r)

    def delete_user_book(self, i):
        self.calls.append(("delete_ub", i))
        self.books.pop(i, None)

    # what the reader does on hardcover.app
    def reader_sets(self, ub, **kw):
        read = kw.pop("read", None)
        self.books[ub].update(kw)
        if read:
            self.books[ub]["user_book_reads"][-1].update(read)


def test_pages_from_a_percentage():
    assert hardcover.pages_for(46, 300) == 138 and hardcover.pages_for(10, None) is None


def setup(tmp_path, books):
    tmp_path.mkdir(exist_ok=True)
    k = tmp_path / "k.sqlite"
    make_kobo(k, books, [])
    st = state.connect(str(tmp_path / "state.db"))
    state.import_books(st, "alice", "kobo1", kobo_db.read_books(kobo_db.open_db(str(k))))
    state.set_mode(st, "alice", [b[0] for b in books], "on")
    return st


def run(tmp_path, fake, live=True):
    return job.run(str(tmp_path / "state.db"), "alice", live=live, client=fake)


def row(st, cid):
    return st.execute("select * from book where content_id=?", (cid,)).fetchone()


def sent(st, cid):
    return json.loads(row(st, cid)["last_sent"])


READING = ("rd", "Blindness", "José Saramago", "978000", 46, 1, "2026-09-29T10:00:00Z", 900)
TRANSL = ("tr", "De strijd der koningen", "George R.R. Martin", "978111", 10, 1, "2026-09-29T10:00:00Z", 900)
OLD_ED = {"111": {"id": 7, "book_id": 70, "isbn_13": "111", "pages": 400, "title": "Old Finished"}}
BLIND = {"Blindness": [{"book_id": 80, "title": "Blindness", "authors": ["Jose Saramago"], "pages": 300, "slug": "b"}]}


def test_dry_run_matches_but_writes_nothing(tmp_path):
    st = setup(tmp_path, [OLD, READING, TRANSL])
    fake = FakeHC(
        isbn=OLD_ED,
        search={
            **BLIND,
            "De": [{"book_id": 90, "title": "A Clash of Kings", "authors": ["George R.R. Martin"], "pages": 700, "slug": "c"}],
        },
    )
    r = run(tmp_path, fake, live=False)
    assert r["status"] == "ok" and r["matched"] == 2 and r["uncertain"] == 1 and r["planned"] == 2
    assert fake.calls == []
    tr = row(st, "tr")
    assert tr["hc_how"] == "uncertain" and json.loads(tr["hc_candidates"])[0]["book_id"] == 90


def test_live_sends_one_read_entry_per_book_and_is_idempotent(tmp_path):
    st = setup(tmp_path, [OLD, READING])
    fake = FakeHC(isbn=OLD_ED, search=BLIND)
    r = run(tmp_path, fake)
    assert r["sent"] == 2 and r["errors"] == 0
    kinds = [c[0] for c in fake.calls]
    # The read entry Hardcover made itself is updated; none is added.
    assert kinds.count("insert_ub") == 2 and kinds.count("update_read") == 2 and "insert_read" not in kinds
    assert all(len(u["user_book_reads"]) == 1 for u in fake.books.values())
    old_read = [c for c in fake.calls if c[0] == "update_read" and c[2].get("finished_at")][0]
    assert old_read[2] == {"edition_id": 7, "finished_at": "2021-05-01"}
    rd_read = [c for c in fake.calls if c[0] == "update_read" and "progress_pages" in c[2]][0]
    assert rd_read[2]["progress_pages"] == 138  # 46% of 300 pages
    fake.calls.clear()
    r2 = run(tmp_path, fake)
    assert r2["sent"] == 0 and r2["adopted"] == 0 and fake.calls == []
    st.execute("update book set percent=60 where content_id='rd'")
    st.commit()
    run(tmp_path, fake)
    assert [c[0] for c in fake.calls] == ["update_read"] and fake.calls[0][2]["progress_pages"] == 180


def test_remove_deletes_and_switches_off(tmp_path):
    st = setup(tmp_path, [OLD])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    ub = sent(st, "old")["user_book_id"]
    job.remove(st, "alice", "old", fake)
    assert fake.calls[-1] == ("delete_ub", ub)
    r = row(st, "old")
    assert r["mode"] == "off" and r["last_sent"] is None


def test_reread_of_a_shelf_book_adds_a_read_but_a_new_book_never_gets_two(tmp_path):
    st = setup(tmp_path, [OLD])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    fake.calls.clear()
    state.set_state(st, "alice", "old", "rereading", "2026-10-01")
    run(tmp_path, fake)
    assert [c[0] for c in fake.calls] == ["update_ub", "insert_read"]  # a second read-through, on purpose
    st2 = setup(tmp_path / "b", [READING])
    fake2 = FakeHC(search=BLIND)
    state.set_state(st2, "alice", "rd", "rereading", "2026-10-01")
    run(tmp_path / "b", fake2)
    assert [c[0] for c in fake2.calls] == ["insert_ub", "update_read"]


# ---------- Hardcover -> kobo-hardcover-sync ----------
def test_read_on_hardcover_becomes_a_pinned_finished_state(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    run(tmp_path, fake)
    ub = sent(st, "rd")["user_book_id"]
    fake.reader_sets(ub, status_id=3, read={"finished_at": "2026-10-02"})
    fake.calls.clear()
    r = run(tmp_path, fake)
    got = row(st, "rd")
    assert r["adopted"] == 1 and got["state"] == "finished" and got["state_date"] == "2026-10-02"
    assert fake.calls == [] and action(got) == ""  # nothing is sent back
    # Later Kobo progress does not undo it.
    st.execute("update book set percent=80 where content_id='rd'")
    st.commit()
    assert run(tmp_path, fake)["sent"] == 0 and fake.books[ub]["status_id"] == 3


def test_want_to_read_and_dnf_are_left_alone_until_follow_kobo(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    run(tmp_path, fake)
    ub = sent(st, "rd")["user_book_id"]
    fake.reader_sets(ub, status_id=5)
    run(tmp_path, fake)
    assert row(st, "rd")["state"] == "dnf"
    st.execute("update book set percent=70 where content_id='rd'")
    st.commit()
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == [] and fake.books[ub]["status_id"] == 5
    fake.reader_sets(ub, status_id=1)
    run(tmp_path, fake)
    assert row(st, "rd")["state"] == "want"
    # Back to Follow Kobo on the page: the Kobo's state goes out again.
    state.set_state(st, "alice", "rd", "kobo")
    run(tmp_path, fake)
    assert fake.books[ub]["status_id"] == 2 and fake.books[ub]["user_book_reads"][-1]["progress_pages"] == 210


def test_finished_book_set_to_reading_on_hardcover_is_a_reread(tmp_path):
    st = setup(tmp_path, [OLD])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    ub = sent(st, "old")["user_book_id"]
    fake.reader_sets(ub, status_id=2, read={"started_at": "2026-10-03"})
    run(tmp_path, fake)
    got = row(st, "old")
    assert got["state"] == "rereading" and got["state_date"] == "2026-10-03" and fake.books[ub]["status_id"] == 2


def test_removed_on_hardcover_switches_sync_off_and_is_not_added_again(tmp_path):
    st = setup(tmp_path, [OLD])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    fake.books.clear()
    fake.calls.clear()
    r = run(tmp_path, fake)
    got = row(st, "old")
    assert r["removed"] == 1 and got["mode"] == "off" and got["last_sent"] is None and got["hc_book_id"] == 70
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == [] and fake.books == {}


def test_state_set_on_the_page_wins_over_an_edit_on_hardcover(tmp_path):
    st = setup(tmp_path, [READING])
    fake = FakeHC(search=BLIND)
    run(tmp_path, fake)
    ub = sent(st, "rd")["user_book_id"]
    fake.reader_sets(ub, status_id=5)  # Did not finish, on Hardcover
    state.set_state(st, "alice", "rd", "finished", "2026-10-05")  # ... and Finished on the page, later
    st.execute("update book set state_changed='2099-01-01T00:00:00Z' where content_id='rd'")
    st.commit()
    run(tmp_path, fake)
    assert row(st, "rd")["state"] == "finished" and fake.books[ub]["status_id"] == 3
    assert fake.books[ub]["user_book_reads"][-1]["finished_at"] == "2026-10-05"


def test_changed_finish_date_on_the_page_is_sent(tmp_path):
    st = setup(tmp_path, [OLD])
    fake = FakeHC(isbn=OLD_ED)
    run(tmp_path, fake)
    state.set_state(st, "alice", "old", "finished", "2022-02-02")
    assert action(row(st, "old")) == "set the finish date to 2022-02-02"
    run(tmp_path, fake)
    assert list(fake.books.values())[0]["user_book_reads"][0]["finished_at"] == "2022-02-02"


# ---------- editions ----------
E_ISBN_EBOOK = {
    "id": 1,
    "isbn_13": "978000",
    "reading_format_id": 4,
    "edition_format": "ebook",
    "pages": 310,
    "users_count": 1,
    "language": {"code2": "nl"},
}
E_ISBN_PAPER = {
    "id": 2,
    "isbn_13": "978000",
    "reading_format_id": 1,
    "edition_format": "Paperback",
    "pages": 320,
    "users_count": 9,
    "language": {"code2": "nl"},
}
E_NL_EBOOK = {
    "id": 3,
    "isbn_13": "999",
    "reading_format_id": 4,
    "edition_format": "",
    "pages": 300,
    "users_count": 2,
    "language": {"code2": "nl"},
}
E_NL_EBOOK_POPULAR = {
    "id": 4,
    "isbn_13": "998",
    "reading_format_id": 4,
    "edition_format": "",
    "pages": 301,
    "users_count": 50,
    "language": {"code2": "nl"},
}
E_EN_EBOOK = {
    "id": 5,
    "isbn_13": "997",
    "reading_format_id": 4,
    "edition_format": "Kindle Edition",
    "pages": 290,
    "users_count": 900,
    "language": {"code2": "en"},
}


def test_edition_choice_order():
    def pick(eds):
        return (hardcover.choose_edition("978000", "nl", eds) or {}).get("id")

    assert pick([E_ISBN_PAPER, E_NL_EBOOK, E_ISBN_EBOOK, E_EN_EBOOK]) == 1  # Kobo's ISBN, marked Ebook
    assert pick([E_ISBN_PAPER, E_NL_EBOOK, E_NL_EBOOK_POPULAR, E_EN_EBOOK]) == 4  # ebook in the book's language, most readers
    assert pick([E_ISBN_PAPER, E_EN_EBOOK]) == 5  # any ebook beats a physical edition
    assert pick([E_EN_EBOOK]) == 5
    assert pick([E_ISBN_PAPER]) == 2  # Kobo's ISBN, whatever its label
    assert pick([]) is None
    assert hardcover.format_name(4, "ebook") == "Ebook" and hardcover.format_name(1, "Paperback") == "Physical (Paperback)"
    assert hardcover.format_name(4, "Kindle Edition") == "Ebook (Kindle Edition)" and hardcover.format_name(None, "") == ""


def test_ebook_edition_is_chosen_and_set_on_the_shelf(tmp_path):
    st = setup(tmp_path, [READING])
    st.execute("update book set language='nl' where content_id='rd'")
    st.commit()
    fake = FakeHC(search=BLIND, catalog={80: [E_ISBN_PAPER, E_NL_EBOOK]})
    r = run(tmp_path, fake)
    got = row(st, "rd")
    assert r["editions"] == 1 and got["hc_edition_id"] == 3 and got["hc_edition_by"] == "auto" and got["hc_format"] == "Ebook"
    ub = sent(st, "rd")["user_book_id"]
    assert fake.books[ub]["edition_id"] == 3 and fake.books[ub]["user_book_reads"][0]["progress_pages"] == 138
    fake.calls.clear()
    assert run(tmp_path, fake)["sent"] == 0 and fake.calls == []  # chosen once, not re-sent


def test_existing_shelf_edition_is_a_baseline_then_replaced_by_the_rule(tmp_path):
    """The first two-way sync: the edition on the shelf is kobo-hardcover-sync's or
    Hardcover's default, not the reader's choice, so the rule may replace it."""
    st = setup(tmp_path, [READING])
    st.execute("update book set language='nl' where content_id='rd'")
    st.commit()
    fake = FakeHC(search=BLIND, catalog={80: [E_ISBN_PAPER]})
    run(tmp_path, fake)  # sent with the paperback ISBN edition
    ub = sent(st, "rd")["user_book_id"]
    s = sent(st, "rd")
    s.pop("hc")
    s.pop("edition_id")
    s.pop("at")  # as written before two-way sync existed
    st.execute("update book set last_sent=?, hc_edition_by=null, hc_edition_checked=null where content_id='rd'", (json.dumps(s),))
    st.commit()
    fake.catalog[80].append(E_NL_EBOOK)
    run(tmp_path, fake)
    assert row(st, "rd")["hc_edition_by"] == "auto" and fake.books[ub]["edition_id"] == 3


def test_edition_chosen_on_hardcover_is_adopted_and_never_overwritten(tmp_path):
    st = setup(tmp_path, [READING])
    st.execute("update book set language='nl' where content_id='rd'")
    st.commit()
    fake = FakeHC(search=BLIND, catalog={80: [E_NL_EBOOK, E_NL_EBOOK_POPULAR, E_EN_EBOOK]})
    run(tmp_path, fake)
    ub = sent(st, "rd")["user_book_id"]
    assert fake.books[ub]["edition_id"] == 4
    fake.reader_sets(ub, edition_id=5)  # the reader prefers the English ebook
    r = run(tmp_path, fake)
    got = row(st, "rd")
    assert r["adopted"] == 1 and got["hc_edition_id"] == 5 and got["hc_edition_by"] == "hardcover" and got["hc_pages"] == 290
    st.execute("update book set percent=50, hc_edition_checked=null where content_id='rd'")
    st.commit()
    run(tmp_path, fake)
    assert fake.books[ub]["edition_id"] == 5 and fake.books[ub]["user_book_reads"][0]["progress_pages"] == 145  # 50% of 290
