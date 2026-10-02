# Local mode, and one tool for both modes

Design, agreed one decision at a time on 2026-10-01. It describes what the
build has to deliver and why it is shaped this way; the server mode itself
is described in `how-it-works.md`.

Built: the package and the command, the Kobo write in Python behind its
gate, the seams with macOS behind them, the tool in server mode, and local
mode itself (`setup`, `token`, `sync`, `status`, `open`, the page on
demand), and the Linux seams. Seen with a real Kobo: local mode on a Mac
(a sync by hand, and a clean account from the README, 2026-10-02). Not yet: the run with a real
Kobo on a Linux desktop.

Where the build differs from what was planned below:

- The page's private file holds the port and the process id, not a hash of
  the secret. A second `open` does not need the secret: it makes a
  one-time key as a file in the state folder, and the page takes the key
  and deletes the file. Nothing worth stealing is written down.
- Only the address `127.0.0.1` is answered, not `localhost`: the cookie
  belongs to one name, and one name is easier to reason about.
- A sync started because some volume was mounted does nothing without a
  Kobo. The "Hardcover half only" happens when a person asks for a sync
  (`sync`, or *Sync now* on the page).
- On Linux the trigger needs no udev rule: systemd's user manager sees
  mounts as units, and a user service that the Kobo's mount unit "wants" is
  started each time the Kobo is mounted. Tried on systemd 257 with a mount
  made by hand: it fired, and fired again on the next mount.
- A Kobo mounted somewhere unusual is found through `KHS_VOLUMES`.
- The Kobo's own name for itself (`.kobo/version`) is read: serial (only
  as a hash, to tell two Kobos apart), software version and model.

## The idea

kobo-hardcover-sync runs in two ways, from one installed command:

- **Local mode.** Everything on your own computer: plug in the Kobo, it
  syncs to Hardcover, the collection on the Kobo is updated, eject. One
  reader, no server, no proxy.
- **Server mode.** The server holds the state for several readers (a
  household sharing one Kobo account). The computer the Kobo is plugged
  into only reads the Kobo and talks to the server.

The same command does both. Given a server address it behaves as today's
upload agent does; without one it runs the whole sync itself.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| How it runs | **On demand.** Plugging in runs one sync and exits; the page starts when asked for and stops when unused. | Nothing runs in between. Edits made on Hardcover are picked up at the next sync instead of every hour, which is enough for one reader. |
| The computer side | **One tool, two modes.** The shell agent goes; the collection write moves to Python. | One implementation of the only code that writes to the Kobo, and it can be tested without a device. |
| The local page | **Loopback, strict Host and Origin checks, and a secret in the link.** | The page has no login. Other websites must not be able to drive it, and other programs or users on the same computer must not be able to read it. |
| Eject | **Off by default, a setting turns it on.** | People plug in for other reasons too. |
| Platforms | **macOS and desktop Linux**, both supported. | Same story on both: someone logged in at a desktop. |
| Linux proof | A **desktop Linux virtual machine with the Kobo passed through** (Ubuntu LTS with GNOME first). | "Supported" means it was seen working with a real Kobo. |
| Install | **Homebrew tap** on the Mac, **PyPI with uv or pipx** on Linux. | The usual channel on each; the Homebrew formula builds from the published package. |

Not in local mode, by design: several readers, sign-up, the admin page,
upload devices, the upload endpoint, snapshots, the stats endpoint, the
hourly sync. A headless sync station (a Raspberry Pi without a screen) is
out of scope: its page could not be reached on the loopback address.

## Parts

```
   commands                 page
       \                    /
        +------ engine ----+
        | Kobo: read the database, device facts, write the collection
        | Hardcover: client, matching, sending
        | plan, two-way sync, state
        +------------------+
   seams to the computer: secret store, find the Kobo, trigger,
                          notify, eject, open the page
```

The engine knows nothing about macOS, Linux, the page or the commands. It
exists today, spread over `kobo_db`, `state`, `plan`, `hardcover`,
`syncback` and `job`; the build turns the code into an installable package
and gives those modules their own place, without rewriting them.

| Seam | macOS | Desktop Linux |
|---|---|---|
| Find the Kobo | `/Volumes/*` | `/run/media/<user>/*`, `/media/<user>/*` |
| Trigger on plug-in | launch agent (start on mount) through the small app wrapper | a user service started by the Kobo's mount |
| Secret store | Keychain | the desktop keyring when there is one, else a private file |
| Notification | the app wrapper | `notify-send` |
| Eject | `diskutil eject` | `udisksctl` |
| Open the page | `open` | `xdg-open` |
| Permission | Full Disk Access for the app wrapper | none |

A Kobo is any mounted volume with `.kobo/KoboReader.sqlite`.

## A sync, step by step

Started by the trigger, or by `sync` in a terminal, or by *Sync now* on the
page.

1. Find the Kobo. None found: in local mode still do the Hardcover half
   (take over edits made there, send what is pending).
2. Take the lock (a lock file in the state folder). A sync that is already
   running wins; the second one leaves quietly.
3. Copy the Kobo's database to a private temporary folder and read from the
   copy. The copy is deleted at the end, whatever happens. The Kobo's own
   file is opened only for the collection write.
4. **Local mode:** import the books, then the same run as the server does
   (take over edits from Hardcover, match, choose editions, send).
   **Server mode:** build a small database holding only what the server
   reads (the book rows and the device's reading events), upload it, and
   ask the server for the collection list.
5. Keep the collection on the Kobo equal to the books switched on, when a
   collection name is set and something changed.
6. Eject, when that setting is on.
7. Notify with one line: what changed, and "eject before unplugging" when
   the Kobo was written to and is still mounted.

Running it twice without changes does nothing the second time: no import,
nothing sent, nothing written to the Kobo.

## The page in local mode

- `open` starts it when it is not running, on the loopback address and a
  free port, and opens the browser with a link that carries a fresh random
  secret. The page trades the secret for a cookie and redirects, so the
  secret does not stay in the address bar or the history.
- Every request must come with that cookie, a `Host` of the page's own
  address and port, and for anything that changes something an `Origin`
  of the same.
- Port, process id and a hash of the secret are kept in a private file in
  the state folder, so a second `open` reuses the running page.
- It stops after 30 minutes without a request.
- The reader is always the one built-in reader. Settings shows the
  Hardcover token (set, remove), live or dry run, the collection
  name and eject after sync. No Admin page.
- First use is as on the server: dry run until the reader goes live, and
  every book already on the Kobo starts as *Off*.

Local mode refuses to listen on anything but the loopback address. Server
mode refuses to start without a trusted proxy address. So no installation
is half open by accident.

## Secrets

- **Local mode:** the Hardcover token is in the secret store, never in the
  state database, never in a log, and never on a command line (also not
  when handing it to the Keychain).
- **Server mode:** the upload token is in the same store on the computer;
  the server keeps Hardcover tokens encrypted as it does now.
- The Kobo account's own login tokens (the `user` table) exist only in the
  temporary copy and are never read. In server mode the upload is built
  from a list of what is needed, not by removing what is known to be
  sensitive.

## Writing to the Kobo

One module, used by both modes, with the rules the shell script has today:
only the collection it created itself, nothing written when nothing
changed, one transaction, a backup first (the last three are kept in the
state folder), ids checked before they reach SQL.

Added with the move to Python:

- **A gate before the backup:** the database version and the columns that
  will be written must be ones the tool knows. Otherwise it stops, says
  which version it found, and writes nothing.
- A check that the Kobo is still there before and after the write.
- Tests on a made-up database with the Kobo's schema, run in CI: create,
  repeat, change, remove, unknown schema, a write that is interrupted.

## Commands

```
kobo-hardcover-sync setup [--server URL]   make the trigger; says what permission to give
kobo-hardcover-sync token                  ask for the Hardcover token, check it, store it
kobo-hardcover-sync sync [--verbose]       one sync now; --verbose shows it book by book
kobo-hardcover-sync status                 mode, last sync, Kobo found, token present, collection
kobo-hardcover-sync doctor                 check everything a sync depends on; changes nothing
kobo-hardcover-sync open                   start the page and open it
kobo-hardcover-sync uninstall [--purge]    remove the trigger; --purge also state and secrets
kobo-hardcover-sync serve                  server mode (what the container runs)
```

`setup` can be run again at any time and changes nothing that is already
right. It never asks for administrator rights; if a step needs them, it
prints the command.

## Where things live

- State: `~/Library/Application Support/kobo-hardcover-sync/` on macOS,
  `~/.local/share/kobo-hardcover-sync/` on Linux (state database, covers,
  Kobo backups, log, lock).
- The log, `agent.log` there, has two levels (`logs.py`): counts and
  messages without book titles, and verbose, a line per book and per
  request to Hardcover. It is kept to about a megabyte, with one older
  file beside it. No token is written to it at either level.
- Settings chosen at `setup` (the mode and the server address): a small
  file next to the state.
- On the Mac the app wrapper stays for now: Full Disk Access given to
  Homebrew's Python would be lost at every Python upgrade, and the wrapper
  has a path that does not change. A signed app replaces it later.

## Tested how

- Without a device: a temporary folder playing a mounted Kobo with a
  made-up database. Sync, sync again (nothing happens), Kobo gone halfway,
  two syncs at once, the collection rules, the page's secret, Host and
  Origin checks.
- macOS: a clean user account in local mode, and an existing server
  installation switched to the tool.
- Linux: the desktop virtual machine with the Kobo passed through.

## To find out during the build

- What `.kobo/version` holds on current firmware (serial, firmware
  version): wanted for naming the device and for the message of the gate.
- Whether a user service can be started by the Kobo's mount on Ubuntu
  without administrator rights; if not, a udev rule that `setup` prints.
- How often a desktop keyring is really reachable from a user service; the
  private file may be the common case.
- The Homebrew formula with compiled dependencies. If it is painful,
  local installs can do without the encryption library, which only the
  server uses.
- Whether Full Disk Access on the wrapper covers the installed command it
  starts, as it covers the shell script today.
