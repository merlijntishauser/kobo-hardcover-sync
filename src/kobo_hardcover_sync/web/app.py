"""The pages. Behind a forward-auth proxy: the reader comes from the
Remote-User / Remote-Email header the proxy passes on, mapped through the
reader table (accounts.py). The header is believed only when the request
comes from the proxy's own address (KHS_TRUSTED_PROXIES); anyone else gets
a 403, and without that setting the server does not start.

Readers manage themselves under /settings; a login that has no reader yet
gets a sign-up page; admins get /admin."""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlencode, urlparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .. import doctor
from ..engine import hardcover, job, oauth, state
from ..engine.plan import action, desired, quiet_for
from ..env import env
from ..server import accounts, proxy, upload
from ..server import stats as stats_mod
from . import account_pages, covers, marks
from .fmt import e, fmt_date, fmt_dt, fmt_dur, shorten
from .strings import T

DATA = env("DATA", "/data")
CONFIG = env("CONFIG", "/config/readers.yaml")
DEVICES = env("DEVICES", os.path.join(os.path.dirname(CONFIG), "devices.yaml"))
PUBLIC_HOST = env("HOST", "localhost")  # public hostname, for the same-origin check

# Two ways to run (docs/local-mode.md). Server mode: several readers, behind
# a sign-in proxy. Local mode: one reader on their own computer, started by
# `kobo-hardcover-sync open`, with the Hardcover token in the computer's
# secret store instead of the database.
MODE = env("MODE", "server")
local = None
if MODE == "local":
    from ..computer import config as computer_config
    from ..computer import page as local_page
    from ..computer import runner

    local = local_page.Local(int(env("PAGE_PORT", "0")))
    accounts.token_store = local_page.KeptToken(local)
else:
    accounts.token_store = None

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Compress(GZipMiddleware):
    """gzip for what shrinks: the pages (a long shelf is close to a megabyte
    of HTML), the stylesheet, the script. Fonts, photographs and covers are
    compressed already and pass untouched."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(("/static/fonts/", "/cover/")):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class Static(StaticFiles):
    """The stylesheet and the script carry their version in the address
    (?v=), so a browser may keep them for good; fonts, photographs and
    icons for a week."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            versioned = b"v=" in scope.get("query_string", b"")
            response.headers["Cache-Control"] = "max-age=31536000, immutable" if versioned else "max-age=604800"
        return response


app.add_middleware(Compress, minimum_size=1024)

STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", Static(directory=STATIC), name="static")
# Cache-buster for the stylesheet and script.
ASSET_V = str(int(max(os.path.getmtime(os.path.join(STATIC, f)) for f in ("kobo.css", "kobo.js"))))


_boot = threading.Lock()
_booted = False


def db():
    """A connection to state.db. The first one of a process takes over the
    readers.yaml / devices.yaml of an older installation (once per database)."""
    global _booted
    con = state.connect(os.path.join(DATA, "state.db"))
    if not _booted and not local:
        with _boot:
            if not _booted:
                accounts.bootstrap(con, CONFIG, DEVICES)
                _booted = True
    return con


def live_for(reader: str) -> bool:
    row = accounts.get(db(), reader)
    return bool(row and row["hardcover_live"])


def check_origin(request: Request):
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if origin and urlparse(origin).hostname not in (PUBLIC_HOST, "localhost", "127.0.0.1"):
        return PlainTextResponse("cross-origin form refused", status_code=403)
    return None


def me_for(request: Request, con=None):
    """The reader row of whoever is signed in, or None. Local mode has one
    reader and no sign-in: the gate in front (local_gate) decides who gets
    this far."""
    if local:
        return accounts.local_reader(con or db(), local.user)
    return accounts.by_identity(con or db(), (request.headers.get("remote-user"), request.headers.get("remote-email")))


def reader_for(request: Request) -> str | None:
    me = me_for(request)
    return me["name"] if me else None


def guard(request: Request, admin: bool = False):
    """(con, me, None) for a signed-in reader on a same-origin request,
    else (None, None, the refusal)."""
    if request.method != "GET" and (bad := check_origin(request)):
        return None, None, bad
    con = db()
    me = me_for(request, con)
    if me is None:
        return None, None, PlainTextResponse(T["unknown_user"], status_code=403)
    if admin and not me["is_admin"]:
        return None, None, PlainTextResponse(T["admins_only"], status_code=403)
    return con, me, None


SYNC_INTERVAL = int(env("INTERVAL", "3600"))

# The reader comes from the proxy's headers, so everything that shows or
# changes a reader's things is only answered to the proxy (server/proxy.py).
# Open to anyone who can reach the port: the health check, the page's own
# files, and the three paths that carry a token of their own.
TRUSTED_PROXIES = proxy.parse(env("TRUSTED_PROXIES", ""))
OPEN_PATHS = ("/healthz", "/upload", "/collection")
OPEN_PREFIXES = ("/static/", "/api/stats/")


# Local mode has none of these: one reader, no uploads, no proxy.
LOCAL_OFF = ("/upload", "/collection", "/signup", "/admin")
LOCAL_OFF_PREFIXES = ("/api/stats/", "/admin/", "/settings/devices/", "/settings/stats/")
LOOPBACK = ("127.0.0.1", "::1")


async def local_gate(request: Request, call_next):
    """Local mode's stand-in for a login (computer/page.py says why each
    check is there): from this computer, to this page's own address, with
    this run's session cookie, and for a change from this page's own origin."""
    local.last_seen = time.monotonic()
    path = request.url.path
    peer = request.client.host if request.client else ""
    if peer not in LOOPBACK or request.headers.get("host") != f"{local_page.HOST}:{local.port}":
        return PlainTextResponse(T["local_only"], status_code=403)
    if path == "/healthz":
        return await call_next(request)
    if path in LOCAL_OFF or path.startswith(LOCAL_OFF_PREFIXES):
        return PlainTextResponse(T["not_in_local_mode"], status_code=404)
    key = request.query_params.get("k")
    if key and request.method == "GET" and local_page.take_key(key):
        rest = urlencode([(k, v) for k, v in request.query_params.multi_items() if k != "k"])
        resp = RedirectResponse(path + ("?" + rest if rest else ""), status_code=303)
        resp.set_cookie(local_page.COOKIE, local.session, httponly=True, samesite="strict", path="/")
        return resp
    # Back from signing in on Hardcover: a cross-site arrival, so without the cookie; the answer
    # itself is checked against the sign-in it belongs to (oauth_callback).
    if path == oauth.CALLBACK and request.method == "GET":
        return await call_next(request)
    if not local.has_session(request.cookies.get(local_page.COOKIE)):
        return PlainTextResponse(T["local_no_key"], status_code=403)
    if request.method not in ("GET", "HEAD") and request.headers.get("origin") != local.origin:
        return PlainTextResponse("cross-origin form refused", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def only_through_the_proxy(request: Request, call_next):
    if local:
        return await local_gate(request, call_next)
    path = request.url.path
    if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return await call_next(request)
    if not proxy.trusted(request.client.host if request.client else None, TRUSTED_PROXIES):
        return PlainTextResponse(T["not_through_proxy"], status_code=403)
    return await call_next(request)


@app.on_event("startup")
def refuse_to_run_without_a_proxy():
    if local:
        if not local.port:
            raise RuntimeError("Local mode is started with `kobo-hardcover-sync open`.")
    elif not TRUSTED_PROXIES:
        raise RuntimeError(proxy.HOW)


@app.on_event("startup")
def start_hourly_sync():
    """Two-way sync without an upload: an edit on Hardcover shows up here
    within the hour. Only readers that are live and have a token. Not in
    local mode: nothing runs there between syncs."""
    if SYNC_INTERVAL <= 0 or local:
        return

    def loop():
        import time

        while True:
            time.sleep(SYNC_INTERVAL)
            try:
                con = db()
                for r in accounts.all_readers(con):
                    if r["hardcover_live"] and (token := token_to_use(con, r["name"], True)):
                        job.run(os.path.join(DATA, "state.db"), r["name"], True, token=token)
            except Exception:  # a bad hour must not end the loop
                pass

    threading.Thread(target=loop, daemon=True, name="hourly-sync").start()


def token_to_use(con, reader: str, live: bool) -> str | None:
    """The reader's token for a run; "" when they have none. None when
    there is a connection that cannot be used: that is written down as a
    run that could not start, so that the page says so instead of staying
    quiet, and there is nothing left to start."""
    try:
        return accounts.token_for(con, reader)
    except hardcover.HardcoverError as ex:
        job.could_not_start(os.path.join(DATA, "state.db"), reader, live, str(ex))
        return None


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


FILTERS = {
    "all": "1=1",
    "reading": "((status=1 or (status=0 and percent>0)) and coalesce(finished_at,'')='' and state!='finished') or state='rereading'",
    "finished": "(status=2 or coalesce(finished_at,'')!='' or state='finished') and state!='rereading'",
    "unread": "(status=0 and coalesce(percent,0)=0)",
    "history": "history=1",
    "new": "history=0",
    "on": "(mode='on' or (mode='auto' and history=0))",
    "off": "not (mode='on' or (mode='auto' and history=0))",
    "needs_match": "(mode='on' or (mode='auto' and history=0)) and hc_book_id is null and hc_how in ('uncertain','none')",
    # On the Hardcover shelf with an edition that is not marked Ebook: to fix there.
    "not_ebook": "(mode='on' or (mode='auto' and history=0)) and last_sent is not null and coalesce(hc_format_id,0)!=4",
}
FILTER_GROUPS = [
    ("progress", ["all", "reading", "finished", "unread"]),
    ("kobo", ["history", "new"]),
    ("hardcover", ["on", "off", "needs_match", "not_ebook"]),
]
FUNNEL = (
    '<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"'
    ' stroke-linejoin="round"><path d="M1.5 2.5h13l-5 6v4.5l-3 1.5V8.5z"/></svg>'
)
SORTS = {
    "last_read": "last_read desc",
    "author": "author collate nocase, title collate nocase",
    "title": "title collate nocase",
}


def _where(reader, q, f):
    # Each filter in its own parentheses: some contain a top-level OR, which
    # would otherwise escape the reader condition.
    where, args = [f"({FILTERS.get(f, '1=1')})", "reader=?"], [reader]
    if q:
        where.append("(title like ? or author like ?)")
        args += [f"%{q}%", f"%{q}%"]
    return " and ".join(where), args


def query_rows(con, reader, q, f, sort):
    where, args = _where(reader, q, f)
    return con.execute(f"select * from book where {where} order by {SORTS.get(sort, SORTS['last_read'])}", args).fetchall()


def filter_counts(con, reader, q):
    out = {}
    for k in FILTERS:
        where, args = _where(reader, q, k)
        out[k] = con.execute(f"select count(*) from book where {where}", args).fetchone()[0]
    return out


# ---------- row pieces (also returned by /mode and /state for in-place redraw) ----------
def book_cell(r) -> str:
    want = desired(r)
    done = bool(want and want["status"] == "read")
    pct = 100 if done else max(0, min(100, int(r["percent"] or 0)))
    tag = "" if r["history"] else f'<span class="tag">{T["new_tag"]}</span>'
    meta = []
    if done:
        when = fmt_date(want.get("finished"))
        meta.append(f"{T['finished_on']} {when}" if when else T["finished_pin"])
    elif pct or r["status"] == 1:
        meta.append(f"{pct}%")
        if r["last_read"]:
            meta.append(f"{T['last_read']} {fmt_date(r['last_read'])}")
    else:
        meta.append(T["not_started"])
    if r["seconds_read"]:
        meta.append(f'<span title="{T["account_time_help"]}">{fmt_dur(r["seconds_read"])} {T["read_time"]}</span>')
    label = T["finished_pin"] if done else f"{pct}%"
    # Decorative: the title is right next to it. The browser asks for covers
    # as rows scroll into view; a book without one keeps the plain tile.
    # The cover opens larger in the lightbox (kobo.js); without JS the link
    # simply opens the large image.
    src = f"/cover/{quote(r['content_id'], safe='')}"
    cover = (
        f'<a class="coverlink" href="{src}?size=large" data-title="{e(r["title"])}" data-author="{e(r["author"])}"'
        f' aria-label="{e(T["show_cover"].format(title=r["title"]))}">'
        f'<img class="cover" src="{src}" alt="" width="48" height="72" loading="lazy"></a>'
        if r["image_id"]
        else '<span class="cover"></span>'
    )
    return (
        f'<div class="bk">{cover}<div class="info"><div class="title">{e(r["title"])}{tag}</div><div class="author">{e(r["author"])}</div>'
        f'<div class="bar{" done" if done else ""}" role="img" aria-label="{label}"><span style="width:{pct}%"></span></div>'
        f'<div class="meta">{"".join(m if m.startswith("<span") else f"<span>{e(m)}</span>" for m in meta)}</div></div></div>'
    )


def hc_status(r, live: bool, quiet: dict) -> tuple[str, str]:
    """(kind, text) of the Hardcover status line: what the next sync does.
    kind: ok | next | wait | warn | err | none (marks.py). `quiet`: plan.quiet for this reader."""
    if r["hc_error"]:
        return "err", T["status_error"]
    if (r["device"], r["content_id"]) in quiet:
        return "none", T["other_copy"]
    a = action(r)
    if a.startswith("needs"):
        return "warn", T["needs_match"]
    if a.startswith("match pending"):
        return "next", T["match_pending"]
    if a:
        return "next", f"{T['next_sync'] if live else T['would_send']}: {a}"
    if state.syncs(r) and r["last_sent"]:
        return "ok", T["up_to_date"]
    if state.syncs(r):
        return "wait", T["not_yet_sent"]
    return "none", T["not_syncing"]


def status_html(status: tuple[str, str]) -> str:
    return marks.line(*status)


def first_run(con, reader: str, live: bool) -> str:
    """Above the list until the reader goes live: what to do with a Kobo full
    of books read before, and the three steps from here to a live shelf. Going
    live is the last step, so going live ends it. Empty when there is nothing
    to show."""
    total, history = con.execute("select count(*), coalesce(sum(history), 0) from book where reader=?", (reader,)).fetchone()
    if live or not total:
        return ""
    on = sum(1 for r in con.execute("select mode, history from book where reader=?", (reader,)) if state.syncs(r))
    if accounts.has_token(con, reader):
        connect = f'<li class="done">{marks.mark("ok")}<b>{T["fr_connect"]}</b><span class="s">{T["fr_connect_done"]}</span></li>'
    else:
        connect = (
            f'<li><span class="n">1</span><b>{T["fr_connect"]}</b><span class="s">{T["fr_connect_todo"]} '
            f'<a href="/settings#hardcover">{T["fr_connect_link"]}</a></span></li>'
        )
    return (
        f'<section class="firstrun" aria-labelledby="fr-h"><div><h3 id="fr-h">{T["fr_title"]}</h3>'
        f"<p>{e(T['fr_text'].format(n=total, h=history))}</p>"
        f'<p class="tally"><strong>{on}</strong> <span>{T["fr_tally"]} {T["fr_dry"]}</span></p></div>'
        f'<ol class="steps" aria-label="{T["fr_steps"]}">{connect}'
        f'<li class="here" aria-current="step"><span class="n">2</span><b>{T["fr_pick"]}</b><span class="s">{T["fr_pick_here"]}</span></li>'
        f'<li><span class="n">3</span><b>{T["fr_live"]}</b><span class="s">{T["fr_live_when"]}</span></li></ol></section>'
    )


def sync_progress(reader: str) -> dict | None:
    """While a sync for this reader runs: what it is doing, in the page's words,
    and how far it is (0 to 1, or None while that is not known yet)."""
    p = job.progress.get(reader)
    if p is None:
        return None
    if p["phase"] == "send" and p["total"]:
        key = "sp_send" if live_for(reader) else "sp_check"
        return {"text": T[key].format(i=min(p["done"] + 1, p["total"]), n=p["total"]), "part": p["done"] / p["total"]}
    return {"text": T["sp_" + p["phase"]], "part": None}


def sync_button(con, reader: str, live: bool, back: str, j) -> str:
    """Sync now. While a sync runs: Syncing, what it is doing, and a line gauge
    that fills as the books go out; kobo.js asks /sync/status until it is done
    and then shows the list again with what the sync said. Without JS the
    page refreshes itself while it runs."""
    p = sync_progress(reader)
    kind, said = sync_result(j)
    done = f'<div class="syncdone" role="status" hidden>{marks.line(kind, said)}</div>' if said else ""
    if p is None:
        return (
            f'<form method="post" action="/sync" class="syncnow"><input type="hidden" name="back" value="{e(back)}">'
            f'<button class="primary"><span>{T["sync_now"]}</span><small class="marked">{e(marked_line(con, reader, live))}</small></button>'
            f"{done}</form>"
        )
    part = p["part"]
    bar = (
        f'<div class="bar syncbar" aria-hidden="true"><span style="--p:{round(part, 3)}"></span></div>'
        if part is not None
        else '<div class="bar syncbar wait" aria-hidden="true"><span></span></div>'
    )
    return (
        f'<form class="syncnow" data-running="/sync/status"><button class="primary" type="button" disabled aria-busy="true">'
        f'<span>{T["syncing"]}</span><small class="marked" aria-live="polite">{e(p["text"])}</small></button>{bar}</form>'
    )


def sync_result(j) -> tuple[str, str]:
    """(kind, text) of the last sync, said the way the person who pressed Sync now asked it."""
    if not j or j["status"] == "running":
        return "", ""
    try:
        d = json.loads(j["detail"] or "{}")
    except ValueError:
        d = {}

    def n(key, count):
        one, many = T[key]
        return (one if count == 1 else many).format(n=count)

    if d.get("fatal"):
        return "err", T["sd_failed"].format(why=d["fatal"])
    if d.get("errors"):
        return "err", n("sd_errors", d["errors"])
    if not j["live"]:
        return "ok", n("sd_planned", d["planned"]) if d.get("planned") else T["sd_none"]
    return "ok", n("sd_sent", d["sent"]) if d.get("sent") else T["sd_none"]


def marked_line(con, reader: str, live: bool) -> str:
    """The second line of Sync now: how many books carry the red mark, so the
    button says what it is about to send. Empty when there are none."""
    quiet = quiet_for(con, reader)
    n = sum(1 for r in con.execute("select * from book where reader=?", (reader,)) if hc_status(r, live, quiet)[0] == "next")
    if not n:
        return ""
    one, many = T["marked_send" if live else "marked_would"]
    return (one if n == 1 else many).format(n=n)


def shelf_words(d: dict) -> str:
    """'Currently reading, 37%' / 'Read, finished 30 Sep 2026': a shelf entry
    in the page's words, for what Hardcover has (last_sent) or will get (desired)."""
    st = d.get("status") if d else None
    if not st:
        return ""
    words = T.get("hc_" + st, st)
    if st == "reading" and d.get("progress") is not None:
        words += f", {d['progress']}%"
    if st == "read" and d.get("finished"):
        words += ", " + T["shelf_finished"].format(date=fmt_date(d["finished"]))
    return words


def correction(r) -> tuple[str, str, str] | None:
    """The proof mark for a row the next sync changes: (kept, struck, inserted),
    'Currently reading,' '35%' '37%'. None when there is no shelf change to show
    (no match yet, or only the edition changes)."""
    a = action(r)
    if not a or not r["hc_book_id"] or a.startswith(("needs", "match pending")):
        return None
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    now = shelf_words(desired(r) or {})
    was = shelf_words(sent) if sent.get("user_book_id") else ""
    if not now or now == was:
        return None
    if was:
        h1, _, t1 = was.partition(", ")
        h2, _, t2 = now.partition(", ")
        if h1 == h2 and t1 and t2:
            return h1 + ",", t1, t2
    return "", was, now


def row_json(con, reader, cid, back: str = "", with_details: bool = False):
    """What kobo.js needs to redraw one row in place; with_details adds the
    refreshed content of the details dialog."""
    row = con.execute("select * from book where reader=? and content_id=?", (reader, cid)).fetchone()
    if row is None:
        return {"syncs": False, "action": "", "book": "", "status": '<div class="act"></div>', "hc": ""}
    status = hc_status(row, live_for(reader), quiet_for(con, reader))
    d = {
        "marked": marked_line(con, reader, live_for(reader)),
        "on": sum(1 for r in con.execute("select mode, history from book where reader=?", (reader,)) if state.syncs(r)),
        "syncs": state.syncs(row),
        "action": action(row),
        "book": book_cell(row),
        "status": status_html(status),
        "hc": hc_cell(row, back, status),
    }
    if with_details:
        d["details"] = details_fragment(row, status, back)
    return d


def answer(request: Request, con, reader: str, cid: str, back: str):
    """A dialog form posted by kobo.js gets JSON; a plain form goes back to the row."""
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(row_json(con, reader, cid, back, with_details=True))
    return to_row(back, cid)


STATE_LABEL = {"kobo": "kobo", "finished": "finished_pin", "rereading": "rereading", "want": "want", "dnf": "dnf"}


# A row's switches save by themselves when kobo.js runs. Without it they
# need a button, and only then is there one.
NOSCRIPT_SET = f"<noscript><button>{T['apply_bulk']}</button></noscript>"


def state_cell(r, back: str) -> str:
    cur = r["state"] or "kobo"
    sel = "".join(f'<option value="{s}"{" selected" if s == cur else ""}>{T[STATE_LABEL[s]]}</option>' for s in state.STATES)
    return (
        f'<form method="post" action="/state" class="stateform"><input type="hidden" name="id" value="{e(r["content_id"])}">'
        f'<input type="hidden" name="back" value="{e(back)}">'
        f'<select name="state" class="rowstate" aria-label="{T["col_state"]}">{sel}</select>'
        f'<input type="date" name="date" class="rowdate" aria-label="{T["state_date"]}" value="{e(r["state_date"] or "")}"'
        f"{'' if cur in ('finished', 'rereading') else ' hidden'}>{NOSCRIPT_SET}</form>"
    )


def edition_line(r, sent: dict) -> str:
    """'Blindness, Ebook' style line: the match and its edition. An edition
    chosen on Hardcover carries a stet: it is kept as it is."""
    if not r["hc_book_id"]:
        return ""
    parts = [e(r["hc_title"] or "")]
    if r["hc_format"] or sent.get("user_book_id"):
        parts.append(e(r["hc_format"] or T["format_unknown"]))
    parts = [x for x in parts if x]
    if not parts:
        return ""
    stet = f'{marks.mark("stet")}<span class="sr">{e(T["how_hardcover"])}: </span>' if r["hc_edition_by"] == "hardcover" else ""
    return f'<div class="sub">{stet}{", ".join(parts)}</div>'


def mark_html(r, status: tuple[str, str], labelled: bool = True) -> str:
    """The status line, and for a change the correction itself: the old value
    struck through, the new one after a caret, kept together on one line. The
    words for a screen reader are the status text; the drawn correction is for
    the eye. labelled=False where the page already names it (Details, under
    "Next sync"): the mark and the correction only."""
    kind, text = status
    label, sep, rest = text.partition(": ")
    if kind != "next" or not sep:
        return marks.line(kind, text)
    fix = correction(r)
    if fix is None:
        drawn = f"<ins>{marks.INSERT}{e(rest)}</ins>"
    else:
        kept, was, now = fix
        drawn = (f"{e(kept)} " if kept else "") + '<span class="swap">' + (f"<s>{e(was)}</s> " if was else "")
        drawn += f"<ins>{marks.INSERT}{e(now)}</ins></span>"
    if not labelled:
        return f'<div class="act {kind}">{marks.mark(kind)}<span class="sr">{e(text)}</span><span class="fix" aria-hidden="true">{drawn}</span></div>'
    return marks.line(kind, label, f'<span class="sr">: {e(rest)}</span>') + f'<div class="fix" aria-hidden="true">{drawn}</div>'


def hc_cell(r, back: str, status: tuple[str, str]) -> str:
    """The Hardcover column: one status line, one line for the match, and a
    Details button. Everything else lives in the details dialog."""
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    href = f"/details/{quote(r['content_id'], safe='')}" + (f"?back={quote(back, safe='')}" if back else "")
    return (
        mark_html(r, status)
        + edition_line(r, sent)
        + f'<a class="details" href="{href}" aria-label="{e(T["details_of"].format(title=r["title"]))}">{T["details"]}</a>'
    )


def hc_link(book_id) -> str:
    return f"https://hardcover.app/id/book/{int(book_id)}"


def details_fragment(r, status: tuple[str, str], back: str) -> str:
    """Everything kobo-hardcover-sync knows about one book, with the actions: shown in
    the details dialog (JS) or as its own page (no JS)."""
    cid = e(r["content_id"])
    keep = f'<input type="hidden" name="id" value="{cid}"><input type="hidden" name="back" value="{e(back)}">'
    sent = json.loads(r["last_sent"]) if r["last_sent"] else {}
    kind, status = status
    cover = f'<img class="cover" src="/cover/{cid}" alt="" width="48" height="72">' if r["image_id"] else '<span class="cover"></span>'

    def dl(pairs):
        rows = "".join(f"<div><dt>{e(k)}</dt><dd>{v}</dd></div>" for k, v in pairs if v)
        return f"<dl>{rows}</dl>" if rows else ""

    kobo = [
        (T["col_mode"], e(T[r["mode"]]) + ("" if r["history"] else f' <span class="tag">{T["new_tag"]}</span>')),
        (T["col_state"], e(T[STATE_LABEL[r["state"] or "kobo"]]) + (f", {e(r['state_date'])}" if r["state_date"] else "")),
        (
            T["d_kobo_status"],
            e({0: T["d_unread"], 1: T["d_reading"], 2: T["d_finished"]}.get(r["status"], ""))
            + (f", {r['percent']}%" if r["percent"] else ""),
        ),
        (T["d_finished_on"], e(fmt_date(r["finished_at"]))),
        (T["d_last_read"], e(fmt_date(r["last_read"]))),
        (T["d_read_time"], e(fmt_dur(r["seconds_read"])) if r["seconds_read"] else ""),
        (T["d_language"], e(r["language"] or "")),
        ("ISBN", e(r["isbn"] or "")),
    ]
    hc = []
    if r["hc_book_id"]:
        hc += [
            (
                T["d_book"],
                f'<a href="{hc_link(r["hc_book_id"])}" target="_blank" rel="noopener noreferrer">{e(r["hc_title"])}</a>'
                f' <span class="muted">{e(T.get("how_" + (r["hc_how"] or ""), ""))}</span>',
            ),
            (
                T["d_edition"],
                (
                    e(r["hc_format"] or T["format_unknown"])
                    + (f", {r['hc_pages']} {T['d_pages']}" if r["hc_pages"] else "")
                    + (f' <span class="muted">{e(T["how_hardcover"])}</span>' if r["hc_edition_by"] == "hardcover" else "")
                )
                if (r["hc_format"] or r["hc_pages"])
                else "",
            ),
        ]
    if sent.get("user_book_id"):
        shelf = e(T["hc_" + sent.get("status", "reading")])
        if sent.get("status") == "reading" and sent.get("progress") is not None:
            shelf += f", {sent['progress']}%"
        if sent.get("finished"):
            shelf += f", {e(fmt_date(sent['finished']))}"
        hc.append((T["d_on_shelf"], shelf))
        hc.append((T["d_last_sync"], e(fmt_dt(sent.get("at")))))
    hc.append((T["d_next_sync"], mark_html(r, (kind, status), labelled=False)))
    if r["hc_error"]:
        hc.append((T["d_error"], f'<span class="err">{e(r["hc_error"])}</span>'))
    actions = []
    if not r["hc_book_id"] and r["hc_how"] in ("uncertain", "none"):
        cands = json.loads(r["hc_candidates"] or "[]")
        opts = "".join(
            f'<option value="{c["book_id"]}|{c.get("pages") or ""}|{e(c["title"])}" title="{e(c["title"])}">'
            f"{e(shorten(c['title'], 60))}, {e(shorten((c['authors'] or [''])[0], 30))}</option>"
            for c in cands
        )
        if opts:
            actions.append(
                f'<form method="post" action="/pick" class="pickrow">{keep}<select name="choice" aria-label="{T["candidates"]}">{opts}</select><button class="solid">{T["use"]}</button></form>'
            )
        else:
            actions.append(f'<p class="muted">{T["no_match"]}</p>')
        actions.append(
            f'<form method="post" action="/research" class="pickrow">{keep}<input type="text" name="q" aria-label="{T["search_hc"]}" placeholder="{T["search_hc_hint"]}"><button>{T["search_btn"]}</button></form>'
        )
    if sent.get("user_book_id"):
        actions.append(
            f'<form method="post" action="/remove" data-confirm="{T["confirm_remove"]}">{keep}<button class="danger">{T["remove_hc"]}</button></form>'
        )
    return (
        f'<header class="dhead">{cover}<div><h2>{e(r["title"])}</h2><p class="author">{e(r["author"])}</p></div></header>'
        f"<section><h3>{T['d_section_kobo']}</h3>{dl(kobo)}</section>"
        f"<section><h3>{T['d_section_hardcover']}</h3>{dl(hc)}</section>"
        + (f'<section class="actions">{"".join(actions)}</section>' if actions else "")
    )


def job_line(j) -> str:
    if not j:
        return T["never_synced"]
    when = fmt_dt(j["started"])
    if j["status"] == "running":
        return f"{T['sync_running']} ({when})"
    try:
        d = json.loads(j["detail"] or "{}")
    except ValueError:
        d = {}
    if d.get("fatal"):
        parts = [d["fatal"]]
    else:
        parts = [f"{d.get('sent', 0)} {T['sent']}" if j["live"] else f"{d.get('planned', 0)} {T['planned']}"]
        if d.get("adopted"):
            parts.append(f"{d['adopted']} {T['adopted']}")
        if d.get("removed"):
            parts.append(f"{d['removed']} {T['removed']}")
        if d.get("errors"):
            parts.append(f"{d['errors']} {T['failed']}")
    return f"{T['last_sync']} {when}: {', '.join(parts)}"


# Applies the stored theme before first paint (kobo.js handles the switch).
HEAD_SCRIPT = (
    "<script>try{var t=localStorage.getItem('kobo-theme');"
    "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}</script>"
)
# The browser's own bar in the page's colour, day and night (kobo.js keeps
# it right when the theme is chosen by hand).
THEME_COLOR = (
    '<meta name="theme-color" content="#c3e2ef" media="(prefers-color-scheme: light)">'
    '<meta name="theme-color" content="#123040" media="(prefers-color-scheme: dark)">'
)


def shell(body: str, cls: str = "", head: str = "") -> str:
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{T["title"]}</title>'
        f'{THEME_COLOR}{HEAD_SCRIPT}<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">'
        f'<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">'
        f'<link rel="stylesheet" href="/static/kobo.css?v={ASSET_V}">{head}</head><body{f' class="{cls}"' if cls else ""}>{body}'
        f'<script src="/static/kobo.js?v={ASSET_V}"></script></body></html>'
    )


def help_html() -> str:
    """The help dialog: a title that stays put, and sections that scroll.
    Words from the page are explained as a list of terms, the status
    colours with their own dot."""

    def section(title, items):
        out, terms = [], []

        def flush():
            if terms:
                out.append(f'<dl class="terms">{"".join(terms)}</dl>')
                terms.clear()

        for it in items:
            if isinstance(it, str):
                flush()
                out.append(f"<p>{e(it)}</p>")
            else:
                kind, term, text = it if len(it) == 3 else ("", *it)
                dt = marks.line(kind, term) if kind else e(term)
                terms.append(f"<div><dt>{dt}</dt><dd>{e(text)}</dd></div>")
        flush()
        return f"<section><h3>{e(title)}</h3>{''.join(out)}</section>"

    secs = "".join(section(h, items) for h, items in T["help_sections"])
    return (
        f'<dialog id="help" aria-labelledby="helptitle"><header class="dtop"><h2 id="helptitle">{T["help_title"]}</h2>'
        f'<form method="dialog"><button class="close">{T["close"]}</button></form></header>'
        f'<div class="dbody">{secs}<p class="credit">{e(T["disclaimer"])}</p></div></dialog>'
    )


# Navigation icons (the phone shows them above the words, as a tab bar).
ICON = (
    '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"'
    ' stroke-linecap="round" stroke-linejoin="round">{}</svg>'
)
NAV_ICONS = {
    "books": ICON.format(
        '<rect x="3" y="3.5" width="4" height="13" rx="1"/><rect x="8" y="5.5" width="3.5" height="11" rx="1"/>'
        '<path d="M13.2 7.2l2.9-.8 2.4 9-2.9.8z"/>'
    ),
    "settings": ICON.format('<path d="M3 6h7M14 6h3M3 14h3M10 14h7"/><circle cx="12" cy="6" r="2"/><circle cx="8" cy="14" r="2"/>'),
    "admin": ICON.format(
        '<circle cx="7.5" cy="7" r="2.6"/><path d="M2.5 16c.4-2.8 2.4-4.3 5-4.3s4.6 1.5 5 4.3"/>'
        '<path d="M13 4.6a2.6 2.6 0 010 4.9M14.8 11.9c1.5.5 2.5 1.9 2.7 4.1"/>'
    ),
}


# What the marks in the Hardcover column mean, above the list.
LEGEND = (
    f'<ul class="legend" aria-label="{T["legend"]}">'
    + "".join(f'<li class="{k}">{marks.mark(k)}{T["legend_" + k]}</li>' for k in ("next", "wait", "ok", "stet", "warn", "err", "none"))
    + "</ul>"
)


THEME_SWITCH = (
    '<div class="theme" role="group" aria-label="Theme">'
    '<button type="button" data-set="light">Light</button>'
    '<button type="button" data-set="auto">Auto</button>'
    '<button type="button" data-set="dark">Dark</button></div>'
)


def status_items(con, reader: str, live: bool, last_upload, j) -> str:
    """The three facts at the top, in the column's language (dot + text):
    the Kobo's last upload, Hardcover's state and last sync, the books."""

    def item(kind, text, detail=""):
        return marks.line(kind, text, f'<span class="muted">{e(detail)}</span>' if detail else "")

    if last_upload:
        age = (datetime.now(UTC) - datetime.strptime(last_upload[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)).days
        kobo = item("ok" if age < 3 else "warn", T["kobo_read" if local else "kobo_uploaded"], fmt_dt(last_upload))
    else:
        kobo = item("none", T["kobo_never_local" if local else "kobo_never"])
    if not accounts.has_token(con, reader):
        hc = item("warn", T["hc_no_token"])
    elif not live:
        hc = item("warn", T["hc_dry"], job_line(j))
    elif j is None:
        hc = item("next", T["hc_live"], job_line(j))
    else:
        hc = item({"ok": "ok", "running": "next"}.get(j["status"], "err"), T["hc_live"], job_line(j))
    total = con.execute("select count(*) from book where reader=?", (reader,)).fetchone()[0]
    on = sum(1 for r in con.execute("select mode, history from book where reader=?", (reader,)) if state.syncs(r))
    books = item("none", T["books_total"].format(on=on, n=total))
    return kobo + hc + books


def frame(name: str, main: str, current: str = "", is_admin: bool = False, nav: bool = True, side: str = "", head: str = "") -> str:
    """Every page, one frame: the sidebar (what this is, where to go, and on
    Books the sync status), the page itself, and a footer with who is signed
    in and the page tools. On a phone the sidebar is the top of the page and
    the navigation a bar at the bottom."""
    items = [("books", "/"), ("settings", "/settings")] + ([("admin", "/admin")] if is_admin else [])
    links = "".join(
        f'<a href="{href}"{' aria-current="page"' if k == current else ""}>{NAV_ICONS[k]}<span>{T["nav_" + k]}</span></a>'
        for k, href in items
    )
    return shell(
        f'<aside class="side"><div><div class="brand"><h1>{marks.BRAND}<span>{T["title"]}</span></h1>'
        f'<button type="button" class="bandhelp" data-open="help" aria-label="{T["help"]}" title="{T["help"]}">{marks.HELP}</button></div>'
        f'<p class="tagline">{T["tagline"]} <button type="button" class="linkbtn" data-open="help">{T["about"]}</button></p></div>'
        + (f'<nav class="nav" aria-label="{T["nav"]}">{links}</nav>' if nav else "")
        + side
        + "</aside>"
        + main
        + f'<footer class="foot"><span class="who"><span class="muted">{T["on_this_computer" if local else "signed_in_as"]}</span> <b>{e(name)}</b></span>'
        f'<div class="toolrow">{THEME_SWITCH}<button type="button" class="helpbtn" data-open="help"'
        f' aria-label="{T["help"]}" title="{T["help"]}">{marks.HELP}</button></div>'
        f'<p class="indep">{e(T["disclaimer"])}</p></footer>' + help_html(),
        "app",
        head,
    )


def frame_for(me, current: str, main: str, side: str = "", head: str = "") -> str:
    return frame(me["display_name"] or me["name"], main, current, bool(me["is_admin"]), side=side, head=head)


@app.get("/", response_class=HTMLResponse)
def page(request: Request, q: str = "", f: str = "all", sort: str = "last_read"):
    con = db()
    me = me_for(request, con)
    if me is None:
        who = request.headers.get("remote-user") or request.headers.get("remote-email")
        if not who:  # no proxy in front, or it sent no identity
            return HTMLResponse(
                shell(f'<main class="solo"><h1>{T["unknown_user"]}</h1><p>{T["unknown_user_help"]}</p></main>'), status_code=403
            )
        return HTMLResponse(frame(who, account_pages.signup(who), nav=False))
    reader = me["name"]
    live = bool(me["hardcover_live"])
    back = request.url.query
    rows = query_rows(con, reader, q, f, sort)
    counts = filter_counts(con, reader, q)
    dev = con.execute("select max(last_import) from device where reader=?", (reader,)).fetchone()[0]
    j = con.execute(
        "select started, finished, status, detail, live from job where reader=? order by started desc limit 1", (reader,)
    ).fetchone()

    def link(**kw):
        p = {k: v for k, v in {"q": q, "f": f, "sort": sort, **kw}.items() if v and (k, v) not in (("f", "all"), ("sort", "last_read"))}
        return "/?" + urlencode(p) if p else "/"

    def chip(k):
        return (
            f'<a class="chip{" attn" if k == "needs_match" and counts[k] else ""}" href="{e(link(f=k))}"'
            f"{' aria-current="true"' if k == f else ''}>{T['f_' + k]}<b>{counts[k]}</b></a>"
        )

    # One filter at a time, shown in three groups so the row reads as a
    # choice: by progress, by origin on this Kobo, by Hardcover state.
    chips = "".join(
        f'<div class="fgroup"><span class="gname">{T["g_" + g]}</span>{"".join(chip(k) for k in keys)}</div>' for g, keys in FILTER_GROUPS
    )
    sort_opts = "".join(f'<option value="{k}"{" selected" if k == sort else ""}>{T["sort_" + k]}</option>' for k in SORTS)
    mode_opts = "".join(f'<option value="{m}">{T[m]}</option>' for m in state.MODES)
    body = []
    quiet = quiet_for(con, reader)
    for i, r in enumerate(rows):
        cid = e(r["content_id"])
        mode_sel = "".join(f'<option value="{m}"{" selected" if m == r["mode"] else ""}>{T[m]}</option>' for m in state.MODES)
        body.append(
            f'<tr id="b-{cid}" class="{"on" if state.syncs(r) else "off"}" style="--d:{min(i, 12) * 70}ms" role="row"><td class="book" role="cell">{book_cell(r)}</td>'
            f'<td data-label="{T["col_mode"]}" role="cell"><form method="post" action="/mode"><input type="hidden" name="ids" value="{cid}">'
            f'<input type="hidden" name="back" value="{e(back)}">'
            f'<select name="mode" class="rowmode" aria-label="{T["col_mode"]}">{mode_sel}</select>{NOSCRIPT_SET}</form></td>'
            f'<td data-label="{T["col_state"]}" role="cell">{state_cell(r, back)}</td>'
            f'<td class="hc" data-label="{T["col_hardcover"]}" role="cell"><div>{hc_cell(r, back, hc_status(r, live, quiet))}</div></td></tr>'
        )
    ids = ",".join(r["content_id"] for r in rows)
    table = (
        (
            # The roles say what the tags say already: below 1024px the stylesheet lays the
            # table out as cards, and a browser then stops treating it as a table.
            f'<div class="tablewrap"><table class="books" role="table" aria-label="{T["nav_books"]}"><thead role="rowgroup"><tr role="row">'
            f'<th class="c-book" role="columnheader">{T["col_book"]}</th><th class="c-mode" role="columnheader">{T["col_mode"]}</th>'
            f'<th class="c-state" role="columnheader">{T["col_state"]}</th><th class="c-hc" role="columnheader">{T["col_hardcover"]}</th>'
            f'</tr></thead><tbody role="rowgroup">{"".join(body)}</tbody></table></div>'
        )
        if rows
        else f'<p class="empty">{T["empty"]} <a href="/">{T["empty_reset"]}</a></p>'
    )
    bulk = (
        (
            f'<form class="bulk" method="post" action="/mode" data-confirm="{T["confirm_bulk"].format(n=len(rows), mode="{mode}")}">'
            f'<input type="hidden" name="ids" value="{e(ids)}"><input type="hidden" name="back" value="{e(back)}">'
            f'<input type="hidden" name="bulk" value="1"><label for="bulkmode">{T["set_shown"].format(n=len(rows))}</label>'
            f'<select id="bulkmode" name="mode">{mode_opts}</select><button>{T["apply_bulk"]}</button></form>'
        )
        if rows
        else ""
    )
    if not counts["all"] and not q:  # a new reader: say what to do first
        return frame_for(me, "books", account_pages.start(local=bool(local)))
    # Refresh reloads the same view: search, filter and sort stay as they are.
    keep = "".join(
        f'<input type="hidden" name="{k}" value="{e(v)}">'
        for k, v in (("q", q), ("f", f), ("sort", sort))
        if v and (k, v) not in (("f", "all"), ("sort", "last_read"))
    )
    fcur = f if f in FILTERS else "all"
    total = con.execute("select count(*) from book where reader=?", (reader,)).fetchone()[0]
    first = first_run(con, reader, live)  # says what the line under the title would, and more
    # The sidebar: what the Kobo and Hardcover last did, and the buttons that act on it.
    side = f"""<section class="status" aria-label="{T["status"]}">
{status_items(con, reader, live, dev, j)}
<div class="statusactions">
<form method="get" action="/">{keep}<button>{T["refresh"]}</button></form>
{sync_button(con, reader, live, back, j)}
</div>
</section>"""
    # The sheet: find, filter, and the list. On a phone the filters fold
    # behind one line that names the chosen one (kobo.js).
    return frame_for(
        me,
        "books",
        f"""<main><div class="head"><h2 class="pagehead">{T["nav_books"]}</h2>
{"" if first else f'<p class="intro">{e(T["books_meta"].format(n=total))}</p>'}{LEGEND}</div>
<div class="sheet">{first}
<nav class="toolbar" aria-label="{T["filter"]}">
<form class="find" method="get"><input type="search" name="q" value="{e(q)}" placeholder="{T["search"]}" aria-label="{T["search"]}">
<input type="hidden" name="f" value="{e(f)}"><button>{T["apply"]}</button>
<span class="sortby"><label for="sort">{T["sort_by"]}</label><select id="sort" name="sort" onchange="this.form.submit()">{sort_opts}</select></span></form>
<button type="button" class="ftoggle" aria-expanded="false" aria-controls="fpanel">{FUNNEL}<span>{T["filter"]}: <b>{T["f_" + fcur]}</b></span><span class="n">{counts[fcur]}</span></button>
<div class="filters" id="fpanel">{chips}{bulk}</div>
</nav>
{table}
</div></main>
<dialog id="details" aria-label="{T["details"]}">
<form method="dialog"><button class="close">{T["close"]}</button></form>
<div class="dbody"></div>
</dialog>
<dialog id="lightbox" aria-label="{T["cover_dialog"]}">
<form method="dialog"><button class="close">{T["close"]}</button></form>
<figure><img alt=""><figcaption></figcaption></figure>
</dialog>""",
        side,
        # Without JS the page looks again by itself while a sync runs.
        '<noscript><meta http-equiv="refresh" content="3"></noscript>' if sync_progress(reader) else "",
    )


@app.post("/mode")
def set_mode(
    request: Request, ids: str = Form(...), mode: str = Form(...), back: str = Form(""), bulk: str = Form(""), confirmed: str = Form("")
):
    # Same-origin check: a form posted from another site carries its own Origin.
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if origin and urlparse(origin).hostname not in (PUBLIC_HOST, "localhost", "127.0.0.1"):
        return PlainTextResponse("cross-origin form refused", status_code=403)
    con = db()
    me = me_for(request, con)
    if me is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    reader = me["name"]
    if mode not in state.MODES:
        return PlainTextResponse("unknown sync setting", status_code=400)
    id_list = [i for i in ids.split(",") if i]
    # "Set all shown" asks first. kobo.js asks in a dialog and says so
    # (confirmed); without JS the question is a page of its own.
    if bulk and not confirmed:
        return HTMLResponse(frame_for(me, "books", account_pages.confirm_bulk(len(id_list), mode, ids, back)))
    state.set_mode(con, reader, id_list, mode)
    if request.headers.get("x-requested-with") == "fetch" and len(id_list) == 1:
        return JSONResponse(row_json(con, reader, id_list[0], back))
    return RedirectResponse("/?" + back if back else "/", status_code=303)


@app.post("/state")
def set_state(request: Request, id: str = Form(...), state_: str = Form(..., alias="state"), date: str = Form(""), back: str = Form("")):
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if origin and urlparse(origin).hostname not in (PUBLIC_HOST, "localhost", "127.0.0.1"):
        return PlainTextResponse("cross-origin form refused", status_code=403)
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    con = db()
    try:
        state.set_state(con, reader, id, state_, date if state_ in ("finished", "rereading") else "")
    except ValueError as ex:
        return PlainTextResponse(str(ex), status_code=400)
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(row_json(con, reader, id, back))
    return RedirectResponse("/?" + back if back else "/", status_code=303)


@app.put("/upload")
async def put_upload(request: Request):
    """Device upload: its own bearer token, not the sign-in proxy (the proxy
    lets this path through without a login)."""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    try:
        reader, device = upload.device_for(token, db())
        length = int(request.headers.get("content-length") or 0)
        if length > upload.MAX_BYTES:
            raise upload.UploadError(413, "upload too large")
        import tempfile

        fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".upload")
        try:
            with os.fdopen(fd, "wb") as fh:
                total = 0
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > upload.MAX_BYTES:
                        raise upload.UploadError(413, "upload too large")
                    fh.write(chunk)
            gz = request.headers.get("content-type", "") == "application/gzip"
            result = upload.store_and_import(tmp, gz, reader, device, DATA)
        finally:
            os.unlink(tmp)
    except upload.UploadError as ex:
        return JSONResponse({"ok": False, "error": str(ex)}, status_code=ex.status)
    if token := token_to_use(db(), reader, live_for(reader)):
        job.start(os.path.join(DATA, "state.db"), reader, live_for(reader), token)
    return JSONResponse({"ok": True, **result})


@app.get("/api/stats/{reader}")
def api_stats(request: Request, reader: str):
    """Aggregates only (minutes, current book, finished count), for a
    dashboard such as Home Assistant. Not behind the sign-in proxy, so it
    has a key of its own: off until the reader makes a stats token under
    Settings, then `Authorization: Bearer <token>`. An unknown reader, a
    reader without a token and a wrong token all get the same 401."""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    con = db()
    if not accounts.stats_allowed(con, reader, token):
        return JSONResponse({"error": "a stats token is needed"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return JSONResponse(stats_mod.stats(con, reader))


def to_row(back: str, cid: str) -> RedirectResponse:
    """Back to the same filtered view, scrolled to the book's row."""
    return RedirectResponse(("/?" + back if back else "/") + f"#b-{cid}", status_code=303)


@app.get("/cover/{content_id:path}")
def cover(request: Request, content_id: str, size: str = "thumb"):
    """A book's cover, from kobo-hardcover-sync's own cache (fetched from Kobo once)."""
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    row = db().execute("select image_id from book where reader=? and content_id=?", (reader, content_id)).fetchone()
    path = covers.cover_path(DATA, row["image_id"], size) if row else None
    if path is None:
        return Response(status_code=404, headers={"Cache-Control": "private, max-age=3600"})
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})


@app.get("/collection")
def collection(request: Request):
    """For the device agent (bearer token, like /upload): the collection to
    keep on the Kobo, as text: the name on the first line, then one book
    ContentID per line. Empty when the reader set no collection name."""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    con = db()
    try:
        reader, _device = upload.device_for(token, con)
    except upload.UploadError as ex:
        return PlainTextResponse(str(ex), status_code=ex.status)
    row = accounts.get(con, reader)
    name = (row["kobo_collection"] if row else "") or ""
    if not name.strip():
        return Response(status_code=204)
    ids = [r["content_id"] for r in con.execute("select * from book where reader=? order by last_read desc", (reader,)) if state.syncs(r)]
    return PlainTextResponse(name.strip() + "\n" + "\n".join(ids) + ("\n" if ids else ""))


@app.get("/details/{content_id:path}", response_class=HTMLResponse)
def details(request: Request, content_id: str, back: str = ""):
    """The details dialog's content (fetched by kobo.js), or a page of its own."""
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    con = db()
    r = con.execute("select * from book where reader=? and content_id=?", (reader, content_id)).fetchone()
    if r is None:
        return PlainTextResponse("no such book", status_code=404)
    frag = details_fragment(r, hc_status(r, live_for(reader), quiet_for(con, reader)), back)
    if request.headers.get("x-requested-with") == "fetch":
        return HTMLResponse(frag)
    return HTMLResponse(
        shell(
            f'<main class="dpage"><h1 class="sr">{T["title"]}</h1>'
            f'<p><a href="/?{e(back)}#b-{e(r["content_id"])}">{T["back_to_list"]}</a></p>{frag}</main>'
        )
    )


@app.post("/sync")
def sync_now(request: Request, back: str = Form("")):
    if bad := check_origin(request):
        return bad
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    if local:  # the whole sync, with the Kobo if it is plugged in
        job.begin(reader)

        def whole():
            try:
                runner.sync(local.computer)
            finally:  # also when it ended before Hardcover (no Kobo, another sync holding the lock)
                job.progress.pop(reader, None)

        threading.Thread(target=whole, daemon=True).start()
    elif (token := token_to_use(db(), reader, live_for(reader))) is not None:
        job.start(os.path.join(DATA, "state.db"), reader, live_for(reader), token)  # without a token the run says so itself
    return RedirectResponse("/?" + back if back else "/", status_code=303)  # the same filtered view


@app.get("/sync/status")
def sync_status(request: Request):
    """For kobo.js while a sync runs: where it is, and when it is over, what it said."""
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    p = sync_progress(reader)
    if p is not None:
        return JSONResponse({"running": True, "text": p["text"], "part": p["part"]})
    j = (
        db()
        .execute("select started, finished, status, detail, live from job where reader=? order by started desc limit 1", (reader,))
        .fetchone()
    )
    kind, said = sync_result(j)
    return JSONResponse({"running": False, "kind": kind, "text": said})


@app.post("/pick")
def pick(request: Request, id: str = Form(...), choice: str = Form(...), back: str = Form("")):
    if bad := check_origin(request):
        return bad
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    book_id, pages, title = choice.split("|", 2)
    con = db()
    job.pick(con, reader, id, int(book_id), title, int(pages) if pages else None)
    return answer(request, con, reader, id, back)


@app.post("/research")
def research(request: Request, id: str = Form(...), q: str = Form(...), back: str = Form("")):
    if bad := check_origin(request):
        return bad
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    try:
        cands = hardcover.shown(hardcover.Client(accounts.token_for(db(), reader), tries=1).search(q))
    except hardcover.HardcoverError as ex:
        return PlainTextResponse(str(ex), status_code=502)
    con = db()
    con.execute(
        "update book set hc_how=?, hc_candidates=? where reader=? and content_id=? and hc_book_id is null",
        ("uncertain" if cands else "none", json.dumps(cands), reader, id),
    )
    con.commit()
    return answer(request, con, reader, id, back)


@app.post("/remove")
def remove(request: Request, id: str = Form(...), back: str = Form("")):
    if bad := check_origin(request):
        return bad
    reader = reader_for(request)
    if reader is None:
        return PlainTextResponse(T["unknown_user"], status_code=403)
    try:
        con = db()
        job.remove(con, reader, id, hardcover.Client(accounts.token_for(con, reader)))
    except hardcover.HardcoverError as ex:
        return PlainTextResponse(str(ex), status_code=502)
    return answer(request, con, reader, id, back)


# ---------- sign-up, settings, admin ----------
@app.post("/signup")
def signup(request: Request):
    if bad := check_origin(request):
        return bad
    try:
        accounts.sign_up(
            db(),
            request.headers.get("remote-user") or "",
            request.headers.get("remote-email") or "",
            request.headers.get("remote-name") or "",
        )
    except accounts.AccountError as ex:
        if ex.key != "err_exists":
            return PlainTextResponse(T[ex.key], status_code=403)
    return RedirectResponse("/settings?ok=signed_up", status_code=303)


# Sign-ins that wait for the reader to approve on Hardcover, per reader. In
# memory: one lasts a quarter of an hour, and a restart only means starting again.
_signins: dict[str, oauth.Device | oauth.Browser] = {}


def settings_page(
    con,
    me,
    ok: str = "",
    err: str = "",
    detail: str = "",
    status: int = 200,
    new_stats_token: str = "",
    checks: list | None = None,
    waiting: bool = False,
) -> HTMLResponse:
    me = accounts.get(con, me["name"])  # after a change: the row as it is now
    body = account_pages.settings(
        me,
        accounts.logins(me),
        accounts.token_state(con, me["name"]),
        accounts.can_store_tokens(),
        accounts.devices(con, me["name"]),
        account_pages.flash(ok, err, detail),
        new_stats_token,
        {"eject": computer_config.load().eject_after_sync, "kept_in": local.computer.secret_place(local_page.HARDCOVER)} if local else None,
        checks,
        {
            "kind": accounts.token_kind(con, me["name"]),
            "signin": signin if isinstance(signin := _signins.get(me["name"]), oauth.Device) else None,
            "waiting": waiting,
        }
        if oauth.available()
        else None,
    )
    return HTMLResponse(frame_for(me, "settings", body), status_code=status)


# A new stats token is shown once, after a redirect: the browser ends up on
# an ordinary page, so reloading or restoring that tab cannot send the form
# again and silently replace the token that was just put to use. The token
# waits here, in memory, for that one page view.
_to_show: dict[str, tuple[str, str, float]] = {}
SHOW_SECONDS = 120


def _keep_to_show(reader: str, token: str) -> str:
    now = time.monotonic()
    for k in [k for k, v in _to_show.items() if v[2] < now]:
        del _to_show[k]
    key = secrets.token_urlsafe(16)
    _to_show[key] = (reader, token, now + SHOW_SECONDS)
    return key


def _take_to_show(reader: str, key: str) -> str:
    kept = _to_show.get(key)
    if not kept or kept[0] != reader:  # not there, or someone else's
        return ""
    del _to_show[key]
    return kept[1] if kept[2] >= time.monotonic() else ""


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request, ok: str = "", show: str = ""):
    con, me, bad = guard(request)
    if bad:
        return bad
    token = _take_to_show(me["name"], show) if show else ""
    if show and not token:  # that page was already shown once
        ok = ""
    resp = settings_page(con, me, ok=ok, new_stats_token=token)
    if token:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def change(request: Request, ok: str, fn):
    """One settings form: fn(con, reader name) makes the change; a refusal
    comes back on the page, next to the form."""
    con, me, bad = guard(request)
    if bad:
        return bad
    try:
        fn(con, me["name"])
    except accounts.AccountError as ex:
        return settings_page(con, me, err=ex.key, status=400)
    return RedirectResponse(f"/settings?ok={ok}", status_code=303)


@app.post("/settings/profile")
def settings_profile(request: Request, display_name: str = Form("")):
    return change(request, "profile", lambda con, name: accounts.set_display_name(con, name, display_name))


@app.post("/settings/collection")
def settings_collection(request: Request, collection: str = Form("")):
    return change(request, "collection", lambda con, name: accounts.set_collection(con, name, collection))


@app.post("/settings/live")
def settings_live(request: Request, live: str = Form("0")):
    return change(request, "live" if live == "1" else "dry", lambda con, name: accounts.set_live(con, name, live == "1"))


@app.post("/settings/devices/add")
def settings_device_add(request: Request, device: str = Form(""), hash: str = Form("")):
    return change(request, "device_added", lambda con, name: accounts.add_device(con, name, device, hash))


@app.post("/settings/devices/remove")
def settings_device_remove(request: Request, hash: str = Form("")):
    return change(request, "device_removed", lambda con, name: accounts.remove_device(con, name, hash))


@app.post("/settings/token")
def settings_token(request: Request, token: str = Form("")):
    """Checked with Hardcover first: a token that does not work is never stored."""
    con, me, bad = guard(request)
    if bad:
        return bad
    token = hardcover.bare(token)
    try:
        if not accounts.can_store_tokens():
            raise accounts.AccountError("err_no_key")
        if not token:
            raise accounts.AccountError("err_token_empty")
        who = hardcover.Client(token, tries=1).whoami()
        accounts.set_token(con, me["name"], token, str(who.get("username") or ""))
    except accounts.AccountError as ex:
        return settings_page(con, me, err=ex.key, status=400)
    except hardcover.HardcoverError as ex:
        return settings_page(con, me, err="err_token_refused", detail=str(ex), status=400)
    return RedirectResponse("/settings?ok=token", status_code=303)


@app.post("/settings/connect")
def settings_connect(request: Request):
    """Start signing in to Hardcover (engine/oauth.py): ask for a code, and
    show the reader where to approve it."""
    con, me, bad = guard(request)
    if bad:
        return bad
    try:
        if not accounts.can_store_tokens():
            raise accounts.AccountError("err_no_key")
        if local and oauth.loopback():  # on the reader's own computer: in the browser, back to this page
            sign_in = oauth.browser_start(local.port)
            _signins[me["name"]] = sign_in
            return RedirectResponse(sign_in.url, status_code=303)
        _signins[me["name"]] = oauth.start()
    except accounts.AccountError as ex:
        return settings_page(con, me, err=ex.key, status=400)
    except oauth.OAuthError as ex:
        return settings_page(con, me, err="err_connect", detail=f"{ex}.", status=502)
    resp = settings_page(con, me)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get(oauth.CALLBACK)
def oauth_callback(request: Request):
    """Where Hardcover sends the browser back after a sign-in started on the
    local page. The browser comes from hardcover.app, so the page's session
    cookie (SameSite=Strict) does not come along: what makes the answer
    count is that it belongs to a sign-in started here (its state), and the
    code is worth nothing without the PKCE secret only this process holds.
    The page it ends on sends the browser on to Settings from this origin,
    where the cookie applies again."""
    if not local:
        return PlainTextResponse("Not Found", status_code=404)
    answer = dict(request.query_params)
    con = db()
    name = next((n for n, s in _signins.items() if isinstance(s, oauth.Browser) and s.state == answer.get("state")), None)
    if name is None:  # an old tab, a second visit, or an answer for another sign-in
        return _back_to_settings(T["s_connect_lost"], "/settings")
    sign_in = _signins.pop(name)
    try:
        got = oauth.browser_finish(sign_in, answer)
        who = hardcover.Client(got.access, tries=1).whoami()
        accounts.set_token(con, name, got.pack(), str(who.get("username") or ""))
    except (oauth.OAuthError, hardcover.HardcoverError, accounts.AccountError) as ex:
        detail = T[ex.key] if isinstance(ex, accounts.AccountError) else f"{ex}."
        return _back_to_settings(f"{T['err_connect']} {detail}", "/settings")
    return _back_to_settings(T["ok_connected"], "/settings?ok=connected")


def _back_to_settings(said: str, to: str) -> HTMLResponse:
    """A moment's page that says how the sign-in went and goes on to Settings by itself."""
    resp = HTMLResponse(
        shell(
            f'<main class="solo"><h1>{T["title"]}</h1><p>{e(said)}</p><p><a href="{e(to)}">{T["s_connect_on"]}</a></p></main>',
            head=f'<meta http-equiv="refresh" content="1;url={e(to)}">',
        )
    )
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"  # the address carried the code
    return resp


@app.post("/settings/connect/check")
def settings_connect_check(request: Request):
    """Ask Hardcover once whether the reader has approved. The page does
    this every few seconds by itself (and gets a short answer); the button
    does it for a browser without JavaScript (and gets the page)."""
    con, me, bad = guard(request)
    if bad:
        return bad
    name, quiet = me["name"], request.headers.get("x-requested-with") == "fetch"
    device = _signins.get(name)
    if device is None:  # nothing waiting: done in another tab, cancelled, or the server restarted
        return JSONResponse({"done": True}) if quiet else RedirectResponse("/settings", status_code=303)
    try:
        got = oauth.collect(device)
        if isinstance(got, int):  # not yet; ask again after this many seconds
            _signins[name] = dataclasses.replace(device, interval=got)
            return JSONResponse({"done": False, "wait": got}) if quiet else settings_page(con, me, waiting=True)
        who = hardcover.Client(got.access, tries=1).whoami()
        accounts.set_token(con, name, got.pack(), str(who.get("username") or ""))
    except (oauth.OAuthError, hardcover.HardcoverError, accounts.AccountError) as ex:
        _signins.pop(name, None)
        if quiet:  # the page reloads and the reader starts again
            return JSONResponse({"done": True})
        detail = T[ex.key] if isinstance(ex, accounts.AccountError) else f"{ex}."
        return settings_page(con, me, err="err_connect", detail=detail, status=400)
    _signins.pop(name, None)
    if quiet:
        return JSONResponse({"done": True, "to": "/settings?ok=connected"})
    return RedirectResponse("/settings?ok=connected", status_code=303)


@app.post("/settings/connect/cancel")
def settings_connect_cancel(request: Request):
    con, me, bad = guard(request)
    if bad:
        return bad
    _signins.pop(me["name"], None)
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/check")
def settings_check(request: Request):
    """The Check card (doctor.py): look at everything a sync depends on,
    change nothing. A form, not a link, because it asks Hardcover a
    question, and looking at a page never does that."""
    con, me, bad = guard(request)
    if bad:
        return bad
    if local:
        checks = doctor.computer_checks(local.computer, by_hand=False)
    else:
        name = me["name"]
        token = accounts.token_peek(con, name)  # as it is kept: the check renews nothing
        checks = doctor.server_checks(
            con,
            name,
            accounts.token_state(con, name),
            token,
            accounts.can_store_tokens(),
            accounts.devices(con, name),
            run_out=accounts.has_token(con, name) and not token,
        )
    resp = settings_page(con, me, checks=checks)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/settings/eject")
def settings_eject(request: Request, eject: str = Form("0")):
    """Local mode: eject the Kobo after a sync that changed something."""
    con, me, bad = guard(request)
    if bad:
        return bad
    if not local:
        return PlainTextResponse(T["not_in_server_mode"], status_code=404)
    cfg = computer_config.load()
    cfg.eject_after_sync = eject == "1"
    computer_config.save(cfg)
    return RedirectResponse("/settings?ok=" + ("eject_on" if cfg.eject_after_sync else "eject_off"), status_code=303)


@app.post("/settings/stats/token")
def settings_stats_token(request: Request):
    """Make (or replace) the stats token. It is shown once, on the page
    this redirects to; only its hash is kept."""
    con, me, bad = guard(request)
    if bad:
        return bad
    key = _keep_to_show(me["name"], accounts.new_stats_token(con, me["name"]))
    return RedirectResponse(f"/settings?ok=stats_on&show={key}#stats", status_code=303)


@app.post("/settings/stats/off")
def settings_stats_off(request: Request):
    return change(request, "stats_off", lambda con, name: accounts.clear_stats_token(con, name))


@app.post("/settings/token/remove")
def settings_token_remove(request: Request):
    return change(request, "token_removed", lambda con, name: accounts.clear_token(con, name))


def admin_page(con, me, ok: str = "", err: str = "", status: int = 200) -> HTMLResponse:
    me = accounts.get(con, me["name"])
    body = account_pages.admin(
        me,
        accounts.overview(con),
        accounts.sync_problems(con),
        accounts.storage(DATA),
        accounts.can_store_tokens(),
        account_pages.flash(ok, err),
    )
    return HTMLResponse(frame_for(me, "admin", body), status_code=status)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, ok: str = ""):
    con, me, bad = guard(request, admin=True)
    return bad or admin_page(con, me, ok=ok)


@app.post("/admin/role")
def admin_role(request: Request, name: str = Form(...), admin: str = Form("0")):
    con, me, bad = guard(request, admin=True)
    if bad:
        return bad
    try:
        accounts.set_admin(con, name, admin == "1")
    except accounts.AccountError as ex:
        return admin_page(con, me, err=ex.key, status=400)
    # Someone who gave up their own admin role has no admin page to return to.
    return RedirectResponse("/admin?ok=role" if (name != me["name"] or admin == "1") else "/settings?ok=role", status_code=303)


@app.post("/admin/remove")
def admin_remove(request: Request, name: str = Form(...)):
    con, me, bad = guard(request, admin=True)
    if bad:
        return bad
    try:
        accounts.remove_reader(con, name, DATA)
    except accounts.AccountError as ex:
        return admin_page(con, me, err=ex.key, status=400)
    return RedirectResponse("/admin?ok=reader_removed" if name != me["name"] else "/", status_code=303)
