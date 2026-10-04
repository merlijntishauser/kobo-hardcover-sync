"""The sign-up, Settings and Admin pages, as HTML for web.shell().
Pure functions: web.py does the checking and the changing."""

from __future__ import annotations

import json
import re

from .. import doctor
from ..engine.hardcover import NEW_TOKEN_URL
from . import marks
from .fmt import e, fmt_bytes, fmt_dt
from .strings import T


def plural(key: str, n: int) -> str:
    one, many = T[key]
    return (one if n == 1 else many).format(n=n)


def line(kind: str, text: str) -> str:
    """The page's status language: a mark carries the colour, the text stays plain."""
    return marks.line(kind, text)


def flash(ok: str = "", err: str = "", detail: str = "") -> str:
    if err and err in T:
        return (
            f'<div class="flash bad" role="alert">{line("err", T[err])}'
            + (f'<p class="muted">{e(detail)}</p>' if detail else "")
            + "</div>"
        )
    if ok and "ok_" + ok in T:
        return f'<div class="flash" role="status">{line("ok", T["ok_" + ok])}</div>'
    return ""


def signup(who: str) -> str:
    return (
        f'<main class="cards"><section class="card"><h2>{T["signup_title"]}</h2>'
        f"<p>{e(T['signup_who'].format(who=who))}</p>"
        + "".join(f"<p>{e(p)}</p>" for p in T["signup_what"])
        + f'<form method="post" action="/signup"><button class="solid">{T["signup_btn"]}</button></form></section></main>'
    )


def start(local: bool = False) -> str:
    """Instead of an empty list: what a new reader does first."""
    steps = "".join(f"<li>{e(s)}</li>" for s in T["start_steps_local" if local else "start_steps"])
    return (
        f'<main class="cards"><section class="card"><h2>{T["start_title"]}</h2><ol>{steps}</ol>'
        f'<p><a class="details" href="/settings">{T["start_btn"]}</a></p></section></main>'
    )


def confirm_bulk(n: int, mode: str, q: str, f: str, back: str) -> str:
    """The question before "Set all in this list", for a browser without JS
    (with JS, kobo.js asks the same in a dialog). The list goes on as its
    search and filter, with the count asked about."""
    keep = "".join(
        f'<input type="hidden" name="{k}" value="{e(v)}">'
        for k, v in (("q", q), ("f", f), ("n", str(n)), ("mode", mode), ("back", back), ("bulk", "1"), ("confirmed", "1"))
    )
    return (
        f'<main class="cards"><section class="card"><h2>{e(T["confirm_bulk"][n != 1].format(n=n, mode=T[mode]))}</h2>'
        f"<p>{e(T['confirm_bulk_what'])}</p>"
        f'<div class="btnrow"><form method="post" action="/mode">{keep}<button class="solid">{e(T["confirm_bulk_yes"].format(mode=T[mode]))}</button></form>'
        f'<a class="details" href="{e("/?" + back if back else "/")}">{T["cancel"]}</a></div></section></main>'
    )


def bulk_changed(was: int, now: int, back: str) -> str:
    """Why "Set all" changed nothing: the list no longer holds the books the reader saw counted."""
    return (
        f'<main class="cards"><section class="card"><h2>{e(T["bulk_changed"])}</h2>'
        f"<p>{e(T['bulk_changed_why'].format(was=was, now=now))}</p>"
        f'<div class="btnrow"><a class="details" href="{e("/?" + back if back else "/")}">{T["bulk_changed_back"]}</a></div></section></main>'
    )


def _with_code(text: str) -> str:
    """Escaped, with `a command` set as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", e(text))


CHECK_DOT = {doctor.OK: "ok", doctor.NOTE: "none", doctor.WARN: "warn", doctor.FAIL: "err"}


def check_card(checks: list | None, local: bool) -> str:
    """The Check card. checks: None before the button was pressed, else what
    doctor found. The state is in the mark's colour and shape and, for someone who
    does not see it, in a word before the line."""
    result = ""
    if checks is not None:
        worst = "err" if doctor.problems(checks) else "warn" if any(c.state == doctor.WARN for c in checks) else "ok"
        rows = "".join(
            f'<li class="group">{e(group)}</li>'
            + "".join(
                f'<li><div class="act {CHECK_DOT[c.state]}">{marks.mark(CHECK_DOT[c.state])}<span><span class="sr">{e(doctor.WORDS[c.state])}: </span>'
                f"<b>{e(c.what)}</b> {_with_code(c.found)}</span></div>"
                + (f'<div class="sub">{T["s_check_todo"]} {_with_code(c.todo)}</div>' if c.todo else "")
                + "</li>"
                for c in some
            )
            for group, some in doctor.grouped(checks)
        )
        result = f'<div class="found" role="status">{line(worst, doctor.summary(checks))}</div><ul class="checks">{rows}</ul>'
    return (
        f'<section class="card" id="check"><h2>{T["s_check"]}</h2>{result}'
        f'<form method="post" action="/settings/check#check"><button>{T["s_check_again" if checks is not None else "s_check_btn"]}</button></form>'
        f'<p class="hint">{e(T["s_check_help_local" if local else "s_check_help"])}</p></section>'
    )


def _signin(device, waiting: bool) -> str:
    """A sign-in that waits for the reader: where to approve, the code to
    recognise it by, and a button for when they have. The page asks by
    itself every few seconds (kobo.js); the button does the same without."""
    return (
        f'<div class="signin" data-poll="/settings/connect/check" data-every="{int(device.interval)}">'
        f"<ol><li>{e(T['s_connect_step1'])}"
        f'<div><a class="details" href="{e(device.link_with_code)}" target="_blank" rel="noopener noreferrer">{T["s_connect_open"]}</a></div></li>'
        f'<li>{e(T["s_connect_step2"])} <code class="code">{e(device.user_code)}</code></li>'
        f"<li>{e(T['s_connect_step3'])}</li></ol>"
        + (line("warn", T["s_connect_waiting"]) if waiting else "")
        + f'<div class="btnrow"><form method="post" action="/settings/connect/check#hardcover"><button class="solid">{T["s_connect_done"]}</button></form>'
        f'<form method="post" action="/settings/connect/cancel"><button>{T["s_connect_cancel"]}</button></form></div></div>'
    )


def _token_line(token_state: str, can_store: bool, hc_user: str) -> str:
    if token_state == "stored":
        return line("ok", T["tok_stored_as"].format(user="@" + hc_user) if hc_user else T["tok_stored"])
    if token_state == "unreadable":
        return line("err", T["tok_unreadable"])
    if token_state == "env":
        return line("ok", T["tok_env"])
    return line("none", T["tok_none"])


def settings(
    me,
    logins: list[str],
    token_state: str,
    can_store: bool,
    devices: list,
    msg: str = "",
    new_stats_token: str = "",
    local: dict | None = None,
    checks: list | None = None,
    connect: dict | None = None,
) -> str:
    """local: None in server mode; in local mode what this computer does
    ({"eject": bool, "kept_in": where the token is kept}). Local mode has no
    logins, devices or stats. checks: what the Check card found, when its
    button was just pressed. connect: None when this installation has no
    Hardcover app to connect through; else {"kind": "oauth" | "pasted" | "",
    "signin": a sign-in that waits for the reader (oauth.Device) or None,
    "waiting": the reader said they approved and Hardcover has not seen it}."""
    has_token = token_state in ("stored", "env")
    you = (
        f'<section class="card"><h2>{T["s_profile"]}</h2>'
        f'<form method="post" action="/settings/profile" class="field"><label for="display_name">{T["s_display_name"]}</label>'
        f'<div class="inputs"><input type="text" id="display_name" name="display_name" value="{e(me["display_name"] or me["name"])}" maxlength="60" required>'
        f"<button>{T['save']}</button></div></form>"
        + (
            ""
            if local is not None
            else f"<dl><div><dt>{T['s_logins']}</dt><dd>{e(', '.join(logins))}</dd></div>"
            f"<div><dt>{T['s_reader']}</dt><dd>{e(me['name'])}"
            + (f' <span class="tag role">{T["s_admin"]}</span>' if me["is_admin"] else "")
            + "</dd></div></dl>"
        )
        + "</section>"
    )

    connected = connect is not None and connect["kind"] == "oauth"
    if can_store:
        # With a way to connect, pasting a token is the second way: folded away, and its button is not the filled one.
        filled = "" if connect is not None else ' class="solid"'
        paste = (
            f'<form method="post" action="/settings/token" class="field"><label for="token">{T["s_token_replace"] if token_state == "stored" and not connected else T["s_token"]}</label>'
            f'<div class="inputs"><input type="password" id="token" name="token" autocomplete="off" spellcheck="false" required>'
            f"<button{filled}>{T['s_token_save']}</button></div>"
            f'<p class="hint">{e(T["s_token_help_local" if local is not None else "s_token_help"])} <a href="{e(NEW_TOKEN_URL)}" target="_blank" rel="noopener noreferrer">{T["s_token_link"]}</a></p></form>'
        )
        if connect is None:
            token_form = paste
        elif connect["signin"] is not None:
            token_form = _signin(connect["signin"], connect.get("waiting", False))
        else:
            start = (
                ""
                if connected
                else f'<form method="post" action="/settings/connect#hardcover"><button class="solid">{T["s_connect"]}</button></form>'
                f'<p class="hint">{e(T["s_connect_help"])}</p>'
            )
            token_form = f'{start}<details class="paste"><summary>{T["s_paste_instead"]}</summary>{paste}</details>'
    else:
        token_form = line("warn", T["tok_no_key"])
    token_actions = ""
    if token_state == "stored":  # whether it still works is the Check card's business
        confirm, label = ("s_disconnect_confirm", "s_disconnect") if connected else ("s_token_remove_confirm", "s_token_remove")
        token_actions = (
            f'<div class="btnrow"><form method="post" action="/settings/token/remove" data-confirm="{e(T[confirm])}">'
            f'<button class="danger">{T[label]}</button></form></div>'
        )
    if me["hardcover_live"]:
        mode = (
            line("ok", T["s_live"]) + f'<form method="post" action="/settings/live"><input type="hidden" name="live" value="0">'
            f"<button>{T['s_go_dry']}</button></form>"
        )
    else:
        mode = (
            line("warn", T["s_dry"]) + f'<form method="post" action="/settings/live" data-confirm="{e(T["s_go_live_confirm"])}">'
            f'<input type="hidden" name="live" value="1"><button class="primary"{"" if has_token else " disabled"}>{T["s_go_live"]}</button></form>'
        )
    kept = f'<p class="hint">{e(T["s_token_kept"].format(place=local["kept_in"]))}</p>' if local is not None and has_token else ""
    hardcover = (
        f'<section class="card" id="hardcover"><h2>{T["s_hardcover"]}</h2>{_token_line(token_state, can_store, me["hardcover_user"] or "")}{kept}'
        f'{token_actions}{token_form}<h3>{T["s_mode"]}</h3><div class="moderow">{mode}</div></section>'
    )

    size = me["list_size"] if me["list_size"] is not None else 100
    sizes = "".join(f'<option value="{n}"{" selected" if n == size else ""}>{n or T["s_list_all"]}</option>' for n in (25, 50, 100, 0))
    booklist = (
        f'<section class="card" id="list"><h2>{T["s_list"]}</h2>'
        f'<form method="post" action="/settings/list" class="field"><label for="listsize">{T["s_list_size"]}</label>'
        f'<div class="inputs"><select id="listsize" name="size">{sizes}</select>'
        f'<button>{T["save"]}</button></div><p class="hint">{e(T["s_list_help"])}</p></form></section>'
    )

    collection = (
        f'<section class="card"><h2>{T["s_collection"]}</h2>'
        f'<form method="post" action="/settings/collection" class="field"><label for="collection">{T["s_collection_name"]}</label>'
        f'<div class="inputs"><input type="text" id="collection" name="collection" value="{e(me["kobo_collection"] or "")}" maxlength="60">'
        f'<button>{T["save"]}</button></div><p class="hint">{e(T["s_collection_help"])}</p></form></section>'
    )

    rows = "".join(
        f"<li><div><b>{e(d['device'])}</b> <code>{e(d['token_sha256'][:8])}</code>"
        f'<div class="sub">{T["s_device_added"]} {e(fmt_dt(d["created"]))}, '
        + (f"{T['s_device_last']} {e(fmt_dt(d['last_import']))}" if d["last_import"] else T["s_device_never"])
        + "</div></div>"
        f'<form method="post" action="/settings/devices/remove" data-confirm="{e(T["s_device_remove_confirm"])}">'
        f'<input type="hidden" name="hash" value="{e(d["token_sha256"])}"><button class="danger">{T["s_device_remove"]}</button></form></li>'
        for d in devices
    )
    devs = (
        f'<section class="card"><h2>{T["s_devices"]}</h2>'
        + (f'<ul class="devices">{rows}</ul>' if rows else line("none", T["s_no_devices"]))
        + f'<form method="post" action="/settings/devices/add" class="field adddev"><div class="pair">'
        f'<div><label for="device">{T["s_device_name"]}</label><input type="text" id="device" name="device" maxlength="40" placeholder="{T["s_device_name_hint"]}" required></div>'
        f'<div class="grow"><label for="hash">{T["s_device_hash"]}</label><input type="text" id="hash" name="hash" maxlength="80" spellcheck="false" autocomplete="off" placeholder="{T["s_device_hash_hint"]}" required></div>'
        f'<button>{T["s_device_add"]}</button></div><p class="hint">{e(T["s_devices_help"])}</p></form></section>'
    )
    # Reading stats for a dashboard: off until the reader makes a token, which is shown this once.
    stats_on = bool(me["stats_token_sha256"])
    shown = (
        f'<div class="flash" role="status"><p class="reveal">{T["s_stats_token_once"]} <code class="secret">{e(new_stats_token)}</code></p>'
        f'<p class="muted">{e(T["s_stats_use"].format(name=me["name"]))}</p></div>'
        if new_stats_token
        else ""
    )
    stats = (
        f'<section class="card" id="stats"><h2>{T["s_stats"]}</h2>'
        + line("ok" if stats_on else "none", T["s_stats_on"] if stats_on else T["s_stats_off"])
        + shown
        + '<div class="btnrow"><form method="post" action="/settings/stats/token"'
        + (f' data-confirm="{e(T["s_stats_new_confirm"])}"' if stats_on else "")
        + f"><button>{T['s_stats_new'] if stats_on else T['s_stats_make']}</button></form>"
        + (
            f'<form method="post" action="/settings/stats/off" data-confirm="{e(T["s_stats_off_confirm"])}">'
            f'<button class="danger">{T["s_stats_turn_off"]}</button></form>'
            if stats_on
            else ""
        )
        + f'</div><p class="hint">{e(T["s_stats_help"].format(name=me["name"]))}</p></section>'
    )
    if local is not None:
        on = local["eject"]
        computer = (
            f'<section class="card" id="computer"><h2>{T["s_computer"]}</h2>'
            + line("ok" if on else "none", T["s_eject_on"] if on else T["s_eject_off"])
            + f'<form method="post" action="/settings/eject"><input type="hidden" name="eject" value="{0 if on else 1}">'
            f"<button>{T['s_eject_turn_off'] if on else T['s_eject_turn_on']}</button></form>"
            f'<p class="hint">{e(T["s_eject_help"])}</p></section>'
        )
        return (
            f'<main class="cards"><h2 class="pagetitle">{T["settings_title"]}</h2>{msg}{you}{hardcover}{booklist}{collection}{computer}'
            f"{check_card(checks, True)}</main>"
        )
    return (
        f'<main class="cards"><h2 class="pagetitle">{T["settings_title"]}</h2>{msg}{you}{hardcover}{booklist}{collection}{devs}{stats}'
        f"{check_card(checks, False)}</main>"
    )


def _problem(j) -> str:
    try:
        d = json.loads(j["detail"] or "{}")
    except ValueError:
        d = {}
    return str(d.get("fatal") or plural("a_books_failed", int(d.get("errors") or 0)))


def admin(me, rows: list[dict], problems: list, storage: dict, can_store: bool, msg: str = "") -> str:
    body = []
    n_admins = sum(1 for r in rows if r["is_admin"])
    for r in rows:
        tags = (f' <span class="tag role">{T["a_admin"]}</span>' if r["is_admin"] else "") + (
            f' <span class="muted">({T["a_you"]})</span>' if r["name"] == me["name"] else ""
        )
        if r["token"] in ("none",):
            hc = line("none", T["a_no_token"])
        elif r["token"] == "unreadable":
            hc = line("err", T["a_token_unreadable"])
        else:
            kind = "warn" if not r["live"] else {"ok": "ok", "running": "next", None: "next"}.get(r["sync_status"], "err")
            hc = line(kind, T["a_live"] if r["live"] else T["a_dry"])
        hc += f'<div class="sub">{e(T["a_last_sync"].format(when=fmt_dt(r["last_sync"])) if r["last_sync"] else T["a_never_synced"])}</div>'
        kobo = (
            line(
                "ok" if r["last_upload"] else "none",
                T["a_uploaded"].format(when=fmt_dt(r["last_upload"])) if r["last_upload"] else T["a_no_upload"],
            )
            + f'<div class="sub">{e(plural("a_devices", r["devices"]))}</div>'
        )
        name = f'<input type="hidden" name="name" value="{e(r["name"])}">'
        role = (
            f'<form method="post" action="/admin/role">{name}<input type="hidden" name="admin" value="{0 if r["is_admin"] else 1}">'
            f"<button>{T['a_remove_admin'] if r['is_admin'] else T['a_make_admin']}</button></form>"
        )
        remove = (
            f'<form method="post" action="/admin/remove" data-confirm="{e(T["a_remove_confirm"].format(name=r["display_name"]))}">{name}'
            f'<button class="danger">{T["a_remove"]}</button></form>'
        )
        # The last admin can neither step down nor be removed: no buttons that would only refuse.
        actions = (
            f'<span class="muted">{T["a_only_admin"]}</span>'
            if r["is_admin"] and n_admins <= 1
            else f'<div class="btnrow">{role}{remove}</div>'
        )
        body.append(
            f'<tr id="r-{e(r["name"])}" role="row"><td class="who" role="cell"><div class="rname">{e(r["display_name"])}{tags}</div>'
            f'<div class="sub">{e(", ".join(r["logins"]) or r["name"])}</div></td>'
            f'<td data-label="{T["a_kobo"]}" role="cell"><div>{kobo}</div></td><td data-label="{T["a_hardcover"]}" role="cell"><div>{hc}</div></td>'
            f'<td data-label="{T["a_books"]}" role="cell">{e(T["a_syncing"].format(on=r["syncing"], n=r["books"]))}</td>'
            f'<td data-label="{T["a_actions"]}" role="cell">{actions}</td></tr>'
        )
    readers = (
        f'<section class="card wide"><h2>{T["a_readers"]}</h2><table class="readers" role="table" aria-label="{T["a_readers"]}">'
        f'<thead role="rowgroup"><tr role="row"><th role="columnheader">{T["a_reader"]}</th><th role="columnheader">{T["a_kobo"]}</th>'
        f'<th role="columnheader">{T["a_hardcover"]}</th><th role="columnheader">{T["a_books"]}</th>'
        f'<th role="columnheader">{T["a_actions"]}</th></tr></thead>'
        f'<tbody role="rowgroup">{"".join(body)}</tbody></table></section>'
    )
    plist = "".join(
        f'<li>{line("err", f"{fmt_dt(j['started'])}, {j['reader']}")}<div class="sub">{e(_problem(j))}</div></li>' for j in problems
    )
    probs = (
        f'<section class="card"><h2>{T["a_problems"]}</h2>'
        + (f'<ul class="devices">{plist}</ul>' if plist else line("ok", T["a_no_problems"]))
        + "</section>"
    )
    store = (
        f'<section class="card"><h2>{T["a_storage"]}</h2><dl>'
        + "".join(f"<div><dt>{T['a_' + k]}</dt><dd>{e(fmt_bytes(storage[k]))}</dd></div>" for k in ("database", "snapshots", "covers"))
        + f"</dl><h3>{T['a_key']}</h3>{line('ok', T['a_key_ok']) if can_store else line('warn', T['a_key_missing'])}</section>"
    )
    return (
        f'<main class="cards admin"><h2 class="pagetitle">{T["admin_title"]}</h2><p class="muted intro">{e(T["admin_intro"])}</p>'
        f'{msg}{readers}<div class="two">{probs}{store}</div></main>'
    )
