"""Nothing of the place this tool grew up in goes out with it: no names of
people or machines, no private addresses, no numbers of tickets that mean
nothing to anyone else (and that a code host would link to the wrong issue)."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WHERE = (
    "src",
    "tests",
    "browser_tests",
    "docs",
    "examples",
    ".github",
    "README.md",
    "Dockerfile",
    "pyproject.toml",
    "LICENSE",
    "THIRD-PARTY-NOTICES.md",
    "PRODUCT.md",
    "DESIGN.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "packaging",
    ".impeccable",
)
TEXT = {".py", ".md", ".json", ".toml", ".yml", ".yaml", ".css", ".js", ".html", ".svg", ".txt", ".sh", ".applescript", ""}
# Written in pieces, so this file does not find itself.
PRIVATE = re.compile(
    "|".join(
        [
            "stim" + "py",
            "mer" + "lijn",
            "gargle" + "blaster",
            "cca" + "dd",
            r"192\.168\.",
            "home" + "lab",
            "tiny" + "auth",
            "infi" + "sical",
            "viku" + "nja",
            "help" + "bot",
            r"\(#\d{2,3}\)",
            r"#[34]\d\d\b",
        ]
    ),
    re.I,
)
# What stays: the macOS bundle id, which is the publisher's reverse domain
# name, as bundle ids are; and the author's name.
ALLOWED = (
    "org.gargle" + "blaster.kobo-hardcover-sync",
    # The author, where an author is named: the licence and the package's metadata.
    "Mer" + "lijn Tishauser",
    "mer" + "lijn@cca" + "dd.nl",
    # Where the project lives.
    "github.com/mer" + "lijntishauser/kobo-hardcover-sync",
    "githubusercontent.com/mer" + "lijntishauser/kobo-hardcover-sync",
    "owner `mer" + "lijntishauser`",  # docs/releasing.md: the PyPI publisher
    "mer" + "lijntishauser/tap",  # the Homebrew tap
    "mer" + "lijntishauser/homebrew-tap",
)


def files():
    for name in WHERE:
        p = ROOT / name
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from (f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix in TEXT and "__pycache__" not in f.parts)


def test_the_tree_holds_nothing_private():
    found = []
    for f in files():
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            for ok in ALLOWED:
                line = line.replace(ok, "")
            if PRIVATE.search(line):
                found.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:100]}")
    assert not found, "\n".join(found)


def test_the_check_looks_at_the_files_that_matter():
    seen = {str(f.relative_to(ROOT)) for f in files()}
    for must in (
        "README.md",
        "docs/how-it-works.md",
        "src/kobo_hardcover_sync/web/strings.py",
        "src/kobo_hardcover_sync/web/static/kobo.css",
    ):
        assert must in seen, must
    assert PRIVATE.search("see (#" + "378)") and PRIVATE.search("Home" + "Lab") and not PRIVATE.search("rule F13, 131 books, #1")
