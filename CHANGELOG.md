# Changelog

What changed, for people who use the tool. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a
minor version may change behaviour; the notes will say so.

## Unreleased

Nothing yet.

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
