"""The README is what a stranger installs from. What it names has to exist:
the files it links to, the commands and options it tells them to type, the
settings, and the versions it says were tested."""

import pathlib
import re

from kobo_hardcover_sync import cli
from kobo_hardcover_sync.engine import collection, hardcover

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md")
README = (ROOT / "README.md").read_text()


def test_every_link_to_a_file_leads_somewhere():
    for page in PAGES:
        text = (ROOT / page).read_text()
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text) + re.findall(r'<img src="([^"]+)"', text):
            if not target.startswith(("http://", "https://")):
                assert (ROOT / target).exists(), f"{page} links to {target}"
        for anchor in re.findall(r"\]\(#([^)]+)\)", text):  # a link to a heading of the same page
            headings = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
            assert anchor in headings, f"{page}: no heading for #{anchor}"


def test_every_command_and_option_in_the_text_is_real(capsys):
    def help_of(command):
        try:
            cli.main([command, "--help"])
        except SystemExit as ex:
            return capsys.readouterr().out if ex.code == 0 else None
        return None

    for page in PAGES:
        text = (ROOT / page).read_text()
        for command, rest in re.findall(r"kobo-hardcover-sync ([a-z]+)((?: --[a-z-]+)*)", text):
            if command in ("is", "does", "reads", "on", "s"):  # the name in a sentence, not a command
                continue
            usage = help_of(command)
            assert usage, f"{page}: `kobo-hardcover-sync {command}` is not a command the tool knows"
            for option in rest.split():
                assert f"{option} " in usage or f"{option}]" in usage, f"{page}: `{command}` has no {option}"
        for option in re.findall(r"`(--[a-z-]+)`", text):  # options named on their own, as in "`--purge` also removes ..."
            assert any(option in (help_of(c) or "") for c in ("setup", "token", "sync", "export", "uninstall", "serve", "import")), (
                f"{page}: {option}"
            )


def test_every_setting_it_names_is_read_somewhere():
    source = "".join(p.read_text() for p in (ROOT / "src").rglob("*.py"))
    for name in set(re.findall(r"`KHS_([A-Z_]+)`", README)):
        assert f'env("{name}"' in source or f"KHS_{name}" in source, f"KHS_{name} is in the README and nowhere in the code"
    assert "allow_untested_kobo" in source and "`allow_untested_kobo = true`" in README


def test_what_it_says_was_tested_is_what_the_code_allows():
    for version, software in collection.KNOWN_VERSIONS.items():
        assert f"| {software} | {version} |" in README  # the gate's list and the README's table are the same list
    assert len(re.findall(r"^\| \d[\d.]+ \| \d+ \|", README, re.M)) == len(collection.KNOWN_VERSIONS)
    assert "four\n   permissions" in README or "four permissions" in README
    assert len(hardcover.SCOPES) == 4


def test_it_does_not_promise_what_is_not_there():
    assert "never writes to the device" not in README  # it writes one thing, and says exactly what
    assert "the only thing this tool\never writes to your Kobo" in README
    # Published: the two ways to install are the ones that exist.
    assert "uv tool install kobo-hardcover-sync\n" in README and "brew install merlijntishauser/tap/kobo-hardcover-sync\n" in README
    assert "not affiliated with, endorsed by or sponsored by" in README
    for claim in ("the first tool", "the only tool", "the only way", "the best"):  # no claims about being first or only
        assert claim not in README.lower()
