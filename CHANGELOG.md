# Changelog

What changed, for people who use the tool. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a
minor version may change behaviour; the notes will say so.

## Unreleased

## 0.7.1 - 2026-10-04

Admin says which versions are running.

### Added

- Admin says which version the server runs (in the card *This server*,
  which was *Storage*), and per reader which version of the tool sent the
  last upload, and whether that is the server's. A computer says its
  version from this release on; an upload from an older one shows as
  such.

## 0.7.0 - 2026-10-04

A long list of books is quicker, and sorts either way round.

### Added

- Sorting either way round: *Sort by* now offers *Last read, oldest
  first*, *Author, Z to A* and *Title, Z to A* as well. A book never opened
  comes last either way.
- A long list shows its first 100 books, with *Show 100 more* at its end;
  the next ones join the same list. On a phone the page with 450 books is
  ready about three times sooner. How many it shows is yours to choose
  under Settings, *The list of books*: 25, 50, 100 or all of them.

### Changed

- *Set all shown* is now *Set all in this list* and acts on every book the
  search and filter match, also the ones not shown yet. It changes nothing
  when the list has changed since you looked (a sync, another tab), and
  says so.

## 0.6.0 - 2026-10-04

On your own computer you connect to Hardcover in the browser, with no code
to compare.

### Added

- On your own computer you connect to Hardcover in the browser: `token`
  and *Connect to Hardcover* on the page open Hardcover, you approve, and
  Hardcover sends the browser back to the tool. No code to compare.
  `token --code` keeps the sign-in with a code, for a computer without a
  browser. A server keeps signing in with a code.

## 0.5.1 - 2026-10-03

*Sync now* shows the sync while it runs, and says what it did.

### Changed

- *Sync now* shows the sync running: the button says *Syncing* and what it
  is doing ("Sending 2 of 5"), with a line that fills as the books go out.
  When it is done the list comes back with its new marks, and a line under
  the button says what happened ("Done: 1 change sent to Hardcover.", or
  why it stopped). Before, the page came back at once, still showing the
  change as waiting while the sync had in fact sent it.
- Help says what *stet* means: Latin for "let it stand", the word a
  proofreader writes to keep the original.

## 0.5.0 - 2026-10-03

A new look: the page reads like a proof of your Hardcover shelf, and a new
reader is shown where to start.

### Changed

- A new look for the page. The Hardcover column now reads like the margin
  of a proof: what the next sync changes is marked there, the value
  Hardcover has struck through and the new one after a caret, and a legend
  above the list says what each mark means. Red is only for what a sync
  sends; blue is your own choice or a question for you. The status dots are
  marks now (a tick, a caret, a question mark, a dash), so they can be told
  apart without their colour. New fonts, Schibsted Grotesk and Source Serif
  4, and no more photographs. Nothing about what the page does changed.

### Added

- A first-run guide at the top of the Books page, for as long as you are
  in dry run: what to do with a Kobo full of books read before (search,
  then switch on everything shown), how many you have switched on so far,
  and the three steps to a live shelf (connect, pick, go live). It goes
  away when you go live.
- A container image for the server, built for amd64 and arm64 at every
  release: `ghcr.io/merlijntishauser/kobo-hardcover-sync`. The example
  compose file pulls it. Building it yourself from the repository keeps
  working.

## 0.4.0 - 2026-10-03

You connect to Hardcover on Hardcover itself: no token to make or paste.

### Changed

- Signing in on Hardcover itself is switched on: the project's app is
  registered there. *Connect to Hardcover* under Settings and
  `kobo-hardcover-sync token` show a link and a short code, you approve on
  Hardcover, done. A pasted token keeps working, and stays possible
  (`token --paste`, or *Paste a token instead* on the page). Seen working
  against Hardcover on a self-hosted server: signing in, a sync, and a
  renewal of the connection.
- The page and the commands say "connect to Hardcover" where they said
  "add a token".

### Fixed

- Homebrew bottles were not made for 0.3.0 at first: the formula's own
  test looked for words that 0.3.0 printed with a capital. A test now
  holds the two together.

## 0.3.0 - 2026-10-03

The commands speak the page's language, Homebrew installs in seconds, and
signing in on Hardcover itself is built and waiting to be switched on.

### Added

- Signing in on Hardcover itself instead of pasting a token: *Connect to
  Hardcover* under Settings, and `kobo-hardcover-sync token`. The tool
  shows a link and a short code, you approve on Hardcover, and that is
  all. The connection renews itself; it is kept where a pasted token was
  kept, and ended at Hardcover when you disconnect. This is switched on
  once the project's app is registered at Hardcover; until then, and
  always as a second way, a pasted token works as before
  (`token --paste`).
- Homebrew installs a ready-made build on Macs with Apple silicon and
  macOS 15 or newer, in seconds instead of minutes. Other Macs build from
  source as before.

### Changed

- What the commands print. `doctor`, `status` and `setup` use the page's
  status language: a coloured mark and plain words, grouped under *This
  computer*, *Your Kobo* and *Hardcover*, folded to the width of the
  terminal. `sync` run by hand says each step as it finishes and then
  names the books that went to Hardcover (or would, in a dry run), each
  with its reading line. Those titles are shown in the terminal and
  written nowhere.
- Colour only on a terminal, and never the only sign: the marks differ in
  shape, and piped output carries the word (`ok`, `note`, `warning`,
  `problem`). `NO_COLOR` switches colour off.
- `kobo-hardcover-sync --help` lists the commands by where you use them.
- Counts read "1 book", "9 books", in notifications too.
- The Check card under Settings groups its lines the same way.

## 0.2.1 - 2026-10-03

Two fixes for 0.2.0, and fewer books that wait for a match.

### Changed

- Fewer books wait for a match. A translation is matched when Hardcover
  itself lists the Kobo's title among the book's other titles. The author
  may be any name the Kobo lists (it lists translators too). The first
  five search hits are looked at instead of the first one, a leading
  article no longer matters, and a title may be the book's title without
  its subtitle or series name. On the shelf this was measured on, 10 of 31
  waiting books now match by themselves; the rest are not on Hardcover
  under a title it can be sure of, and still wait for you.
- Books that already wait for a match are looked up once more after the
  upgrade, at the next sync: one search each.
- A title that only starts like another book's title is no longer enough
  when the book is not the search's first hit, and has to match on whole
  words.

### Fixed

- On a wide screen, pressing *Check* under Settings moved the whole page
  up and cut off the side column, with no way to scroll back (0.2.0).
- Details gave an error for a book Hardcover found nothing for, also
  after a search there that found nothing (since 0.1.0). It now says so
  and keeps the search box.

## 0.2.0 - 2026-10-02

For when something does not work: a command and a card that say what is
wrong and what to do, and messages and a log that do the same.

### Added

- `kobo-hardcover-sync doctor`: checks everything a sync depends on (the
  setup, the trigger, the Kobo and its database, the Hardcover token, the
  collection, the backups) and says per item what to do. It changes
  nothing, and ends with status 1 when something stops syncing from
  working.
- The same check on the page: a *Check* card under Settings. It takes the
  place of the *Test* button next to the token.
- `kobo-hardcover-sync sync --verbose`, and `verbose_log = true` in
  `config.toml`: a log line per book and per request to Hardcover. A
  verbose log contains book titles. On a server: `KHS_LOG=verbose`.

### Changed

- Messages say what to do next. A Kobo that was unplugged during a sync, a
  database another program is using, a Mac that does not let the tool read
  the Kobo and a Kobo whose software has not been tested each have their
  own message, instead of one that guessed at Full Disk Access.
- Log lines carry a level (`info`, `warning`, `error`, `detail`), and the
  log is kept to about a megabyte with one older file beside it. The
  server now logs each run for Hardcover, in counts.
- Something the tool did not expect no longer ends a sync without a word:
  the notification says so and the details go to the log.

### Fixed

- A collection that was written to the Kobo just as it was unplugged is
  recognised as the tool's own at the next sync. Before, it could be taken
  for a collection of yours with the same name and left alone for good.
- The Settings page no longer scrolls sideways on a phone with text at
  200%.

## 0.1.0 - 2026-10-02

The first public release.

### What it does

- Reads a stock Kobo's database when the Kobo is plugged in, and sends
  status, progress and dates to Hardcover for the books switched on.
- Two ways to run it: on your own computer (local mode), or on your own
  server for a household behind a sign-in proxy (server mode).
- A dry run until you go live. A match is never guessed.
- Takes over edits made on Hardcover: a status, a finish date, an edition,
  a book taken off the shelf.
- An optional collection on the Kobo with the books that sync, written
  only behind a version gate and after a backup.
- A page for choosing books, fixing matches and settings; light and dark;
  works on a phone and without JavaScript.
- macOS and desktop Linux: a trigger on plug-in, the secret store for
  tokens, notifications.

### Tested

- With a real device: one Kobo Clara Colour (software 6.0.274403), on
  macOS 27, in server mode.
- Local mode on macOS 27, with that Kobo: installed on a clean account
  from the README, synced, uninstalled.
- The Homebrew formula: built from source and tested on macOS 27; an
  upgrade kept the Full Disk Access permission.
- A Hardcover token with only the four permissions the tool asks for.
- Everything on Linux: tested without a device.

### Known limits

See the end of [docs/sync-rules.md](docs/sync-rules.md).
