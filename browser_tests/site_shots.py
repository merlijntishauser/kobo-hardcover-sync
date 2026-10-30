"""Pictures of the site (site/) for a design review: the first viewport and the
whole page, light and dark, at a desk, a laptop and a phone. Not a test:

  uv run --group browser python browser_tests/site_shots.py

They land in $DEV_OUT as site-*.png. The page is served from site/ on a local
port; every lazy picture is scrolled into view before the full-page capture,
which Chromium would otherwise leave blank.
"""

import functools
import http.server
import os
import pathlib
import threading

from playwright.sync_api import sync_playwright

OUT = os.environ.get("DEV_OUT", ".")
SITE = pathlib.Path(__file__).resolve().parents[1] / "site"
SIZES = {"desktop": (1440, 900), "laptop": (1280, 800), "mobile": (390, 844)}


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    server = serve()
    url = f"http://127.0.0.1:{server.server_port}/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            for name, (w, h) in SIZES.items():
                page = browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme, device_scale_factor=1)
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(2500)  # the cards have risen, the write-in is written
                suffix = "" if scheme == "light" else "-dark"
                page.screenshot(path=f"{OUT}/site-{name}{suffix}-first.png")
                height = page.evaluate("document.documentElement.scrollHeight")
                for y in range(0, height, h // 2):  # bring every lazy picture in
                    page.evaluate(f"window.scrollTo(0, {y})")
                    page.wait_for_timeout(120)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(600)
                page.screenshot(path=f"{OUT}/site-{name}{suffix}.png", full_page=True)
                page.close()
        page = browser.new_page(viewport={"width": 1200, "height": 630}, color_scheme="light", device_scale_factor=1)
        page.goto(url, wait_until="networkidle")  # the link preview (og.png): the four cards, by day
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT}/site-og.png")
        page.close()
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
