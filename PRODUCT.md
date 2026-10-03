# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two kinds of reader, and neither outranks the other (confirmed 2026-10-02):

- **One reader on their own computer.** Found the project on GitHub, runs
  it in local mode on a Mac or a Linux desktop. Comfortable installing a
  command-line tool once. After that they plug in the Kobo and it syncs;
  they open the page now and then to switch books on, fix a match, or see
  why something did not sync.
- **A household on a home server.** Several readers behind a sign-in
  proxy, often sharing one Kobo account over several e-readers. One person
  runs the server. The others only see the page, some of them are not
  technical, and they are often on a phone.

When a design decision would differ between the two, it is argued for that
case. There is no default winner.

## Product Purpose

kobo-hardcover-sync reads what a Kobo e-reader knows about your reading
(which books, how far, finished when) from the device's own database when
the Kobo is plugged in, and keeps your shelf on Hardcover (hardcover.app)
in step with it: status, progress and dates. It also keeps reading minutes
for a dashboard of your own, and can put a collection of your synced books
on the Kobo.

It exists because a stock Kobo keeps this to itself: Kobo's cloud has no
public API, and the tools that do sync to Hardcover need other reading
software that cannot open books from the Kobo store.

Success is a Hardcover shelf that is right without the reader having to
think about it, and a page that answers "what will the next sync do with
this book, and why" when they do want to look.

## Positioning

Core, confirmed 2026-10-02:

- **The Kobo as it comes, with store books.** No KOReader, no replacement
  reading software, no Calibre in between. Books bought in the Kobo store,
  DRM included, are the normal case.
- **Yours, on your machine.** No account with this project and no cloud of
  its own: your computer or your own server, your own Hardcover token. The
  page loads nothing from elsewhere; book covers are fetched by the tool.

Supporting, true and worth showing, but not what sets it apart:

- Careful with your shelf: dry run before anything is sent, a match is
  never guessed, one read-through per book, edits made on Hardcover are
  respected, the Kobo is written to only behind a version gate and a backup.
- It says what it does: every sync rule is written down and held by a test
  (`docs/sync-rules.md`), and the page tells per book what the next sync
  will do.

## Operating Context

- **The moment of use is plugging in a Kobo.** A sync runs by itself and a
  notification says what happened ("8 books updated. Eject before
  unplugging."). Most days nobody opens the page.
- **The page is opened for a reason:** the first run (choosing which of
  hundreds of already-read books sync), a book that needs a match, a wrong
  finish date, an error, a setting.
- **Local mode:** the page is started on request (`kobo-hardcover-sync
  open`) on the computer's own loopback address and stops when unused.
  Setup is done in a terminal.
- **Server mode:** the page is always there, behind the household's
  sign-in proxy; each reader signs up with one click and enters their own
  Hardcover token. A computer the Kobo is plugged into uploads to it.
- **The other half is Hardcover.** Readers also edit their shelf there;
  those edits are taken over at the next sync, not overwritten.
- A library is typically several hundred books, most of them history from
  before the tool was installed.

## Capabilities and Constraints

- Sends status, progress and dates to Hardcover. No highlights, no ratings.
- Per book: sync Auto, On or Off; a state that overrules the Kobo
  (Finished with a date, Rereading, Want to read, Did not finish); a match
  to choose when the tool is not sure; remove from Hardcover.
- Dry run until the reader goes live.
- Server mode adds: readers who sign up and manage themselves, an admin
  page that shows counts and never a book or a token, upload devices, a
  stats endpoint for a dashboard.
- The page works without JavaScript; with it, rows update in place.
- Light and dark, and a phone layout, are part of the product, not extras.
- Everything the page needs is served by the tool itself, book covers
  included: the tool fetches them from Kobo's servers once and keeps them.
- English only for now. All page texts are in one module so the page can
  be translated.
- Terms used on the page and in the documentation, to keep: *reader*,
  *sync* (Auto, On, Off), *State*, *match*, *edition*, *collection*,
  *dry run* and *live*, *history* and *new*.
- Tested with a real device on one Kobo (Clara Colour, software
  6.0.274403) and macOS. Linux desktop support is built and not yet seen
  working with a real Kobo.
- Published on PyPI and in a Homebrew tap. A reader signs in on Hardcover
  itself (OAuth, the device flow: a link and a short code); pasting a
  personal token is the second way.
- Not built: a hook on the Kobo that syncs over Wi-Fi; statistics shared
  between readers.

## Brand Commitments

- The name is **kobo-hardcover-sync**; on the page it reads *Kobo
  Hardcover Sync*.
- Independent: not affiliated with, endorsed by or sponsored by Rakuten
  Kobo or Hardcover. That sentence stays wherever the project introduces
  itself.
- Voice, as the shipped texts have it: plain words, short sentences,
  addressed to "you", says what happened and what to do next, no
  exclamation, no jargon where a common word exists.
- MIT licence. The two fonts the page uses have their own licences
  (`THIRD-PARTY-NOTICES.md`); new bundled assets need a licence that allows
  redistribution, and a notice.

## Evidence on Hand

- `docs/how-it-works.md`: how it works and why, with what was measured on a real
  device and a real shelf (reading time is account-wide, events are local
  to the device; the edition rule moved 3 of 100 books; 95 duplicate
  read-throughs before the one-entry rule).
- `docs/sync-rules.md`: every rule, each naming the tests that hold it.
- `docs/hardcover-api.md`: what Hardcover's API terms ask and how the tool
  keeps to them.
- `browser_tests/shots.py`: renders every page, light and dark, at desk,
  tablet and phone width, with a made-up shelf.
- One installation in daily use by its author's household.

Absent, and not to be invented: testimonials, user or download numbers,
reviews, a list of supported Kobo models beyond the one tested, any
statement from Kobo or Hardcover about the project.

## Product Principles

1. **The Kobo stays as it is.** Nothing asks the reader to change the
   device, the books or how they read.
2. **It is theirs.** Their machine, their token, their data; nothing goes
   to a third place, and the page does not depend on one.
3. **Two readers, one product.** Every surface has to work for the person
   who installed it from a terminal and for the least technical member of
   a household on a phone.
4. **Show before doing.** What the next sync will do is visible first; the
   reader's own edits and choices win over the tool's.
5. **Quiet when it works.** The normal case needs no visit to the page;
   when the page is opened, it answers the question that brought the
   reader there.

## Accessibility & Inclusion

WCAG 2.2 AA is the bar for the pages (confirmed 2026-10-02): contrast,
keyboard, visible focus, target sizes, reduced motion. Already part of the
product: it works without JavaScript and by keyboard.
