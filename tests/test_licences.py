"""A stranger can tell from the repository what they may do with every file
in it: the licence is there, everything that is not the project's own has
its notice next to it, and the list of what gets installed is the real one."""

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "kobo_hardcover_sync" / "web" / "static"
NOTICES = (ROOT / "THIRD-PARTY-NOTICES.md").read_text()
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def test_the_licence_is_mit_and_the_package_says_so():
    text = (ROOT / "LICENSE").read_text()
    assert text.startswith("MIT License") and "Permission is hereby granted, free of charge" in text
    assert re.search(r"Copyright \(c\) \d{4} \S", text)
    assert PROJECT["license"] == "MIT" and set(PROJECT["license-files"]) == {"LICENSE", "THIRD-PARTY-NOTICES.md"}
    assert PROJECT["authors"][0]["name"] in text
    readme = (ROOT / "README.md").read_text()
    assert "](LICENSE)" in readme and "](THIRD-PARTY-NOTICES.md)" in readme
    assert "LICENSE" in (ROOT / "Dockerfile").read_text()  # the image is built from the package, licence included


def test_every_font_travels_with_its_full_licence():
    fonts = sorted((STATIC / "fonts").glob("*.woff2"))
    assert len(fonts) == 4
    for f in fonts:
        family = f.name.split("-")[0]
        licence = (STATIC / "fonts" / f"{family}-LICENSE.txt").read_text()
        assert licence.startswith("Copyright ") and family in licence.splitlines()[0], f.name
        assert "SIL OPEN FONT LICENSE Version 1.1" in licence and "PERMISSION & CONDITIONS" in licence and "TERMINATION" in licence
        assert f.name in NOTICES and licence.splitlines()[0] in NOTICES and f.name in (STATIC / "fonts" / "README.txt").read_text()
    assert not {p.suffix for p in (STATIC / "fonts").iterdir()} - {".woff2", ".txt"}  # nothing in there without a notice


def test_every_picture_that_is_not_ours_is_credited():
    credits = (STATIC / "img" / "CREDITS.txt").read_text()
    pictures = sorted(p.name for p in (STATIC / "img").iterdir() if p.name != "CREDITS.txt")
    assert pictures == ["kobo-day.webp", "kobo-night.webp"]
    for name in pictures:
        line = next(ln for ln in credits.splitlines() if ln.startswith(name))
        url = re.search(r"https://unsplash\.com/photos/\S+", line).group(0)
        assert name in NOTICES and url in NOTICES
    assert "Unsplash License" in credits and "Unsplash License" in NOTICES and "not under its MIT licence" in credits
    # The project's own artwork is the icon, and only that.
    assert sorted(p.name for p in STATIC.iterdir() if p.is_file()) == ["apple-touch-icon.png", "favicon.svg", "kobo.css", "kobo.js"]


def installed_with_it() -> dict[str, str]:
    """The packages a user gets, from the lock file: name -> version."""
    packages = {p["name"]: p for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    seen: dict[str, str] = {}
    todo = [d["name"] for d in packages["kobo-hardcover-sync"].get("dependencies", [])]
    while todo:
        name = todo.pop()
        if name not in seen:
            seen[name] = packages[name]["version"]
            todo += [d["name"] for d in packages[name].get("dependencies", [])]
    return seen


def test_the_list_of_what_is_installed_next_to_it_is_the_real_one():
    listed = {m[0]: (m[1], m[2]) for m in re.findall(r"^\| ([a-z0-9-]+) \| ([0-9][^ |]*) \| ([^|]+?) \|$", NOTICES, re.M)}
    real = installed_with_it()
    assert len(real) > 10
    assert {n: v for n, (v, _) in listed.items()} == real  # a new package or version: look up its licence, then update the table
    permissive = re.compile(r"^(MIT|MIT-0|BSD-3-Clause|BSD-2-Clause|Apache-2\.0|PSF-2\.0|ISC)( OR (MIT|BSD-3-Clause|Apache-2\.0))?$")
    for name, (_, licence) in listed.items():
        assert permissive.match(licence), f"{name}: {licence} needs a look before it is passed on"
