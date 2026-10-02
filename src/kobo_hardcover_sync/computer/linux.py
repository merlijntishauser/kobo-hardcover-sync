"""Desktop Linux: the same story as on the Mac, for someone logged in at a
desktop. The desktop mounts the Kobo (udisks), a user service runs the
sync, a desktop notification shows the result.

The trigger needs no administrator rights: a user service that the Kobo's
mount "wants". systemd's user manager sees mounts as units, so the service
is started when /run/media/<user>/KOBOeReader (or /media/<user>/KOBOeReader,
on distributions that mount there) appears, each time it appears. Seen
working on systemd 257 with a mount made by hand; KOBOeReader is the name
the Kobo's own partition carries.

Secrets: the desktop keyring through `secret-tool` when that works from
here, else a private file in the state folder. secret-tool takes the secret
on standard input, never as an argument.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess

from . import config
from .platform import Computer

UNIT = "kobo-hardcover-sync.service"
LABEL = "KOBOeReader"  # the volume name of a Kobo's own partition
KEYRING = ("service", "kobo-hardcover-sync")


class Linux(Computer):
    name = "this computer"

    def __init__(self, run=subprocess.run, home: str | None = None, user: str | None = None, which=shutil.which):
        self.run = run
        self.which = which
        self.home = home or os.path.expanduser("~")
        self.user = user or getpass.getuser()

    def _call(self, *args: str, **kw):
        return self.run(list(args), capture_output=True, text=True, **kw)

    # --- the Kobo
    def volume_roots(self) -> list[str]:
        return [f"/run/media/{self.user}", f"/media/{self.user}"]

    def eject(self, mount: str) -> bool:
        """Unmount, and switch the device off when that is possible, as a
        file manager's eject does."""
        if not self.which("udisksctl") or not self.which("findmnt"):
            return False
        device = self._call("findmnt", "-n", "-o", "SOURCE", "--target", mount).stdout.strip()
        if not device.startswith("/dev/") or self._call("udisksctl", "unmount", "-b", device).returncode != 0:
            return False
        parent = self._call("lsblk", "-n", "-o", "PKNAME", device).stdout.strip() if self.which("lsblk") else ""
        if parent:
            self._call("udisksctl", "power-off", "-b", "/dev/" + parent)
        return True

    # --- secrets
    @property
    def _secrets_file(self) -> str:
        return os.path.join(config.state_dir(), "secrets.json")

    def _file_secrets(self) -> dict:
        try:
            with open(self._secrets_file) as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_file_secrets(self, data: dict) -> None:
        os.makedirs(config.state_dir(), mode=0o700, exist_ok=True)
        if not data:
            try:
                os.unlink(self._secrets_file)
            except FileNotFoundError:
                pass
            return
        tmp = self._secrets_file + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, self._secrets_file)

    def _keyring(self, verb: str, name: str, value: str | None = None):
        """secret-tool lookup | store | clear for this secret; None when
        there is no secret-tool."""
        if not self.which("secret-tool"):
            return None
        attrs = [*KEYRING, "account", name]
        if verb == "store":
            return self._call("secret-tool", "store", "--label", f"Kobo Hardcover Sync ({name})", *attrs, input=value)
        return self._call("secret-tool", verb, *attrs)

    def secret(self, name: str) -> str:
        kept = self._file_secrets().get(name)
        if kept:
            return kept
        r = self._keyring("lookup", name)
        return r.stdout.strip() if r is not None and r.returncode == 0 else ""

    def set_secret(self, name: str, value: str) -> None:
        if not value or "\n" in value:
            raise ValueError("this secret cannot be kept")
        files = self._file_secrets()
        r = self._keyring("store", name, value)
        if r is not None and r.returncode == 0:
            back = self._keyring("lookup", name)
            if back is not None and back.returncode == 0 and back.stdout.strip() == value:
                if files.pop(name, None) is not None:  # one place only
                    self._write_file_secrets(files)
                return
        files[name] = value  # no keyring that works from here: the private file
        self._write_file_secrets(files)

    def delete_secret(self, name: str) -> None:
        files = self._file_secrets()
        if files.pop(name, None) is not None:
            self._write_file_secrets(files)
        self._keyring("clear", name)

    def secret_place(self, name: str) -> str:
        if name in self._file_secrets():
            return f"a private file on this computer ({self._secrets_file})"
        return "the desktop keyring"

    # --- the person
    def notify(self, title: str, message: str) -> None:
        if self.which("notify-send"):
            self._call("notify-send", "--app-name", "Kobo Hardcover Sync", "--icon", "media-removable", title, message)

    def open_page(self, url: str) -> None:
        if not self.which("xdg-open"):
            print(url)  # no desktop to open it on: at least say where it is
            return
        self._call("xdg-open", url)

    # --- the trigger: a user service the Kobo's mount wants
    @property
    def unit_dir(self) -> str:
        return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(self.home, ".config"), "systemd", "user")

    def mount_units(self) -> list[str]:
        """The mount units a plugged-in Kobo becomes, as systemd names them."""
        return [_mount_unit(os.path.join(root, LABEL)) for root in self.volume_roots()]

    def install_trigger(self, command: str, rebuild: bool = False) -> list[str]:
        units = " ".join(self.mount_units())
        env = f'Environment="KHS_HOME={os.environ["KHS_HOME"]}"\n' if os.environ.get("KHS_HOME") else ""
        os.makedirs(self.unit_dir, exist_ok=True)
        with open(os.path.join(self.unit_dir, UNIT), "w") as fh:
            fh.write(
                "[Unit]\n"
                "Description=Kobo Hardcover Sync: sync the Kobo that was just plugged in\n"
                f"After={units}\n\n"
                "[Service]\n"
                "Type=oneshot\n"
                f'{env}ExecStart="{command}" sync --trigger mount\n\n'
                "[Install]\n"
                f"WantedBy={units}\n"
            )
        if not self.which("systemctl"):
            return [
                f"No systemd here: the unit is written ({os.path.join(self.unit_dir, UNIT)}), but nothing will start it. Run `kobo-hardcover-sync sync` by hand."
            ]
        self._call("systemctl", "--user", "daemon-reload")
        self._call("systemctl", "--user", "disable", UNIT)  # so the links follow a changed unit
        r = self._call("systemctl", "--user", "enable", UNIT)
        if r.returncode != 0:
            return [
                f"The user service could not be enabled ({(r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else 'no user session?'}).",
                "Plugging in will not start a sync; run `kobo-hardcover-sync sync` by hand, or run setup again from a desktop session.",
            ]
        return [
            "User service enabled: plugging in the Kobo starts a sync (no administrator rights involved).",
            f"It reacts to a Kobo mounted as {LABEL} under {' or '.join(self.volume_roots())}, where the desktop puts it.",
        ]

    def remove_trigger(self) -> list[str]:
        if self.which("systemctl"):
            self._call("systemctl", "--user", "disable", UNIT)
        try:
            os.unlink(os.path.join(self.unit_dir, UNIT))
        except FileNotFoundError:
            pass
        if self.which("systemctl"):
            self._call("systemctl", "--user", "daemon-reload")
        return ["User service removed."]


def _mount_unit(path: str) -> str:
    """systemd's unit name for a mount point (what `systemd-escape -p
    --suffix=mount` prints)."""
    out = []
    for i, ch in enumerate(path.strip("/")):
        if ch == "/":
            out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in ":_" or (ch == "." and i > 0)):
            out.append(ch)
        else:
            out.append("".join(f"\\x{b:02x}" for b in ch.encode()))
    return "".join(out) + ".mount"
