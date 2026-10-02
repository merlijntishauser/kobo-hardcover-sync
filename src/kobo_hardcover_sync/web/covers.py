"""Book covers: fetched once from Kobo's public cover CDN by the book's
ImageId, kept in DATA/covers, served by the app itself. The browser never
talks to Kobo; the page loads nothing from outside.

A book without a usable cover gets a marker file, so a missing cover is
asked for once a week, not on every page view.
"""

from __future__ import annotations

import os
import re
import time
import urllib.request

CDN = os.environ.get("KHS_COVER_URL") or "https://cdn.kobo.com/book-images/{id}/{size}/False/image.jpg"
# width/height/quality as Kobo's CDN takes them. "large" is for the lightbox:
# sharp on a laptop or retina screen at about 420 KB (2400 wide is over 1 MB).
SIZES = {"thumb": "240/360/85", "large": "1200/1800/90"}
ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,80}$")  # the id goes into a URL and a filename
RETRY_MISSING_AFTER = 7 * 86400
MAX_BYTES = 4 * 1024 * 1024


def download(image_id: str, size: str = "thumb") -> bytes | None:
    """The cover as JPEG bytes, or None. Separate so tests can replace it."""
    req = urllib.request.Request(CDN.format(id=image_id, size=SIZES[size]), headers={"User-Agent": "kobo-hardcover-sync"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200 or "image" not in r.headers.get("Content-Type", ""):
                return None
            data = r.read(MAX_BYTES + 1)
    except Exception:
        return None
    return data if 0 < len(data) <= MAX_BYTES else None


def cover_path(data_dir: str, image_id: str, size: str = "thumb") -> str | None:
    """Path of the cached cover, fetching it on first use. None = no cover."""
    if not image_id or not ID_OK.match(image_id) or size not in SIZES:
        return None
    d = os.path.join(data_dir, "covers")
    os.makedirs(d, exist_ok=True)
    stem = image_id if size == "thumb" else f"{image_id}.{size}"
    path, missing = os.path.join(d, stem + ".jpg"), os.path.join(d, stem + ".none")
    if os.path.exists(path):
        return path
    if os.path.exists(missing) and time.time() - os.path.getmtime(missing) < RETRY_MISSING_AFTER:
        return None
    data = download(image_id, size)
    if data is None:
        open(missing, "w").close()
        return None
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    if os.path.exists(missing):
        os.unlink(missing)
    return path
