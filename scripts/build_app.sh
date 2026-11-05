#!/bin/bash
# Builds dist/Vulcan Celox.app from source (no external dependencies).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
APP="dist/Vulcan Celox.app"
VERSION="$(/usr/bin/python3 -c 'import vulcan_celox as v; print(v.__version__)')"

if [ -d "$APP" ]; then
  # dist/ is our own build artifact and ignored by git; recreated on every build
  find "$APP" -depth -delete
fi
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
touch dist/.metadata_never_index  # the build copy does not show up in Spotlight or Launchpad

rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' vulcan_celox "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>
	<string>Vulcan Celox</string>
	<key>CFBundleDisplayName</key>
	<string>Vulcan Celox</string>
	<key>CFBundleIdentifier</key>
	<string>com.byvulcan.celox</string>
	<key>CFBundleVersion</key>
	<string>${VERSION}</string>
	<key>CFBundleShortVersionString</key>
	<string>${VERSION}</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleExecutable</key>
	<string>vulcan-celox</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>LSMinimumSystemVersion</key>
	<string>13.0</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>LSApplicationCategoryType</key>
	<string>public.app-category.developer-tools</string>
	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsLocalNetworking</key>
		<true/>
	</dict>
</dict>
</plist>
PLIST

# native executable (AppKit + WKWebView) that starts the embedded Python server
ARCH="$(uname -m)"
if [ "${VULCAN_UNIVERSAL:-0}" = "1" ]; then
  # universal binary (Apple Silicon + Intel) for distribution
  UNI_TMP="$(mktemp -d)"
  for arch in arm64 x86_64; do
    swiftc -O -target "${arch}-apple-macos13.0" -o "$UNI_TMP/vulcan-celox-$arch" packaging/macos/main.swift packaging/macos/notify.swift packaging/macos/pick_panel.swift \
      -framework AppKit -framework WebKit -framework Security
  done
  lipo -create -output "$APP/Contents/MacOS/vulcan-celox" "$UNI_TMP/vulcan-celox-arm64" "$UNI_TMP/vulcan-celox-x86_64"
  find "$UNI_TMP" -depth -delete
else
  swiftc -O -target "${ARCH}-apple-macos13.0" \
    -o "$APP/Contents/MacOS/vulcan-celox" packaging/macos/main.swift packaging/macos/notify.swift packaging/macos/pick_panel.swift \
    -framework AppKit -framework WebKit -framework Security
fi

# approved brand icon, without the 16 and 32 px sizes: macOS downsamples from the larger ones
cp packaging/macos/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

echo "build: $ROOT/$APP ($VERSION)"
