# Contributing

Thank you for looking. This is a small project kept by one person in spare
time, so the way in is deliberately simple.

## How changes are taken

- **A bug, or something that works on your Kobo and is not on the list:**
  open an issue. For a bug, the form asks for what is needed to look at it.
- **A small fix** (a typo, a wrong message, a clear bug with a test): send
  a pull request straight away.
- **Anything larger** (a new feature, a new platform, a change in how books
  sync): open an issue first and say what you have in mind. That saves you
  building something that will not be taken, and it is where the reasons
  get written down.
- **A security problem:** not in an issue. See [SECURITY.md](SECURITY.md).

There is no contributor agreement to sign. What you send is offered under
the same [MIT licence](LICENSE) as the rest, and stays yours.

Answers can take a few days.

**Using AI tools** is fine, and this project does too: see the
[AI disclaimer](README.md#ai-disclaimer). Say so when you did, understand
every line you send, keep the pull request small, and run the tests before
you open or update it.

**Never attach your Kobo's database** (`KoboReader.sqlite`) to an issue or
a pull request. It holds your Kobo account's login tokens and your whole
library. The tests use a made-up one (`tests/kobo_fixture.py`).

## Set up

You need [uv](https://docs.astral.sh/uv/); it brings Python and the
packages.

```
git clone https://github.com/merlijntishauser/kobo-hardcover-sync
cd kobo-hardcover-sync
uv run pytest -q tests                              # the unit tests
uv run ruff check . && uv run ruff format --check . # style
uv run kobo-hardcover-sync serve                    # the server, on 127.0.0.1:3012
```

`serve` needs `KHS_TRUSTED_PROXIES` (for trying it: `127.0.0.1`) and then
believes a `Remote-User` header from that address, which is how the browser
tests sign in. A browser cannot send that header by itself, so to look at
the pages local mode is the easy way, in a folder of its own:

```
KHS_HOME=/tmp/khs-dev uv run kobo-hardcover-sync setup --local --no-trigger
KHS_HOME=/tmp/khs-dev uv run kobo-hardcover-sync open
```

The browser tests drive a real Chromium through the pages with a made-up
shelf:

```
uv run --group browser pytest -q browser_tests
uv run --group browser python browser_tests/shots.py   # screenshots of every page
```

Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to use a Chromium you already
have, and `DEV_OUT` for where the screenshots go.

## Where things are

One package, `kobo_hardcover_sync`, under `src/`:

| | |
|---|---|
| `engine` | Reading the Kobo's database, the state, the plan, Hardcover, the two-way sync, the collection. It knows nothing about the page or the command. |
| `server` | Readers and their tokens, uploads, the stats endpoint. |
| `web` | The page: HTML, texts (`strings.py`), the stylesheet and script. |
| `computer` | The tool where the Kobo is plugged in: the seams to macOS and Linux, the server client, one sync. |
| `cli` | The command. |

[docs/how-it-works.md](docs/how-it-works.md) says why it is built this way.

## What a change needs

- **Tests.** A change in behaviour comes with a test that fails without
  it. Nothing in the tests talks to Hardcover or needs a Kobo.
- **A sync rule changes:** change [docs/sync-rules.md](docs/sync-rules.md)
  in the same commit. Every rule there names its tests, and a test fails
  when a rule names none.
- **Anything that writes to the Kobo** goes through
  `engine/collection.py` and keeps its promises: its own collection only,
  the version gate, a backup first, all or nothing.
- **The page:** [PRODUCT.md](PRODUCT.md) says who it is for,
  [DESIGN.md](DESIGN.md) what it looks like and why. Texts go in
  `web/strings.py`, in plain words. Colours are held to WCAG 2.2 AA by
  `tests/test_design_tokens.py`. The page has to keep working without
  JavaScript and on a phone.
- **A new dependency or a version bump** fails `tests/test_licences.py`
  until its licence is in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
  Permissive licences only.
- **Style:** `ruff format` and `ruff check` decide; lines up to 140.
  Comments say why, not what.
- **Commit messages** say what changed and why, in a sentence someone can
  read in a year.
