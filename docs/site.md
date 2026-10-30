# The site

One static page at <https://merlijntishauser.github.io/kobo-hardcover-sync/>,
for a Kobo reader who heard of the tool and wants to know in a minute whether
it is for them. It lives in `site/` on `main` and is published by the `pages`
workflow (`.github/workflows/pages.yml`), which uploads the folder as it is;
nothing is built. The workflow's first run switches GitHub Pages on for the
repository, with Actions as its source (`configure-pages` with `enablement`).

## What is on it

The site has a world of its own, apart from the tool's page (`DESIGN.md`,
the site): the made-up shelf told as the share cards of a year in review,
on a white ground by day and a near-black one at night, with the same two
faces as the page from the same files.

- **The first viewport** is four cards in a row: a plum-to-coral card with
  the count of books on the Kobo; a photograph of a Kobo being read in a
  park with *Middlemarch, 100%, finished 21 Sep* on it; a teal-to-lime card
  on which *Currently reading, 88%* is struck through and *Read, 21 Sep
  2026* is written in after the caret, the page's own motion; and the
  download card, ink by day and white at night, with the one filled
  button, the version line, and brew and uv as code. Under the row the
  headline and the lede. The cards rise into place once on load, 60ms
  apart; under reduced motion nothing moves. Below 1100px the cards stand
  two by two, below 640px in one column, and there the headline comes
  first and the download card second, so that the button is within the
  first screen on a 390x844 phone.
- **The download** goes to the latest release on GitHub. With JavaScript the
  version, date, size and the disk image's own address are read from the
  GitHub API (`releases/latest`, no token, one request); without it the link
  is the releases page, which GitHub redirects to the newest. Homebrew and
  uv follow as the second way. The button comes back twice more: on the Mac
  app's card and on the close.
- **The proof** is real: the Books page rendered from the code with a made-up
  shelf (`browser_tests/shots.py`), light and dark at 2560 pixels wide, a
  phone at 390, and a book's Details, each in a quiet card with its caption;
  the Mac app by the owner's own screenshots of its window (Overview, Books,
  Covers), taken on the Mac in both themes and shown in the theme the page
  is in (a `<picture>` on the system's theme, swapped by the theme switch).
  The sample covers are drawn (`browser_tests/covers/`, a publisher's series
  on bookcloth, each saying *A made-up shelf* at its foot); the captions say
  the shelf is made up.
- **The photographs** are five from Unsplash, chosen by the owner, under the
  Unsplash License (`THIRD-PARTY-NOTICES.md` lists them; each file carries
  its origin in its JPEG comment): a Kobo in a park on the first viewport,
  a Kobo in a hammock and a reader in bed on the first two steps, a reader
  looking over a teal book beside *What it does* and *What it leaves alone*
  (*It never guesses a match*), and a reader on a quay as the close. They
  are bundled with the site; the page still loads nothing from elsewhere.
- **The rest**: the four steps from the cable to the shelf as four cards
  with their figures, what it does and what it leaves alone as a teal and
  an ink card, the comparison with the other tools (the README's table,
  with its date) in a quiet card, the independent-project sentence and the
  photographers' names, the links, and a theme switch kept in the browser.

The direction is written down in `.impeccable/surfaces/site-index-html.md`;
the tokens and rules in `DESIGN.md` under *The site*.

## Making the pictures again

The page's screenshots:

    KOBO_TEST_COVERS_DIR=browser_tests/covers SHOT_SCALE=2 DEV_OUT=out \
      uv run --group browser python browser_tests/shots.py

then `shot-books-light.png`, `shot-books-dark.png`, `shot-details-light.png`
and `shot-phone-books-light.png` as JPEG into `site/img/` (quality 84 to 86).

The site's own pictures, for a review and for the link preview:

    DEV_OUT=out uv run --group browser python browser_tests/site_shots.py

serves `site/` on a local port and captures the first viewport and the whole
page at a desk, a laptop and a phone, light and dark, scrolling every lazy
picture into view first (Chromium's full-page capture leaves them blank
otherwise), and `site-og.png`, the first viewport at 1200x630, which is
`site/img/og.png`.

`tests/test_site.py` checks that every file the page names exists, that the
words that must be there are, and that the page loads nothing from outside
itself but the one GitHub API request; no analytics, no font host, no script
host.
