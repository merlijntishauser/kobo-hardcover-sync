# The Mac app

Design, agreed on 2026-10-23. It describes a signed, notarised app on
GitHub Releases: download it, drag it to Applications, open it, done. No
Homebrew and no terminal. Homebrew and PyPI stay; the app is a third way
to install the same tool on a Mac.

Built so far: the parts of the tool that know they run inside the app,
the wrapper, the build and signing scripts and the workflows. Seen: the
app built and signed ad hoc on macOS 15 (CI) and macOS 27; there, started
by a launch agent in the logged-in session, the wrapper ran a sync
against a made-up Kobo and the update check. Not seen yet: setup through
the app, its notifications, and anything with a Developer ID. The app has
not been released. "Done" means a notarised build installs and syncs on a
Mac that has never seen the project, with Gatekeeper on. What only a real
Mac can show is listed under *To see on a real Mac* at the end.

## Why an app at all

macOS does not let a process that launchd starts read a removable volume
unless the person allowed it, and it remembers that permission per app,
by the app's signature. A Homebrew install has no app of its own, so
`setup` builds a small AppleScript app and signs it ad hoc. That works,
but an ad-hoc signature is new each time the app is rebuilt, so macOS
treats a rebuild as another app and the permission has to be given again,
by hand and without a prompt.

An app signed with a Developer ID is recognised by its team and bundle
id. The permission survives updates, and macOS can ask for it with a
proper prompt.

## Decisions

| Topic | Decision | Turned down |
|---|---|---|
| Python inside the app | **A small native wrapper in Swift**, with a standalone Python and the tool inside the bundle. The wrapper runs the tool as a child process, unchanged. | Briefcase (Python runs in-process; notifications and the launch agent would need Objective-C calls from Python); PyInstaller (the same, and notarisation and the disk image are our own work anyway). |
| Signing and notarising | **In GitHub Actions, in a separate workflow, behind an environment that needs the maintainer's approval for each run.** The certificate and the notary key are secrets of that environment only. | On the maintainer's own Mac with a script: the key never leaves that Mac, but every release then needs it, and the build cannot be repeated from the tag. |
| Updates | **The app checks, and says so; it does not update itself.** At most once a day, after a sync, it asks GitHub for the newest release. A newer version is shown on the page and in the app's window, with a link to the release. It can be switched off. | No check at all (people would stay on old versions without knowing); a full updater with Sparkle (a signing key of its own to look after, and the largest attack surface). |
| Modes | **Local and server mode**, chosen the first time the app is opened. | Local mode only. |

## Settled without asking

- **Apple silicon only, macOS 13 or newer.** Intel Macs are out, as for the
  Homebrew bottles. macOS 13 is the first with `SMAppService`, which
  registers the launch agent as the app's own background item.
- **A disk image** with the app and a link to Applications. The app and
  the disk image are both notarised and stapled, so the first start works
  offline as well.
- **Name and identity.** `Kobo Hardcover Sync.app`, bundle id
  `org.gargleblaster.kobo-hardcover-sync.app`, launch agent
  `org.gargleblaster.kobo-hardcover-sync.app.agent`. Both differ from the
  AppleScript app's (`org.gargleblaster.kobo-hardcover-sync`), so the two
  never share a permission entry, and one can replace the other cleanly.
- **The same folder and the same Keychain items** as a Homebrew install
  (`~/Library/Application Support/kobo-hardcover-sync`, Keychain service
  `kobo-hardcover-sync`). Someone who moves from Homebrew to the app keeps
  their books, their settings and their connection.
- **One trigger per Mac.** Setting up the app removes the AppleScript app
  and its launch agent, if there are any. `setup` run from Homebrew on a
  Mac where the app's launch agent is loaded installs nothing and says
  that the app has the trigger.
- **The version** is the package's: `CFBundleShortVersionString` and
  `CFBundleVersion` are both `0.11.0` for 0.11.0. The release notes are the
  GitHub release's, which already come from `CHANGELOG.md`.
- **Licences.** `LICENSE`, `THIRD-PARTY-NOTICES.md` and Python's own licence
  go into `Contents/Resources`. The packages inside keep their own licence
  files in their `.dist-info` folders.
- **No entitlements** under the hardened runtime, to start with. Every
  library in the bundle is signed with the same team id, so library
  validation passes without exceptions. If something needs one, it is
  added with its reason next to it.

## The bundle

```
Kobo Hardcover Sync.app/Contents/
  Info.plist
  MacOS/Kobo Hardcover Sync              the wrapper (Swift)
  Library/LaunchAgents/org.gargleblaster.kobo-hardcover-sync.app.agent.plist
  Resources/
    python/                              a standalone CPython, with the tool
      bin/python3                        and its packages in site-packages
    python-licenses/                     the licences of what Python is built with
    AppIcon.icns
    LICENSE, THIRD-PARTY-NOTICES.md, PYTHON-LICENSE.txt
```

The Python is a build from
[python-build-standalone](https://github.com/astral-sh/python-build-standalone),
pinned by version and SHA-256 in `packaging/macos/build.sh`. The packages
are the ones `uv.lock` pins, with their hashes, as wheels only. Everything
is compiled to bytecode at build time (unchecked hashes), so nothing in
the bundle is written to while it runs, which would break the signature.

## What the wrapper does

The wrapper is the AppleScript app ported to Swift, plus setup. It is
started in three ways:

- **By the launch agent, when a volume is mounted.** The agent sets
  `KHS_TRIGGER=mount`. The wrapper runs `sync --trigger mount`, shows each
  `NOTIFY|title|message` line the tool prints as a notification, and quits.
- **Opened by hand, before setup.** It asks: on this computer, or with a
  server (and its address). It registers its launch agent, asks to show
  notifications, and runs `setup`. It then shows what `setup` said. In
  local mode it opens the page, where the reader connects to Hardcover; in
  server mode what `setup` said includes this Mac's hash, to paste on the
  server's page.
- **Opened by hand after setup, or by a click on a notification.** It
  shows the last message, a newer version if there is one, and the buttons
  *Sync now*, *Open the page* and *OK*.

It runs the tool as `Resources/python/bin/python3 -I -m
kobo_hardcover_sync ...`, with two variables:

- `KHS_APP`: the path of the app. The tool then knows that the app owns
  the trigger, words its messages for someone without a terminal, and
  checks for a newer version.
- `KHS_NOTIFY=stdout`: notifications come back as lines for the wrapper to
  show, so a click on one lands on the app.

The tool is a child of the app, so what macOS allowed the app also covers
the tool.

## The permission to read the Kobo

The app's `Info.plist` has `NSRemovableVolumesUsageDescription`. With a
real signature, macOS should then ask the first time the app reads the
Kobo, and remember the answer. If it does not ask, the message the tool
gives is the one it gives today: turn on Full Disk Access for the app, by
hand. Which of the two happens is the first thing to see on a real Mac.

## The update check

- Only inside the app. Homebrew and PyPI have their own way of saying a
  version is out.
- After a sync that the trigger started, at most once a day, and after the
  notification has been shown, so it never makes a sync slower.
- One request, `GET https://api.github.com/repos/merlijntishauser/kobo-hardcover-sync/releases/latest`,
  with a timeout of five seconds. Nothing is sent but the request itself.
  A failure is logged and otherwise ignored.
- Only the tag is used, and only if it reads `v` plus three numbers. The
  link that is shown is built from that version, never taken from the
  answer.
- The result is kept in `update.json` in the state folder; the page and
  the wrapper both read it from there.
- Switched off on the page (Settings, This computer) or with
  `check_for_updates = false` in `config.toml`.

## Building and signing

- `packaging/macos/build.sh` builds the app from a wheel: it fetches and
  checks the Python, installs the wheel and the locked packages, compiles
  the wrapper and puts the bundle together. It signs the result ad hoc, so
  that it runs on the Mac it was built on. CI builds it on every push and
  starts the tool in it, so a broken bundle shows up before a release.
- `packaging/macos/sign.sh` signs every Mach-O file in the bundle, then
  the app. With a Developer ID it adds the hardened runtime and Apple's
  timestamp. An ad-hoc build gets no hardened runtime: under it, a library
  is only loaded when it has a team id, and an ad-hoc signature has none.
  So the hardened runtime is first tried in the release's signing job,
  which starts the tool once more after signing.
- `packaging/macos/package.sh` notarises and staples the app, puts it on
  a disk image with a link to Applications, then signs, notarises and
  staples that.
- `.github/workflows/macos-app.yml` does both at a release. Building
  happens in a job without secrets. Signing happens in a second job, in the
  `macos-signing` environment, which downloads the built app and runs only
  Apple's tools and `sign.sh`: no package is installed and no code from
  elsewhere runs where the certificate is. The certificate goes into a
  keychain made for that run and deleted at its end. The disk image is
  added to the GitHub release.

What the environment holds, and how to set it up once, is in
`docs/releasing.md`.

## To see on a real Mac

None of these can be seen in CI; each one is a check on a Mac that has
never had the project, with the notarised build.

1. Gatekeeper opens the downloaded disk image and the app without a
   warning beyond "downloaded from the internet".
2. Whether macOS asks for the removable volume by itself, or Full Disk
   Access has to be given by hand.
3. That permission survives installing the next version over it.
4. The launch agent starts the app when the Kobo is plugged in, also
   after a restart, and the app shows up under Login Items as itself.
5. A click on a notification opens the app's window.
6. The hardened runtime with no entitlements: a full sync, with the
   collection write, runs (cryptography, the Keychain, the page).
7. Moving from Homebrew to the app on one Mac keeps the books and the
   connection, and leaves a single trigger.
8. Dragging the app to the Bin: what is left under Login Items, and in
   the permission lists.
