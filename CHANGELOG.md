# Changelog

What changed, for people who use the tool. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a
minor version may change behaviour; the notes will say so.

## Unreleased

### Added

- A full-screen cover in the Mac app: on a cover shown large, the button
  in its corner (or F) puts it alone on black over the whole screen; a
  click or any key puts it back.

### Changed

- Covers in the Mac app takes about a third less of the processor while
  the rows drift, and next to nothing while a book or its large cover is
  open over them: each row now moves as one, and the rows stop drawing
  when they stand still.
- The Mac app's overview and History are on the page's paper: your Kobo
  in the rail's blue, Hardcover in the proof margin, the status in its
  mark's colour, and a sync's outcome as the page shows it. The count of
  books a live sync will send is in red.
- The Mac app keeps only the last four large covers in memory, not every
  one opened since it started, and reads each away from the window's
  thread before showing it.

### Fixed

- ⌘V pastes in the Mac app's text fields, the Hardcover token among them:
  the Edit menu had no Paste (nor Cut, Undo and Redo). A new *Sync* menu
  holds *Sync Now* (⌘R), *Check Again* (⇧⌘R) and *Show the Log*.
- VoiceOver says when a sync starts and how it ended, in the Mac app.
- The Mac app's grey text (authors, facts, labels) is dark enough to read
  in light mode, in every pane, Settings and the widget. A book selected
  in Books keeps its status, marks and gauge readable on the selection's
  blue, and the covers on the Covers pile open by keyboard too. Its red
  "Next sync" stays readable on the grey a selected row takes when the
  window is in the back.
- The Mac app's menu bar has a *View* menu (the four panes on ⌘1 to ⌘4,
  the sidebar on ⌃⌘S, full screen on ⌃⌘F), *Zoom* and *Bring All to
  Front* in *Window*, and a *Help* menu with the guide and the search of
  the menus.
- VoiceOver can move by heading through a book's Details, and open a
  cover on the Covers rows. Covers shows its keys for a few seconds each
  time the keyboard comes into its rows.
- *Open the page* in the Mac app no longer holds up the window while the
  tool starts.
- A book's *Open on the Page* in the Mac app opened the server's front
  page in server mode, not the book; `open --book` now lands on the book
  there too. The button says where it goes: *Open in Browser*, or *Open
  on* and the server's name.
- With Increase Contrast on (Accessibility, Display), the Mac app's grey
  text, colours and rules are stronger: the words 7:1 on the paper.

## 0.16.0 - 2026-10-27

### Added

- *Show* on Covers in the Mac app: the rows hold only the books of one
  of the list's filters, such as the ones that sync (the books in your
  Kobo collection), the ones you are reading or the ones you have not
  started. Covers and Books each remember what you chose to show.

## 0.15.0 - 2026-10-27

### Added

- In server mode the Mac app has your books too, as in local mode: the
  list with its marks, Details, Sync, State, a match, *Set all* and going
  live, all made on the server for you. It asks with this Mac's upload
  token, so nothing new to set up on the Mac. The server needs 0.15.0
  too, and its proxy has to let `/api/app/` past its sign-in, as it does
  `/upload` (README).
- A tip above the Mac app's list of books: one book from your own shelf,
  asked as a question. A book you stopped halfway through more than half
  a year ago, then one on your Want to read that is already on your Kobo,
  then one you never opened. The same one all day; *Not now* puts it
  aside for a month. It is chosen from what the tool already knows;
  nothing is asked of Hardcover or anyone else. In a terminal,
  `book ID --not-now`.
- *Covers* in the Mac app's sidebar: your library as a press run. Three
  rows of covers drift slowly left: at the front the books you read in
  the last year, behind them the rest you read, at the back the ones you
  never opened. Pointing at a cover stops its row and lifts it, with its
  title, how far you are and what the next sync does. A click opens the
  cover large in a third of the window, with its Details and what you can
  do with it beside it; a click on that cover, or Space, shows it over the
  whole window. The arrow keys walk the rows, two fingers move them. A
  red caret marks a book the next sync changes.
  Below the rows: the book you are reading, and the tip. With Reduce
  motion on, the rows stand still. Full screen with ⌃⌘F.
- Your books in Spotlight on your Mac: type a title, and the app opens
  Covers at that book. The index is your Mac's own; removing the app
  takes the books out again.
- A widget for the desktop and Notification Center (macOS 14 and later):
  the book you are reading with its cover and how far you are, and in the
  medium size the tip beside it. A click opens Covers at that book. It
  needs the signed app from the release; a build of your own, signed ad
  hoc, has no widget.
- When a sync marks a book as read on Hardcover, the Mac app says so in
  a notification of its own, "Finished: …", with the book's cover; on
  Linux the cover is the notification's icon. In local mode: in server
  mode the server marks books read, after the upload.

### Fixed

- Book titles in the Mac app are in the page's serif, Source Serif 4, as
  meant. macOS picked the font's subset without lowercase letters, and
  set them in the system font instead.

## 0.14.0 - 2026-10-26

The Mac app gets an icon of its own, drawn like the page, and the disk
image it comes on says what to do with it.

### Changed

- The Mac app has a new icon, drawn like the page: a galley of your books
  with the next sync's red caret in its margin. On macOS 26 and later it
  is a proper icon for those versions, with the system's glass, where the
  old one was shrunk into a grey tile. At the smallest sizes it is drawn
  for the size, not made smaller.
- The disk image the app comes on has its own icon, and its window shows
  what to do: drag the app onto Applications.

## 0.13.0 - 2026-10-24

The Mac app becomes the home of local mode: an overview that draws the
way a sync goes, your books in the app, changed there, and connecting
to Hardcover and going live without the page.

### Changed

- The Mac app's window has a sidebar: *Overview*, *Books* and *History*.
  Overview draws the way a sync goes, Kobo, this Mac, the server (in
  server mode), Hardcover, each with the page's mark for how it is; a
  click shows its checks, and the first that needs something opens by
  itself. A sync plays out along it. In local mode it counts the books
  as well: how many came from the Kobo, how many the next sync sends,
  how many are in the collection. The marks are the page's, in the
  page's colours, where the window had coloured symbols.
- In local mode the Mac app's *Books* is the list of books itself, as
  the page has it: covers, titles, Sync, State and what the next sync
  does on Hardcover, in the page's marks, with search, filters, sorts
  and each book's Details. Sync, State and its date, a match (from the
  books it could be, or a search on Hardcover), removing a book from
  Hardcover and *Set all* are changed there too, without the page.
- In local mode the Mac app connects to Hardcover itself (*Connect…*, on
  the Hardcover link, above the list and in Settings), with a pasted
  token as the second way, and goes live: the page's first run is above
  the list until then, with a red *Go live*. Settings, Sync, has the
  connection and *Send to Hardcover*. Local mode on a Mac needs no
  browser any more.
- In the Mac app, a sync and the doctor say to connect and to choose a
  match in the app, not on the page.

### Added

- `kobo-hardcover-sync books` lists your books in local mode, each with
  what the next sync does with it; `--covers` fetches the covers this
  computer does not have yet, `--json` is for the Mac app.
- `kobo-hardcover-sync open --book ID` opens the page at that book.
- `status --json` counts the books in local mode (`books`), for the
  app's overview.
- `kobo-hardcover-sync token --json` signs in as lines of JSON (where to
  approve, then who signed in), for the Mac app; `settings --set
  live=true` goes live in local mode, and `settings --json` says whether
  it is live.
- `kobo-hardcover-sync book ID` shows one book and changes what the
  page changes: `--sync`, `--state` (with `--date`), `--search` and
  `--pick` for a match, `--remove` from Hardcover. `books --sync MODE
  --filter F` is the page's Set all; `--expect N` changes nothing unless
  that is still N books.

### Fixed

- In the Mac app, what to do no longer names terminal commands: the
  window's checks and a failed sync point at the app's own buttons and
  Settings (*Set up*, *Sync now*, *Check again*, the untested Kobo
  setting). A Kobo the app may not read says what to allow for the app,
  not for a terminal, and has its *Open Privacy* button again.
- Doctor's line about a collection of someone else's says the name is
  chosen on the page, under Settings.

## 0.12.2 - 2026-10-24

Look for a newer version at once: *Check now* in the Mac app's Settings,
*Check for Updates…* in its menu, and `update` in a terminal.

### Added

- `kobo-hardcover-sync update` asks GitHub now whether there is a newer
  version, also when the Mac app's daily look is switched off; `--json`
  for the app. In the Mac app: *Check now* in Settings, App, and *Check
  for Updates…* in the app menu.

## 0.12.1 - 2026-10-24

The Mac app's window shows a sync that plugging in the Kobo started, and
says when macOS hides what notifications say.

### Fixed

- The Mac app's window shows a sync that plugging in the Kobo started:
  "Syncing…" while it runs, then its outcome. Before, the window looked
  idle until that sync had ended, and *Sync now* during it only said that
  another sync was running.
- *Sync now*'s steps fold into History a few seconds after the sync,
  instead of staying on screen: an old "A sync is already running" read as
  if one still was. An answer that History does not keep ("No Kobo
  found") stays until the next sync.
- The window says when macOS shows only the app's name in a
  notification (*Show previews* set to Never), with a button to its
  settings.

### Added

- `status --json` says whether a sync is running now, and what started
  it (`"syncing"`); `status` says so in a row.

## 0.12.0 - 2026-10-24

The Mac app gets a window and Settings of its own: what `status`,
`doctor`, `history` and the settings tell in a terminal, about this Mac.

### Added

- `kobo-hardcover-sync history`: the last syncs on this computer, newest
  first, with what started each and what it said. The last hundred are
  kept in `history.jsonl` in the tool's folder, without book titles.
- `kobo-hardcover-sync settings`: this computer's settings, and `--set
  NAME=VALUE` to change one that is true or false, instead of editing
  `config.toml`.
- `--json` for `status`, `doctor`, `history` and `settings`, and `sync
  --steps` (each step and the outcome as a line of JSON): what the Mac
  app's window reads, and usable in scripts. Each answer carries
  `"schema": 1`.
- `setup --check`: before anything changes, ask the server whether it
  answers as kobo-hardcover-sync does. A typo in the address, or a
  server that is down, then changes nothing. It also says when the
  server knows this computer already.
- The Mac app has Settings (⌘-,): where the reading goes and the
  server's address, the upload token's hash and a new token, eject after
  a sync, a detailed log, an untested Kobo version, looking for a newer
  version; in local mode also the webhook and *Export my reading…*.
  *Remove…* stops syncing on this Mac, or also deletes what the app
  keeps there, and says how to remove the app itself.

### Changed

- The Mac app has a window of its own, about this Mac: whether it is
  ready for the Kobo, a check of everything a sync depends on with a
  button where the app can mend something, a sync's steps as it runs,
  and the last syncs, with the log a click away. It replaces the dialog
  that showed the last message. While the window is open the app has a
  Dock icon and a menu bar.
- The notification of a sync the Kobo started shows as soon as the sync
  has said it, instead of after the once-a-day look for a newer version.

## 0.11.1 - 2026-10-24

The Mac app's *Sync now* always answers, and notifications are asked for
at a better moment.

### Fixed

- The Mac app: *Sync now* shows that it is busy, and then what the sync
  did, in the app's window. When there was nothing new, or no Kobo is
  plugged in, it says so; before, it said nothing at all.
- The Mac app asks whether it may show notifications after setup's
  windows are closed, and says beforehand that it will ask. Before, the
  question came while they were open, and was easily missed or answered
  no. When notifications are off, the app's window says so, with a
  button to their settings.

## 0.11.0 - 2026-10-24

A Mac app: download it, drag it to Applications, open it.

### Added

- A Mac app, signed and notarised, as a third way to install on a Mac:
  `Kobo-Hardcover-Sync-0.11.0.dmg` on this release, for Apple silicon and
  macOS 13 or newer. Drag it to Applications and open it. It sets itself
  up (on this computer, or with a server) without a terminal, and starts
  a sync when the Kobo is plugged in. It uses the same folder and
  Keychain items as a Homebrew installation, and takes over its trigger.
  See `docs/macos-app.md`. This is its first release: it has not yet
  been tried on many Macs, so please say how it went in an issue.
- The Mac app looks for a newer version once a day at most, after a
  sync, and says so on the page and in its window. It never updates
  itself, and it can be switched off. Homebrew and PyPI installations
  do not look.

### Changed

- `setup` from Homebrew or PyPI, on a Mac where the app has the trigger,
  leaves the trigger to the app instead of installing a second one.

## 0.10.1 - 2026-10-08

Connecting again ends the old connection at Hardcover.

### Fixed

- Connecting to Hardcover again, or pasting a token in place of a
  connection, ends the earlier connection at Hardcover, as Disconnect
  does. Before, it stayed listed and working there.

## 0.10.0 - 2026-10-08

One book on two Kobos, one write for a new collection name, and a
shelf that is known to be yours.

### Added

- The tool remembers which Hardcover account your books were put on. A
  connection to another account now stops the sync from the first book,
  before anything is sent or switched off, and says which two accounts
  they are (before, it was noticed only once three or more books seemed
  gone from the shelf). Moving to another account on purpose: *Start
  over* under Settings, or `kobo-hardcover-sync token --start-over`.

### Changed

- The same book on two of your Kobos is one book: Sync, State and the
  Hardcover match are set for the book, not per Kobo. The page lists it
  once, as the Kobo you read it on last says it, and what you set holds on
  both. A book that turns up on another Kobo later brings what was set for
  it, so a match you chose by hand is no longer looked up again. Where the
  two copies differed before, the one read last decides, once.
- Another collection name: the old collection is taken off and the new
  one made in one write to the Kobo, with one backup instead of two. When
  the new name cannot be used, because a collection of yours already has
  it, the old collection now stays instead of being removed.

## 0.9.0 - 2026-10-06

A webhook: each sync to an address of your own.

### Added

- `kobo-hardcover-sync webhook URL`: after every sync that read something
  new from the Kobo, a POST with JSON to an address of your own, for a
  reading tracker, a database or an automation. It carries the book you
  are reading, the books that changed in that sync, and the reading
  summary. `--token` adds a Bearer token, kept in the Keychain. It is sent
  only over https (plain http only to this computer), a redirect is never
  followed, and a test must be answered before anything is stored. Local
  mode. What is sent: [docs/webhook.md](docs/webhook.md).

## 0.8.0 - 2026-10-05

Your reading as a file: for a database or dashboard of your own, with or
without Hardcover.

### Added

- `kobo-hardcover-sync export`: your reading as JSON, for a database, a
  spreadsheet or a dashboard of your own. Every book the Kobo has seen
  opened, with how far, the dates and whether it syncs, the minutes read
  per day, and the summary `/api/stats` gives. It needs no Hardcover
  account. `--output FILE` writes a file only you can read; on a server,
  `--reader NAME` exports one reader.
- `export --output FILE --every-sync` writes that file again after every
  sync on your own computer, for a dashboard that reads it; `status` says
  where it goes, and `export --stop` ends it. A file that cannot be
  written is said in the sync's notification; the sync itself still
  counts.
- The same export on the page: Settings, *Your reading as a file*, a
  download for the reader who is signed in. On a server that is the way
  for a reader without a shell there.

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
