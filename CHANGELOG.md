# Changelog

What changed, for people who use the tool. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a
minor version may change behaviour; the notes will say so.

## Unreleased

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
