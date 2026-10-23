#!/bin/sh
# Notarises the signed app, staples it, puts it on a disk image with a link
# to Applications, and signs, notarises and staples that (docs/macos-app.md):
#
#   packaging/macos/package.sh IDENTITY APP DMG
#
# notarytool's credentials come from the environment, an App Store Connect
# API key: NOTARY_KEY (the path of its .p8 file), NOTARY_KEY_ID and
# NOTARY_ISSUER.
set -eu
identity=${1:?"package.sh: give the identity"}
app=${2:?"package.sh: give the signed app"}
dmg=${3:?"package.sh: give the disk image to make"}
: "${NOTARY_KEY:?}" "${NOTARY_KEY_ID:?}" "${NOTARY_ISSUER:?}"

notarise() {
	xcrun notarytool submit "$1" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" \
		--wait --timeout 1h --output-format json >"$work/notary.json" || true
	status=$(plutil -extract status raw -o - "$work/notary.json" 2>/dev/null || echo "no answer")
	if [ "$status" != Accepted ]; then
		echo "package.sh: notarisation of $(basename "$1"): $status" >&2
		id=$(plutil -extract id raw -o - "$work/notary.json" 2>/dev/null || true)
		[ -z "$id" ] || xcrun notarytool log "$id" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" >&2 || true
		exit 1
	fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# The app first, so that it is stapled itself and opens offline once copied out.
ditto -c -k --keepParent "$app" "$work/app.zip"
notarise "$work/app.zip"
xcrun stapler staple "$app"

mkdir "$work/image"
ditto "$app" "$work/image/$(basename "$app")"
ln -s /Applications "$work/image/Applications"
rm -f "$dmg"
hdiutil create -volname "Kobo Hardcover Sync" -srcfolder "$work/image" -fs HFS+ -format UDZO -ov "$dmg" >/dev/null
codesign --force --sign "$identity" --timestamp "$dmg"
notarise "$dmg"
xcrun stapler staple "$dmg"

# What Gatekeeper will say on a Mac that downloads it.
spctl --assess --type execute --verbose=2 "$app"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
echo "Notarised: $dmg"
