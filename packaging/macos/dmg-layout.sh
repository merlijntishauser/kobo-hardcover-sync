#!/bin/sh
# Writes dmg.DS_Store: the disk image's window as Finder keeps it, 640 by 400
# points without toolbar, sidebar or status bar, dmg-background.png behind it,
# and the app and Applications where the move mark in dmg-background.svg is
# drawn round them (docs/macos-app.md, "The pictures"):
#
#   packaging/macos/dmg-layout.sh
#
# package.sh puts the file on every disk image, so this runs again only when the
# window changes, on a Mac with uv. dmgbuild writes it without Finder. Finder
# finds the background on a newly made image by its path, so the one file
# serves every release: checked on macOS 27 with an image made as package.sh
# makes it.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'hdiutil detach "$work/m" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

mkdir "$work/Kobo Hardcover Sync.app" # the positions go by name; an empty folder will do
tiffutil -cathidpicheck "$here/dmg-background.png" "$here/dmg-background@2x.png" -out "$work/background.tiff" >/dev/null 2>&1
cat >"$work/settings.py" <<EOF
volume_name = "Kobo Hardcover Sync"
format = "UDRO"
files = ["$work/Kobo Hardcover Sync.app"]
symlinks = {"Applications": "/Applications"}
background = "$work/background.tiff"
window_rect = ((200, 140), (640, 400))
default_view = "icon-view"
show_status_bar = show_tab_view = show_toolbar = show_pathbar = show_sidebar = False
icon_size = 128
text_size = 13
icon_locations = {"Kobo Hardcover Sync.app": (170, 190), "Applications": (470, 190)}
EOF
uvx --from dmgbuild==1.6.7 dmgbuild -s "$work/settings.py" "Kobo Hardcover Sync" "$work/layout.dmg" >/dev/null
hdiutil attach -nobrowse -readonly -mountpoint "$work/m" "$work/layout.dmg" >/dev/null
cp "$work/m/.DS_Store" "$here/dmg.DS_Store"
echo "Written: $here/dmg.DS_Store"
