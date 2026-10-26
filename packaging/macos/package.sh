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

# Up to three tries: the first submission from a CI runner fails now and
# then, and passes when sent again. Only "Invalid" is a verdict on the
# build; no answer, an upload error or a wait that gave up is tried again.
notarise() {
	for try in 1 2 3; do
		xcrun notarytool submit "$1" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" \
			--wait --timeout 1h --output-format json >"$work/notary.json" || true
		status=$(plutil -extract status raw -o - "$work/notary.json" 2>/dev/null || echo "no answer")
		id=$(plutil -extract id raw -o - "$work/notary.json" 2>/dev/null || true)
		case $status in
		Accepted) return 0 ;;
		Invalid)
			echo "package.sh: notarisation of $(basename "$1"): Invalid" >&2
			[ -z "$id" ] || xcrun notarytool log "$id" --key "$NOTARY_KEY" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" >&2 || true
			exit 1
			;;
		esac
		echo "package.sh: try $try for $(basename "$1"): ${status} (${id:-no submission}); again in a minute" >&2
		[ "$try" = 3 ] || sleep 60
	done
	echo "package.sh: notarisation of $(basename "$1") gave no verdict in three tries" >&2
	exit 1
}

here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'hdiutil detach "$work/volume" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

# The app first, so that it is stapled itself and opens offline once copied out.
ditto -c -k --keepParent "$app" "$work/app.zip"
notarise "$work/app.zip"
xcrun stapler staple "$app"

mkdir "$work/image"
ditto "$app" "$work/image/$(basename "$app")"
ln -s /Applications "$work/image/Applications"
# The window: its background and layout (dmg-layout.sh), and the disk's icon.
tiffutil -cathidpicheck "$here/dmg-background.png" "$here/dmg-background@2x.png" -out "$work/image/.background.tiff" >/dev/null 2>&1
cp "$here/dmg.DS_Store" "$work/image/.DS_Store"
mkdir "$work/VolumeIcon.iconset"
for size in 16 32 128 256 512; do
	sips -z $size $size "$here/VolumeIcon.png" --out "$work/VolumeIcon.iconset/icon_${size}x${size}.png" >/dev/null
	sips -z $((size * 2)) $((size * 2)) "$here/VolumeIcon.png" --out "$work/VolumeIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
# 16 and 32 pixels are drawn for their size (art.py), not made smaller.
cp "$here/VolumeIcon-16.png" "$work/VolumeIcon.iconset/icon_16x16.png"
cp "$here/VolumeIcon-32.png" "$work/VolumeIcon.iconset/icon_16x16@2x.png"
cp "$here/VolumeIcon-32.png" "$work/VolumeIcon.iconset/icon_32x32.png"
iconutil -c icns -o "$work/image/.VolumeIcon.icns" "$work/VolumeIcon.iconset"
# Made writable first: the flags that show the disk's icon and hide ".app" are
# set on the mounted image, where they last (on the folder they are not copied).
hdiutil create -volname "Kobo Hardcover Sync" -srcfolder "$work/image" -fs HFS+ -format UDRW -ov "$work/rw.dmg" >/dev/null
hdiutil attach -nobrowse -readwrite -noverify -mountpoint "$work/volume" "$work/rw.dmg" >/dev/null
xattr -wx com.apple.FinderInfo 0000000000000000040000000000000000000000000000000000000000000000 "$work/volume"
xattr -wx com.apple.FinderInfo 0000000000000000001000000000000000000000000000000000000000000000 "$work/volume/$(basename "$app")"
hdiutil detach "$work/volume" >/dev/null
rm -f "$dmg"
hdiutil convert "$work/rw.dmg" -format UDZO -o "$dmg" >/dev/null
codesign --force --sign "$identity" --timestamp "$dmg"
notarise "$dmg"
xcrun stapler staple "$dmg"

# What Gatekeeper will say on a Mac that downloads it.
spctl --assess --type execute --verbose=2 "$app"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
echo "Notarised: $dmg"
