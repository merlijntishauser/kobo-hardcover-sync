"""Browser tests: a real Chromium clicks through the page (theme switch,
in-place Sync and State switches). Kept out of tests/ because they need a
browser; run them where one exists:

  uv run --group browser pytest -q browser_tests

The app runs locally with made-up books; no login and no Hardcover involved.
"""

import os
import socket
import subprocess
import sys
import time

import pytest
from playwright.sync_api import sync_playwright

CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
OUT = os.environ.get("DEV_OUT")
DARK_BG, LIGHT_BG = "rgb(15, 23, 42)", "rgb(240, 244, 255)"
IMAGE_IDS = [i for i in os.environ.get("KOBO_TEST_IMAGE_IDS", "").split(",") if i]


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
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
    assert "Would send: mark Currently reading" in row.locator(".act").inner_text()
    page.reload()  # and it was saved
    assert "on" in page.locator("tr#b-b25").get_attribute("class")
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
    assert (round(box["width"]), round(box["height"])) == (56, 84)
    if IMAGE_IDS:
        img = page.locator("tr#b-b00 img.cover")
        img.scroll_into_view_if_needed()
        page.wait_for_function(
            "(() => { const i = document.querySelector('tr#b-b00 img.cover'); return i.complete && i.naturalWidth > 0; })()"
        )
        box = img.bounding_box()
        assert (round(box["width"]), round(box["height"])) == (56, 84)
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
    assert "How Kobo Hardcover Sync works" in box.inner_text() and "Amber" in box.inner_text()
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
    assert asked == ["Change sync to On for all books shown (1)?"]
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
    assert "Change sync to On for all books shown (1)?" in page.inner_text("main h2")
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
