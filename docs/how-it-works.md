# How it works, and why

What kobo-hardcover-sync is built to do, the parts it is made of, and the
reasons behind the choices that are not obvious. What it does with each
book is in [sync-rules.md](sync-rules.md); running it on your own computer
is in [local-mode.md](local-mode.md); what Hardcover's API allows is in
[hardcover-api.md](hardcover-api.md).

## The problem

- A stock Kobo e-reader with books from the Kobo store keeps what you read
  to itself. Kobo's cloud has no public API.
- KOReader has a Hardcover plugin, but KOReader cannot open the store's
  DRM books.
- The reading data is on the device, in `.kobo/KoboReader.sqlite`. So that
  file is the source: read it when the Kobo is plugged in, and tell
  Hardcover what changed.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| What goes to Hardcover | Status, progress and dates. No highlights, no ratings. | The things the Kobo knows for certain. |
| Which books | Books already read before the first import start *Off*; books opened after it sync by themselves. | See *Reading time is shared*. |
| Switching a book off | Stops syncing. Taking it off Hardcover is a separate, explicit button. | Stopping and deleting are different wishes. |
| Matching | By ISBN, else by title and author when both agree. Otherwise the reader picks. | A wrong match puts a book on someone's public shelf. It never guesses. |
| First use | Dry run: everything is matched and planned, nothing is written to Hardcover until the reader goes live. | The first list deserves a look. |
| Writing to the Kobo | Only one collection, and only behind a version gate, with a backup. | Everything else on the device is the Kobo's. |
| Readers | Each record is keyed by reader and by Kobo. | A household often shares one Kobo account over several e-readers. |

## Two ways to run it

```
   local mode                         server mode
   ----------                         -----------
   your computer                      computer the Kobo is plugged into
     reads the Kobo                     reads the Kobo
     talks to Hardcover                 uploads the book rows  ------>  server
     writes the collection              writes the collection  <------    state for every reader
     page on 127.0.0.1                                                    talks to Hardcover
                                                                          page behind your sign-in proxy
```

- **Local mode:** one reader, no server. Plugging in the Kobo runs one
  sync; the page is started when asked for.
- **Server mode:** several readers. The server has no login of its own: it
  sits behind a forward-auth proxy and believes the `Remote-User` header
  only from the proxy's address. It refuses to start without knowing that
  address.

The engine (reading the Kobo's database, the state, the plan, Hardcover,
the collection) is the same code in both.

## What is read from the Kobo

- **Books:** rows of `content` with `ContentType = 6`: title, author, ISBN,
  `___PercentRead`, `ReadStatus` (0 unread, 1 reading, 2 finished),
  `DateLastRead`, `TimeSpentReading`, `LastTimeFinishedReading`.
- **Events:** the `Event` table, for the first time a book was opened on
  this device.
- **Never:** the `user` table, which holds the Kobo account's login
  tokens. In server mode the upload is built from a list of what is needed
  (the book rows and the events), and the server refuses anything more.

### Reading time is shared, events are not

Found on a real device, and the reason the selection works the way it
does: `TimeSpentReading` is synced through Kobo's cloud across every
device on the account. A replacement Kobo, three weeks in use, showed
reading time on 408 of its 688 books, with last-read dates going back five
years: the previous device's history, and that of everyone else on the
account. The `Event` table is device-local: 97 rows, 20 books, all from
the day the device was first used.

So:

- **History**, every book with reading time at the first import, is chosen
  by hand, once. It starts *Off*.
- **New books**, whose first event on this Kobo comes after that import,
  sync by themselves and are marked as new, so they can be switched off.
  What someone else reads on another Kobo never creates events here.
- **Reading minutes** count only for books opened on this Kobo.

## Hardcover, both ways

At first the tool only wrote to Hardcover. But readers edit there too, and
those edits were overwritten the next time the book changed on the Kobo.
Now every sync starts by taking over what changed on Hardcover.

- **How an edit is seen:** for each shelf book, Hardcover's status, edition
  and finish date are compared with what was recorded the last time this
  tool wrote or read that book.
- **What it becomes:** the same kind of override a reader can set on the
  page (pinned as finished, a re-read, want to read, did not finish, sync
  off). The table is in the sync rules.
- **Progress is never taken from Hardcover.** The Kobo knows where you are.

### The edition

When the reader has not chosen an edition on Hardcover, the tool picks
one: the edition with the Kobo's ISBN if Hardcover marks it as an ebook,
else an ebook edition in the book's language, else any ebook edition, else
the one with the Kobo's ISBN, else Hardcover's default. An ebook edition
with a foreign title beats a physical one in the right language, because
the form is what was read. Checked once per book, and again after 30 days,
since the catalogue grows.

Measured on a first real shelf of 100 books, mostly not in English: the
rule moved only 3 books. For most of the rest Hardcover has no ebook
edition in that language, or lists the right ISBN as a physical book.
Fixing that means editing Hardcover's public catalogue, which this tool
does not do; the page has a filter for those books.

### One read-through per book

Hardcover makes a read entry by itself when a book lands on the shelf. The
tool updates that one. Adding another made every book count as read twice
(95 duplicates on that first shelf, removed by hand). Only a re-read the
reader declared adds an entry.

## The collection on the Kobo

A shared Kobo account lists everyone's books on every device. A collection
holding the books a reader syncs gives them a list of their own. It is the
one thing written to the device, and it is treated accordingly:

- only the collection the tool made itself, known by the id it stored; a
  collection of the same name that it did not make is left alone;
- a version gate: a database version the code was not tried on is not
  written to;
- a full backup before a write (the last three are kept), one transaction,
  rows shaped like the Kobo's own, nothing written when nothing changed.

What a Kobo does with it (seen on software 6.0):

- collections are `Shelf` and `ShelfContent` rows; removing one is
  `_IsDeleted = 1`;
- a collection inserted this way is shown by the Kobo, keeps its id
  through account syncs, and was never sent to the account (`_IsSynced`
  stayed 0). It stays on that device; others on the account do not see it.

## Readers on a server

- **Self sign-up.** Anyone the proxy lets through gets a sign-up page; one
  click creates their reader, in dry run. The proxy already decides who may
  come in; a second approval would only be friction. The first reader is
  the admin.
- **Each reader enters their own Hardcover token.** It is checked with
  Hardcover before it is stored, never shown again, and removing it puts
  the reader back in dry run.
- **Tokens are encrypted in the database**, with a key that comes from the
  environment and is in neither the database nor its backups. Chosen over
  plain text (a copy of the database would hold everyone's shelf access)
  and over one secret per reader outside the database (no self-service).
- **A computer that uploads** has its own token. The reader pastes the
  token's SHA-256 under Settings; the hash cannot upload anything, so it is
  safe to show and to type.
- **Safeguards:** every settings route works on the signed-in reader only,
  with no reader parameter to tamper with; the admin page shows counts and
  states, never a book or a token; the last admin cannot step down or be
  removed; removing a reader deletes what the tool holds, never their
  Hardcover shelf; every form checks where it came from.
- **The stats endpoint** (`/api/stats/<reader>`: minutes read, the current
  book, books finished this year) is outside the sign-in, for a dashboard.
  It needs a token of its own, per reader, and can change nothing.

## When things go wrong

- A sync never loses what the Kobo said. If Hardcover fails, the book
  stays pending and the next sync tries again.
- One book's error does not block the others; trouble that is the same for
  every book stops the run.
- An upload is refused when it holds the Kobo's login tokens, more tables
  than the server reads, is too large, or is not a Kobo database; the
  answer says which.

## The pages

One frame for every page: a sidebar that is "your Kobo" (a photograph of
one, the navigation, what the Kobo and Hardcover last did, *Sync now*) and
a sheet that is "your books". On a phone the sidebar becomes the top of
the page, the navigation a bar at the bottom, and each book a card. Two
photographs, one per theme, both of a real Kobo; two typefaces, Literata
for titles and Sora for the interface. Everything is served by the tool
itself, book covers included: it fetches them from Kobo's servers once
and keeps them, so the browser talks to nobody else.

`browser_tests/shots.py` renders every page in both themes at three widths
with a made-up shelf; look at its pictures after a change to the
stylesheet.

## Not built

- **A hook on the Kobo itself** that sends the database over Wi-Fi, so
  nobody has to plug anything in. It would have to be installed through a
  firmware update package and probably reinstalled after each Kobo update;
  untried on current Kobo software.
- **Highlights and ratings.**
- **Statistics shared between readers.**
