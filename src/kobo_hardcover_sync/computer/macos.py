"""macOS: Keychain, a launch agent that fires when a volume mounts, and a
small app that the launch agent starts.

Why the app: macOS privacy (TCC) does not let a process started by launchd
read a removable volume, and shows no prompt for it. The app gets Full Disk
Access once, from the person; what it starts (this tool) is covered by that.
Its path never changes, so the grant survives upgrades of the tool. It also
shows the notifications, so a click on one lands on it and not on Script
Editor, and opened by hand it shows the last message.

The app is built once. Rebuilding it gives it a new ad-hoc signature, which
macOS treats as another app: the grant has to be given again.
"""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess

from . import config
from .platform import Computer

BUNDLE_ID = "org.gargleblaster.kobo-hardcover-sync"
LABEL = BUNDLE_ID + ".agent"
KEYCHAIN = "kobo-hardcover-sync"
APP = "KoboHardcoverSync.app"
SECRET_OK = re.compile(r"^[A-Za-z0-9._~+/=-]{1,4096}$")  # what may go through `security -i` unquoted


APPLESCRIPT = """\
-- kobo-hardcover-sync: runs the installed tool and shows what it says.
-- The tool's path is read from the file "command" each time, so this app
-- does not have to be rebuilt (and re-granted) when the tool moves.
property stateDir : "__STATE__/"

on toolLine(args)
	set tool to do shell script "cat " & quoted form of (stateDir & "command")
	return "__ENV__KHS_NOTIFY=stdout " & quoted form of tool & " " & args & " 2>/dev/null; true"
end toolLine

on runSync()
	try
		set output to do shell script my toolLine("sync --trigger mount")
	on error
		set output to ""
	end try
	set AppleScript's text item delimiters to "|"
	repeat with l in paragraphs of output
		if (l as text) starts with "NOTIFY|" then
			set parts to text items of (l as text)
			if (count of parts) is greater than or equal to 3 then
				display notification (item 3 of parts) with title (item 2 of parts)
			end if
		end if
	end repeat
	set AppleScript's text item delimiters to ""
end runSync

on showLast()
	try
		set msg to do shell script "cat " & quoted form of (stateDir & "last-message.txt")
	on error
		set msg to "Nothing synced yet."
	end try
	try
		activate
		set choice to button returned of (display dialog msg with title "Kobo Hardcover Sync" buttons {"Sync now", "Open the page", "OK"} default button "OK")
		if choice is "Open the page" then do shell script my toolLine("open")
		if choice is "Sync now" then my runSync()
	end try
end showLast

on run
	if (system attribute "KHS_TRIGGER") is "mount" then
		my runSync()
	else
		my showLast()
	end if
end run
"""


def _applescript_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


class MacOS(Computer):
    name = "this Mac"

    def __init__(self, run=subprocess.run, home: str | None = None, volumes: str = "/Volumes"):
        self.run = run
        self.home = home or os.path.expanduser("~")
        self.volumes = volumes

    # --- paths
    @property
    def state(self) -> str:
        return config.state_dir()

    @property
    def app(self) -> str:
        return os.path.join(self.state, APP)

    @property
    def plist(self) -> str:
        return os.path.join(self.home, "Library", "LaunchAgents", LABEL + ".plist")

    def _call(self, *args: str, **kw):
        return self.run(list(args), capture_output=True, text=True, **kw)

    # --- the Kobo
    def volume_roots(self) -> list[str]:
        return [self.volumes]

    def eject(self, mount: str) -> bool:
        return self._call("/usr/sbin/diskutil", "eject", mount).returncode == 0

    def cannot_read(self, by_hand: bool) -> str:
        if by_hand:
            return (
                "macOS does not let this terminal read the Kobo. Allow it when macOS asks, or under System Settings, "
                "Privacy & Security, Files & Folders (Removable Volumes)."
            )
        return (
            f"macOS does not let the tool read the Kobo. Give {APP} Full Disk Access (System Settings, Privacy & Security, "
            "Full Disk Access), then plug the Kobo in again."
        )

    # --- secrets: the Keychain
    def secret(self, name: str, service: str = KEYCHAIN) -> str:
        r = self._call("/usr/bin/security", "find-generic-password", "-s", service, "-a", name, "-w")
        return r.stdout.strip() if r.returncode == 0 else ""

    def set_secret(self, name: str, value: str) -> None:
        # `security add-generic-password -w VALUE` would put the secret in
        # the process list. In interactive mode the command is read from
        # standard input instead, so it only ever travels through a pipe.
        if not SECRET_OK.match(value) or not SECRET_OK.match(name):
            raise ValueError("this secret has characters the Keychain helper cannot take")
        self._call("/usr/bin/security", "-i", input=f"add-generic-password -U -s {KEYCHAIN} -a {name} -w {value}\n")
        if self.secret(name) != value:
            raise RuntimeError("The Keychain did not keep the secret.")

    def delete_secret(self, name: str, service: str = KEYCHAIN) -> None:
        self._call("/usr/bin/security", "delete-generic-password", "-s", service, "-a", name)

    def secret_place(self, name: str) -> str:
        return "the Keychain"

    # --- the person
    def notify(self, title: str, message: str) -> None:
        def clean(s):
            return " ".join(s.replace("|", "/").split())

        if os.environ.get("KHS_NOTIFY") == "stdout":  # the app shows it, so a click lands on the app
            print(f"NOTIFY|{clean(title)}|{clean(message)}", flush=True)
            return
        self._call(
            "/usr/bin/osascript",
            "-e", "on run argv",
            "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
            "-e", "end run",
            title, message,
        )  # fmt: skip

    def open_page(self, url: str) -> None:
        self._call("/usr/bin/open", url)

    # --- the trigger
    def install_trigger(self, command: str, rebuild: bool = False) -> list[str]:
        said = []
        os.makedirs(self.state, mode=0o700, exist_ok=True)
        os.makedirs(os.path.dirname(self.plist), exist_ok=True)
        with open(os.path.join(self.state, "command"), "w") as fh:
            fh.write(command + "\n")
        env = f"KHS_HOME={_shell_quote(os.environ['KHS_HOME'])} " if os.environ.get("KHS_HOME") else ""
        script = APPLESCRIPT.replace("__STATE__", _applescript_string(self.state)).replace("__ENV__", _applescript_string(env))
        source = os.path.join(self.state, "KoboHardcoverSync.applescript")
        try:
            with open(source) as fh:
                same = fh.read() == script
        except FileNotFoundError:
            same = False
        if os.path.isdir(self.app) and same and not rebuild:
            said.append(f"{APP} kept (its Full Disk Access stays).")
        else:
            said += self._build_app(source, script)
        with open(self.plist, "wb") as fh:
            plistlib.dump(
                {
                    "Label": LABEL,
                    "ProgramArguments": [os.path.join(self.app, "Contents", "MacOS", "applet")],
                    "EnvironmentVariables": {"KHS_TRIGGER": "mount"},
                    "StartOnMount": True,
                    "StandardErrorPath": os.path.join(self.state, "agent.err"),
                },
                fh,
            )
        target = f"gui/{os.getuid()}"
        self._call("/bin/launchctl", "bootout", f"{target}/{LABEL}")
        r = self._call("/bin/launchctl", "bootstrap", target, self.plist)
        said.append(
            "Launch agent loaded: plugging in the Kobo starts a sync."
            if r.returncode == 0
            else f"launchctl could not load the launch agent: {r.stderr.strip()}"
        )
        return said

    def _build_app(self, source: str, script: str) -> list[str]:
        _remove(self.app)
        with open(source, "w") as fh:
            fh.write(script)
        r = self._call("/usr/bin/osacompile", "-o", self.app, source)
        if r.returncode != 0:
            raise RuntimeError(f"osacompile could not build {APP}: {r.stderr.strip()}")
        info = os.path.join(self.app, "Contents", "Info.plist")
        # Own bundle id, own name, no Dock icon; then sign again (ad hoc).
        # Editing Info.plist breaks osacompile's signature, and macOS then
        # attributes the access to Script Editor, so a permission given to
        # this app never applies (seen 2026-09-30).
        for key, kind, value in (
            ("CFBundleIdentifier", "string", BUNDLE_ID),
            ("CFBundleName", "string", "Kobo Hardcover Sync"),
            ("LSUIElement", "bool", "true"),
        ):
            if self._call("/usr/libexec/PlistBuddy", "-c", f"Set :{key} {value}", info).returncode != 0:
                self._call("/usr/libexec/PlistBuddy", "-c", f"Add :{key} {kind} {value}", info)
        self._call("/usr/bin/codesign", "--force", "--deep", "--sign", "-", self.app)
        r = self._call("/usr/bin/codesign", "--verify", "--strict", self.app)
        if r.returncode != 0:
            raise RuntimeError(f"{APP} could not be signed: {r.stderr.strip()}")
        return [
            f"{APP} built and signed (ad hoc), id {BUNDLE_ID}.",
            "One-time permission, macOS shows no prompt for it: System Settings > Privacy & Security > Full Disk Access > + > Cmd+Shift+G >",
            f"  {self.app}",
            "(Remove an older Kobo Hardcover Sync entry there first.)",
        ]

    def trigger_state(self) -> tuple[bool, str]:
        again = "Run `kobo-hardcover-sync setup` again."
        if not os.path.isfile(self.plist) or not os.path.isdir(self.app):
            return False, f"No trigger on this Mac: plugging in the Kobo does nothing by itself. {again}"
        try:
            with open(os.path.join(self.state, "command")) as fh:
                command = fh.read().strip()
        except OSError:
            command = ""
        if not (command and os.access(command, os.X_OK)):
            return False, f"The trigger starts {command or 'a command'} that is not there any more. {again}"
        if self._call("/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}").returncode != 0:
            return False, f"The launch agent is there but not loaded. {again}"
        return True, f"Plugging in the Kobo starts a sync (launch agent loaded; it runs {command})."

    def remove_trigger(self) -> list[str]:
        self._call("/bin/launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}")
        _remove(self.plist)
        for name in (APP, "KoboHardcoverSync.applescript", "command"):
            _remove(os.path.join(self.state, name))
        return ["Launch agent and app removed. Remove the Full Disk Access entry by hand if you like."]


def _remove(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
