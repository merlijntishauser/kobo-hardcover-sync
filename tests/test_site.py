"""The site (site/, docs/site.md): one static page that names only files it
ships, says what it must say, and sends people to the latest release."""

import pathlib
import re

SITE = pathlib.Path(__file__).resolve().parents[1] / "site"
PAGE = (SITE / "index.html").read_text()


def test_every_file_the_page_and_its_stylesheet_name_is_shipped():
    named = set(re.findall(r'(?:src|href)="([^"#:]+)"', PAGE))
    for srcset in re.findall(r'srcset="([^"]+)"', PAGE):  # "a.jpg 800w, b.jpg 1600w"
        named |= {candidate.split()[0] for candidate in srcset.split(",")}
    named |= set(re.findall(r"url\(([^)]+)\)", (SITE / "site.css").read_text()))
    named = {n.strip("\"'") for n in named if not n.startswith(("./", "#"))}
    assert named, "the page names its files"
    for name in named:
        assert (SITE / name).is_file(), name


def test_the_download_goes_to_the_latest_release_and_the_page_says_who_it_is():
    assert 'id="dmg" href="https://github.com/merlijntishauser/kobo-hardcover-sync/releases/latest"' in PAGE
    assert "not affiliated with, endorsed by or sponsored by Rakuten Kobo or Hardcover" in PAGE
    assert "made-up shelf" in PAGE  # the proof is real, the shelf is not
    assert 'property="og:image" content="https://merlijntishauser.github.io/kobo-hardcover-sync/img/og.png"' in PAGE  # absolute: a link card needs it
    assert "brew install merlijntishauser/tap/kobo-hardcover-sync" in PAGE


def test_the_page_loads_nothing_from_elsewhere():
    outside = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', PAGE) if not u.startswith("https://github.com/")]
    outside = [u for u in outside if "fonts.g" in u or ".js" in u or ".css" in u or "cdn" in u]
    assert outside == []
    script = (SITE / "site.js").read_text()
    assert "https://api.github.com/repos/" in script and 'REPO = "merlijntishauser/kobo-hardcover-sync"' in script


def test_the_fonts_come_with_their_licences():
    for face in ("SchibstedGrotesk", "SourceSerif4"):
        assert (SITE / "fonts" / f"{face}-LICENSE.txt").is_file()
