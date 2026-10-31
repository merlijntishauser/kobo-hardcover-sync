#!/bin/sh
# Builds "Lastread.app" from a wheel of the tool (docs/macos-app.md):
#
#   packaging/macos/build.sh dist/lastread-0.11.0-py3-none-any.whl [folder]
#
# The app lands in folder (build/macos by default), signed ad hoc so that it
# runs on this Mac; sign.sh signs it with a Developer ID. Needs a Mac with
# Xcode (26 or later, for the icon), uv and zstd. Nothing here is secret, and
# nothing here needs one.
#
# KHS_PYTHON_ONLY=1 builds only the Python half (no wrapper, no icon, no
# signature), on any computer this Python build exists for: a quick look at
# what goes into the bundle.
#
# KHS_PREVIEW=1 builds the preview: its own bundle id and name, its own
# folder (~/Library/Application Support/kobo-hardcover-sync-preview, to
# copy a tool folder into), no launch agent, and a Sync now that syncs
# nothing. For looking at the window on a Mac with the app installed,
# without touching that app, its permissions or its trigger.
set -eu

# The Python inside: python-build-standalone, pinned. The full build is only
# fetched for the licence texts of the libraries Python is built with, which
# the smaller install_only build leaves out.
PYTHON=3.13.17
PYTHON_BUILD=20261021
TRIPLE=${KHS_TRIPLE:-aarch64-apple-darwin}
case $TRIPLE in
aarch64-apple-darwin)
	PYTHON_SHA256=8dc60610a82f1e73be7faf964383e02520f95f6e39592a5c37c3809f5a7b798e
	FULL_SHA256=3ccb423f96990a6ac6a10e23052ba6c70144117559af097cd0c0305939dc015b
	;;
x86_64-unknown-linux-gnu) # only for KHS_PYTHON_ONLY
	PYTHON_SHA256=f829adc9d888e76c8801b4799ed444188d35239fcae3a9808a99ec5cb0d8d92c
	FULL_SHA256=
	;;
*)
	echo "build.sh: no pinned Python for $TRIPLE" >&2
	exit 1
	;;
esac
RELEASE=https://github.com/astral-sh/python-build-standalone/releases/download/$PYTHON_BUILD
NAME="Lastread"

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
wheel=${1:?"build.sh: give the wheel, e.g. dist/lastread-0.11.0-py3-none-any.whl"}
case $wheel in /*) ;; *) wheel=$(pwd)/$wheel ;; esac
out=${2:-$root/build/macos}
mkdir -p "$out/cache"
out=$(cd "$out" && pwd)

# 0.11.0 from lastread-0.11.0-py3-none-any.whl; macOS wants three numbers.
version=$(basename "$wheel" | sed -E 's/^lastread-([^-]+)-.*$/\1/')
short=$(printf '%s' "$version" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*$/\1/')
printf '%s' "$short" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || {
	echo "build.sh: cannot read a version from $wheel" >&2
	exit 1
}

sha256() { if command -v shasum >/dev/null; then shasum -a 256 "$1"; else sha256sum "$1"; fi | cut -d' ' -f1; }

fetch() { # file sha256: into the cache, checked, every time
	if [ ! -f "$out/cache/$1" ] || [ "$(sha256 "$out/cache/$1")" != "$2" ]; then
		curl -fsSL --retry 3 -o "$out/cache/$1.part" "$RELEASE/$(printf '%s' "$1" | sed 's/+/%2B/g')"
		mv "$out/cache/$1.part" "$out/cache/$1"
	fi
	got=$(sha256 "$out/cache/$1")
	[ "$got" = "$2" ] || {
		echo "build.sh: $1 has SHA-256 $got, expected $2" >&2
		exit 1
	}
}

app="$out/$NAME.app"
contents="$app/Contents"
resources="$contents/Resources"
rm -rf "$app"
mkdir -p "$contents/MacOS" "$contents/Library/LaunchAgents" "$resources"

# ---------- Python, and the tool in it ----------
small=cpython-$PYTHON+$PYTHON_BUILD-$TRIPLE-install_only_stripped.tar.gz
fetch "$small" "$PYTHON_SHA256"
tar -xzf "$out/cache/$small" -C "$resources"
py="$resources/python/bin/python3"
lib="$resources/python/lib/python${PYTHON%.*}"

# The packages uv.lock pins, with their hashes, as wheels only; then the tool.
(cd "$root" && uv export --frozen --no-dev --no-emit-project --format requirements-txt) >"$out/requirements.txt"
uv pip install --python "$py" --no-deps --require-hashes --only-binary :all: -r "$out/requirements.txt"
uv pip install --python "$py" --no-deps "$wheel"

# What the tool never uses: a package installer, the GUI toolkit, the tests
# of Python itself, scripts that point at the build machine.
rm -rf "$lib"/site-packages/pip "$lib"/site-packages/pip-*.dist-info \
	"$lib"/test "$lib"/idlelib "$lib"/tkinter "$lib"/turtledemo "$lib"/ensurepip \
	"$lib"/lib-dynload/_tkinter* "$resources"/python/lib/libtcl* "$resources"/python/lib/libtk* \
	"$resources"/python/lib/tcl* "$resources"/python/lib/tk* "$resources"/python/lib/itcl* \
	"$resources"/python/lib/thread* "$resources"/python/include "$resources"/python/share
find "$resources/python/bin" ! -type d ! -name python3 ! -name "python${PYTHON%.*}" -exec rm -f {} +

# Bytecode for everything, now: nothing is written into the bundle while
# it runs. Unchecked hashes, because a copied file's time means nothing.
"$py" -I -m compileall -q -f -j 0 --invalidation-mode unchecked-hash "$resources/python/lib" >/dev/null
"$py" -I -B -c "import lastread.cli, lastread.web.app, cryptography.fernet, yaml" # it is all there

# Licences: this tool's, Python's, and those of what Python is built with.
cp "$root/LICENSE" "$root/THIRD-PARTY-NOTICES.md" "$resources/"
cp "$lib/LICENSE.txt" "$resources/PYTHON-LICENSE.txt"
if [ -n "${KHS_PYTHON_ONLY:-}" ]; then
	echo "$NAME.app, the Python half only: $app"
	exit 0
fi
full=cpython-$PYTHON+$PYTHON_BUILD-$TRIPLE-pgo+lto-full.tar.zst
fetch "$full" "$FULL_SHA256"
mkdir -p "$out/full"
zstd -dc "$out/cache/$full" | tar -x -C "$out/full" python/licenses
[ -n "$(ls "$out/full/python/licenses")" ] || {
	echo "build.sh: no licence texts in $full" >&2
	exit 1
}
rm -rf "$resources/python-licenses"
cp -R "$out/full/python/licenses" "$resources/python-licenses"

# ---------- the wrapper, its agent and its icon ----------
swiftc -O -swift-version 5 -target arm64-apple-macos13.0 -parse-as-library -o "$contents/MacOS/$NAME" \
	"$here/Lastread.swift" "$here/Window.swift" "$here/Setup.swift" "$here/Paper.swift" "$here/Chain.swift" "$here/Books.swift" "$here/Covers.swift" \
	"$here/Shelf.swift" "$here/Spotlight.swift" "$here/Hardcover.swift" "$here/Settings.swift" "$here/Model.swift" "$here/Update.swift" "$here/Help.swift"
sed "s/__VERSION__/$short/g" "$here/Info.plist" >"$contents/Info.plist"
if [ -n "${KHS_PREVIEW:-}" ]; then
	plutil -replace CFBundleIdentifier -string org.gargleblaster.kobo-hardcover-sync.app.preview "$contents/Info.plist"
	plutil -replace CFBundleDisplayName -string "$NAME Preview" "$contents/Info.plist"
	plutil -replace CFBundleName -string "$NAME Preview" "$contents/Info.plist"
	plutil -insert KHSPreview -bool YES "$contents/Info.plist"
fi
plutil -lint "$contents/Info.plist" >/dev/null

# The widget (ShelfWidget.swift), from macOS 14. An extension starts at
# _NSExtensionMain, as Xcode links it: from Swift's own main it traps in
# ExtensionFoundation before the widget can say what it is. macOS only
# shows a widget signed with a Developer ID (sign.sh): signed ad hoc, as
# here, it is in the app but never in the widget gallery.
widget="$contents/PlugIns/Widget.appex/Contents"
mkdir -p "$widget/MacOS" "$widget/Resources/fonts"
swiftc -O -swift-version 5 -target arm64-apple-macos14.0 -parse-as-library -application-extension \
	-Xlinker -e -Xlinker _NSExtensionMain -o "$widget/MacOS/Widget" \
	"$here/ShelfWidget.swift" "$here/Shelf.swift" "$here/Paper.swift" "$here/Model.swift"
sed "s/__VERSION__/$short/g" "$here/Widget-Info.plist" >"$widget/Info.plist"
if [ -n "${KHS_PREVIEW:-}" ]; then
	plutil -replace CFBundleIdentifier -string org.gargleblaster.kobo-hardcover-sync.app.preview.widget "$widget/Info.plist"
	plutil -replace CFBundleDisplayName -string "$NAME Preview" "$widget/Info.plist"
fi
plutil -lint "$widget/Info.plist" >/dev/null
cp "$lib/site-packages/lastread/web/static/fonts/SourceSerif4-latin.woff2" \
	"$lib/site-packages/lastread/web/static/fonts/SourceSerif4-latin-ext.woff2" \
	"$lib/site-packages/lastread/web/static/fonts/SourceSerif4-LICENSE.txt" "$widget/Resources/fonts/"
cp "$here/org.gargleblaster.kobo-hardcover-sync.app.agent.plist" "$contents/Library/LaunchAgents/"
iconset="$out/AppIcon.iconset"
rm -rf "$iconset"
mkdir "$iconset"
for size in 16 32 128 256 512; do
	sips -z $size $size "$here/AppIcon.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
	sips -z $((size * 2)) $((size * 2)) "$here/AppIcon.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
# 16 and 32 pixels are drawn for their size (art.py), not made smaller.
cp "$here/AppIcon-16.png" "$iconset/icon_16x16.png"
cp "$here/AppIcon-32.png" "$iconset/icon_16x16@2x.png"
cp "$here/AppIcon-32.png" "$iconset/icon_32x32.png"
iconutil -c icns -o "$resources/AppIcon.icns" "$iconset"
# From macOS 26 on the icon is AppIcon.icon, compiled into Assets.car; without it the
# system shrinks the one above into a grey tile. Only actool from Xcode 26 on reads that
# format: the selected Xcode's, or else the newest installed. (Its own AppIcon.icns, at
# most 256 pixels, is left out for the one above.)
car="$out/car"
: >"$out/actool.log"
for xcode in "" $(ls -d /Applications/Xcode*.app 2>/dev/null | sort -rV); do
	rm -rf "$car"
	mkdir "$car"
	echo "== actool of ${xcode:-the selected Xcode}:" >>"$out/actool.log"
	if env ${xcode:+DEVELOPER_DIR="$xcode/Contents/Developer"} xcrun actool "$here/AppIcon.icon" --compile "$car" \
		--platform macosx --minimum-deployment-target 13.0 --app-icon AppIcon \
		--output-partial-info-plist "$car/partial.plist" >>"$out/actool.log" 2>&1 && grep -q CFBundleIconName "$car/partial.plist"; then
		cp "$car/Assets.car" "$resources/"
		break
	fi
done
[ -s "$resources/Assets.car" ] || {
	cat "$out/actool.log" >&2
	echo "build.sh: no actool here compiles AppIcon.icon; it needs Xcode 26 or later" >&2
	exit 1
}

"$here/sign.sh" - "$app"
echo "$NAME.app $version: $app"
