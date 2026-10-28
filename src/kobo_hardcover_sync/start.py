"""Getting started, and what needs the reader once live: worked out once,
here, for both surfaces. The page draws it above the books (web/app.py);
the Mac app reads it from `books --json` (appbooks.py) for its Overview and
its Books band. Same steps, same words (strings.py).

Pure functions over a few facts about the reader; `facts()` gathers them
from the database."""

from __future__ import annotations

from .engine import state
from .web.strings import T

STEPS = ("connect", "kobo", "books", "live")


def _n(key: str, n: int) -> str:
    one, many = T[key]
    return (one if n == 1 else many).format(n=n)


def facts(con, reader: str) -> dict:
    """The counts the steps and the band are worked out from: books from the
    Kobo, how many are switched on, and of those how many wait for a match
    (as the filter Needs a match counts them) or could not be sent."""
    rows = (
        con.execute("select mode, history, hc_book_id, hc_how, hc_error from reader_book where reader=?", (reader,)).fetchall()
        if con
        else []
    )
    on = [r for r in rows if state.syncs(r)]
    match = {i for i, r in enumerate(on) if not r["hc_book_id"] and r["hc_how"] in ("uncertain", "none")}
    failed = {i for i, r in enumerate(on) if r["hc_error"]}
    return {"books": len(rows), "on": len(on), "match": len(match), "failed": len(failed), "need": len(match | failed)}


def steps(
    *,
    connected: bool,
    books: int,
    on: int,
    live: bool,
    mode: str,
    devices: tuple[str, ...] = (),
    app: bool = False,
) -> dict | None:
    """The four steps from a new reader to a live shelf: Connect to
    Hardcover, Plug in your Kobo, Choose your books, Go live. Each is done,
    now (the first that is not done) or later, with one line of text and the
    action that does it (the surface draws it: see `action`). None once the
    reader is live and has books: there is nothing left to start.

    mode: "local" or "server". devices: in server mode, the names of the
    computers that upload for the reader. app: said to the Mac app, which is
    itself the computer the Kobo is plugged into, also in server mode."""
    if live and books:
        return None
    done = {"connect": connected, "kobo": books > 0, "books": on > 0, "live": live}
    now = next((k for k in STEPS if not done[k]), "")
    server = mode == "server"

    def text(key: str) -> str:
        if done[key]:
            return {
                "connect": T["gs_connect_done"],
                "kobo": _n("gs_kobo_done", books),
                "books": f"{on} {T['fr_tally']}",
                "live": T["gs_live_done"],
            }[key]
        if key == "connect":
            return T["gs_connect_server" if server and app else "gs_connect_text"]
        if key == "kobo":
            if server and not app:
                return T["gs_kobo_at"].format(device=T["gs_or"].join(devices)) if devices else T["gs_kobo_add"]
            return T["gs_kobo_local"]
        if key == "books":
            return T["gs_books_text"]
        return T["gs_live_text"]

    def action(key: str) -> str:
        """What the step's one control does. "connect": sign in to Hardcover
        here; "server_page": the server's page, where the connection is made
        (the app in server mode); "add_device": the form that adds a
        computer by its code (the page, in server mode, before there is one);
        "show_books": the list (the app's Overview; on the page the list is
        right below); "go_live": going live, with its question, and only
        once connected. A step that is done has none. Adding the first
        computer does not wait for the connection (the two are apart on a
        server); Choose your books waits for the books; Go live is always
        there, and can be chosen once connected."""
        if key == "live":
            return "go_live"
        if done[key]:
            return ""
        if key == "connect":
            return "server_page" if server and app else "connect"
        if key == "kobo":
            return "add_device" if server and not app and not devices else ""
        return "show_books" if key == now else ""

    return {
        "title": T["gs_title"],
        "on": on,
        "tally": T["fr_tally"],
        "can_go_live": connected,
        "steps": [
            {
                "key": key,
                "n": n,
                "title": T["gs_" + key],
                "text": text(key),
                "state": "done" if done[key] else "now" if key == now else "later",
                "action": action(key),
            }
            for n, key in enumerate(STEPS, 1)
        ],
    }


def needs_you(*, live: bool, match: int, failed: int, need: int, **_) -> dict | None:
    """Once live, the books switched on that wait for the reader: without a
    Hardcover match, or not sent at the last sync. None when there are none,
    and before going live, when Getting started says what to do."""
    if not live or not need:
        return None
    if match and failed:
        text = f"{_n('ny_need', need)}: {_n('ny_match_some', match)}, {_n('ny_failed_some', failed)}."
    elif match:
        text = _n("ny_match", match)
    else:
        text = _n("ny_failed", failed)
    return {"n": need, "match": match, "failed": failed, "text": text}
