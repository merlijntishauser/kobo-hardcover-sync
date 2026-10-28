# The site

One static page at <https://merlijntishauser.github.io/kobo-hardcover-sync/>,
for a Kobo reader who heard of the tool and wants to know in a minute whether
it is for them. It lives in `site/` on `main` and is published by the `pages`
workflow (`.github/workflows/pages.yml`), which uploads the folder as it is;
nothing is built. The workflow's first run switches GitHub Pages on for the
repository, with Actions as its source (`configure-pages` with `enablement`).

## What is on it

- **The first viewport** is a Kobo at reading scale, its e-ink screen on the
  last page of *Middlemarch* with the reading line as the Kobo keeps it, and,
  beside it, the page's own proof margin with four sample books and their
  marks. One red stroke runs from the end of the gauge into the first mark:
  a path written for the desk layout and stretched with it, so it is there
  without JavaScript; with JavaScript it is measured so it meets both ends at
  any width and drawn once on load, still under reduced motion; left out
  below 1024px where the two stack. The e-ink's colours are the icon's own. The headline and the download sit under the device; the download
  is within the first screen at 1280x800 and on a 390x844 phone.
- **The download** goes to the latest release on GitHub. With JavaScript the
  version, date, size and the disk image's own address are read from the
  GitHub API (`releases/latest`, no token, one request); without it the link
  is the releases page, which GitHub redirects to the newest. Homebrew and
  uv follow as the second way.
- **The proof** is real: the Books page rendered from the code with a made-up
  shelf (`browser_tests/shots.py`), light and dark at 2560 pixels wide, a
  phone at 390, and a book's Details; the Mac app by its icon and its words,
  until there is a screenshot of it worth showing. The sample covers are
  drawn (`browser_tests/covers/`, a publisher's series on bookcloth, each
  saying *A made-up shelf* at its foot) so the shelf does not show the
  crossed box of a missing cover; the captions say the shelf is made up.
- **The rest**: the four steps from the cable to the shelf as one row that
  scrolls and never wraps, what it does and what it leaves alone, the
  comparison with the other tools (the README's table, with its date), the
  independent-project sentence, the links, and a theme switch kept in the
  browser.

The world is the page's (`DESIGN.md`, the galley proof): the same tokens as
`kobo.css`, the same two faces from the same files (`site/fonts/`, under the
SIL Open Font License, licences beside them), square-cut corners, the two
pencils with their one job each. Three things are the site's own: a 1rem body
and a fluid headline, because a page read once from a chair is set larger than
a list worked daily; the drawn device, from the icon's geometry; and the
stroke. The e-ink's greys are darker than the page's graphite to stay at 4.5:1
on the paper tint. The direction is written down in
`.impeccable/surfaces/site-index-html.md`.

## Making the pictures again

    KOBO_TEST_COVERS_DIR=browser_tests/covers SHOT_SCALE=2 DEV_OUT=out \
      uv run --group browser python browser_tests/shots.py

then `shot-books-light.png`, `shot-books-dark.png`, `shot-details-light.png`
and `shot-phone-books-light.png` as JPEG into `site/img/` (quality 84 to 86),
and `og.png` as a 1200x630 crop of the light list. `tests/test_site.py` checks
that every file the page names exists and that the words that must be there
are.

The page loads nothing from outside itself but the one GitHub API request;
no analytics, no font host, no script host.
