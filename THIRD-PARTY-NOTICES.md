# Third-party notices

kobo-hardcover-sync's own code, documentation and artwork (the icon
included) are under the MIT licence: see [LICENSE](LICENSE). This file is
about everything else: what is in this repository under another licence,
what is installed next to it, and what it fetches while it runs.

## In this repository, under their own licences

### Fonts

Both under the **SIL Open Font License 1.1**. The full licence text, with
each font's copyright notice, is in the folder with the font files,
`src/kobo_hardcover_sync/web/static/fonts/`.

| Font | Files | Copyright | Licence text |
|---|---|---|---|
| Sora | `Sora-latin.woff2`, `Sora-latin-ext.woff2` | Copyright 2019 The Sora Project Authors (https://github.com/sora-xor/sora-font) | `Sora-LICENSE.txt` |
| Literata | `Literata-latin.woff2`, `Literata-latin-ext.woff2` | Copyright 2017 The Literata Project Authors (https://github.com/googlefonts/literata) | `Literata-LICENSE.txt` |

The files are the subsets Google Fonts serves, unchanged. If you pass this
project on, the fonts go with their licence files; the Open Font License
does not allow selling the fonts by themselves.

### Photographs

Both under the **Unsplash License** (https://unsplash.com/license), in
`src/kobo_hardcover_sync/web/static/img/`, credited in `CREDITS.txt` there
and in the page's help dialog.

| File | Photographer | Source |
|---|---|---|
| `kobo-day.webp` | Spencer (@spen) | https://unsplash.com/photos/DXobXpIa9_4 |
| `kobo-night.webp` | Amanz (@amanz) | https://unsplash.com/photos/S6R5ZirJAFk |

The Unsplash License lets you copy, change and distribute the photographs,
also commercially. It does not let you sell them without significant
modification, or collect them into a competing image service. That is
narrower than MIT: the MIT licence above does not cover these two files.

## Installed next to it, not in this repository

The Python packages it needs. None of their code is in this repository;
`pip`, `uv` or the container build fetches them, each with its own licence
file. As locked in `uv.lock`:

| Package | Version | Licence |
|---|---|---|
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.115.6 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| python-multipart | 0.0.20 | Apache-2.0 |
| pyyaml | 6.0.2 | MIT |
| starlette | 0.41.3 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.34.0 | BSD-3-Clause |

The licences are what each package declares in its own metadata. A test
(`tests/test_licences.py`) fails when the lock file gains a package or a
version that this table does not have.

Whoever passes on a bundle that contains these packages (the container
image built from the `Dockerfile`, which also contains Python and a Debian
base system) passes on their licences with it; they are inside the bundle,
in each package's own folder.

The tools used only to develop and test (pytest, httpx, ruff, Playwright)
are not part of what is installed for use.

## Fetched while it runs

- **Book covers** are loaded from Kobo's servers when the page shows a
  book. They are not in this repository and not passed on by it.
- Nothing else: fonts, photographs, styles and scripts are served by the
  tool itself.

## Names

Kobo is a trademark of Rakuten Kobo Inc.; Hardcover is the name of the
service at hardcover.app. This project is independent of both: not
affiliated with, endorsed by or sponsored by either. The names are used to
say what the tool works with.
