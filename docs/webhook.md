# The webhook

After every sync that read something new from the Kobo, the tool can send
it to an address of your own: a reading tracker, a database behind a small
API, an automation such as n8n or Home Assistant. It is not made for one
service. It sends a POST with a JSON body, described below, and your side
does with it what it likes.

This is local mode only: the computer the Kobo is plugged into sends it.

## Set up

```
kobo-hardcover-sync webhook https://tracker.example.org/api/kobo --token
```

`--token` asks for a token, which is sent as `Authorization: Bearer
<token>` and kept in the Keychain (or the desktop keyring), never in a
settings file. Leave it out when your address needs none.

A test is sent first, with `"event": "test"`. Nothing is stored unless
your address answers it with a 2xx status, so a typo or a wrong token is
found at once.

| | |
|---|---|
| `kobo-hardcover-sync webhook` | Where it goes now, and whether with a token. |
| `kobo-hardcover-sync webhook --test` | Send a test now. |
| `kobo-hardcover-sync webhook --token` | Give the same address a new token. |
| `kobo-hardcover-sync webhook --remove` | Stop, and forget the address and the token. |

The rules it keeps:

- **https only.** Plain http is accepted to this computer itself
  (`localhost`, `127.0.0.1`), where nothing crosses a network.
- **No user name or password in the address**: use `--token`.
- **Redirects are not followed.** A 3xx answer counts as a failure, so the
  token goes to the address you gave and nowhere else. Give the final
  address.
- **One try, ten seconds.** A failure is said in the sync's notification
  ("Webhook not sent: ... answered 503.") and is not tried again. The next
  sync sends its own changes; `reading` and `summary` always describe the
  whole present state, so a missed one is caught up there.
- **Only when the Kobo's database changed since the last sync.** Plugging
  it in again with nothing read in between sends nothing. The Kobo also
  changes its database by itself now and then (its own sync with Kobo's
  servers), so a POST can come with an empty `changed`; `reading` and
  `summary` are there all the same.

## What is sent

```json
{
  "event": "sync",
  "format": 1,
  "tool": "kobo-hardcover-sync 0.9.0",
  "made": "2026-10-06T08:15:02Z",
  "reader": "me",
  "device": "kobo-3f9a1c2b",
  "first_sync": false,
  "reading": {
    "device": "kobo-3f9a1c2b",
    "kobo_id": "0d6e5d1c-...",
    "title": "A Book",
    "author": "An Author",
    "isbn": "9780000000000",
    "language": "en",
    "status": "reading",
    "percent": 55,
    "last_read": "2026-10-06T08:00:00Z",
    "finished": null,
    "started": "2026-10-01",
    "seconds_read": 14400,
    "opened_on_this_kobo": true,
    "sync": "auto",
    "syncs": true,
    "state": "kobo",
    "state_date": null,
    "hardcover": null
  },
  "changed": [ { "...": "the same fields, one object per book" } ],
  "summary": {
    "minutes_today": 25,
    "minutes_week": 140,
    "minutes_month": 410,
    "finished_this_year": 12,
    "current_title": "A Book",
    "current_author": "An Author",
    "current_percent": 55,
    "last_upload": "2026-10-06T08:15:01Z"
  }
}
```

| Field | |
|---|---|
| `event` | `sync`, or `test` for the test that `webhook` sends. |
| `format` | Goes up when a field changes meaning or disappears; a new field does not change it. |
| `first_sync` | `true` for this Kobo's first sync. Everything would be new then, and most of it is history, so `changed` is empty. |
| `reading` | The book being read: opened on this Kobo, marked as reading, not finished, read last. `null` when there is none. |
| `changed` | Every book whose progress, status, finish date or reading time changed in this sync, books opened for the first time included, most recently read first. A book you finished is here with `"status": "finished"` and its `finished` date. |
| `summary` | The same numbers as the stats for a dashboard. `finished_this_year` counts the books that sync to Hardcover. |

Per book, `status` is the Kobo's own (`unread`, `reading`, `finished`).
`state` is what you set on the page to overrule it (`kobo` when you did
not), and `hardcover` is the match when there is one. `started` is the
date the tool first saw the book being read; the Kobo keeps no start date
of its own. On a Kobo account shared with others, their books can change
too: `opened_on_this_kobo` is `false` for those.

`kobo-hardcover-sync export` gives the same per-book fields for the whole
shelf, when your side wants to start from everything.

## On your side

Anything that takes a POST with JSON will do. Answer with a 2xx status;
the body of the answer is not read. The request carries
`User-Agent: kobo-hardcover-sync/<version>`.
