#!/bin/sh
# Signs "Kobo Hardcover Sync.app" from the inside out (docs/macos-app.md):
#
#   packaging/macos/sign.sh IDENTITY APP
#
# IDENTITY "-" signs ad hoc: a build to try on this Mac. It gets no
# hardened runtime, because under the hardened runtime a library is only
# loaded when it has a team id, and an ad-hoc signature has none.
# Otherwise IDENTITY is a "Developer ID Application: ..." certificate in a
# keychain on the search list: the hardened runtime, no entitlements, and
# Apple's timestamp, as notarisation asks.
set -eu
identity=${1:?"sign.sh: give the identity, or - for ad hoc"}
app=${2:?"sign.sh: give the app"}

sign() {
	if [ "$identity" = "-" ]; then
		codesign --force --sign - "$1"
	else
		codesign --force --sign "$identity" --options runtime --timestamp "$1"
	fi
}

# Every Mach-O file in the bundle first (Python, its libraries, the
# packages' compiled parts), then the app, which seals the rest.
list=$(mktemp)
trap 'rm -f "$list"' EXIT
find "$app/Contents/Resources" -type f \( -name '*.so' -o -name '*.dylib' -o -perm -u+x \) >"$list"
count=0
while IFS= read -r f; do
	if file -b "$f" | grep -q Mach-O; then
		sign "$f"
		count=$((count + 1))
	fi
done <"$list"
sign "$app"
codesign --verify --strict --deep "$app"
echo "Signed ($identity): $count files inside, and the app."
