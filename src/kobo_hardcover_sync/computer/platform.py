"""The seams to the operating system. One class per platform; the rest of
the tool only talks to this interface (see docs/local-mode.md)."""

from __future__ import annotations

import os
import sys

KOBO_DB = os.path.join(".kobo", "KoboReader.sqlite")
UPLOAD = "upload"  # the secret that lets this computer upload to the server
HARDCOVER = "hardcover"  # local mode: the reader's Hardcover token


class Unsupported(Exception):
    pass


class Computer:
    name = "this computer"

    # --- the Kobo
    def volume_roots(self) -> list[str]:
        """Folders under which a plugged-in Kobo shows up."""
        raise NotImplementedError

    def find_kobo(self) -> str | None:
        """The folder a Kobo is mounted on, or None. A Kobo is any volume
        with .kobo/KoboReader.sqlite."""
        # KHS_VOLUMES: more folders to look under (colon-separated), for a
        # Kobo mounted by hand somewhere else.
        extra = [p for p in os.environ.get("KHS_VOLUMES", "").split(":") if p]
        for root in [*self.volume_roots(), *extra]:
            try:
                names = sorted(os.listdir(root))
            except OSError:
                continue
            for name in names:
                mount = os.path.join(root, name)
                if os.path.isfile(os.path.join(mount, KOBO_DB)):
                    return mount
        return None

    def eject(self, mount: str) -> bool:
        raise NotImplementedError

    # --- secrets (never on a command line, never in a log)
    def secret(self, name: str) -> str:
        raise NotImplementedError

    def set_secret(self, name: str, value: str) -> None:
        raise NotImplementedError

    def delete_secret(self, name: str) -> None:
        raise NotImplementedError

    def secret_place(self, name: str) -> str:
        """Where a secret is kept, in words for the person."""
        return "this computer's secret store"

    # --- the person
    def notify(self, title: str, message: str) -> None:
        raise NotImplementedError

    def open_page(self, url: str) -> None:
        raise NotImplementedError

    # --- the trigger on plug-in
    def install_trigger(self, command: str, rebuild: bool = False) -> list[str]:
        raise NotImplementedError

    def remove_trigger(self) -> list[str]:
        raise NotImplementedError


def pick() -> Computer:
    if sys.platform == "darwin":
        from .macos import MacOS

        return MacOS()
    if sys.platform.startswith("linux"):
        from .linux import Linux

        return Linux()
    raise Unsupported("the tool for the computer runs on macOS and on desktop Linux.")
