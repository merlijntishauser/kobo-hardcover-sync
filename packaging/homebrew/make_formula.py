#!/usr/bin/env python3
"""Write the Homebrew formula for a release.

    python packaging/homebrew/make_formula.py --url URL --sha256 HEX
    python packaging/homebrew/make_formula.py --sdist dist/kobo_hardcover_sync-0.1.0.tar.gz

The formula builds everything from source, the Homebrew way: the tool's own
source package, and one `resource` for each Python package it needs, with
the address and SHA-256 that uv.lock pins. So what Homebrew installs is
what the tests ran with, and a dependency bump shows up here as a changed
formula.

--sdist is for trying a formula before there is a public download: it
points the formula at the file on this computer.

Only the standard library is used, so the release does not need the
project's own environment to cut a formula.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPOSITORY = "https://github.com/merlijntishauser/kobo-hardcover-sync"
PYTHON = "python@3.13"  # the version the tests run on

CAVEATS = """\
To finish, run:
  kobo-hardcover-sync setup
It makes the trigger that syncs when the Kobo is plugged in, and says
which permission to give (on a Mac: Full Disk Access, once; it stays
through upgrades).

Before `brew uninstall kobo-hardcover-sync`, run:
  kobo-hardcover-sync uninstall
or the trigger stays behind. Your books, settings and tokens are kept
either way; `kobo-hardcover-sync uninstall --purge` removes them."""


def resources(lock: dict) -> list[tuple[str, str, str]]:
    """(name, source package address, sha256) of every package the tool
    needs when installed for use, from uv.lock, in alphabetical order."""
    packages = {p["name"]: p for p in lock["package"]}
    needed: dict[str, dict] = {}
    todo = [d["name"] for d in packages["kobo-hardcover-sync"].get("dependencies", [])]
    while todo:
        name = todo.pop()
        if name not in needed:
            needed[name] = packages[name]
            todo += [d["name"] for d in packages[name].get("dependencies", [])]
    out = []
    for name in sorted(needed):
        sdist = needed[name].get("sdist")
        if not sdist:
            raise SystemExit(f"{name} has no source package in uv.lock: Homebrew cannot build it from source")
        algorithm, _, digest = sdist["hash"].partition(":")
        if algorithm != "sha256":
            raise SystemExit(f"{name}: uv.lock has a {algorithm} hash, Homebrew wants sha256")
        out.append((name, sdist["url"], digest))
    return out


def formula(url: str, sha256: str, project: dict, lock: dict) -> str:
    blocks = "\n\n".join(
        f'  resource "{name}" do\n    url "{address}"\n    sha256 "{digest}"\n  end' for name, address, digest in resources(lock)
    )
    caveats = "\n".join(("      " + line).rstrip() for line in CAVEATS.splitlines())
    return f'''\
# Written by packaging/homebrew/make_formula.py from uv.lock. Do not edit by
# hand: change the lock file and write it again.
class KoboHardcoverSync < Formula
  include Language::Python::Virtualenv

  desc "{description(project)}"
  homepage "{REPOSITORY}"
  url "{url}"
{version_line(project["version"])}  sha256 "{sha256}"
  license "{project["license"]}"
  head "{REPOSITORY}.git", branch: "main"

  # pydantic-core and cryptography are written in Rust; cryptography links
  # against OpenSSL, PyYAML against libyaml, cffi against libffi.
  depends_on "pkgconf" => :build
  depends_on "rust" => :build
  depends_on "libyaml"
  depends_on "openssl@3"
  depends_on "{PYTHON}"

  uses_from_macos "libffi"

{blocks}

  def install
    ENV["OPENSSL_NO_VENDOR"] = "1"
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
{caveats}
    EOS
  end

  test do
    assert_match "kobo-hardcover-sync", shell_output("#{{bin}}/kobo-hardcover-sync --version")
    # A folder of its own: nothing is set up there, and it says so.
    ENV["KHS_HOME"] = testpath.to_s
    assert_match "not set up", shell_output("#{{bin}}/kobo-hardcover-sync status")
  end
end
'''


def version_line(version: str) -> str:
    """Homebrew reads the version from the file's name, and gets a plain
    release right (0.1.0). A development version it does not: for
    kobo_hardcover_sync-0.1.0.dev0.tar.gz it found "0" (seen 2026-10-02).
    So such a version is written out; a plain one is left to Homebrew,
    whose audit objects to saying it twice."""
    return "" if re.fullmatch(r"\d+(\.\d+)*", version) else f'  version "{version}"\n'


def description(project: dict) -> str:
    """Homebrew wants a short line, no leading article, no full stop."""
    text = project["description"].split(",")[0].rstrip(".")
    return text if len(text) <= 80 else text[:77].rstrip() + "..."


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", help="where the release's source package can be downloaded")
    p.add_argument("--sha256", help="its SHA-256")
    p.add_argument("--sdist", help="a source package on this computer, for trying the formula before a release")
    a = p.parse_args(argv)
    if a.sdist:
        path = pathlib.Path(a.sdist).resolve()
        url, sha256 = path.as_uri(), hashlib.sha256(path.read_bytes()).hexdigest()
    elif a.url and a.sha256:
        url, sha256 = a.url, a.sha256
    else:
        p.error("give --url and --sha256, or --sdist")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    sys.stdout.write(formula(url, sha256, project, lock))


if __name__ == "__main__":
    main()
