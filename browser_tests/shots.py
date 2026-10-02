"""Design review: screenshots of every page, light and dark, desk and phone,
with made-up books that look like a real shelf. Not a test; run it after a
change to the stylesheet and look at the pictures:

  uv run --group browser python browser_tests/shots.py

They land in $DEV_OUT as shot-*.png. KOBO_TEST_IMAGE_IDS (comma-separated
Kobo image ids) gives the first books real covers.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

OUT = os.environ.get("DEV_OUT", ".")
IMAGE_IDS = [i for i in os.environ.get("KOBO_TEST_IMAGE_IDS", "").split(",") if i]
SHELF = [  # title, author, percent, kobo status, mode, state, how, sent
    ("Moby-Dick; or, The Whale", "Herman Melville", 37, 1, "on", "kobo", "isbn", {"status": "reading", "progress": 35}),
    ("Middlemarch", "George Eliot", 100, 2, "on", "kobo", "isbn", {"status": "read", "finished": "2026-09-21"}),
    ("The Left Hand of Darkness", "Ursula K. Le Guin", 62, 1, "auto", "kobo", "isbn", {"status": "reading", "progress": 62}),
    ("De avonden: een winterverhaal", "Gerard Reve", 12, 1, "on", "kobo", "uncertain", None),
    ("A Wizard of Earthsea", "Ursula K. Le Guin", 100, 2, "on", "rereading", "search", {"status": "read", "finished": "2024-02-03"}),
    ("The Remains of the Day", "Kazuo Ishiguro", 0, 0, "auto", "want", "isbn", None),
    ("Bleak House", "Charles Dickens", 8, 1, "off", "kobo", "isbn", None),
    ("The Master and Margarita", "Mikhail Bulgakov", 100, 2, "off", "kobo", "isbn", None),
    ("Piranesi", "Susanna Clarke", 100, 2, "on", "finished", "isbn", {"status": "read", "finished": "2026-08-30"}),
    ("The Dispossessed: An Ambiguous Utopia", "Ursula K. Le Guin", 44, 1, "off", "kobo", "isbn", None),
    ("Stoner", "John Williams", 0, 0, "off", "kobo", "none", None),
    ("The Name of the Rose", "Umberto Eco", 21, 1, "off", "dnf", "isbn", None),
]


def seed(d, reader="sam"):
    from kobo_hardcover_sync.engine import state

    st = state.connect(os.path.join(d, "state.db"))
    st.execute("insert into device values (?,'kobo','2026-09-01T08:00:00Z','2026-10-01T09:36:16Z')", (reader,))
    for i in range(34):
        title, author, pct, status, mode, stt, how, sent = (
            SHELF[i]
            if i < len(SHELF)
            else (f"Collected Stories, Volume {i - len(SHELF) + 1}", "Anton Chekhov", (i * 13) % 100, 1, "off", "kobo", "isbn", None)
        )
        new = mode == "auto"
        if sent:
            sent = dict(sent, user_book_id=500 + i, at="2026-10-01T09:36:40Z")
        st.execute(
            """insert into book (reader, device, content_id, title, author, isbn, percent, status, last_read,
                      seconds_read, first_event, history, mode, state, state_date, finished_at, hc_how, hc_book_id, hc_pages,
                      hc_title, hc_format, hc_format_id, last_sent, hc_candidates, image_id)
                      values (?,'kobo',?,?,?,'9780000000000',?,?,?,?,'',?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                reader,
                f"b{i:02d}",
                title,
                author,
                pct,
                status,
                f"2026-09-{30 - i % 28:02d}T10:00:00Z",
                1800 * (i % 9 + 1),
                0 if new else 1,
                mode,
                stt,
                "2024-02-03" if stt == "rereading" else None,
                "2026-09-21T20:00:00Z" if status == 2 else None,
                how,
                None if how in ("uncertain", "none") else 100 + i,
                320,
                title.split(";")[0],
                "Ebook" if i % 4 else "Paperback",
                4 if i % 4 else 1,
                json.dumps(sent) if sent else None,
                json.dumps([{"book_id": 9, "title": "De avonden", "authors": ["Gerard Reve"], "pages": 320}])
                if how == "uncertain"
                else None,
                IMAGE_IDS[i] if i < len(IMAGE_IDS) else None,
            ),
        )
    st.execute("insert into job values (?,'2026-10-01T09:36:20Z','2026-10-01T09:36:41Z',1,'ok',?)", (reader, json.dumps({"sent": 3})))
    st.commit()


def local_shots(new_page, snap):
    """The same pages in local mode: the page started as `open` starts it,
    one reader, the token in this computer's secret store (on Linux without
    a desktop keyring: the private file). Linux only, so that taking
    pictures never writes to a real Keychain."""
    if not sys.platform.startswith("linux"):
        return
    d = tempfile.mkdtemp()
    os.environ["KHS_HOME"] = d
    from kobo_hardcover_sync.computer import config, page, platform
    from kobo_hardcover_sync.engine import state
    from kobo_hardcover_sync.server import accounts

    seed(d, reader="me")
    con = state.connect(os.path.join(d, "state.db"))
    accounts.local_reader(con, "sam")
    con.execute("update reader set hardcover_live = 1, hardcover_user = 'sam', kobo_collection = 'On Hardcover' where name = 'me'")
    con.commit()
    con.close()
    config.save(config.Config())
    platform.pick().set_secret(platform.HARDCOVER, "a-made-up-token")
    env = {k: v for k, v in os.environ.items() if k != "KHS_TRUSTED_PROXIES"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "kobo_hardcover_sync", "page"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(150):
            if page.running():
                break
            time.sleep(0.1)
        url = f"http://127.0.0.1:{page.running()['port']}"
        for scheme, width, height in (("light", 1280, 800), ("dark", 390, 844)):
            p = new_page(scheme, width, height)
            p.goto(f"{url}/?k={page.new_key()}")
            snap(p, f"local-books-{scheme}")
            p.goto(url + "/settings")
            snap(p, f"local-settings-{scheme}", full=True)
    finally:
        proc.terminate()


def main():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "readers.yaml"), "w") as fh:
        fh.write("readers:\n  sam:\n    identities: [sam]\n")
    seed(d)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    from cryptography.fernet import Fernet

    env = dict(
        os.environ,
        KHS_DATA=d,
        KHS_CONFIG=os.path.join(d, "readers.yaml"),
        KHS_HOST="127.0.0.1",
        KHS_TRUSTED_PROXIES="127.0.0.1",
        KHS_SECRET_KEY=Fernet.generate_key().decode(),
        KHS_INTERVAL="0",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "kobo_hardcover_sync.web.app:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    # Live, with a token: the status the reader normally sees.
    os.environ["KHS_SECRET_KEY"] = env["KHS_SECRET_KEY"]
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"), headless=True)

            open_contexts = []

            def page(scheme, width, height=800, user="sam"):
                # One context at a time: two dozen left open is more memory than the dev sandbox gives (1.5 GB).
                while open_contexts:
                    open_contexts.pop().close()
                ctx = b.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme=scheme,
                    extra_http_headers={"Remote-User": user},
                    device_scale_factor=2 if width < 700 else 1,
                )
                open_contexts.append(ctx)
                return ctx.new_page()

            def snap(p, name, full=False):
                p.wait_for_timeout(700)
                p.screenshot(path=os.path.join(OUT, f"shot-{name}.png"), full_page=full)

            p = page("light", 1280)
            p.goto(url)  # first request takes over readers.yaml
            from kobo_hardcover_sync.engine import state
            from kobo_hardcover_sync.server import accounts

            con = state.connect(os.path.join(d, "state.db"))
            accounts.set_token(con, "sam", "x" * 40, "sam")
            accounts.set_live(con, "sam", True)
            for scheme in ("light", "dark"):
                p = page(scheme, 1280)
                p.goto(url)
                snap(p, f"books-{scheme}")
                p.goto(url + "/settings")
                snap(p, f"settings-{scheme}")
                p.goto(url + "/admin")
                snap(p, f"admin-{scheme}")
                p = page(scheme, 390, 844)
                p.goto(url)
                snap(p, f"phone-books-{scheme}")
                snap(p, f"phone-books-{scheme}-full", full=True) if scheme == "light" else None
                p.evaluate("window.scrollTo(0, 560)")
                snap(p, f"phone-list-{scheme}")
                p.goto(url + "/settings")
                snap(p, f"phone-settings-{scheme}")
            p = page("light", 1280)
            p.goto(url + "/?f=needs_match")
            p.locator("a.details").first.click()
            snap(p, "details-light")
            for scheme in ("dark", "light"):
                p = page(scheme, 1280)
                p.goto(url)
                p.click("button.helpbtn")
                snap(p, f"help-{scheme}")
            p.evaluate("document.querySelector('#help .dbody').scrollTop = 1180")
            snap(p, "help-light-scrolled")
            p = page("light", 390, 844)
            p.goto(url)
            p.click(".tagline .linkbtn")
            snap(p, "phone-help-light")
            p.evaluate("document.querySelector('#help .dbody').scrollTop = 900")
            snap(p, "phone-help-light-scrolled")
            p = page("light", 390, 844)
            p.goto(url)
            p.click(".ftoggle")
            snap(p, "phone-filters-light")
            p.goto(url + "/?f=on")
            p.locator("a.details").first.click()
            snap(p, "phone-details-light")
            p = page("light", 820, 1100)
            p.goto(url)
            snap(p, "tablet-books-light")
            p = page("light", 1680, 1000)
            p.goto(url)
            snap(p, "wide-books-light")
            for scheme, width, height in (("light", 1280, 800), ("dark", 390, 844)):
                p = page(scheme, width, height)
                p.goto(url + "/settings")
                p.once("dialog", lambda d: d.accept())  # the second time it asks before replacing the token
                p.click("form[action='/settings/stats/token'] button")
                p.locator("#stats").scroll_into_view_if_needed()
                snap(p, f"stats-token-{scheme}")
            p.once("dialog", lambda d: d.accept())
            p.click("form[action='/settings/stats/off'] button")
            p = page("dark", 1280, user="kim")
            p.goto(url)
            snap(p, "signup-dark")
            local_shots(page, snap)
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
