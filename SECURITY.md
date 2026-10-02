# Security

## Reporting a problem

Please report it privately, not in a public issue:

**<https://github.com/merlijntishauser/kobo-hardcover-sync/security/advisories/new>**

(the *Report a vulnerability* button under the repository's *Security*
tab). Say what you found, how to reproduce it, and what someone could do
with it.

This is a one-person project. Expect an answer within days, not hours. You
will be told what was found, what the fix is, and when it is released; if
you want to be named in the release notes, say so.

**Do not attach your Kobo's database** (`KoboReader.sqlite`) or a token. A
description is enough.

## What matters most here

The parts where a mistake would hurt someone:

- **Who the server believes.** In server mode there is no login; the
  reader's name comes from the `Remote-User` header, which is believed only
  from the addresses in `KHS_TRUSTED_PROXIES`. A way to be someone else is
  a serious problem.
- **Tokens.** Hardcover tokens (encrypted on a server, in the secret store
  on a computer), upload tokens and stats tokens. Anything that shows,
  logs or leaks one.
- **What leaves the computer.** The Kobo's database holds the Kobo
  account's login tokens. They must never be read or sent; an upload holds
  the book rows and reading events only, and the server refuses more.
- **Writing to the Kobo.** The collection is the only thing written. A way
  to make the tool write anything else, or damage the Kobo's database.
- **The local page.** It has no login and is closed by other means
  (loopback only, its own address and port, a key from `open`). A way for
  another program or a website to read or drive it.

## Supported versions

The latest release. There are no long-term branches.

## What this project does not promise

It is not affiliated with Rakuten Kobo or Hardcover, and cannot fix
problems in their services. If you find one there, tell them.
