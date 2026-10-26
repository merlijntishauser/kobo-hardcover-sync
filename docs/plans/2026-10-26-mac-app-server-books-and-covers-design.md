# Your books in the Mac app in server mode, and a reason to open it

Design, agreed on 2026-10-26, after 0.14.0. It follows
`2026-10-24-mac-app-native-books-design.md`, which brought the books into
the app for local mode and left server mode on the page.

## Why

In server mode the app is a sync button and a chain: Books in the sidebar
says "Your books are on the server, behind its sign-in." A reader with
the app on their Mac has to open a browser, pass the household's sign-in
and look at the same list the app already knows how to draw.

And in either mode the app shows a library the way the page does: as a
list. The covers are the one picture the tool has of your reading, and
the Mac can do more with them than a browser tab: fill a screen, sit on
the desktop, turn up in Spotlight, run as the screen saver.

## Decisions

| Topic | Decision | Turned down |
|---|---|---|
| Server books | **Browse and change, as in local mode**: Sync, State, a match, removal, Set all, Go live. Admin and other readers stay on the page. | Browse only; the page in a web view. |
| Who may | **The device's upload token**, for its own reader only. It already sends that reader's whole Kobo database and fetches their collection; it is in the Mac's Keychain. Removing the device under Settings on the page takes it all away. | A second token per Mac, made on the page: safer on paper, one more step for every reader, and the same Keychain holds both. |
| Source of truth | **The tool, as before.** In server mode `books --json` and `book ID … --json` ask the server and answer in the same shape; the app does not know which mode fed it. | The app talking to the server itself. |
| The tip | **From your own shelf**, chosen by the tool, one at a time. Nothing is sent anywhere. | Hardcover's lists and recommendations: new API calls, and a stranger's taste. |
| Covers | **The press run** (below), a pane of its own: *Covers*, between Books and History. | The reading year on a time axis; a shelf of drawn spines. |
| Motion | **A second authored motion, for Covers only**: the drift and the lift. DESIGN.md allows one (the strike and the write-in); this adds one, by the reader's choice. Under reduced motion the run stands still. | A still wall of covers. |
| Native reach | **The same pile, smaller, everywhere**: a widget, Spotlight, a *Finished* notification with the cover, a screen saver. | Each as its own design. |

## The press run

The window's Covers pane, and full screen with ⌃⌘F.

- **The run**, the upper 62%: three rows of covers drifting left, the
  front row largest and fastest. Front row: books read in the last year;
  middle row: every other book you read; back row: books on your Kobo
  you never opened. Covers are 150, 108 and 72 pt tall, with the cover
  shadow and nothing else. A book without a cover is the crossed box.
- **Marks on the run**: only the red caret, at the foot of a cover that
  the next sync changes, so "8 change at the next sync" can be seen.
  Every other mark waits until the cover is lifted.
- **Hover** slows the row to a stop and lifts the cover under the
  pointer (1.12×, 0.25 s, the page's expo ease-out), with its title in
  Source Serif, the author, the line gauge and its status line under it.
  **Click** opens its Details as a sheet, with every change Books has.
  **Space** shows the large cover (Quick Look). Arrow keys move along a
  row; Return opens; the run stops while the keyboard is in it.
- **Two fingers** on the trackpad move the run by hand; it picks up its
  drift a few seconds after you let go.
- **The delivery pile**, the lower 38%, under a 3px double rule: the book
  you are reading (the most recently read that is not finished) at 150
  pt, the tip beside it at 150 pt, then the title in Source Serif at
  22 pt, the gauge, the facts, and the tip's question.
- **Speed**: the front row moves one cover width in about six seconds;
  the rows behind are slower. It stops when the window is not visible.

States: no books yet (the run is empty paper and the pile says what to
do: plug in the Kobo); covers still coming (the crossed box, filled in
as they arrive); a server that answers 404 (an older server: "Update the
server to see your books here"); reduced motion (a still wall, moved by
hand, the lift without growing).

## The tip

One book, chosen by the tool, the same until you act on it or a day
passes. The first rule that finds a book wins:

1. **Left off**: started, between 10% and 90%, not finished, not read for
   six months. "You stopped at 31% in March 2025. Pick it up again?"
2. **Wanted, and here**: on your Want to read on Hardcover, and on your
   Kobo. "On your Want to read, and already on your Kobo."
3. **Never opened**: on your Kobo, never opened. "On your Kobo, never
   opened." The tool does not read when a book came onto the Kobo; if
   the Kobo's database turns out to hold it, the oldest goes first and
   the sentence says the year.

It carries the blue circled query: it is a question for you. *Open*
opens its Details; *Not now* puts it aside for 30 days and shows the
next. `books --json` carries it as `tip` (the book's id, the rule, the
sentence); `book ID --not-now` puts it aside. Nothing is sent to
Hardcover or anywhere else.

## Everywhere else

Each is the pile, at another size, read from what the app last fetched:

- **Widget** (macOS 14 and later, the desktop and Notification Center):
  small, the current cover and its gauge; medium, the cover and the tip.
  It needs a widget extension in the app and an app group for the data,
  so the build and the signing change.
- **Spotlight**: every book's title and author, so typing a title opens
  Covers lifted at that book.
- **Notification**: after a sync that marked a book finished, "Finished:
  Piranesi" with its cover attached.
- **Screen saver**: the run without the pile and without chrome, slower;
  installed from the app (Settings, *Use as screen saver*).

## The tool's side

- The server: `GET /api/books`, `POST /api/book/{id}` (the same changes
  as `book ID`), `POST /api/books/sync` (Set all), `GET /api/cover/{id}`
  (`thumb` or `large`), all with the device's bearer token, all answered
  for that device's reader only, through the same row model as the page.
  Open paths like `/upload`: the proxy lets them through, the token is
  the key. Not for Admin, signing up, tokens or devices.
- The tool on the Mac, in server mode: `books --json` and `book …` ask
  those, and keep the covers they fetch in the same cover cache as local
  mode, so `cover` in the answer is still a file.
- `books --json` gains `tip`; `book ID --not-now` is new; both modes.
- A schema bump only if a field changes meaning; new fields do not.

## Untouched

The page and its look, the admin page, signing up, Linux. Books stays the
list it is. No menu bar item: the app still does not run between syncs
(the earlier design), and the widget gives the same glance without it. No Hardcover call for the tip. No colours outside DESIGN.md,
no blur, no glow.

## Order

Each step ships on its own:

1. **Server books**: the server's API, the tool asking it, Books in the
   app in server mode. An older server: the placeholder stays, with the
   sentence about updating.
2. **The tip**: the rules, `tip` in `books --json`, `--not-now`, the tip
   at the top of Books.
3. **Covers**: the press run in the window and full screen.
4. **Spotlight and the notification.**
5. **The widget**: the extension, the app group, the build and signing.
6. **The screen saver.**

## Open

- The widget extension and the screen saver need checking first: whether
  a widget built without an Xcode project (build.sh uses `swiftc`)
  signs and notarises, and whether a screen saver may read the app's
  covers (macOS runs third-party screen savers in a sandboxed host).
  Either may turn out not to be worth it; the steps before do not
  depend on them.
- Covers: the cache holds a thumbnail (240 by 360) and a large size
  (1200 by 1800). The thumbnail is sharp for all three rows on a Retina
  screen; only the pile and Space take the large one. Measure memory and
  the drift's frame rate with 1,500 books.
