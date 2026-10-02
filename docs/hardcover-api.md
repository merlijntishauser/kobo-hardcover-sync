# Hardcover's API: what it allows, and what this tool does with that

Read on 2026-10-02. Sources: Hardcover's documentation as published in its
public repository (`hardcoverapp/hardcover-docs`, the pages *Getting Started
with the API*, *OAuth*, *PAT Link Builder* and *Actions & Scopes*, last
changed 2026-09-24), `https://api.hardcover.app/capabilities.json`, and a
few read-only requests to the live API. The documentation site itself
refuses automated reading, which is why this page exists: so the next
person does not have to find out again.

Hardcover calls the API a beta: "Anything you build using it could break in
the future", and tokens may be reset without notice.

## What Hardcover asks

| Their rule | What this tool does |
|---|---|
| "You own your data. This means you can't use the API to access and use someone else's data." | Each reader's token is used for that reader's own shelf, and nothing else. |
| "Don't share your token." It must be kept where it is secure; not in a browser. | Local mode: in the computer's secret store. Server mode: encrypted in the server's database, never sent to a browser, never logged. |
| A commercial product or a public website may not use data owned by users, "unless on behalf a user who has allowed their data to be accessed". | Not commercial, and it only acts for the reader who gave the token. The stats endpoint shows a reader's own numbers, behind that reader's own token. |
| "it is recommended to include a user-agent header with a description of the script". | `kobo-hardcover-sync/<version>`. |
| Not to be used "to train large language models". | It is not. |
| Rate limits per reader: 60 requests a minute (a burst of 10), 5000 a day on the free plan; each top-level field of a request counts as one. A request holds at most 5 top-level queries. | One request every 1.1 seconds at most, one or two top-level fields each. When told to slow down it waits as long as Hardcover says. When the day is used up it stops. |
| "Queries have a max timeout of 30 seconds", searches 2 seconds. | The shelf is asked for in pages of 250 books. |

## Tokens: what changed in August and September 2026

- A token ("personal access token") now has an **expiry date the reader
  chooses** and a list of **permissions**. The old rule "tokens expire every
  1 January" is gone from the documentation.
- This tool needs four permissions, taken from `capabilities.json`:
  `read:me:content` (who am I), `read:catalog` (find the book and its
  editions), `read:library` (read the shelf), `write:library` (change it).
  Settings and the `token` command link to Hardcover's form with exactly
  those ticked.
- **Tried on 2026-10-02** with a token made through that link: every read
  the tool makes works (who am I, the shelf, read entries, editions by
  ISBN, editions of a book, search), and so do changes: two syncs put a
  book on the shelf and sent its progress, without an error. A missing
  permission would be reported by name.

## The open question: OAuth

Hardcover added OAuth on 2026-09-24 and is plain about when to use it:

> For anything a user signs into, use OAuth [...] Never ask a user to paste
> a PAT into your app.

> If you're building something other people install rather than a script
> they run themselves, consider OAuth instead.

and, about tokens pasted by hand: "great for scripts and tools you run
yourself".

What that means here:

- **Local mode** (one person, their own computer, their own token) is the
  case a pasted token is meant for. Hardcover's own examples of tools that
  take a pasted token are of this kind (an e-reader plugin). For a tool
  "other people install" they would rather see OAuth; for a command-line
  tool that is the browser flow with a loopback address, or the device
  flow.
- **Server mode** (several readers each paste a token into a web page) is
  what they ask not to do. For a household on its own server it harms
  nobody, but it is not how they want a multi-user app built. The fitting
  flow is the confidential web app one.

Both need an app registered on Hardcover by whoever publishes the tool, and
a decision on what happens to installations that hold a pasted token. That
is a decision, not a fix: it has its own ticket and is to be settled before
the first public release.

## What the live API does (2026-10-02)

- A shelf of 131 books comes back whole without a limit; a catalogue query
  for 1000 rows returned 1000. No cap was found, and the code does not rely
  on that: it pages, and counts with `user_books_aggregate`.
- A token that is not accepted: HTTP 401, `{"error": "invalid_token"}`.
- Something a token may not do: HTTP 403, with `error` saying which kind.
- Every answer carries `RateLimit` and `RateLimit-Policy` headers; a 429
  carries `Retry-After`.
