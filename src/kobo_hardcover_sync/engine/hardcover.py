"""Hardcover (https://hardcover.app) client, matcher and sender.

API facts (docs.hardcover.app as of 2026-09-24, and the live API on
2026-10-02; see docs/hardcover-api.md):
- GraphQL at https://api.hardcover.app/v1/graphql, header `authorization`
  with the reader's token. Beta: anything can change, tokens can be reset.
- A token has an expiry date and permissions chosen by the reader. This
  tool needs SCOPES. Rate limits are per reader: 60 a minute (a burst of
  10), 5000 a day; every top-level field of a request counts as one.
- 401 token not accepted, 403 permission missing or not allowed, 429 too
  many (with Retry-After), 503 "safe to retry", 408 query took over 30 s.
- Status ids: 1 want to read, 2 currently reading, 3 read, 5 did not finish.
- Reading dates and progress live in "reads" (DatesReadInput): started_at,
  finished_at, and progress only as **progress_pages** (or seconds for
  audiobooks). The Kobo percentage is converted with the edition's pages.

Matching (tested on 128 real books: 58 by ISBN-13, 39 by title+author
search, 31 uncertain): ISBN first; else search on "title first-author" and
accept only when the normalised title and the author's last name both
agree. Everything else is left for the reader to pick on the page; it never
guesses.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from importlib import metadata

API = os.environ.get("HARDCOVER_API", "https://api.hardcover.app/v1/graphql")
MIN_INTERVAL = 1.1  # seconds between requests: stays under 60/minute
BACKOFF = (2, 5)  # seconds before the second and the third try
TRIES = len(BACKOFF) + 1  # a request is tried this often before the run gives up
MAX_WAIT = 60  # asked to wait longer than this: the day's limit is used up, stop instead
SHELF_PAGE = 250  # shelf books per request

# What a token must be allowed to do (docs.hardcover.app/api/graphql/actions):
# who am I, look up editions and search, read the shelf, change the shelf.
SCOPES = ("read:me:content", "read:catalog", "read:library", "write:library")
NEW_TOKEN_URL = "https://hardcover.app/account/api/keys/new?scope=" + "+".join(SCOPES)

STATUS_IDS = {"want": 1, "reading": 2, "read": 3, "dnf": 5}
STATUS_NAMES = {v: k for k, v in STATUS_IDS.items()}
FORMAT_EBOOK = 4
FORMATS = {1: "Physical", 2: "Audiobook", 3: "Physical + audio", 4: "Ebook"}

try:
    USER_AGENT = "kobo-hardcover-sync/" + metadata.version("kobo-hardcover-sync")
except metadata.PackageNotFoundError:  # run from a source tree that is not installed
    USER_AGENT = "kobo-hardcover-sync"


class HardcoverError(Exception):
    """Hardcover's side of a sync went wrong. The message is for the reader:
    what happened and what to do. `kind` is for the code:

      token        the token is not accepted (expired, removed, mistyped)
      scope        the token may not do this: a permission is missing
      rate         too many requests (after waiting, or the day's limit)
      unreachable  no usable answer: network, timeout, Hardcover down
      answer       an answer this code does not understand
      refused      Hardcover understood, and said no to this one request

    The first four are the same for every book, so a run stops at the first
    one instead of failing book after book."""

    def __init__(self, message: str, kind: str = "refused"):
        super().__init__(message)
        self.kind = kind

    @property
    def stops_the_run(self) -> bool:
        return self.kind in ("token", "scope", "rate", "unreachable")


NOTHING_LOST = "Nothing is lost: the next sync carries on"
log = logging.getLogger(__name__)
ASKS = re.compile(r"\{\s*(\w+)")  # the first field of a request: what it asks for


def not_understood(what: str) -> HardcoverError:
    return HardcoverError(f"Hardcover gave an answer this tool does not understand ({what}). Nothing was changed for it", "answer")


class _Again(Exception):
    """This try failed in a way another try may mend. `wait`: the seconds
    Hardcover asked for; None: the usual back-off."""

    def __init__(self, error: HardcoverError, wait: float | None = None):
        super().__init__(str(error))
        self.error, self.wait = error, wait


def bare(token: str) -> str:
    """The token as Hardcover's account page shows it, without "Bearer "."""
    tok = (token or "").strip()
    return tok[7:].strip() if tok.lower().startswith("bearer ") else tok


def _said(raw: bytes) -> dict:
    """What an error answer says: {"error", "error_description", "scope", ...}."""
    try:
        d = json.loads(raw)
    except ValueError:
        return {}
    if isinstance(d, dict) and isinstance(d.get("errors"), list) and d["errors"]:  # some refusals come as a GraphQL errors list
        first = d["errors"][0]
        return {"error": str(first.get("message", "")) if isinstance(first, dict) else str(first)}
    return d if isinstance(d, dict) else {}


class Client:
    def __init__(self, token: str, opener=None, sleep=None, tries: int = TRIES):
        """tries: 1 for a person waiting at a page, who is better served by
        an answer now than by a third attempt."""
        if not bare(token):
            raise HardcoverError("There is no Hardcover token yet: add one under Settings", "token")
        self.token = "Bearer " + bare(token)
        self._last = 0.0
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep or time.sleep
        self._backoff = BACKOFF[: max(tries, 1) - 1]
        self._me: dict | None = None

    def _exchange(self, payload: bytes) -> tuple[int, object, bytes]:
        """One request. (status, headers, body); status 0: no answer at all."""
        req = urllib.request.Request(
            API, data=payload, headers={"authorization": self.token, "Content-Type": "application/json", "User-Agent": USER_AGENT}
        )
        try:
            with self._open(req, timeout=30) as r:
                return int(getattr(r, "status", 200) or 200), getattr(r, "headers", {}), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers or {}, e.read()
        except Exception as e:  # no name, no route, refused, reset, timed out
            reason = getattr(e, "reason", None) or e
            return 0, {}, (str(reason) or e.__class__.__name__).encode()

    def _judge(self, status: int, headers, raw: bytes, write: bool) -> dict:
        """The data of a good answer. Otherwise the error: raised as it is
        when asking again is pointless or could do harm, wrapped in _Again
        when another try may mend it."""
        if status == 200:
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            if isinstance(body, dict) and body.get("errors"):
                msgs = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in body["errors"])
                raise HardcoverError(f"Hardcover refused: {msgs[:260]}")
            if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
                # Cut off on the way, or not Hardcover answering. A question can be asked again.
                error = not_understood("no data in it")
                raise error if write else _Again(error)
            return body["data"]
        said = _said(raw)
        why = str(said.get("error_description") or said.get("message") or said.get("error") or "").strip()[:200]
        if status == 401:
            raise HardcoverError(
                "Hardcover does not accept your token. It has expired, was removed or is not complete: "
                "make a new one on Hardcover and put it under Settings",
                "token",
            )
        if status == 403 and said.get("error") == "insufficient_scope":
            lacks = str(said.get("scope") or why or "a permission")[:120]
            raise HardcoverError(
                f"Your Hardcover token may not do this (it lacks: {lacks}). Make a new one with the link under Settings", "scope"
            )
        if status == 429:
            try:
                wait = float(headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                wait = 0.0
            if wait > MAX_WAIT:
                raise HardcoverError(f"Today's number of requests to Hardcover is used up. {NOTHING_LOST} tomorrow", "rate")
            # Not counted and not carried out: also a change can be sent again.
            raise _Again(HardcoverError(f"Hardcover asked to slow down, more than once. {NOTHING_LOST}", "rate"), max(wait, 0) + 1)
        if status == 503:  # documented as safe to retry, changes too
            raise _Again(HardcoverError(f"Hardcover is not available right now. {NOTHING_LOST}", "unreachable"))
        if status == 0 or status == 408 or status >= 500:
            what = raw.decode("utf-8", "replace")[:80] if status == 0 else f"error {status}"
            error = HardcoverError(f"Hardcover could not be reached ({what}). {NOTHING_LOST}", "unreachable")
            # A change may or may not have happened: it is not sent twice.
            # The next sync looks at the shelf first and carries on from there.
            raise error if write else _Again(error)
        raise HardcoverError(f"Hardcover refused: {why or ('not allowed' if status == 403 else f'error {status}')}")

    def gql(self, query: str, variables: dict | None = None, write: bool = False) -> dict:
        """write: the request changes something on Hardcover, so it is only
        sent again when Hardcover says it was not carried out."""
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        asks = m.group(1) if (m := ASKS.search(query)) else "?"
        for backoff in (*self._backoff, None):  # None: the last try
            pause = MIN_INTERVAL - (time.monotonic() - self._last)
            if pause > 0:
                self._sleep(pause)
            began = time.monotonic()
            status, headers, raw = self._exchange(payload)
            self._last = time.monotonic()
            # What was asked and how it went; never what was sent with it.
            log.debug("hardcover %s: %s in %.1fs", asks, status or "no answer", self._last - began)
            try:
                return self._judge(status, headers, raw, write)
            except _Again as again:
                if backoff is None:
                    raise again.error from None
                self._sleep(backoff if again.wait is None else again.wait)

    # --- lookups -------------------------------------------------------
    def whoami(self) -> dict:
        """The account the token belongs to: {"id", "username"}."""
        if self._me is None:
            me = _rows(self.gql("{ me { id username } }"), "me")
            if not me or not isinstance(me[0].get("id"), int):
                raise not_understood("it does not say whose token this is")
            self._me = me[0]
        return self._me

    def editions_by_isbn(self, isbns: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(isbns), 100):
            d = self.gql(
                "query($i:[String!]){ editions(where:{isbn_13:{_in:$i}}){ id book_id isbn_13 pages title } }", {"i": isbns[i : i + 100]}
            )
            for e in _rows(d, "editions"):
                out.setdefault(e["isbn_13"], e)
        return out

    def search(self, text: str, n: int = 3) -> list[dict]:
        d = self.gql('query($q:String!,$n:Int!){ search(query:$q, query_type:"Book", per_page:$n){ results } }', {"q": text, "n": n})
        results = (d.get("search") or {}).get("results") or {}
        hits = results.get("hits", []) if isinstance(results, dict) else []
        return [
            {
                "book_id": int(h["document"]["id"]),
                "title": h["document"].get("title", ""),
                "authors": h["document"].get("author_names", []),
                "pages": h["document"].get("pages"),
                "slug": h["document"].get("slug", ""),
            }
            for h in hits
            if isinstance(h, dict) and isinstance(h.get("document"), dict) and str(h["document"].get("id", "")).isdigit()
        ]

    def shelf(self) -> list[dict]:
        """The reader's whole shelf: status, edition (with format and page
        count) and read entries (oldest first) per book.

        Asked for in pages, and counted: Hardcover says how many books the
        shelf has, and fewer than that is an error, never a shorter shelf.
        A book missing from this list is taken for removed by the reader
        (syncback), so a list that is cut off must not get through."""
        me = self.whoami()["id"]
        fields = (
            "id book_id status_id edition_id edition { id pages reading_format_id edition_format isbn_13 }"
            " user_book_reads(order_by:{id:asc}) { id started_at finished_at progress_pages edition_id }"
        )
        page = "user_books(where:{user_id:{_eq:$u}}, order_by:{id:asc}, limit:$n, offset:$o){ " + fields + " }"
        d = self.gql(
            "query($u:Int!,$n:Int!,$o:Int!){ user_books_aggregate(where:{user_id:{_eq:$u}}){ aggregate { count } } " + page + " }",
            {"u": me, "n": SHELF_PAGE, "o": 0},
        )
        total = ((d.get("user_books_aggregate") or {}).get("aggregate") or {}).get("count")
        if not isinstance(total, int):
            raise not_understood("it does not say how many books the shelf has")
        got = _shelf_rows(d)
        books = {u["id"]: u for u in got}
        while got and len(books) < total:
            got = _shelf_rows(self.gql("query($u:Int!,$n:Int!,$o:Int!){ " + page + " }", {"u": me, "n": SHELF_PAGE, "o": len(books)}))
            books.update((u["id"], u) for u in got)
        if len(books) < total:
            raise not_understood(f"{len(books)} of the {total} books on the shelf")
        return list(books.values())

    def editions_for_books(self, book_ids: list[int], isbns: list[str]) -> dict[int, list[dict]]:
        """Per book: its editions that carry one of `isbns` or are ebooks
        (the only ones the edition rule can choose)."""
        out: dict[int, list[dict]] = {}
        for i in range(0, len(book_ids), 50):
            d = self.gql(
                "query($i:[Int!],$n:[String!]){ editions(where:{book_id:{_in:$i},"
                " _or:[{isbn_13:{_in:$n}},{reading_format_id:{_eq:4}}]}){ id book_id isbn_13 pages"
                " reading_format_id edition_format users_count language { code2 } } }",
                {"i": book_ids[i : i + 50], "n": isbns},
            )
            for e in _rows(d, "editions"):
                out.setdefault(e["book_id"], []).append(e)
        return out

    def reads(self, ub_id: int) -> list[dict]:
        """The read entries of one shelf book, oldest first."""
        d = self.gql(
            "query($i:Int!){ user_book_reads(where:{user_book_id:{_eq:$i}}, order_by:{id:asc})"
            "{ id started_at finished_at progress_pages edition_id } }",
            {"i": ub_id},
        )
        return _rows(d, "user_book_reads")

    # --- writes --------------------------------------------------------
    def _change(self, name: str, query: str, variables: dict, need_id: bool = False) -> dict:
        r = self.gql(query, variables, write=True).get(name)
        if not isinstance(r, dict):
            raise not_understood(f"no {name} in it")
        if r.get("error") or (need_id and not r.get("id")):
            raise HardcoverError(f"Hardcover refused: {str(r.get('error') or 'no id came back')[:260]}")
        return r

    def insert_user_book(self, obj: dict) -> int:
        return self._change(
            "insert_user_book", "mutation($o:UserBookCreateInput!){ insert_user_book(object:$o){ id error } }", {"o": obj}, need_id=True
        )["id"]

    def update_user_book(self, ub_id: int, obj: dict) -> None:
        self._change(
            "update_user_book",
            "mutation($id:Int!,$o:UserBookUpdateInput!){ update_user_book(id:$id, object:$o){ id error } }",
            {"id": ub_id, "o": obj},
        )

    def insert_read(self, ub_id: int, read: dict) -> int:
        return self._change(
            "insert_user_book_read",
            "mutation($id:Int!,$r:DatesReadInput!){ insert_user_book_read(user_book_id:$id, user_book_read:$r){ id error } }",
            {"id": ub_id, "r": read},
            need_id=True,
        )["id"]

    def update_read(self, read_id: int, read: dict) -> None:
        self._change(
            "update_user_book_read",
            "mutation($id:Int!,$r:DatesReadInput!){ update_user_book_read(id:$id, object:$r){ id error } }",
            {"id": read_id, "r": read},
        )

    def delete_user_book(self, ub_id: int) -> None:
        self.gql("mutation($id:Int!){ delete_user_book(id:$id){ id } }", {"id": ub_id}, write=True)


def _rows(data: dict, name: str) -> list[dict]:
    rows = data.get(name)
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise not_understood(f"no list of {name} in it")
    return rows


def _shelf_rows(data: dict) -> list[dict]:
    rows = _rows(data, "user_books")
    for u in rows:
        if not isinstance(u.get("id"), int) or not isinstance(u.get("book_id"), int) or not isinstance(u.get("user_book_reads"), list):
            raise not_understood("a shelf book without its id or its read-throughs")
    return rows


# --- matching -----------------------------------------------------------
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def first_author(attribution: str) -> str:
    return (attribution or "").split(",")[0].strip()


def confident(title: str, author: str, cand: dict) -> bool:
    t, ct = norm(title), norm(cand["title"])
    t_ok = bool(t and ct) and (t == ct or t.startswith(ct) or ct.startswith(t))
    last = norm(author).split()[-1:] if author else []
    a_ok = bool(last) and any(norm(a).split()[-1:] == last for a in cand["authors"])
    return t_ok and a_ok


def match_books(client: Client, rows) -> dict[str, dict]:
    """rows: state rows without a match. Returns content_id -> match dict:
    {how: isbn|search|uncertain|none, book_id, edition_id, pages, title, candidates}."""
    rows = list(rows)
    out: dict[str, dict] = {}
    by_isbn = client.editions_by_isbn(sorted({r["isbn"] for r in rows if r["isbn"]}))
    for r in rows:
        e = by_isbn.get(r["isbn"])
        if e:
            out[r["content_id"]] = {
                "how": "isbn",
                "book_id": e["book_id"],
                "edition_id": e["id"],
                "pages": e["pages"],
                "title": e["title"],
                "candidates": [],
            }
            continue
        author = first_author(r["author"])
        cands = client.search(f"{r['title']} {author}")
        if cands and confident(r["title"], author, cands[0]):
            c = cands[0]
            out[r["content_id"]] = {
                "how": "search",
                "book_id": c["book_id"],
                "edition_id": None,
                "pages": c["pages"],
                "title": c["title"],
                "candidates": [],
            }
        else:
            out[r["content_id"]] = {
                "how": "uncertain" if cands else "none",
                "book_id": None,
                "edition_id": None,
                "pages": None,
                "title": None,
                "candidates": cands,
            }
    return out


# --- editions -----------------------------------------------------------
def format_name(reading_format_id, edition_format="") -> str:
    """'Ebook', 'Physical (Paperback)', ... for display."""
    base = FORMATS.get(reading_format_id, "")
    extra = (edition_format or "").strip()
    if base and extra and extra.lower() not in (base.lower(), "ebook"):
        return f"{base} ({extra})"
    return base or extra


def choose_edition(isbn: str, language: str, editions: list[dict]) -> dict | None:
    """kobo-hardcover-sync's own choice (an ebook edition in any language beats
    a physical one: it is the form that was read), best first:
    1. the edition with the Kobo's ISBN, if marked Ebook;
    2. an Ebook edition in the book's language (most readers first);
    3. any Ebook edition (most readers first);
    4. the edition with the Kobo's ISBN, whatever its label;
    5. none: Hardcover's default stays.
    An edition chosen on Hardcover by the reader never comes through here."""
    by_isbn = [e for e in editions if isbn and e.get("isbn_13") == isbn]

    def ebook(e):
        return e.get("reading_format_id") == FORMAT_EBOOK

    for e in by_isbn:
        if ebook(e):
            return e

    def popular(e):
        return (bool(e.get("pages")), e.get("users_count") or 0)

    ebooks = [e for e in editions if ebook(e)]
    same_lang = [e for e in ebooks if language and ((e.get("language") or {}).get("code2") or "") == language]
    if same_lang:
        return max(same_lang, key=popular)
    if ebooks:
        return max(ebooks, key=popular)
    return by_isbn[0] if by_isbn else None


# --- sending ------------------------------------------------------------
def pages_for(percent: int, pages) -> int | None:
    if not pages:
        return None
    return max(0, min(int(pages), round(int(percent or 0) / 100 * int(pages))))


def apply(client: Client, row, want: dict, sent: dict, existing: dict | None) -> dict:
    """Bring Hardcover to `want` for one book. Returns the new last_sent
    (hardcover ids, and "hc": Hardcover's state as left behind, the baseline
    the next two-way sync compares against). `existing`: the reader's shelf
    entry for this book, if any, so a book already there is updated."""
    ub_id = sent.get("user_book_id") or (existing or {}).get("id")
    read_id = sent.get("read_id")
    was_on_shelf = bool(ub_id)
    status = STATUS_IDS[want["status"]]
    edition = row["hc_edition_id"]
    shelf_edition = sent.get("edition_id") or (existing or {}).get("edition_id")
    new = dict(sent)
    if not ub_id:
        obj = {"book_id": row["hc_book_id"], "status_id": status}
        if edition:
            obj["edition_id"] = edition
        ub_id = client.insert_user_book(obj)
        read_id = None
    else:
        change = {}
        if sent.get("status") != want["status"] or (existing and existing.get("status_id") != status):
            change["status_id"] = status
        if edition and shelf_edition != edition:
            change["edition_id"] = edition
        if change:
            client.update_user_book(ub_id, change)
    read = {}
    if want["status"] in ("read", "reading"):
        if edition:
            read["edition_id"] = edition
        if want["status"] == "read":
            if want.get("finished"):
                read["finished_at"] = want["finished"]
        else:
            if want.get("started"):
                read["started_at"] = want["started"]
            p = pages_for(want.get("progress", 0), row["hc_pages"])
            if p is not None:
                read["progress_pages"] = p
        if want.get("reread") and not sent.get("reread") and was_on_shelf:
            read_id = None  # a re-read of a book already on the shelf is a new read-through
        elif read and not read_id:
            # Hardcover creates a read entry by itself when a book lands on the
            # shelf (dated that day). Use that one; inserting another made every
            # book count as read twice (found 2026-09-30: 95 duplicates).
            have = client.reads(ub_id)
            if have:
                read_id = have[-1]["id"]
        if read:
            if read_id:
                client.update_read(read_id, read)
            else:
                read_id = client.insert_read(ub_id, read)
    final_edition = edition or shelf_edition
    new.update(
        {
            "status": want["status"],
            "user_book_id": ub_id,
            "read_id": read_id,
            "progress": want.get("progress"),
            "finished": want.get("finished"),
            "reread": bool(want.get("reread")),
            "edition_id": final_edition,
            "hc": {
                "status_id": status,
                "edition_id": final_edition,
                "finished_at": read.get("finished_at"),
                "started_at": read.get("started_at"),
            },
        }
    )
    return new
