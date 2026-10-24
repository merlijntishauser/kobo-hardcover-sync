# The Mac app as the home of local mode

Design, agreed on 2026-10-24, after 0.12.2. It follows the window of
0.12.0 (`2026-10-24-mac-app-window-design.md`), which kept the books on
the page and the page's look out of the app. This design changes both
for local mode on a Mac: the books come into the app, drawn natively,
and the window takes the page's marks.

## Why

The window answers whether this Mac is in order, but as a list of checks
that reads the same whether one thing is wrong or nothing is. Everything
about the books still sends the reader to the browser: the first run,
a match, a State, going live, connecting to Hardcover. For someone who
uses the app instead of a terminal, local mode is half an app and half
a web page.

The overview should answer "is everything in order, and if not, where
does it break" in one look, with the details one click away. In local
mode nothing should need the browser.

## Decisions

| Topic | Decision | Turned down |
|---|---|---|
| Books | **Native in local mode**: Overview, Books and History in one native window. Books is a native list, fed by the tool in JSON. The page stays for server mode, for Linux, and for anyone who prefers it. | Only the books that need something native, the rest on the page; the page shown in a web view inside the window; no books in the app. |
| Overview | **The chain**: the sync drawn as the path it takes, Kobo → This Mac → (Server) → Hardcover, each link ok or not. | Cards in a grid; Health folded to one row per part. |
| Look | **A Mac app with the page's marks**: system font, sidebar, standard controls; status in the page's proofreader marks and two pencils; book titles in Source Serif 4. | Plain Mac (SF Symbols, brand only in the wording); the page's full galley world in SwiftUI. |
| Hardcover | **Connected in the app**: the same sign-in as the page (a link and a short code), shown natively; pasting a token stays the second way. | Connecting on the page only. |
| First version | **Everything, in steps** that each ship; until a step lands, its action opens the page at that book. | Daily use only; read-only. |
| Window | **One window with a sidebar**: Overview, Books, History. Settings stays its own window (⌘,). | A second window for Books. |
| Source of truth | **The tool**, as before. What the next sync does with a book is still decided once, in Python; the app draws it. | The app reading the tool's database itself. |

## The look

System font, sidebar, standard controls, the system's light and dark.
Status is the page's marks, drawn as vector shapes in the strokes of
`web/marks.py`, never SF Symbols or coloured dots: the tick, the caret,
the dashed caret, the circled query, the ink square with a cross, the
dash and *stet*. The two pencils keep their jobs: red is what a sync
sends and fills only *Sync now* and *Go live*; blue is the reader's own
choice or a question for them. Book titles are set in Source Serif 4,
bundled in the app with its licence notice; nothing else is.

## The overview: the chain

The sync is drawn as the path it takes: **Kobo → This Mac → Hardcover**,
with **Server** between This Mac and Hardcover in server mode. Each link
carries its mark and two short lines ("Clara Colour · not plugged in",
"Login Items: not allowed", "Live · @sam"). The arrows carry the books:
"312 books read" from the Kobo, "8 change at the next sync" to
Hardcover, and an arrow back to the Kobo for the collection ("41 in On
Hardcover").

The links are doctor's three groups as they are (`doctor.GROUPS`), with
the Server check taken out of This computer into a link of its own.
A click on a link opens its checks under the chain, with the fix buttons
the window has now. One thing that needs the reader opens by itself,
with its sentence and its button: today's "Needs attention", aimed at
its link.

A sync plays out on the chain. While it runs, from the `--steps` lines,
the arrow being worked on carries the red line gauge (the page's
motion); a link that is done gets its tick. Then it folds into History,
as now. This is the same for a sync the Kobo started.

The top line with *Sync now* stays above every section.

## Books

A table: the book (cover, title in Source Serif, author), *Sync*,
*State*, and *Hardcover status* with its mark and words. When the next
sync changes something, the old value is struck in red and the new one
written in after a caret, as on the page. A missing cover is the crossed
box. The legend of the seven marks sits above the table (the page's
Legend Rule). Search, the page's filters and its sort are in the
toolbar.

Details is a pane on the right of the list: the same struck and inserted
correction as the row, the State with its date, the match and its
editions, and removing the book from Hardcover.

In local mode while it is a dry run, the first run sits above the list
as on the page: "Pick the books that are yours", the count switched on
so far, and the three steps (Connect to Hardcover, Pick your books, Go
live). *Go live* is red.

In server mode, Books in the sidebar opens the server's page: the books
live behind its sign-in, which the upload token cannot pass.

## States

- Not set up: the window is *Set up*, as now.
- The Kobo not plugged in is the normal state: the dash and "last seen",
  never a warning.
- Syncing, started here or by the Kobo.
- The last sync failed: the ink square on the link where it broke.
- Dry run: the Hardcover link says so, and the first run shows on Books.
- Books that need a match: a count on Books in the sidebar.
- No permission to read the Kobo, a tool that does not start, the
  preview build.
- A library is about 300 to 1,500 books; the table gets them all at
  once.

## The tool's side

Each also usable in a terminal, each with `"schema": 1` and a sample
answer that the Python tests and the `macos-app` job both hold to:

- `books --json`: every book with what the row shows (title, author, the
  cover's file, Sync, State, the status's kind and words, the
  correction) and the filters it is in, so searching, filtering and
  sorting happen in the app without starting the tool per keystroke.
- `book <id> --json`: what Details shows. `book <id> --set …`: Sync,
  State and date, a chosen match, a search for one, removal.
- Set all, through the same filter as the page.
- `settings --set live=…` for going live.
- `token --json`: the device sign-in as lines of JSON (the link and the
  code, then who signed in).

First, the row model moves out of `web/app.py` (`action()`,
`hc_status()`, `correction()` and what they need) into a module the
page and these commands both use, so the two drawings cannot drift.

## Untouched

The page in server mode, the admin page, signing up, Linux, the page's
own look. macOS 13 stays the oldest supported, so Details is a split
view, not `.inspector`. No menu bar item, and the app does not run
between syncs. No galley paper in the app's chrome, no coloured dots or
badges.

## Order

Each step ships on its own:

1. The shell and the overview: the sidebar (Books opens the page until
   step 2), the chain instead of Health, the live sync on the chain.
2. Books to read: `books --json`, the table, its marks, search, filters,
   sort, the legend, covers, Details. A change opens the page at the
   book.
3. Changing books: Sync, State, match, removal, Set all.
4. Hardcover and the first run: the native sign-in, the first run,
   *Go live*. Then local mode needs no browser.

## Open

- A change starts the tool, about 0.3 s each. Measure it in step 3; only
  then decide whether the app keeps one tool process running.
- The chain in a narrow window: it stacks vertically, or folds into a
  short list. Decide when it is built and looked at.
