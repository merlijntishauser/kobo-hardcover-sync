"""The Hardcover client against a made-up Hardcover: what it does with a
refused token, too many requests, a server in trouble, no answer at all, an
answer that is cut off, and a shelf that does not fit in one page."""

import io
import json
import urllib.error

import pytest

from kobo_hardcover_sync.engine import hardcover

TOKEN = "hc_pat_made_up_for_the_tests"


class Answer:
    def __init__(self, body, status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def refusal(status, body=None, headers=None):
    return urllib.error.HTTPError(hardcover.API, status, "", headers or {}, io.BytesIO(json.dumps(body or {}).encode()))


class Line:
    """What Hardcover answers, in order. An exception is raised, anything
    else is the answer; a function is called with the request's variables."""

    def __init__(self, *answers):
        self.answers, self.requests, self.slept = list(answers), [], []

    def __call__(self, req, timeout=None):
        sent = json.loads(req.data)
        self.requests.append(
            {"query": sent["query"], "variables": sent["variables"], "headers": dict(req.header_items()), "timeout": timeout}
        )
        a = self.answers.pop(0)
        if callable(a):
            a = a(sent["variables"])
        if isinstance(a, BaseException):
            raise a
        return a if isinstance(a, Answer) else Answer(a)

    def client(self):
        c = hardcover.Client(TOKEN, opener=self, sleep=self.slept.append)
        c._last = -1e9  # no pause before the first request
        return c


ME = {"data": {"me": [{"id": 7, "username": "sam"}]}}
ADDED = {"data": {"insert_user_book": {"id": 501, "error": None}}}
THROTTLED = {"error": "Too Many Requests", "message": "slow down"}


def waits(line):
    """The pauses that were asked for, without the ordinary one between requests."""
    return [s for s in line.slept if s > hardcover.MIN_INTERVAL]


def test_every_request_says_who_asks_and_never_waits_for_ever():
    line = Line(ME)
    assert line.client().whoami() == {"id": 7, "username": "sam"}
    h = {k.lower(): v for k, v in line.requests[0]["headers"].items()}
    assert (
        h["authorization"] == "Bearer " + TOKEN and h["user-agent"].startswith("kobo-hardcover-sync") and line.requests[0]["timeout"] == 30
    )
    assert hardcover.Client("Bearer  " + TOKEN + " ").token == "Bearer " + TOKEN
    with pytest.raises(hardcover.HardcoverError) as ex:
        hardcover.Client("  ")
    assert ex.value.kind == "token"


def test_a_token_hardcover_does_not_accept_is_said_once_and_not_tried_again():
    line = Line(refusal(401, {"error": "invalid_token", "error_description": "Token is not associated with a user"}))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert ex.value.kind == "token" and ex.value.stops_the_run and len(line.requests) == 1 and waits(line) == []
    assert "does not accept your token" in str(ex.value) and "make a new one" in str(ex.value) and TOKEN not in str(ex.value)


def test_a_token_without_the_permission_names_what_is_missing():
    line = Line(refusal(403, {"error": "insufficient_scope", "error_description": "Missing scope", "scope": "write:library"}))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().insert_user_book({"book_id": 1, "status_id": 2})
    assert ex.value.kind == "scope" and ex.value.stops_the_run and "write:library" in str(ex.value) and len(line.requests) == 1
    line = Line(refusal(403, {"error": "unsupported_operation", "error_description": "Not available to API tokens: nope"}))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert ex.value.kind == "refused" and "Not available to API tokens" in str(ex.value) and len(line.requests) == 1
    for scope in hardcover.SCOPES:
        assert scope in hardcover.NEW_TOKEN_URL  # the link under Settings asks for exactly what is used


def test_asked_to_slow_down_it_waits_as_long_as_asked_and_tries_again():
    line = Line(refusal(429, THROTTLED, {"Retry-After": "7"}), ME)
    assert line.client().whoami()["username"] == "sam" and waits(line) == [8]
    # A change that was turned away for this was not carried out: it is sent again.
    line = Line(refusal(429, THROTTLED, {"Retry-After": "2"}), ADDED)
    assert line.client().insert_user_book({"book_id": 1, "status_id": 2}) == 501 and len(line.requests) == 2
    # It does not go on for ever.
    line = Line(*[refusal(429, THROTTLED, {"Retry-After": "1"})] * 3)
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert ex.value.kind == "rate" and len(line.requests) == hardcover.TRIES and "slow down" in str(ex.value)


def test_when_the_days_requests_are_used_up_it_stops_instead_of_waiting_for_hours():
    line = Line(refusal(429, THROTTLED, {"Retry-After": "51234"}))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert ex.value.kind == "rate" and ex.value.stops_the_run and len(line.requests) == 1 and waits(line) == []
    assert "Today's number of requests" in str(ex.value)


def test_a_question_is_asked_again_when_hardcover_is_in_trouble():
    line = Line(refusal(502), refusal(500, {"error": "An unknown error occurred"}), ME)
    assert line.client().whoami()["id"] == 7 and waits(line) == list(hardcover.BACKOFF)
    line = Line(refusal(500), refusal(500), refusal(500))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert (
        ex.value.kind == "unreachable" and len(line.requests) == 3 and "error 500" in str(ex.value) and "Nothing is lost" in str(ex.value)
    )


def test_a_change_is_not_sent_twice_when_nobody_knows_whether_it_happened():
    for trouble in (refusal(500), refusal(502), refusal(408, {"error": "Request timeout"}), TimeoutError("timed out")):
        line = Line(trouble, ADDED)
        with pytest.raises(hardcover.HardcoverError) as ex:
            line.client().insert_user_book({"book_id": 1, "status_id": 2})
        assert ex.value.kind == "unreachable" and len(line.requests) == 1, trouble
    # 503 is the one Hardcover documents as safe to send again.
    line = Line(refusal(503, {"error": "Service temporarily unavailable"}), ADDED)
    assert line.client().insert_user_book({"book_id": 1, "status_id": 2}) == 501


def test_a_person_waiting_at_the_page_gets_one_try():
    line = Line(refusal(500), ME)
    with pytest.raises(hardcover.HardcoverError) as ex:
        hardcover.Client(TOKEN, opener=line, sleep=line.slept.append, tries=1).whoami()
    assert ex.value.kind == "unreachable" and len(line.requests) == 1 and waits(line) == []


def test_no_answer_at_all():
    line = Line(TimeoutError("timed out"), urllib.error.URLError("Name or service not known"), ME)
    assert line.client().whoami()["id"] == 7 and len(line.requests) == 3
    line = Line(*[urllib.error.URLError(TimeoutError("timed out"))] * 3)
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert ex.value.kind == "unreachable" and "could not be reached (timed out)" in str(ex.value)


def test_an_answer_that_is_cut_off_or_not_hardcovers_is_not_taken_for_data():
    for junk in (b'{"data": {"me": [{"id": 7, "usern', b"<html>gateway</html>", b"null", b'{"data": null}', b"[]"):
        line = Line(Answer(junk), Answer(junk), Answer(junk))
        with pytest.raises(hardcover.HardcoverError) as ex:
            line.client().whoami()
        assert ex.value.kind == "answer" and len(line.requests) == 3, junk  # a question: asked again first
        line = Line(Answer(junk), ADDED)
        with pytest.raises(hardcover.HardcoverError):
            line.client().insert_user_book({"book_id": 1, "status_id": 2})
        assert len(line.requests) == 1
    for odd in ({"data": {}}, {"data": {"me": []}}, {"data": {"me": [{"username": "sam"}]}}, {"data": {"me": "sam"}}):
        with pytest.raises(hardcover.HardcoverError) as ex:
            Line(odd).client().whoami()
        assert ex.value.kind == "answer"


def test_what_hardcover_refuses_is_said_in_its_own_words_and_not_tried_again():
    line = Line({"errors": [{"message": "field 'nope' not found in type: 'query_root'"}]})
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().whoami()
    assert (
        ex.value.kind == "refused" and not ex.value.stops_the_run and "field 'nope' not found" in str(ex.value) and len(line.requests) == 1
    )
    line = Line({"data": {"insert_user_book": {"id": None, "error": "Book not found"}}})
    with pytest.raises(hardcover.HardcoverError, match="Hardcover refused: Book not found"):
        line.client().insert_user_book({"book_id": 1, "status_id": 2})
    with pytest.raises(hardcover.HardcoverError) as ex:
        Line({"data": {"insert_user_book": None}}).client().insert_user_book({"book_id": 1, "status_id": 2})
    assert ex.value.kind == "answer"


# ---------- the shelf ----------
def shelf_book(i):
    return {"id": 1000 + i, "book_id": i, "status_id": 3, "edition_id": None, "edition": None, "user_book_reads": []}


class Shelf:
    """Hardcover's side of the shelf query: `books`, at most `cap` per request."""

    def __init__(self, n, cap=10**6, says=None):
        self.books, self.cap, self.says = [shelf_book(i) for i in range(n)], cap, says

    def __call__(self, v):
        rows = self.books[v["o"] : v["o"] + min(v["n"], self.cap)]
        return {
            "data": {
                "user_books_aggregate": {"aggregate": {"count": self.says if self.says is not None else len(self.books)}},
                "user_books": rows,
            }
        }


def test_a_shelf_larger_than_one_page_is_fetched_whole():
    shelf = Shelf(2 * hardcover.SHELF_PAGE + 20)
    line = Line(ME, shelf, shelf, shelf)
    got = line.client().shelf()
    assert [u["id"] for u in got] == [u["id"] for u in shelf.books] and line.answers == []
    assert [r["variables"]["o"] for r in line.requests[1:]] == [0, hardcover.SHELF_PAGE, 2 * hardcover.SHELF_PAGE]
    assert "user_books_aggregate" in line.requests[1]["query"] and "user_books_aggregate" not in line.requests[2]["query"]
    assert "order_by:{id:asc}" in line.requests[1]["query"]  # pages of a list that keeps its order


def test_a_small_shelf_is_one_request_and_an_empty_one_is_empty():
    line = Line(ME, Shelf(131))
    assert len(line.client().shelf()) == 131 and line.answers == []
    line = Line(ME, Shelf(0))
    assert line.client().shelf() == [] and line.answers == []


def test_a_server_that_gives_fewer_books_per_request_than_asked_still_gives_the_whole_shelf():
    shelf = Shelf(25, cap=10)  # a limit on Hardcover's side we were not told about
    line = Line(ME, shelf, shelf, shelf)
    assert len(line.client().shelf()) == 25 and line.answers == []


def test_a_shelf_that_comes_back_short_is_an_error_never_a_shorter_shelf():
    shelf = Shelf(6, says=10)  # Hardcover says ten, and gives six
    line = Line(ME, shelf, shelf)
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().shelf()
    assert ex.value.kind == "answer" and "6 of the 10 books" in str(ex.value)
    for broken in (
        {"data": {"user_books": [shelf_book(1)]}},  # no count
        {"data": {"user_books_aggregate": {"aggregate": {"count": 1}}}},  # no list
        {"data": {"user_books_aggregate": {"aggregate": {"count": 1}}, "user_books": [{"id": 1001, "book_id": 1}]}},  # no read-throughs
        {"data": {"user_books_aggregate": {"aggregate": {"count": 1}}, "user_books": [None]}},
    ):
        with pytest.raises(hardcover.HardcoverError) as ex:
            Line(ME, broken).client().shelf()
        assert ex.value.kind == "answer", broken


def test_a_page_that_fails_halfway_fails_the_shelf():
    shelf = Shelf(hardcover.SHELF_PAGE + 5)
    line = Line(ME, shelf, refusal(500), refusal(500), refusal(500))
    with pytest.raises(hardcover.HardcoverError) as ex:
        line.client().shelf()
    assert ex.value.kind == "unreachable"


def test_search_results_that_are_not_books_are_skipped():
    hits = [{"document": {"id": "80", "title": "Blindness", "author_names": ["José Saramago"], "pages": 300}}, {"document": {}}, "x", {}]
    assert [c["book_id"] for c in Line({"data": {"search": {"results": {"hits": hits}}}}).client().search("Blindness")] == [80]
    # The other titles Hardcover lists for a book come along, for matching a translation.
    hits = [{"document": {"id": "1", "title": "The Eye of the World", "alternative_titles": ["Het Oog van de Wereld", 7, None]}}]
    line = Line({"data": {"search": {"results": {"hits": hits}}}})
    assert line.client().search("Het Oog")[0]["also"] == ["Het Oog van de Wereld"]
    assert line.requests[-1]["variables"]["n"] == hardcover.HITS == 5  # five hits are looked at
    assert Line({"data": {"search": {"results": "Service unavailable"}}}).client().search("Blindness") == []
    assert Line({"data": {"search": None}}).client().search("Blindness") == []
