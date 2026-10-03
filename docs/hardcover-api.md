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

## OAuth: what was decided

Hardcover added OAuth on 2026-09-24 and is plain about when to use it:

> For anything a user signs into, use OAuth [...] Never ask a user to paste
> a PAT into your app.

> If you're building something other people install rather than a script
> they run themselves, consider OAuth instead.

and, about tokens pasted by hand: "great for scripts and tools you run
yourself".

This tool is something other people install, so it signs in with OAuth,
and keeps the pasted token as a second way.

**Which kind of app.** Hardcover has three: a web app on a server (it
gets a secret, and Hardcover sends the reader back to a registered https
address), a single-page app, and "mobile, desktop, or CLI" (public: no
secret). This tool runs on a reader's own computer, or on a household's
own server at an address only they know, and its code is public. It
cannot keep a secret and has no one address to register. So it is a
public app, for both ways of running it.

**Which flow.** On a server, the device flow (RFC 8628): the tool shows a
link and a short code, the reader approves on hardcover.app, the tool
collects the tokens. It needs no address to come back to, which a
household's server, at an address only they know, could not offer one
shared app.

On a reader's own computer Hardcover suggested the standard flow instead
(2026-10-03, on their Discord): the authorization code flow with PKCE
(RFC 7636), the browser coming back to an address on this computer
(RFC 8252, `http://127.0.0.1:<port>/oauth/callback`). Nothing to type, no
code to compare. Hardcover publishes what it needs
(`api.hardcover.app/.well-known/oauth-authorization-server`): the
authorize page at `hardcover.app/oauth2/authorize`, PKCE with S256, public
clients without a secret, and its own name (`iss`) in the answer, which
the tool checks. Both the `token` command (a moment's server on a free
port) and the local page (its own address) use it. It needs that address
registered for the app at Hardcover, with any port accepted, so it is off
until it is: `LOOPBACK_READY` in `engine/oauth.py`, and
`KHS_HARDCOVER_LOOPBACK=1` to try it before. `token --code` keeps the
device flow at hand.

The local page's cookie is `SameSite=Strict`, so it does not come along
when Hardcover sends the browser back. The way back is checked on its
own: from this computer, to the page's own address, with the `state` of a
sign-in the page started; the code is useless without the PKCE secret the
page kept. A moment's page then sends the browser on to Settings from the
page's own origin, where the cookie applies again. A browser test goes the
whole way round against a stand-in Hardcover.

Hardcover warns that both public flows can be misused by someone who
copies the app's public id; PKCE and the state keep a stolen code or a
forged answer from being of use to them.

**The tokens.** An access token lasts a week and is used like a pasted
one. A refresh token lasts six months and is replaced on every use; one
that is used twice ends the whole connection. So renewing happens in one
place (`engine/oauth.py`, `usable`), for one reader at a time: a lock in
the server's process, and on a reader's own computer a lock on a file,
because a sync and the page are two programs. The new pair is kept before
it is used. A renewal that got no answer is not sent again while the old
access token still works. The connection is kept where a pasted token is
kept: encrypted in the server's database, or in the computer's secret
store.

**What a reader sees when it ends** (revoked on Hardcover, or six months
without a sync): the run is recorded as one that could not start, with
"Connect again under Settings".

**The app.** Registered at Hardcover by this project; its id is in
`engine/oauth.py` and is public by design. `KHS_HARDCOVER_CLIENT_ID` names
another app, for a fork. Without an id the tool offers only the pasted
token.

**Seen working against Hardcover** (2026-10-03, one reader on a
self-hosted server): the sign-in from the page to "Connected", a sync with
the access token, a renewal (the refresh token exchanged for a new pair,
and the sync after it), and the check that asks whose token it is. Not
seen yet: disconnecting (the revoke), a sign-in that is refused, the
`token` command on a real computer.

Settled (2026-10-03): Hardcover is content with the device flow for
self-hosted servers. Open: whether they accept the loopback address with
any port for a public app, so that the browser sign-in can be switched on.

## What the live API does (2026-10-02)

- A shelf of 131 books comes back whole without a limit; a catalogue query
  for 1000 rows returned 1000. No cap was found, and the code does not rely
  on that: it pages, and counts with `user_books_aggregate`.
- A token that is not accepted: HTTP 401, `{"error": "invalid_token"}`.
- Something a token may not do: HTTP 403, with `error` saying which kind.
- Every answer carries `RateLimit` and `RateLimit-Policy` headers; a 429
  carries `Retry-After`.
