"""The Homebrew formula is written from uv.lock. These hold the writer to
that: every package a user gets is a resource, pinned as the lock pins it,
and the formula says what to do before and after."""

import importlib.util
import pathlib
import re
import tomllib

from tests.test_licences import installed_with_it

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_formula", ROOT / "packaging" / "homebrew" / "make_formula.py")
make_formula = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_formula)

LOCK = tomllib.loads((ROOT / "uv.lock").read_text())
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
URL, SHA = "https://example.org/kobo_hardcover_sync-0.1.0.tar.gz", "ab" * 32
FORMULA = make_formula.formula(URL, SHA, PROJECT, LOCK)


def test_every_package_a_user_gets_is_a_resource_pinned_as_the_lock_pins_it():
    found = {n: (u, h) for n, u, h in re.findall(r'resource "([^"]+)" do\n    url "([^"]+)"\n    sha256 "([0-9a-f]{64})"\n  end', FORMULA)}
    assert set(found) == set(installed_with_it()) and len(found) > 10
    by_name = {p["name"]: p for p in LOCK["package"]}
    for name, (url, digest) in found.items():
        assert url == by_name[name]["sdist"]["url"] and "sha256:" + digest == by_name[name]["sdist"]["hash"], name
        assert url.endswith((".tar.gz", ".zip")) and by_name[name]["version"] in url  # source, not a ready-made build
    assert list(found) == sorted(found)  # in order, so a bump is a small diff


def test_the_formula_is_one_homebrew_can_read():
    assert FORMULA.splitlines()[2] == "class KoboHardcoverSync < Formula"
    assert f'  sha256 "{SHA}"\n  license "MIT"' in FORMULA and f'  url "{URL}"\n' in FORMULA
    assert "include Language::Python::Virtualenv" in FORMULA and "virtualenv_install_with_resources" in FORMULA
    for needs in ('depends_on "rust" => :build', 'depends_on "python@3.13"', 'depends_on "openssl@3"', 'depends_on "libyaml"'):
        assert needs in FORMULA
    desc = re.search(r'  desc "([^"]+)"', FORMULA).group(1)
    assert len(desc) <= 80 and not desc.endswith(".") and not desc.lower().startswith(("a ", "an ", "the "))
    # every block that opens, closes
    opens = len(re.findall(r"^\s*(class|def|test do|resource .* do)\b", FORMULA, re.M))
    assert (
        opens == len(re.findall(r"^\s*end$", FORMULA, re.M)) and FORMULA.count("<<~EOS") == len(re.findall(r"^\s+EOS$", FORMULA, re.M)) == 1
    )


def test_it_says_what_to_do_after_installing_and_before_removing():
    caveats = FORMULA[FORMULA.index("def caveats") : FORMULA.index("test do")]
    assert "kobo-hardcover-sync setup" in caveats and "Full Disk Access" in caveats
    assert "Before `brew uninstall kobo-hardcover-sync`" in caveats and "kobo-hardcover-sync uninstall" in caveats and "--purge" in caveats
    test = FORMULA[FORMULA.index("test do") :]
    assert (
        "--version" in test and 'ENV["KHS_HOME"] = testpath.to_s' in test and "not set up" in test
    )  # the test never touches a real installation


def test_a_formula_for_trying_points_at_the_file_on_this_computer(tmp_path, capsys):
    sdist = tmp_path / "kobo_hardcover_sync-0.1.0.tar.gz"
    sdist.write_bytes(b"not really a tarball")
    make_formula.main(["--sdist", str(sdist)])
    out = capsys.readouterr().out
    assert f'url "{sdist.as_uri()}"' in out and 'sha256 "' + __import__("hashlib").sha256(b"not really a tarball").hexdigest() + '"' in out


def test_setup_points_the_trigger_at_the_tool_it_was_run_from(tmp_path, monkeypatch):
    from kobo_hardcover_sync import cli

    brewed = tmp_path / "homebrew" / "bin" / "kobo-hardcover-sync"
    brewed.parent.mkdir(parents=True)
    brewed.write_text("#!/bin/sh\n")
    brewed.chmod(0o755)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/somewhere/else/first/on/the/path/kobo-hardcover-sync")
    monkeypatch.setattr(cli.sys, "argv", [str(brewed), "setup"])
    assert cli._own_path() == str(brewed)  # the one that was started, also when another is first on the PATH
    monkeypatch.setattr(cli.sys, "argv", ["-c", "setup"])  # not started by its own name: fall back to the PATH
    assert cli._own_path() == "/somewhere/else/first/on/the/path/kobo-hardcover-sync"


def test_a_development_version_is_written_out_and_a_release_is_left_to_homebrew():
    # Homebrew took "0" from kobo_hardcover_sync-0.1.0.dev0.tar.gz: the keg landed in Cellar/kobo-hardcover-sync/0.
    dev = make_formula.formula(URL, SHA, {**PROJECT, "version": "0.1.0.dev0"}, LOCK)
    assert f'  url "{URL}"\n  version "0.1.0.dev0"\n  sha256 "{SHA}"' in dev
    release = make_formula.formula(URL, SHA, {**PROJECT, "version": "0.1.0"}, LOCK)
    assert f'  url "{URL}"\n  sha256 "{SHA}"' in release and "  version " not in release  # brew audit objects to a version said twice
    for odd in ("1.0.0rc1", "0.2.0a1", "0.1.0.post1"):
        assert f'version "{odd}"' in make_formula.formula(URL, SHA, {**PROJECT, "version": odd}, LOCK)
