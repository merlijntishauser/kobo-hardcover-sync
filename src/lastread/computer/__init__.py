"""The computer the Kobo is plugged into: one tool, two modes.

- config: where the tool keeps its things, and what `setup` chose.
- platform: the seams to the operating system (find the Kobo, keep a secret,
  notify, eject, open the page, the trigger on plug-in). macOS in macos.py.
- remote: server mode's half of a sync (upload, ask for the collection).
- runner: one sync, start to finish.

Nothing here is imported by the server.
"""
