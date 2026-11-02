#!/bin/bash
# Gera dist/Vulcan Terminal.app a partir do fonte (sem dependências externas).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
APP="dist/Vulcan Terminal.app"
VERSION="$(/usr/bin/python3 -c 'import vulcan_terminal as v; print(v.__version__)')"

if [ -d "$APP" ]; then
  # dist/ é artefato de build nosso e ignorado pelo git; recriado a cada build
  find "$APP" -depth -delete
fi
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' vulcan_terminal "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>
	<string>Vulcan Terminal</string>
	<key>CFBundleDisplayName</key>
	<string>Vulcan Terminal</string>
	<key>CFBundleIdentifier</key>
	<string>com.byvulcan.terminal</string>
	<key>CFBundleVersion</key>
	<string>${VERSION}</string>
	<key>CFBundleShortVersionString</key>
	<string>${VERSION}</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleExecutable</key>
	<string>vulcan-terminal</string>
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

# executável nativo (AppKit + WKWebView) que sobe o servidor Python embutido
ARCH="$(uname -m)"
if [ "${VULCAN_UNIVERSAL:-0}" = "1" ]; then
  # binário universal (Apple Silicon + Intel) para distribuição
  UNI_TMP="$(mktemp -d)"
  for arch in arm64 x86_64; do
    swiftc -O -target "${arch}-apple-macos13.0" -o "$UNI_TMP/vulcan-terminal-$arch" packaging/macos/main.swift \
      -framework AppKit -framework WebKit -framework Security
  done
  lipo -create -output "$APP/Contents/MacOS/vulcan-terminal" "$UNI_TMP/vulcan-terminal-arm64" "$UNI_TMP/vulcan-terminal-x86_64"
  find "$UNI_TMP" -depth -delete
else
  swiftc -O -target "${ARCH}-apple-macos13.0" \
    -o "$APP/Contents/MacOS/vulcan-terminal" packaging/macos/main.swift \
    -framework AppKit -framework WebKit -framework Security
fi

# ícone desenhado em código (packaging/macos/icon.swift), sem ativos binários no repositório
ICON_TMP="$(mktemp -d)"
swiftc -O -target "${ARCH}-apple-macos13.0" -o "$ICON_TMP/icon" packaging/macos/icon.swift -framework AppKit
"$ICON_TMP/icon" "$ICON_TMP/AppIcon.iconset" >/dev/null
iconutil -c icns "$ICON_TMP/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
# PNGs do ícone ficam em build/ para o pacote Linux
mkdir -p build/icon
cp "$ICON_TMP/AppIcon.iconset/"*.png build/icon/
find "$ICON_TMP" -depth -delete

echo "build: $ROOT/$APP ($VERSION)"
