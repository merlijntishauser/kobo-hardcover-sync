"""Browser tests: a real Chromium clicks through the page (theme switch,
in-place Sync and State switches). Kept out of tests/ because they need a
browser; run them where one exists:

  uv run --group browser pytest -q browser_tests

The app runs locally with made-up books; no login and no Hardcover involved.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import sync_playwright

CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
OUT = os.environ.get("DEV_OUT")
DARK_BG, LIGHT_BG = "rgb(15, 17, 20)", "rgb(237, 239, 234)"
IMAGE_IDS = [i for i in os.environ.get("KOBO_TEST_IMAGE_IDS", "").split(",") if i]


class PretendHardcover(BaseHTTPRequestHandler):
    """Hardcover's sign-in, for the browser to go through: a code that waits
    until someone "approves" (GET /approve), then tokens, and a whoami."""

    approved: set = set()

    def log_message(self, *a):
        pass

    def answer(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # the test, playing the reader on hardcover.app
        PretendHardcover.approved.add(urllib.parse.urlparse(self.path).query)
        self.answer(200, {})

    def do_POST(self):
        sent = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        fields = dict(urllib.parse.parse_qsl(sent))
        if self.path == "/device":
            code = f"CODE-{len(PretendHardcover.approved) + int(time.time() * 1000) % 9000 + 1000}"
            return self.answer(
                200,
                {
                    "device_code": "secret-" + code,
                    "user_code": code,
                    "verification_uri": "https://hardcover.app/link",
                    "verification_uri_complete": f"https://hardcover.app/link?code={code}",
                    "expires_in": 900,
                    "interval": 1,
                },
            )
        if self.path == "/token":
            code = fields.get("device_code", "").removeprefix("secret-")
            if code not in PretendHardcover.approved:
                return self.answer(400, {"error": "authorization_pending"})
            return self.answer(200, {"access_token": "hc_at_browser", "refresh_token": "hc_rt_browser", "expires_in": 604800})
        if self.path == "/graphql":
            return self.answer(200, {"data": {"me": [{"id": 7, "username": "ada_reads"}]}})
        self.answer(200, {})


@pytest.fixture(scope="module")
def pretend_hardcover():
    server = ThreadingHTTPServer(("127.0.0.1", 0), PretendHardcover)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def base_url(tmp_path_factory, pretend_hardcover):
    d = tmp_path_factory.mktemp("kobo")
    (d / "readers.yaml").write_text("readers:\n  sam:\n    identities: [sam]\n")
    from kobo_hardcover_sync.engine import state

    st = state.connect(str(d / "state.db"))
    st.execute("insert into device values ('sam','kobo','2026-09-01T08:00:00Z','2026-09-30T10:24:16Z')")
    for i in range(30):  # enough rows to scroll
        st.execute(
            """insert into book (reader, device, content_id, title, author, isbn, percent, status, last_read,
                      seconds_read, first_event, history, mode, state, hc_how, hc_book_id, hc_pages, hc_title)
                      values ('sam','kobo',?,?,?,'978',?,1,?,3600,'',1,'off','kobo','isbn',?,300,?)""",
            (f"b{i:02d}", f"Book {i:02d}", "An Author", 10 + i, f"2026-09-{30 - i % 28:02d}T10:00:00Z", 100 + i, f"Book {i:02d}"),
        )
    # Optional: real Kobo image ids, to see covers (needs internet).
    for i, image_id in enumerate(IMAGE_IDS):
        st.execute("update book set image_id=? where content_id=?", (image_id, f"b{i:02d}"))
    st.commit()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    from cryptography.fernet import Fernet

    env = dict(
        os.environ,
        KHS_DATA=str(d),
        KHS_CONFIG=str(d / "readers.yaml"),
        KHS_HOST="127.0.0.1",
        KHS_TRUSTED_PROXIES="127.0.0.1",
        KHS_SECRET_KEY=Fernet.generate_key().decode(),
        KHS_INTERVAL="0",
        # Signing in goes to the pretend Hardcover of this file, never to the real one.
        KHS_HARDCOVER_CLIENT_ID="an-app-id",
        HARDCOVER_OAUTH_DEVICE=pretend_hardcover + "/device",
        HARDCOVER_OAUTH_TOKEN=pretend_hardcover + "/token",
        HARDCOVER_OAUTH_REVOKE=pretend_hardcover + "/revoke",
        HARDCOVER_API=pretend_hardcover + "/graphql",
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
    yield url
    proc.terminate()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROMIUM, headless=True)
        yield b
        b.close()


def new_page(browser, base_url, scheme="light", width=1280, user="sam"):
    ctx = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, extra_http_headers={"Remote-User": user})
    page = ctx.new_page()
    page.goto(base_url)
    return ctx, page


def bg(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def shot(page, name):
    if OUT:
        page.screenshot(path=os.path.join(OUT, name))


def test_theme_switch_light_dark_auto_and_remembered(browser, base_url):
    ctx, page = new_page(browser, base_url, scheme="light")
    assert bg(page) == LIGHT_BG
    assert page.get_attribute('.theme button[data-set="auto"]', "aria-pressed") == "true"
    page.click('.theme button[data-set="dark"]')
    assert page.get_attribute("html", "data-theme") == "dark" and bg(page) == DARK_BG
    shot(page, "kobo-dark.png")
    page.reload()  # remembered, applied before paint
    assert page.get_attribute("html", "data-theme") == "dark" and bg(page) == DARK_BG
    assert page.get_attribute('.theme button[data-set="dark"]', "aria-pressed") == "true"
    page.click('.theme button[data-set="light"]')
    assert bg(page) == LIGHT_BG
    page.click('.theme button[data-set="auto"]')
    assert page.get_attribute("html", "data-theme") is None
    ctx.close()
    # Auto follows the system: a dark system gives the dark page.
    ctx, page = new_page(browser, base_url, scheme="dark")
    assert bg(page) == DARK_BG
    ctx.close()


def test_sync_switch_saves_in_place_and_keeps_scroll(browser, base_url):
    ctx, page = new_page(browser, base_url)
    row = page.locator("tr#b-b25")
    row.scroll_into_view_if_needed()
    page.evaluate("window.__stayed = true")
    y = page.evaluate("document.querySelector('.tablewrap').scrollTop")
    assert y > 0 and "off" in row.get_attribute("class")
    row.locator("select.rowmode").select_option("on")
    page.wait_for_function("document.querySelector('tr#b-b25').className === 'on'")
    assert page.evaluate("window.__stayed") is True  # no page reload
    assert page.evaluate("document.querySelector('.tablewrap').scrollTop") == y  # same place
    # What the eye gets: the label, and the change drawn as a correction after a caret;
    # what a screen reader gets: the whole sentence.
    assert row.locator(".act").inner_text().startswith("Would send") and "Currently reading" in row.locator(".fix ins").inner_text()
    assert "Would send: mark Currently reading" in row.locator(".act").text_content()
    page.reload()  # and it was saved
    assert "on" in page.locator("tr#b-b25").get_attribute("class")
    ctx.close()


def test_sync_now_says_when_it_is_done_and_what_it_did(browser, base_url):
    ctx, page = new_page(browser, base_url)
    assert not page.locator(".syncdone").is_visible()  # nothing said before anyone asked
    page.click("form.syncnow button")
    # Running or already over when the list comes back: either way it ends with what the sync said.
    page.locator(".syncdone").wait_for(state="visible", timeout=15000)
    # This reader has not connected to Hardcover yet, and the sync says so in so many words.
    assert page.inner_text(".syncdone") == "The sync stopped: Not connected to Hardcover yet: connect under Settings"
    assert page.inner_text("form.syncnow button span") == "Sync now"  # ready for the next one
    page.reload()
    assert not page.locator(".syncdone").is_visible()  # said once, not on every visit
    ctx.close()


def test_state_finished_shows_date_and_full_reading_line(browser, base_url):
    ctx, page = new_page(browser, base_url)
    row = page.locator("tr#b-b03")
    row.locator("select.rowmode").select_option("on")
    page.wait_for_function("document.querySelector('tr#b-b03').className === 'on'")
    assert not row.locator(".rowdate").is_visible()
    row.locator("select.rowstate").select_option("finished")
    row.locator(".bar.done").wait_for()
    assert row.locator(".rowdate").is_visible()
    row.locator(".rowdate").fill("2026-09-15")
    row.locator(".rowdate").dispatch_event("change")
    page.wait_for_function("document.querySelector('tr#b-b03 .act').textContent.includes('finished 2026-09-15')")
    assert "Finished 15 Sep 2026" in row.locator("td.book").inner_text()
    shot(page, "kobo-light.png")
    ctx.close()


def test_phone_layout_does_not_scroll_sideways(browser, base_url):
    ctx, page = new_page(browser, base_url, width=390)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    shot(page, "kobo-phone.png")
    ctx.close()


def test_covers_sit_beside_the_title_without_stretching_the_row(browser, base_url):
    ctx, page = new_page(browser, base_url, scheme="dark")
    # A book without an image id keeps a plain tile of the same size.
    tile = page.locator("tr#b-b29 .cover")
    assert tile.evaluate("e => e.tagName") == "SPAN"
    box = tile.bounding_box()
    assert (round(box["width"]), round(box["height"])) == (48, 72)
    if IMAGE_IDS:
        img = page.locator("tr#b-b00 img.cover")
        img.scroll_into_view_if_needed()
        page.wait_for_function(
            "(() => { const i = document.querySelector('tr#b-b00 img.cover'); return i.complete && i.naturalWidth > 0; })()"
        )
        box = img.bounding_box()
        assert (round(box["width"]), round(box["height"])) == (48, 72)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(800)
    shot(page, "kobo-covers-dark.png")
    ctx.close()


def test_cover_opens_in_a_lightbox_and_closes(browser, base_url):
    if not IMAGE_IDS:
        pytest.skip("needs KOBO_TEST_IMAGE_IDS (real covers, internet)")
    ctx, page = new_page(browser, base_url)
    box = page.locator("#lightbox")
    assert not box.is_visible()
    page.locator("tr#b-b00 a.coverlink").click()
    box.wait_for(state="visible")
    assert page.url.rstrip("/") == base_url.rstrip("/")  # stayed on the page
    assert "Book 00" in box.locator("figcaption").inner_text()
    # The large version replaces the thumbnail once loaded.
    page.wait_for_function("document.querySelector('#lightbox img').naturalWidth >= 600")
    assert "size=large" in box.locator("img").get_attribute("src")
    page.wait_for_timeout(400)  # let the fade-in finish
    shot(page, "kobo-lightbox.png")
    # The frame follows the cover's own shape: no band beside it.
    ratio = box.locator("img").evaluate("i => (i.clientWidth / i.clientHeight) / (i.naturalWidth / i.naturalHeight)")
    assert 0.98 < ratio < 1.02
    page.keyboard.press("Escape")
    box.wait_for(state="hidden")
    # Keyboard: focus the cover link, Enter opens; a click outside the cover closes.
    page.locator("tr#b-b01 a.coverlink").focus()
    page.keyboard.press("Enter")
    box.wait_for(state="visible")
    page.mouse.click(5, 400)
    box.wait_for(state="hidden")
    page.locator("tr#b-b01 a.coverlink").click()
    box.locator("button.close").click()
    box.wait_for(state="hidden")
    ctx.close()


def test_list_scrolls_in_its_own_panel_and_the_page_stays(browser, base_url):
    ctx, page = new_page(browser, base_url)
    wrap = page.locator(".tablewrap")
    page.mouse.move(640, 600)
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(200)
    assert page.evaluate("window.scrollY") == 0  # the page did not move
    assert wrap.evaluate("w => w.scrollTop") > 400  # the list did
    assert page.locator("h1").is_visible() and page.locator(".filters").is_visible()
    wrap_box, th = wrap.bounding_box(), page.locator("thead th").first.bounding_box()
    assert abs(th["y"] - wrap_box["y"]) <= 2  # headings stuck to the panel's top
    assert wrap_box["y"] + wrap_box["height"] <= 800 + 1  # the panel ends inside the window
    # A row reached through its anchor is scrolled into the panel, below the headings.
    page.goto(base_url + "/#b-b15")
    page.wait_for_timeout(300)
    row = page.locator("tr#b-b15").bounding_box()
    th = page.locator("thead th").first.bounding_box()
    assert row["y"] >= th["y"] + th["height"] - 1 and row["y"] < 800
    shot(page, "kobo-sticky.png")
    ctx.close()


def test_details_dialog_opens_and_closes(browser, base_url):
    ctx, page = new_page(browser, base_url, scheme="dark")
    box = page.locator("#details")
    page.locator("tr#b-b02 a.details").click()
    box.wait_for(state="visible")
    assert "Book 02" in box.locator("h2").inner_text()
    assert "On the Kobo" in box.inner_text() and "On Hardcover" in box.inner_text()
    assert page.url.rstrip("/") == base_url.rstrip("/")
    shot(page, "kobo-details.png")
    page.keyboard.press("Escape")
    box.wait_for(state="hidden")
    page.mouse.wheel(0, 200)
    page.wait_for_timeout(300)
    shot(page, "kobo-column.png")
    ctx.close()


def test_help_dialog(browser, base_url):
    ctx, page = new_page(browser, base_url)
    page.click("button.helpbtn")
    box = page.locator("#help")
    box.wait_for(state="visible")
    assert "How Kobo Hardcover Sync works" in box.inner_text() and "Circled question mark" in box.inner_text()
    shot(page, "kobo-help.png")
    page.keyboard.press("Escape")
    box.wait_for(state="hidden")
    ctx.close()


def test_header_names_the_reader_and_leads_to_settings_and_admin(browser, base_url):
    ctx, page = new_page(browser, base_url)
    assert page.inner_text(".who") == "Signed in as sam"
    assert page.get_attribute('.nav a[aria-current="page"]', "href") == "/"
    shot(page, "kobo-header.png")
    page.click(".nav a[href='/settings']")
    assert page.inner_text(".pagetitle") == "Settings"
    # Name: saved, and the header follows.
    page.fill("#display_name", "Sam the Reader")
    page.click("form[action='/settings/profile'] button")
    assert page.inner_text(".who") == "Signed in as Sam the Reader" and "Name saved." in page.inner_text(".flash")
    # A device: a bad hash is refused next to the form, a good one is listed and can be removed.
    page.fill("#device", "kobo-sam")
    page.fill("#hash", "nope")
    page.click("form[action='/settings/devices/add'] button")
    assert "The hash is 64 characters" in page.inner_text(".flash.bad")
    page.fill("#device", "kobo-sam")
    page.fill("#hash", "ab" * 32)
    page.click("form[action='/settings/devices/add'] button")
    assert "kobo-sam" in page.inner_text(".devices") and "abababab" in page.inner_text(".devices")
    assert page.get_attribute("#token", "type") == "password"
    if OUT:
        page.screenshot(path=os.path.join(OUT, "kobo-settings.png"), full_page=True)
    page.once("dialog", lambda d: d.accept())
    page.click(".devices button.danger")
    page.wait_for_selector(".flash")
    assert page.locator(".devices").count() == 0 and "No device yet" in page.inner_text("main")
    # Going live needs a token: the button is off until there is one.
    assert page.is_disabled("form[action='/settings/live'] button")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.click(".nav a[href='/admin']")
    assert page.inner_text(".pagetitle") == "Admin" and "Sam the Reader" in page.inner_text(".readers")
    shot(page, "kobo-admin.png")
    ctx.close()


def test_settings_and_admin_on_a_phone_and_in_dark(browser, base_url):
    ctx, page = new_page(browser, base_url, scheme="dark", width=390)
    for path, name in (("/settings", "kobo-settings-phone-dark.png"), ("/admin", "kobo-admin-phone-dark.png")):
        page.goto(base_url + path)
        assert bg(page) == DARK_BG
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path
        page.screenshot(path=os.path.join(OUT, name), full_page=True) if OUT else None
    ctx.close()


def test_the_check_card_says_what_it_found_and_fits_a_phone(browser, base_url):
    ctx, page = new_page(browser, base_url, scheme="dark", width=390)
    page.goto(base_url + "/settings")
    assert page.locator(".checks").count() == 0  # nothing is checked by looking at the page
    page.click("#check button")
    page.wait_for_selector(".checks li")
    assert page.url == base_url + "/settings/check#check"
    assert page.evaluate("document.querySelector('#check').getBoundingClientRect().top") < 300  # the page lands on the card
    found = page.inner_text(".checks")
    assert "Not connected to Hardcover yet" in found and "kobo-hardcover-sync doctor" in found
    assert page.inner_text("#check button") == "Check again" and page.locator("#check [role=status]").count() == 1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=os.path.join(OUT, "kobo-check-phone-dark.png"), full_page=True) if OUT else None
    page.add_style_tag(content="html { font-size: 200% !important; }")
    page.wait_for_timeout(200)
    sticking_out = page.evaluate(
        """() => [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1)
                 .map(e => e.tagName + '.' + e.className + ' ' + (e.getAttribute('action') || e.textContent.slice(0, 30)))"""
    )
    assert sticking_out == [], sticking_out[:6]
    ctx.close()
    # At a desk the cards scroll in their own panel. The jump to the card must move that panel and
    # nothing else: the page itself has nowhere to go, and no scrollbar to come back with.
    ctx, page = new_page(browser, base_url)
    page.goto(base_url + "/settings")
    page.click("#check button")
    page.wait_for_selector(".checks li")
    page.wait_for_timeout(200)
    where = page.evaluate(
        """() => ({page: scrollY, tall: document.documentElement.scrollHeight - innerHeight,
                   side: document.querySelector('.side').getBoundingClientRect().top,
                   panel: document.querySelector('main').scrollTop, card: document.querySelector('#check').getBoundingClientRect().top})"""
    )
    assert where["page"] == 0 and where["tall"] == 0 and where["side"] >= 0, where
    assert where["panel"] > 0 and 0 <= where["card"] < 400, where
    page.screenshot(path=os.path.join(OUT, "kobo-check.png")) if OUT else None
    ctx.close()


def test_a_new_login_signs_up_and_sees_what_to_do(browser, base_url):
    ctx, page = new_page(browser, base_url, user="kim")
    assert "Welcome to Kobo Hardcover Sync" in page.inner_text("main") and page.locator(".nav").count() == 0
    shot(page, "kobo-signup.png")
    page.click("form[action='/signup'] button")
    assert page.inner_text(".pagetitle") == "Settings" and "Your reader is ready" in page.inner_text(".flash")
    assert page.locator(".nav a[href='/admin']").count() == 0  # not an admin
    page.click(".nav a[href='/']")
    assert "Nothing from your Kobo yet" in page.inner_text("main") and "Book 01" not in page.inner_text("body")
    shot(page, "kobo-start.png")
    assert page.goto(base_url + "/admin").status == 403
    ctx.close()


def test_sync_now_and_refresh_keep_the_filter(browser, base_url):
    ctx, page = new_page(browser, base_url)
    page.click("a.chip[href*='f=off']")
    page.click(".statusactions form[action='/sync'] button")
    page.wait_for_load_state()
    assert page.url.endswith("/?f=off") and page.get_attribute("a.chip[aria-current]", "href") == "/?f=off"
    page.click(".statusactions form[method='get'] button")
    page.wait_for_load_state()
    assert page.url.endswith("/?f=off") and page.get_attribute("a.chip[aria-current]", "href") == "/?f=off"
    shot(page, "kobo-refresh.png")
    ctx.close()
    ctx, page = new_page(browser, base_url, width=390)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    shot(page, "kobo-refresh-phone.png")
    ctx.close()


def test_set_all_shown_asks_first(browser, base_url):
    ctx, page = new_page(browser, base_url)
    page.goto(base_url + "/?q=Book+07")
    asked = []
    # Cancel: nothing changes, the page stays.
    page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    page.select_option("#bulkmode", "on")
    page.click("form.bulk button")
    page.wait_for_timeout(300)
    assert asked == ["Change sync to On for the 1 book in this list?"]
    assert "off" in page.locator("tr#b-b07").get_attribute("class")
    page.reload()
    assert "off" in page.locator("tr#b-b07").get_attribute("class")
    # OK: the book shown is switched on, and the search is kept.
    page.once("dialog", lambda d: d.accept())
    page.select_option("#bulkmode", "on")
    page.click("form.bulk button")
    page.wait_for_function("document.querySelector('tr#b-b07') && document.querySelector('tr#b-b07').className === 'on'")
    assert "q=Book+07" in page.url
    page.goto(base_url + "/")
    assert "off" in page.locator("tr#b-b08").get_attribute("class")  # the others were left alone
    ctx.close()


def test_set_all_shown_asks_on_a_page_without_js(browser, base_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, java_script_enabled=False, extra_http_headers={"Remote-User": "sam"})
    page = ctx.new_page()
    page.goto(base_url + "/?q=Book+09")
    page.select_option("#bulkmode", "on")
    page.click("form.bulk button")
    assert "Change sync to On for the 1 book in this list?" in page.inner_text("main h2")
    shot(page, "kobo-confirm.png")
    page.click("main a.details")  # Cancel: back to the same search, unchanged
    assert "q=Book+09" in page.url and "off" in page.locator("tr#b-b09").get_attribute("class")
    page.select_option("#bulkmode", "on")
    page.click("form.bulk button")
    page.click("main form[action='/mode'] button")
    assert "q=Book+09" in page.url and "on" in page.locator("tr#b-b09").get_attribute("class")
    ctx.close()


# What is on top of the control that has keyboard focus, if it is not the control itself.
COVERED = """() => { const el = document.activeElement; if (!el || el === document.body) return '';
  const r = el.getBoundingClientRect();
  if (r.bottom <= 0 || r.top >= innerHeight) return 'out of view: ' + el.tagName;
  const hit = document.elementFromPoint(Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2)), Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2)));
  return hit && (hit === el || el.contains(hit) || hit.contains(el)) ? '' : el.tagName + '.' + el.className + ' under ' + (hit ? hit.tagName + '.' + hit.className : 'nothing'); }"""


def test_keyboard_focus_is_never_under_a_bar_that_stays_put(browser, base_url):
    # A phone has the navigation fixed at the bottom; a desk has the table's head fixed at the top of the list.
    for width, height in ((390, 844), (1280, 800)):
        ctx = browser.new_context(viewport={"width": width, "height": height}, extra_http_headers={"Remote-User": "sam"})
        page = ctx.new_page()
        page.goto(base_url)
        hidden = []
        for key, presses in (("Tab", 70), ("Shift+Tab", 45)):
            for _ in range(presses):
                page.keyboard.press(key)
                hidden.append(page.evaluate(COVERED))
        assert not [h for h in hidden if h], (width, [h for h in hidden if h][:3])
        ctx.close()


def test_a_rows_switch_works_without_javascript(browser, base_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, extra_http_headers={"Remote-User": "sam"}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(base_url)
    row = page.locator("tbody tr").nth(3)
    book = row.get_attribute("id")
    assert "off" in row.get_attribute("class")
    row.locator("select.rowmode").select_option("on")
    row.locator('form[action="/mode"] button').click()  # only there because there is no script
    page.wait_for_load_state()
    assert "on" in page.locator(f'[id="{book}"]').get_attribute("class")
    page.locator(f'[id="{book}"] select.rowmode').select_option("off")
    page.locator(f'[id="{book}"] form[action="/mode"] button').click()
    page.wait_for_load_state()
    assert "off" in page.locator(f'[id="{book}"]').get_attribute("class")
    ctx.close()
    ctx, page = new_page(browser, base_url)  # with script the switch saves by itself, and shows no button
    assert page.locator("tbody tr form button").count() == 0
    ctx.close()


def test_text_twice_the_size_still_fits_a_phone(browser, base_url):
    ctx, page = new_page(browser, base_url, width=390)
    page.add_style_tag(content="html { font-size: 200% !important; }")
    page.wait_for_timeout(200)
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0
    ctx.close()


def test_under_a_finger_every_control_is_44px(browser, base_url):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, extra_http_headers={"Remote-User": "sam"}, has_touch=True, is_mobile=True
    )
    page = ctx.new_page()
    page.goto(base_url)
    assert page.evaluate("matchMedia('(pointer: coarse)').matches")
    page.click(".ftoggle")  # the filters, unfolded
    # What a finger gets: the control must answer 21px above and below its middle.
    # (A filter chip is drawn smaller than that and reaches further than it looks.)
    small = page.evaluate(
        """() => { const out = [];
        for (const e of document.querySelectorAll('a[href], button, select, input:not([type=hidden])')) {
          if (e.closest('dialog:not([open])') || !e.getClientRects().length || getComputedStyle(e).display === 'inline') continue;
          if (/linkbtn|coverlink/.test(e.className)) continue;
          e.scrollIntoView({block: 'center'});
          const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
          const mine = p => { const h = document.elementFromPoint(x, p); return h && (h === e || e.contains(h) || h.contains(e)); };
          if (!(mine(y - 21) && mine(y + 21))) out.push(e.tagName + '.' + e.className + ' ' + Math.round(r.height));
        }
        return out; }"""
    )
    assert small == [], small[:5]
    shot(page, "kobo-touch.png")
    ctx.close()


def signed_up(browser, base_url, user, **kw):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, extra_http_headers={"Remote-User": user}, **kw)
    page = ctx.new_page()
    page.goto(base_url)
    page.click("form[action='/signup'] button")
    page.goto(base_url + "/settings")
    return ctx, page


def approve_on_hardcover(pretend_hardcover, page):
    code = page.inner_text(".signin code.code")
    assert page.get_attribute(".signin a.details", "href") == f"https://hardcover.app/link?code={code}"
    urllib.request.urlopen(f"{pretend_hardcover}/approve?{code}").read()


def test_connecting_to_hardcover_the_page_notices_the_approval_by_itself(browser, base_url, pretend_hardcover):
    ctx, page = signed_up(browser, base_url, "ada")
    assert page.inner_text("#hardcover .act") == "Not connected yet" and page.locator("#hardcover details.paste").count() == 1
    assert not page.is_visible("#hardcover details.paste input")  # pasting a token is folded away
    page.click("#hardcover form[action^='/settings/connect'] button")
    page.wait_for_selector(".signin code.code")
    assert page.url.endswith("/settings/connect#hardcover") and page.inner_text(".signin .btnrow .solid") == "I have approved it"
    assert page.evaluate("document.querySelector('#hardcover').getBoundingClientRect().top") < 400
    assert page.evaluate("scrollY") == 0  # the panel scrolled to the card; the page itself stayed
    shot(page, "kobo-connect.png")
    approve_on_hardcover(pretend_hardcover, page)
    page.wait_for_url("**/settings?ok=connected", timeout=10000)  # nobody pressed anything: the page asked by itself
    assert page.inner_text("#hardcover .act") == "Connected to Hardcover as @ada_reads"
    assert page.inner_text("#hardcover .btnrow .danger") == "Disconnect" and page.locator(".signin").count() == 0
    assert "hc_at_browser" not in page.content() and "hc_rt_browser" not in page.content()
    shot(page, "kobo-connected.png")
    ctx.close()


def test_connecting_to_hardcover_without_javascript_and_on_a_phone(browser, base_url, pretend_hardcover):
    ctx, page = signed_up(browser, base_url, "bea", java_script_enabled=False)
    page.set_viewport_size({"width": 390, "height": 844})
    page.click("#hardcover form[action^='/settings/connect'] button")
    page.wait_for_selector(".signin code.code")
    page.click(".signin .btnrow .solid")  # too early
    assert "Not approved on Hardcover yet." in page.inner_text(".signin")
    approve_on_hardcover(pretend_hardcover, page)
    page.click(".signin .btnrow .solid")
    page.wait_for_url("**/settings?ok=connected#hardcover")  # back on the card it was started from
    assert page.inner_text("#hardcover .act") == "Connected to Hardcover as @ada_reads"
    ctx.close()
    # On a phone, with text twice the size, the waiting sign-in still fits.
    ctx, page = signed_up(browser, base_url, "cas")
    page.set_viewport_size({"width": 390, "height": 844})
    page.click("#hardcover form[action^='/settings/connect'] button")
    page.wait_for_selector(".signin code.code")
    page.add_style_tag(content="html { font-size: 200% !important; }")
    page.wait_for_timeout(200)
    sticking_out = page.evaluate(
        "() => [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).map(e => e.tagName + '.' + e.className)"
    )
    assert sticking_out == [], sticking_out[:6]
    page.click(".signin form[action='/settings/connect/cancel'] button")
    assert page.locator(".signin").count() == 0
    ctx.close()


class PretendHardcoverBrowser(BaseHTTPRequestHandler):
    """Hardcover's browser sign-in (authorization code with PKCE): the
    authorize page approves at once and sends the browser back; the token
    endpoint gives tokens only for the verifier that matches the challenge."""

    challenges: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path != "/authorize" or q.get("code_challenge_method") != "S256":
            self.send_response(400)
            self.end_headers()
            return
        PretendHardcoverBrowser.challenges["a-code"] = (q["code_challenge"], q["redirect_uri"])
        back = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "a-code", "state": q["state"], "iss": "https://api.hardcover.app"})
        self.send_response(302)
        self.send_header("Location", back)
        self.end_headers()

    def do_POST(self):
        fields = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()))
        if self.path == "/graphql":
            body, status = {"data": {"me": [{"id": 7, "username": "anna_reads"}]}}, 200
        else:
            import base64
            import hashlib

            challenge, redirect = PretendHardcoverBrowser.challenges.get(fields.get("code"), ("", ""))
            made = base64.urlsafe_b64encode(hashlib.sha256(fields.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
            ok = fields.get("grant_type") == "authorization_code" and made == challenge and fields.get("redirect_uri") == redirect
            body, status = (
                ({"access_token": "hc_at_1", "refresh_token": "hc_rt_1", "expires_in": 604800}, 200)
                if ok
                else ({"error": "invalid_grant"}, 400)
            )
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the local page keeps the token in a file only on Linux")
def test_on_your_own_computer_connecting_goes_through_the_browser_and_comes_back_signed_in(browser, tmp_path, monkeypatch):
    # The page's own cookie is SameSite=Strict: it does not come along when Hardcover sends the browser
    # back. This is the whole way round in a real browser, to see that the sign-in still lands.
    server = ThreadingHTTPServer(("127.0.0.1", 0), PretendHardcoverBrowser)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    hc = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("KHS_HOME", str(tmp_path))
    from kobo_hardcover_sync.computer import config, page
    from kobo_hardcover_sync.engine import state
    from kobo_hardcover_sync.server import accounts

    con = state.connect(str(tmp_path / "state.db"))
    accounts.local_reader(con, "anna")
    con.close()
    config.save(config.Config())
    env = {k: v for k, v in os.environ.items() if k != "KHS_TRUSTED_PROXIES"}
    env.update(
        KHS_HARDCOVER_CLIENT_ID="an-app-id",
        KHS_HARDCOVER_LOOPBACK="1",
        HARDCOVER_OAUTH_AUTHORIZE=hc + "/authorize",
        HARDCOVER_OAUTH_TOKEN=hc + "/token",
        HARDCOVER_API=hc + "/graphql",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "kobo_hardcover_sync", "page"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(150):
            if page.running():
                break
            time.sleep(0.1)
        ctx = browser.new_context()
        p = ctx.new_page()
        p.goto(page.link().replace("/?k=", "/settings?k="))
        p.click("#hardcover form[action^='/settings/connect'] button")
        p.wait_for_url("**/settings?ok=connected", timeout=15000)  # back at Settings, with the page's own cookie again
        assert "Connected to Hardcover as @anna_reads" in p.inner_text("#hardcover")
        ctx.close()
    finally:
        proc.terminate()
        server.shutdown()


@pytest.fixture(scope="module")
def long_url(tmp_path_factory):
    """A shelf of 130 books: more than the 100 the list shows at first."""
    d = tmp_path_factory.mktemp("long")
    (d / "readers.yaml").write_text("readers:\n  sam:\n    identities: [sam]\n")
    from kobo_hardcover_sync.engine import state

    st = state.connect(str(d / "state.db"))
    for i in range(130):
        st.execute(
            """insert into book (reader, device, content_id, title, author, isbn, percent, status, last_read,
                      seconds_read, first_event, history, mode, state, hc_how, hc_book_id, hc_pages, hc_title)
                      values ('sam','kobo',?,?,?,'978',?,1,?,3600,'',1,'off','kobo','isbn',?,300,?)""",
            (f"l{i:03d}", f"Long {i:03d}", "An Author", 10, f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", 100 + i, f"Long {i:03d}"),
        )
    st.commit()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    from cryptography.fernet import Fernet

    env = dict(
        os.environ,
        KHS_DATA=str(d),
        KHS_CONFIG=str(d / "readers.yaml"),
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
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.terminate()


def test_show_more_adds_the_next_books_to_the_same_list_and_keeps_them(browser, long_url):
    ctx, page = new_page(browser, long_url, width=390)
    rows = page.locator("table.books tbody tr")
    assert rows.count() == 100 and page.inner_text(".more .shown") == "100 of 130 shown"
    assert page.inner_text("form.bulk label") == "Set all 130 in this list to"  # the whole list, shown or not
    page.click("a.morelink")
    page.wait_for_function("document.querySelectorAll('table.books tbody tr').length === 130")
    assert page.locator(".more").count() == 0  # nothing left to ask for
    assert page.inner_text("#listsaid") == "30 more books shown."
    assert page.evaluate("document.activeElement.closest('tr').id") == "b-l029"  # the first new one: the oldest-read come last
    assert page.url.endswith("/?show=130") and page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # A new row works like the first ones, and its way back keeps the longer list.
    new = page.locator("tr#b-l000")
    assert new.locator('input[name="back"]').first.input_value() == "show=130"
    new.locator("select.rowmode").select_option("on")
    page.wait_for_function("document.querySelector('tr#b-l000').className === 'on'")
    page.reload()
    assert rows.count() == 130
    ctx.close()
    # Without JavaScript: a link to the same view with more of it, landing on the first new book.
    ctx = browser.new_context(java_script_enabled=False, extra_http_headers={"Remote-User": "sam"})
    page = ctx.new_page()
    page.goto(long_url)
    page.click("a.morelink")
    page.wait_for_url("**/?show=200#b-l029")
    assert page.locator("table.books tbody tr").count() == 130
    ctx.close()
