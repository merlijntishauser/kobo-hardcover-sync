"""Readers, their devices and their Hardcover tokens.

Everything a reader manages lives in state.db, so the page can do it and
nobody edits files on the server:

- `reader`: the logins (forward-auth Remote-User / Remote-Email) that map to
  a reader, the display name, live or dry run, the Kobo collection name,
  whether the reader is an admin, and the Hardcover token.
- `device_token`: the SHA-256 of each upload token, with its reader and
  device. The token itself stays on the device that made it.

The Hardcover token is encrypted with the key in KHS_SECRET_KEY
(Fernet: 32 random bytes, url-safe base64). The key is not in the database
or its backups. Without a key no token can be stored on the page, and the
older HARDCOVER_TOKEN_<READER> environment variable keeps working.

A reader only ever reads or changes their own rows. An admin sees who the
readers are and how their sync is doing (counts), never a token or a book.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil

import yaml
from cryptography.fernet import Fernet, InvalidToken

from ..engine import state
from ..env import env
from .upload import safe

HASH = re.compile(r"^[0-9a-f]{64}$")
DEVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
SYNCING = "(mode='on' or (mode='auto' and history=0))"  # state.syncs, in SQL


class AccountError(Exception):
    """Carries a key of strings.T: the text shown to the reader."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


# ---------- the key ----------
def _fernet():
    key = (env("SECRET_KEY") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key)
    except (ValueError, TypeError):  # not 32 url-safe base64 bytes
        return None


LOCAL_READER = "me"


def local_reader(con, display: str = ""):
    """Local mode's one reader, made on first use: in dry run like any new
    reader, and not an admin (there is nothing to administer)."""
    row = get(con, LOCAL_READER)
    if row is None:
        con.execute(
            "insert into reader (name, display_name, identities, is_admin, hardcover_live, created) values (?,?,?,0,0,?)",
            (LOCAL_READER, (display or LOCAL_READER).strip()[:60], "[]", state.now()),
        )
        con.commit()
        row = get(con, LOCAL_READER)
    return row


def can_store_tokens() -> bool:
    if token_store is not None:
        return True
    return _fernet() is not None


def _env_token(name: str) -> str:
    return os.environ.get("HARDCOVER_TOKEN_" + re.sub(r"[^A-Z0-9]", "_", name.upper()), "").strip()


# ---------- readers ----------
def get(con, name: str):
    return con.execute("select * from reader where name=?", (name,)).fetchone()


def all_readers(con) -> list:
    return con.execute("select * from reader order by created, name").fetchall()


def logins(row) -> list[str]:
    try:
        return [str(i) for i in json.loads(row["identities"] or "[]")]
    except ValueError:
        return []


def by_identity(con, ids) -> object | None:
    """The reader one of these logins belongs to."""
    want = {str(i).strip().lower() for i in ids if i and str(i).strip()}
    if not want:
        return None
    for r in all_readers(con):
        if want & set(logins(r)):
            return r
    return None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40]


def sign_up(con, user: str, email: str, display: str = "") -> str:
    """A new reader for this login, in dry run. The very first reader of an
    installation becomes its admin."""
    ids = sorted({v.strip().lower() for v in (user, email) if v and v.strip()})
    if not ids:
        raise AccountError("err_no_identity")
    if by_identity(con, ids) is not None:
        raise AccountError("err_exists")
    base = slug(user) or slug((email or "").split("@")[0]) or "reader"
    name, n = base, 1
    while get(con, name) is not None:
        n += 1
        name = f"{base}-{n}"
    first = con.execute("select 1 from reader where is_admin=1").fetchone() is None
    con.execute(
        "insert into reader (name, display_name, identities, is_admin, hardcover_live, created) values (?,?,?,?,0,?)",
        (name, (display or user or name).strip()[:60], json.dumps(ids), int(first), state.now()),
    )
    con.commit()
    return name


def set_display_name(con, name: str, display: str) -> None:
    display = " ".join((display or "").split())[:60]
    if not display:
        raise AccountError("err_name_empty")
    con.execute("update reader set display_name=? where name=?", (display, name))
    con.commit()


def set_collection(con, name: str, collection: str) -> None:
    con.execute("update reader set kobo_collection=? where name=?", (" ".join((collection or "").split())[:60] or None, name))
    con.commit()


def set_live(con, name: str, live: bool) -> None:
    if live and not token_for(con, name):
        raise AccountError("err_live_needs_token")
    con.execute("update reader set hardcover_live=? where name=?", (int(bool(live)), name))
    con.commit()


def admins(con) -> int:
    return con.execute("select count(*) from reader where is_admin=1").fetchone()[0]


def set_admin(con, name: str, admin: bool) -> None:
    row = get(con, name)
    if row is None:
        raise AccountError("err_no_reader")
    if row["is_admin"] and not admin and admins(con) <= 1:
        raise AccountError("err_last_admin")
    con.execute("update reader set is_admin=? where name=?", (int(bool(admin)), name))
    con.commit()


def remove_reader(con, name: str, data_dir: str) -> None:
    """Everything kobo-hardcover-sync holds for this reader. Their Hardcover shelf is
    theirs and stays as it is."""
    row = get(con, name)
    if row is None:
        raise AccountError("err_no_reader")
    if row["is_admin"] and admins(con) <= 1:
        raise AccountError("err_last_admin")
    for table in ("book", "device", "reading_day", "job", "import", "device_token"):
        con.execute(f"delete from {table} where reader=?", (name,))
    con.execute("delete from reader where name=?", (name,))
    con.execute("delete from meta where key=?", (f"env_token:{name}",))
    con.commit()
    shutil.rmtree(os.path.join(data_dir, "snapshots", safe(name)), ignore_errors=True)


# ---------- stats token ----------
# The stats endpoint is off for a reader until they make a token. Only its
# SHA-256 is kept, as with the upload tokens: it is shown once, on the page.
def new_stats_token(con, name: str) -> str:
    token = secrets.token_urlsafe(32)
    con.execute("update reader set stats_token_sha256=? where name=?", (hashlib.sha256(token.encode()).hexdigest(), name))
    con.commit()
    return token


def clear_stats_token(con, name: str) -> None:
    con.execute("update reader set stats_token_sha256=null where name=?", (name,))
    con.commit()


def stats_allowed(con, name: str, token: str) -> bool:
    """Does this token open this reader's stats? False for an unknown
    reader, a reader without a token, and a wrong token alike."""
    row = get(con, name)
    stored = (row["stats_token_sha256"] if row else "") or ""
    given = hashlib.sha256((token or "").encode()).hexdigest()
    return bool(stored) and bool(token) and hmac.compare_digest(stored, given)


# ---------- Hardcover token ----------
# Server mode keeps tokens encrypted in the database. Local mode has one
# reader and a better place: the computer's own secret store. It sets
# `token_store` to an object with get() -> str, set(token) and delete();
# the token is then never in the database at all.
token_store = None


def token_state(con, name: str) -> str:
    """none | stored | unreadable (key changed or missing) | env (legacy)."""
    if token_store is not None:
        return "stored" if token_store.get() else "none"
    row = get(con, name)
    f = _fernet()
    if row is not None and row["hardcover_token_enc"]:
        if f is None:
            return "unreadable"
        try:
            f.decrypt(row["hardcover_token_enc"].encode())
            return "stored"
        except InvalidToken:
            return "unreadable"
    return "env" if f is None and _env_token(name) else "none"


def token_for(con, name: str) -> str:
    """The reader's Hardcover token, or "". With a key the database is the
    only source; without one the legacy environment variable is."""
    if token_store is not None:
        return token_store.get() or ""
    f = _fernet()
    if f is None:
        return _env_token(name)
    row = get(con, name)
    if row is None or not row["hardcover_token_enc"]:
        return ""
    try:
        return f.decrypt(row["hardcover_token_enc"].encode()).decode()
    except InvalidToken:
        return ""


def set_token(con, name: str, token: str, hardcover_user: str = "") -> None:
    token = (token or "").strip()
    if token_store is not None:
        if not token or len(token) > 4096:
            raise AccountError("err_token_empty")
        token_store.set(token)
        set_hardcover_user(con, name, hardcover_user)
        return
    f = _fernet()
    if f is None:
        raise AccountError("err_no_key")
    if not token or len(token) > 4096:
        raise AccountError("err_token_empty")
    con.execute(
        "update reader set hardcover_token_enc=?, hardcover_user=? where name=?",
        (f.encrypt(token.encode()).decode(), hardcover_user or None, name),
    )
    con.commit()


def set_hardcover_user(con, name: str, hardcover_user: str) -> None:
    con.execute("update reader set hardcover_user=? where name=?", (hardcover_user or None, name))
    con.commit()


def clear_token(con, name: str) -> None:
    """Without a token nothing can go to Hardcover: back to dry run too."""
    if token_store is not None:
        token_store.delete()
    con.execute("update reader set hardcover_token_enc=null, hardcover_user=null, hardcover_live=0 where name=?", (name,))
    con.commit()


# ---------- devices ----------
def devices(con, name: str) -> list:
    return con.execute(
        """select t.token_sha256, t.device, t.created, d.last_import
                          from device_token t left join device d on d.reader=t.reader and d.device=t.device
                          where t.reader=? order by t.created, t.device""",
        (name,),
    ).fetchall()


def add_device(con, name: str, device: str, token_sha256: str) -> None:
    device, digest = (device or "").strip(), (token_sha256 or "").strip().lower()
    if not DEVICE.match(device):
        raise AccountError("err_device_name")
    if not HASH.match(digest):
        raise AccountError("err_hash")
    if con.execute("select 1 from device_token where token_sha256=?", (digest,)).fetchone():
        raise AccountError("err_hash_taken")
    con.execute("insert into device_token values (?,?,?,?)", (digest, name, device, state.now()))
    con.commit()


def remove_device(con, name: str, token_sha256: str) -> None:
    """Uploads with that token stop; what was uploaded stays."""
    con.execute("delete from device_token where reader=? and token_sha256=?", (name, (token_sha256 or "").strip().lower()))
    con.commit()


# ---------- admin overview: who and how many, never what ----------
def overview(con) -> list[dict]:
    out = []
    for r in all_readers(con):
        n = r["name"]
        job = con.execute("select started, status from job where reader=? order by started desc limit 1", (n,)).fetchone()
        out.append(
            {
                "name": n,
                "display_name": r["display_name"] or n,
                "logins": logins(r),
                "is_admin": bool(r["is_admin"]),
                "live": bool(r["hardcover_live"]),
                "token": token_state(con, n),
                "devices": con.execute("select count(*) from device_token where reader=?", (n,)).fetchone()[0],
                "last_upload": con.execute("select max(last_import) from device where reader=?", (n,)).fetchone()[0],
                "last_sync": job["started"] if job else None,
                "sync_status": job["status"] if job else None,
                "books": con.execute("select count(*) from book where reader=?", (n,)).fetchone()[0],
                "syncing": con.execute(f"select count(*) from book where reader=? and {SYNCING}", (n,)).fetchone()[0],
            }
        )
    return out


def sync_problems(con, limit: int = 10) -> list:
    return con.execute(
        "select reader, started, status, detail from job where status in ('failed','errors') order by started desc limit ?", (limit,)
    ).fetchall()


def _tree_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def storage(data_dir: str) -> dict:
    db = os.path.join(data_dir, "state.db")
    return {
        "database": os.path.getsize(db) if os.path.exists(db) else 0,
        "snapshots": _tree_bytes(os.path.join(data_dir, "snapshots")),
        "covers": _tree_bytes(os.path.join(data_dir, "covers")),
    }


# ---------- first start ----------
def _meta(con, key: str):
    row = con.execute("select value from meta where key=?", (key,)).fetchone()
    return row["value"] if row else None


def _load(path: str) -> dict:
    try:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    except OSError:
        return {}


def bootstrap(con, readers_yaml: str, devices_yaml: str) -> None:
    """Once per database: take over readers.yaml and devices.yaml of an
    installation from before readers managed themselves. The first reader in the file becomes the admin unless the file
    says `admin: true` somewhere. After that the files are never read again.

    Every start: with a key present, move a reader's legacy
    HARDCOVER_TOKEN_<READER> into the database, once per reader, so removing
    the token on the page is not undone by the environment."""
    if _meta(con, "config_imported") is None:
        readers = _load(readers_yaml).get("readers") or {}
        explicit = any((r or {}).get("admin") for r in readers.values())
        for i, (name, r) in enumerate(readers.items()):
            r = r or {}
            ids = sorted({str(x).strip().lower() for x in r.get("identities") or [] if str(x).strip()})
            con.execute(
                "insert or ignore into reader (name, display_name, identities, is_admin, hardcover_live, kobo_collection, created)"
                " values (?,?,?,?,?,?,?)",
                (
                    str(name),
                    str(r.get("display_name") or name),
                    json.dumps(ids),
                    int(bool(r.get("admin")) if explicit else i == 0),
                    int(bool(r.get("hardcover_live"))),
                    (r.get("kobo_collection") or None),
                    state.now(),
                ),
            )
        for d in _load(devices_yaml).get("devices") or []:
            digest = str(d.get("token_sha256", "")).strip().lower()
            if HASH.match(digest) and d.get("reader") and d.get("device"):
                con.execute(
                    "insert or ignore into device_token values (?,?,?,?)", (digest, str(d["reader"]), str(d["device"]), state.now())
                )
        con.execute("insert into meta values ('config_imported', ?)", (state.now(),))
    f = _fernet()
    if f is not None:
        for r in all_readers(con):
            key, tok = f"env_token:{r['name']}", _env_token(r["name"])
            if tok and not r["hardcover_token_enc"] and _meta(con, key) is None:
                if tok.lower().startswith("bearer "):
                    tok = tok[7:].strip()
                con.execute("update reader set hardcover_token_enc=? where name=?", (f.encrypt(tok.encode()).decode(), r["name"]))
                con.execute("insert into meta values (?, ?)", (key, state.now()))
    con.commit()
