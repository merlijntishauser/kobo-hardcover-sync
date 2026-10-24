# The Mac app's window

Design, agreed on 2026-10-24, for 0.12.0. It follows the first release of
the Mac app (`docs/macos-app.md`), which is a few dialogs around the tool:
setup, the last message, *Sync now*.

## Why

The first real installation, on a Mac that had used the Homebrew
installation before, showed what the dialogs leave out. With Homebrew,
`status`, `doctor` and the log answer four questions; the app answers
none of them:

- **Is this Mac in order?** The trigger, permission to read the Kobo, the
  token, the server or Hardcover.
- **What happened?** The last syncs, and what each did or why it failed.
- **Change something.** Mode and server, a new upload token, eject after a
  sync, a detailed log, removal: today flags and `config.toml`.
- **Watch a sync run**, step by step, as a sync in a terminal shows it.

In local mode the page already answers some of this (the Check card,
Settings). In server mode almost nothing has a place: *Open the page* opens
the server's page, which knows the books but nothing about this Mac.

## Decisions

| Topic | Decision | Turned down |
|---|---|---|
| Shape | **A native window about this Mac only**: its health, its syncs, a live sync, its settings. Books and Hardcover stay on the page, in both modes. | A local page for the computer, shown in a web view (one implementation for Mac and Linux, but a web page where a Mac window is expected, and a web server per visit in server mode); a menu bar item (the app would have to keep running, and nothing runs between syncs). |
| Settings | Mode and server, sync behaviour, the app itself, and the local-mode extras, each in the app. Connecting to Hardcover and the webhook are shown in the app and changed on the page. | Building the sign-in to Hardcover a second time, in Swift. |
| Source of truth | **The tool.** The app reads and changes everything through it, in JSON that a terminal can use as well. | The app reading and writing the tool's files itself. |
| Look | Native macOS: system font, SF Symbols, system colours. The brand is in the wording and in how a row that needs attention is marked. | The page's galley design in a Mac window. |

## The window

- **The top line answers the question.** A status dot and a sentence
  ("Ready for the Kobo", "Syncing…", "Needs attention: macOS does not let
  the app read the Kobo"), under it the mode and the last sync, and on the
  right *Sync now* and *Open the page*.
- **Health** is `doctor`: a row per thing a sync depends on, each with
  its mark and a sentence. A row with a problem has the button that fixes
  it ("Turn on", "Open Login Items", "Set up again"). It is checked when
  the window opens, and again on request.
- **History**: the recent syncs, newest first: when, started by the Kobo
  or by *Sync now*, and what it did. *Show the log* opens `agent.log` in
  Console.
- **A live sync**: *Sync now* turns the top into the steps as they happen
  (Kobo, upload or Hardcover, collection), then folds into one line in
  History.

With the window open the app is an ordinary app: a Dock icon, ⌘-Tab, ⌘-,
for Settings. Closing the window quits it. A sync started by the Kobo
stays invisible: a notification, then it quits. A click on that
notification opens the window.

## Settings (⌘-,)

- **Mode**: on this computer or with a server, and the server's address;
  a change runs `setup` again, which checks the address before anything
  switches. The upload token's hash with *Copy*, and *New upload token*,
  which first says that this Mac must then be added on the server's page
  again.
- **Sync**: eject after a sync; a detailed log for the next syncs; allow
  an untested Kobo software version, with what that risks. In local mode:
  the Hardcover connection and the webhook as they are, each with a link
  to the page where they are changed, and *Export my reading…* with a
  save dialog.
- **App**: the version, looking for a newer version, notifications and a
  link to macOS's own settings for them, and *Remove…*: stop syncing on
  this Mac (books, settings and tokens stay), or also delete those, with
  a list of what goes. Then it says to drag the app to the Bin.

Nothing about books is in Settings.

## The tool's side

What the app needs, each also usable in a terminal:

- `status --json`: mode, server, version, the last sync. Local files only,
  so the window fills at once.
- `doctor --json`: the checks as a list, each with its group, what it is
  about, its state (ok, note, warn, fail), what was found and what to do.
  The server or Hardcover are asked with a time limit; the window shows
  the rows as being checked until they come.
- `history.jsonl` in the tool's folder: one line per sync (when, what
  started it, whether it went well, what it said), the last
  hundred kept. `history` shows them; `history --json` gives them.
- `sync --steps`: each step as a line of JSON while it runs, so the app
  shows them as they come instead of after the end.
- `settings` shows the settings of this computer, `settings --json` gives
  them, and `settings --set NAME=VALUE` changes one. A mode change, a new
  token and a removal go through `setup` and `uninstall`, as now; export
  through `export`.

Every JSON answer carries `"schema": 1`. Sample answers in the repository
hold both sides to it: the Python tests check the tool writes that shape,
the `macos-app` CI job compiles the app's data types and reads the same
files.

What only macOS knows the app adds itself: whether its launch agent is
allowed (Login Items), and whether notifications are on.

When things go wrong: a tool that does not start is one row in the window,
with "download the app again"; a call that fails says so in its place, not
in a dialog. A sync the Kobo starts while the window is open runs in a
second process; the window watches `history.jsonl` and updates.

## Testing

- The tool's side in CI on Linux: each JSON answer and its schema,
  `history.jsonl` growing and kept to a hundred, the `--steps` lines,
  `settings --set` refusing an unknown name or a wrong value.
- The agreement between the two sides: the sample answers, as above.
- The window itself only on a Mac with a screen: a preview build with its
  own bundle id, which never registers a launch agent and reads a copy of
  a state folder, so it can be looked at without touching an installed
  app, its permissions or its trigger.

## Order

All in 0.12.0, in three steps, each looked at before the next:

1. The tool: the JSON answers, `history.jsonl`, `--steps`, `settings`.
2. The window, in SwiftUI: the top line, Health, History, the live sync,
   the Dock icon while it is open.
3. Settings and *Remove…*.

macOS 13 stays the oldest supported: SwiftUI's Settings window and lists
are there from 13 on.
