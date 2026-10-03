"""The package as a whole: its layering, its command, its packaged files."""

import os
import pathlib
import re

import kobo_hardcover_sync
from kobo_hardcover_sync import cli
from kobo_hardcover_sync.engine import job, state

PKG = pathlib.Path(kobo_hardcover_sync.__file__).parent


def test_the_engine_imports_nothing_from_the_page_the_server_or_the_command():
    for f in (PKG / "engine").glob("*.py"):
        src = f.read_text()
        assert not re.search(r"^\s*from \.\.|^\s*(from|import) kobo_hardcover_sync", src, re.M), f.name


def test_the_page_files_are_part_of_the_package():
    static = PKG / "web" / "static"
    for name in ("kobo.css", "kobo.js", "favicon.svg", "fonts/SchibstedGrotesk-latin.woff2", "fonts/SourceSerif4-latin.woff2"):
        assert (static / name).is_file(), name


def test_version_and_help(capsys):
    for flag in ("--version", "--help"):
        try:
            cli.main([flag])
        except SystemExit as ex:
            assert ex.code == 0
    out = capsys.readouterr().out
    assert "kobo-hardcover-sync" in out and "serve" in out and "import" in out


def test_serve_listens_on_loopback_unless_told_otherwise(monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.append((target, kw)))
    cli.main(["serve"])
    cli.main(["serve", "--host", "0.0.0.0", "--port", "3012"])
    # proxy_headers off: the address the app checks is the one that really connected.
    assert calls[0] == ("kobo_hardcover_sync.web.app:app", {"host": "127.0.0.1", "port": 3012, "proxy_headers": False})
    assert calls[1][1]["host"] == "0.0.0.0"


def test_a_sync_without_a_token_fails_with_a_plain_reason(tmp_path):
    db = str(tmp_path / "state.db")
    state.connect(db)
    r = job.run(db, "nobody", live=True)  # no client, no token handed over
    assert r["status"] == "failed" and "Not connected to Hardcover yet" in r["fatal"]
    con = state.connect(db)
    assert con.execute("select status from job where reader='nobody'").fetchone()[0] == "failed"
    assert os.path.exists(db)


def test_what_ci_tests_is_what_the_package_says_it_supports():
    import tomllib

    root = pathlib.Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    promised = sorted(c.rsplit(" ", 1)[1] for c in project["classifiers"] if c.startswith("Programming Language :: Python :: 3."))
    workflow = (root / ".github" / "workflows" / "test.yml").read_text()
    tested = sorted(re.findall(r'"(3\.\d+)"', re.search(r"python: \[(.*?)\]", workflow).group(1)))
    assert promised == tested and project["requires-python"] == f">={promised[0]}"
    for name in ("Homepage", "Changelog", "Issues"):
        assert project["urls"][name].startswith("https://github.com/")


def test_the_readme_pypi_shows_has_no_link_that_leads_nowhere():
    """PyPI cannot follow a link to a file in the repository. The build
    rewrites them (pyproject.toml); this applies the same rules."""
    import tomllib

    root = pathlib.Path(__file__).resolve().parents[1]
    hook = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["hatch"]["metadata"]["hooks"]["fancy-pypi-readme"]
    text = (root / hook["fragments"][0]["path"]).read_text()
    relative = r"\]\((?!https?://|#)[^)]+\)|src=\"(?!https?://)[^\"]+"
    assert len(re.findall(relative, text)) > 8  # the repository's own README links to its files
    for rule in hook["substitutions"]:
        text = re.sub(rule["pattern"], rule["replacement"].replace("$HFPR_VERSION", "9.9.9"), text)
    assert re.findall(relative, text) == []
    assert "https://raw.githubusercontent.com/merlijntishauser/kobo-hardcover-sync/v9.9.9/docs/img/books.png" in text
    assert "(https://github.com/merlijntishauser/kobo-hardcover-sync/blob/v9.9.9/docs/sync-rules.md)" in text
    assert "](#the-collection-on-the-kobo)" in text  # a link within the page stays as it is
