# The Mac app

Design, agreed on 2026-10-23. It describes a signed, notarised app on
GitHub Releases: download it, drag it to Applications, open it, done. No
Homebrew and no terminal. Homebrew and PyPI stay; the app is a third way
to install the same tool on a Mac.

Built so far: the parts of the tool that know they run inside the app,
the wrapper, the build and signing scripts and the workflows. Seen: the
app built and signed ad hoc on macOS 15 (CI) and macOS 27; there, started
by a launch agent in the logged-in session, the wrapper ran a sync
against a made-up Kobo and the update check. Its first release is
0.11.0, signed with a Developer ID and notarised. On the maintainer's Mac
(macOS 27, until then a Homebrew installation in server mode) 0.11.0 set
itself up, took the trigger over, and macOS asked by itself for the
removable volume; the first sync at a plug-in uploaded. Two things were
wrong there, and 0.11.1 changes them: *Sync now* said nothing when
there was nothing new, and the question about notifications came while
setup's windows were open, was answered no, and nothing said so after.
Not seen yet: a click on a notification, and a Mac that has never had
the project. "Done" means a notarised build installs and syncs on such a
Mac, with Gatekeeper on. What only a real Mac can show is listed
under *To see on a real Mac* at the end.

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
  server (and its address). It registers its launch agent and runs
  `setup`. It then shows what `setup` said, and says that macOS is about
  to ask whether it may show notifications; macOS asks once that window
  is closed. (macOS asks in a corner of the screen; asked while setup's
  windows were still open, the question was missed.) In local mode it
  opens the page, where the reader connects to Hardcover; in server mode
  what `setup` said includes this Mac's hash, to paste on the server's
  page.
- **Opened by hand after setup, or by a click on a notification.** It
  opens its window; the design is
  `docs/plans/2026-10-24-mac-app-native-books-design.md`, which follows
  `docs/plans/2026-10-24-mac-app-window-design.md`. One line says whether
  it is ready for the Kobo, with the mode and the last sync, beside
  *Open the page* and *Sync now*. Beside it a sidebar: *Overview*,
  *Books* and *History*. Overview is the chain a sync takes: Kobo, This
  Mac, the server in server mode, Hardcover. Each link has the page's
  mark for how it is, from `doctor --json` and whether notifications are
  on. In local mode the arrows carry the counts of `status --json`: the
  books from the Kobo, what the next sync sends, the collection. A click
  on a link shows its checks, with a button where the app can mend what
  a check found; the first link that needs something is open by itself.
  While a sync runs (`sync --trigger app --steps`) a red line sweeps along
  the arrow it works on, the links it passed get their marks, and the
  steps are listed under the chain. Books, in local mode, is the page's
  list drawn in the app, from `books --json`: each book with its cover
  (fetched once by `books --covers`), its title in the page's Source
  Serif 4, its Sync, its State and its Hardcover status with the page's
  marks, a change struck and written in as on the page; search, the
  page's filters and its sorts above it, with the legend of the marks.
  A click opens its Details beside the list. Sync and State are changed
  in the row or in Details (`book ID --sync`, `--state`, `--date`); a
  book without a match shows the books it could be, with *Use*
  (`--pick`), and a search on Hardcover (`--search`); *Remove from
  Hardcover…* takes it off the shelf after asking (`--remove`). *Set all*
  sets Sync for every book the search and filter show, after asking, and
  only while the list still holds as many (`books --sync ... --expect
  N`). Each change starts the tool once, about 0.06 s on an M-series Mac,
  and the answer redraws the book. Until you go live, the page's first
  run sits above the list ("Pick the books that are yours", from
  `books --json`): *Connect…*, then picking your books, then a red *Go
  live* that asks first (`settings --set live=true`). *Connect…* (also on
  Overview's Hardcover link and in Settings, Sync) signs in as the page
  does: `token --json` opens Hardcover in the browser and says each step
  as a line of JSON, the sheet follows it, and *Paste a token instead…*
  gives a token on standard input (`token --paste --json`). Settings,
  Sync, has the connection with *Disconnect…* and *Send to Hardcover*,
  the switch between live and a dry run. *Open on the Page* opens the page at
  the book (`open --book`). In server mode Books opens the server's
  page. History (`history --json`) has *Show the log*. A sync the Kobo starts while the window is open
  shows as "Syncing…" while it runs (`status --json` says so, from the
  sync's lock; the sync keeps a `sync.running` marker in the tool's folder,
  which wakes the window), and in History when it ends. With the window open the app has a
  Dock icon and a menu bar; closing the window quits it.
- **Settings (⌘-,),** three tabs, each change through the tool. *Mode*:
  local or a server, which runs `setup --local` or `setup --server ...
  --check` (the server is asked first; nothing changes if it does not
  answer), and in server mode the upload token's hash with *New upload
  token…* (`setup --new-token`). *Sync*: the settings that are true or
  false (`settings --set`); in local mode the Hardcover connection (it
  is changed on the page), the webhook (`webhook`, its token given on
  standard input, never as an argument) and *Export my reading…* (`export
  --output`, with a save dialog). *App*: the version, looking for a newer
  one (and *Check now*, `update --json`, which is also *Check for
  Updates…* in the app menu), notifications, and *Remove…*: the app unregisters its launch agent
  and runs `uninstall`, or `uninstall --purge` to delete the folder and
  the tokens as well, then says to drag the app to the Bin, and quits.
- **The notification of a sync the Kobo started** is shown as soon as
  the tool prints it: the wrapper reads the tool's output line by line,
  so the notification does not wait for what the tool does after it (the
  update check).

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
  starts the tool in it, so a broken bundle shows up before a release, and
  checks that the app reads the sample answers in `packaging/macos/samples`
  (`CheckSamples.swift`), which the tool's tests hold the tool to.
- `KHS_PREVIEW=1 packaging/macos/build.sh ...` builds a preview: its own
  bundle id and name, its own folder
  (`~/Library/Application Support/kobo-hardcover-sync-preview`, to copy a
  tool folder into), no launch agent, and a *Sync now* that only plays
  sample steps. The window can then be looked at on a Mac where the app
  is installed, without touching that app, its permissions or its trigger.
  In its Settings, what would touch this Mac (a mode change, a new token,
  the webhook, *Remove…*) only says what it would do; the true-or-false
  settings and an export work, on its own folder. It shares the
  Hardcover connection in the Keychain with the app itself, so it does
  not connect, disconnect or take a book off the shelf. Opened with
  `open --env KHS_SNAPSHOT=<folder>`, it saves a picture of each pane of
  its window, of a book's Details, of a sample sync on the chain, and of each Settings tab
  there, and quits (the sidebar comes out empty in these pictures: what
  is drawn behind it is not in them): a look from an SSH session, which
  macOS does not let take a screenshot.
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
