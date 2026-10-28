"""Getting started and Needs you (start.py): the steps the page and the Mac app both show."""

from kobo_hardcover_sync import start


def states(found):
    return [s["state"] for s in found["steps"]]


def test_the_first_step_not_done_is_the_one_of_now():
    new = start.steps(connected=False, books=0, on=0, live=False, mode="local")
    assert states(new) == ["now", "later", "later", "later"] and [s["n"] for s in new["steps"]] == [1, 2, 3, 4]
    # A Kobo read first, before connecting: the connection is still the step of now.
    assert states(start.steps(connected=False, books=5, on=2, live=False, mode="local")) == ["now", "done", "done", "later"]
    assert states(start.steps(connected=True, books=5, on=0, live=False, mode="local")) == ["done", "done", "now", "later"]
    # Live, with books: nothing left to start. Live before any book came: the Kobo is still to plug in.
    assert start.steps(connected=True, books=5, on=2, live=True, mode="local") is None
    assert states(start.steps(connected=True, books=0, on=0, live=True, mode="server")) == ["done", "now", "later", "done"]


def test_each_surface_gets_the_control_it_has():
    page = start.steps(connected=True, books=0, on=0, live=False, mode="server")
    assert page["steps"][1]["action"] == "add_device" and "paste it below" in page["steps"][1]["text"]
    # The first computer can be added before connecting: on a server the two do not wait for each other.
    first = start.steps(connected=False, books=0, on=0, live=False, mode="server")
    assert [s["action"] for s in first["steps"]] == ["connect", "add_device", "", "go_live"] and states(first)[1] == "later"
    at = start.steps(connected=True, books=0, on=0, live=False, mode="server", devices=("kobo-kim", "kobo-attic"))
    assert at["steps"][1]["action"] == "" and at["steps"][1]["text"] == "Plug in the Kobo at kobo-kim or kobo-attic. Tap Connect on it."
    # The app is the computer the Kobo is plugged into; in server mode it connects on the server's page.
    app = start.steps(connected=False, books=0, on=0, live=False, mode="server", app=True)
    assert [s["action"] for s in app["steps"]] == ["server_page", "", "", "go_live"]
    assert app["steps"][1]["text"] == "Tap Connect on the Kobo. The first sync reads your books." and not app["can_go_live"]


def test_needs_you_counts_what_waits_once_live():
    assert start.needs_you(live=False, match=2, failed=1, need=3) is None  # before live, Getting started says what to do
    assert start.needs_you(live=True, match=0, failed=0, need=0) is None
    assert start.needs_you(live=True, match=1, failed=0, need=1)["text"] == "1 book needs a Hardcover match."
    both = start.needs_you(live=True, match=1, failed=1, need=2)
    assert both["text"] == "2 books need you: 1 needs a Hardcover match, 1 could not be sent at the last sync."
    # A book that has no match and failed too is one book that needs you.
    assert start.needs_you(live=True, match=2, failed=1, need=2)["text"].startswith("2 books need you: 2 need a Hardcover match, 1 could")
