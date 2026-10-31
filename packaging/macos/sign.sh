#!/bin/sh
# Signs "Lastread.app" from the inside out (docs/macos-app.md):
#
#   packaging/macos/sign.sh IDENTITY APP
#
# IDENTITY "-" signs ad hoc: a build to try on this Mac. It gets no
# hardened runtime, because under the hardened runtime a library is only
# loaded when it has a team id, and an ad-hoc signature has none.
# Otherwise IDENTITY is a "Developer ID Application: ..." certificate in a
# keychain on the search list: the hardened runtime and Apple's timestamp,
# as notarisation asks.
#
# Entitlements only for the widget (Shelf.swift): it is sandboxed, as macOS
# asks of a widget, and it and the app share an app group, the folder where
# the app leaves the book being read and the tip. The group is the team id
# and the app's bundle id: from macOS 15 a group outside the App Store has
# to begin with the team id, and an ad-hoc signature has none, so signed
# ad hoc there is no group (and macOS shows no widget either).
set -eu
identity=${1:?"sign.sh: give the identity, or - for ad hoc"}
app=${2:?"sign.sh: give the app"}

sign() { # file [entitlements]
	if [ "$identity" = "-" ]; then
		codesign --force --sign - ${2:+--entitlements "$2"} "$1"
	else
		codesign --force --sign "$identity" --options runtime --timestamp ${2:+--entitlements "$2"} "$1"
	fi
}

entitlements() { # file sandboxed: the plist, with the group when there is a team
	{
		echo '<?xml version="1.0" encoding="UTF-8"?>'
		echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
		echo '<plist version="1.0"><dict>'
		[ "$2" = yes ] && echo '<key>com.apple.security.app-sandbox</key><true/>'
		[ -n "$team" ] && echo "<key>com.apple.security.application-groups</key><array><string>$team.$(plutil -extract CFBundleIdentifier raw "$app/Contents/Info.plist")</string></array>"
		echo '</dict></plist>'
	} >"$1"
	plutil -lint "$1" >/dev/null
}
team=$(printf '%s' "$identity" | sed -nE 's/^Developer ID Application: .*\(([A-Z0-9]{10})\)$/\1/p')

# Every Mach-O file in the bundle first (Python, its libraries, the
# packages' compiled parts), then the app, which seals the rest.
list=$(mktemp)
widget=$(mktemp)
shared=$(mktemp)
trap 'rm -f "$list" "$widget" "$shared"' EXIT
find "$app/Contents/Resources" -type f \( -name '*.so' -o -name '*.dylib' -o -perm -u+x \) >"$list"
count=0
while IFS= read -r f; do
	if file -b "$f" | grep -q Mach-O; then
		sign "$f"
		count=$((count + 1))
	fi
done <"$list"
# The widget, then the app, which seals it in.
entitlements "$widget" yes
sign "$app/Contents/PlugIns/Widget.appex" "$widget"
if [ -n "$team" ]; then
	entitlements "$shared" no
	sign "$app" "$shared"
else
	sign "$app"
fi
codesign --verify --strict --deep "$app"
echo "Signed ($identity): $count files inside, the widget, and the app${team:+ (app group $team.*)}."
