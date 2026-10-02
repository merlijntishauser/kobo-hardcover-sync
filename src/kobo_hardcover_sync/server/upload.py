"""PUT /upload: the tool on the reader's computer sends a small gzipped
database holding only what the server reads: the book rows and the device's
reading events (kobo_db.export_for_upload). Anything with more tables in it
is refused; a whole KoboReader.sqlite holds DRM keys, reviews and more.

Auth: `Authorization: Bearer <token>`. The server holds only the SHA-256 of
each token, with the reader and device it belongs to (table device_token,
filled by the reader under Settings), so the token never leaves the device
that made it.

Every accepted upload is kept as a dated snapshot for SNAPSHOT_DAYS (backup,
and re-processing), then imported.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime

from ..engine import kobo_db, state
from ..env import env

MAX_BYTES = int(env("MAX_UPLOAD_MB", "200")) * 1024 * 1024
SNAPSHOT_DAYS = int(env("SNAPSHOT_DAYS", "90"))


class UploadError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def device_for(token: str, con) -> tuple[str, str]:
    if not token:
        raise UploadError(401, "missing bearer token")
    digest = hashlib.sha256(token.encode()).hexdigest()
    d = con.execute("select reader, device from device_token where token_sha256=?", (digest,)).fetchone()
    if d is None:
        raise UploadError(401, "unknown token")
    return d["reader"], d["device"]


def safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def store_and_import(body_path: str, gzipped: bool, reader: str, device: str, data_dir: str) -> dict:
    snap_dir = os.path.join(data_dir, "snapshots", safe(reader), safe(device))
    os.makedirs(snap_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=data_dir, suffix=".sqlite", delete=False) as out:
        db_path = out.name
        try:
            src = gzip.open(body_path, "rb") if gzipped else open(body_path, "rb")
            with src:
                total = 0
                while chunk := src.read(1 << 20):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise UploadError(413, f"database larger than {MAX_BYTES // 2**20} MB")
                    out.write(chunk)
        except (OSError, EOFError) as e:  # bad gzip
            os.unlink(db_path)
            raise UploadError(400, f"cannot read upload: {e}") from e
    try:
        try:
            con = kobo_db.open_db(db_path)
        except kobo_db.ContainsKoboTokens as e:
            raise UploadError(422, str(e)) from e
        except kobo_db.NotAKoboDatabase as e:
            raise UploadError(422, str(e)) from e
        extra = sorted({r[0] for r in con.execute("select name from sqlite_master where type='table'")} - kobo_db.UPLOAD_TABLES)
        if extra:  # a whole Kobo database, or most of one: it has no business here
            con.close()
            raise UploadError(
                422,
                "this upload holds more than the server reads ("
                + ", ".join(extra[:3])
                + ("..." if len(extra) > 3 else "")
                + "); update kobo-hardcover-sync on the computer the Kobo is plugged into",
            )
        books = kobo_db.read_books(con)
        con.close()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap, n = os.path.join(snap_dir, f"{stamp}.sqlite.gz"), 1
        while os.path.exists(snap):  # a second upload in the same second keeps its own snapshot
            n += 1
            snap = os.path.join(snap_dir, f"{stamp}-{n}.sqlite.gz")
        with open(db_path, "rb") as fi, gzip.open(snap, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        prune(snap_dir)
        st = state.connect(os.path.join(data_dir, "state.db"))
        result = state.import_books(st, reader, device, books, source=os.path.basename(snap))
        return {**result, "reader": reader, "device": device, "snapshot": os.path.basename(snap)}
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def prune(snap_dir: str) -> None:
    cutoff = time.time() - SNAPSHOT_DAYS * 86400
    for name in os.listdir(snap_dir):
        p = os.path.join(snap_dir, name)
        if name.endswith(".sqlite.gz") and os.path.getmtime(p) < cutoff:
            os.unlink(p)
