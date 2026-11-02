#!/bin/bash
# Gera os pacotes de distribuição em executaveis/: macOS (.dmg e .zip, binário universal) e Linux (.tar.gz e .deb).
# Roda no macOS (precisa de swiftc, lipo, codesign, hdiutil). Os pacotes gerados ficam fora do git.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(/usr/bin/python3 -c 'import vulcan_terminal as v; print(v.__version__)')"
OUT="$ROOT/executaveis"
WORK="$(mktemp -d)"
trap 'find "$WORK" -depth -delete 2>/dev/null || true' EXIT

step() { printf '\n==> %s\n' "$*"; }
mkdir -p "$OUT/macos" "$OUT/linux"
find "$OUT/macos" "$OUT/linux" -type f \( -name '*.dmg' -o -name '*.zip' -o -name '*.tar.gz' -o -name '*.deb' \) -delete
rm -f "$OUT/SHA256SUMS"

# ── macOS ─────────────────────────────────────────────────────────────────
step "macOS: app universal (arm64 + x86_64)"
VULCAN_UNIVERSAL=1 bash scripts/build_app.sh
APP="dist/Vulcan Terminal.app"
lipo -archs "$APP/Contents/MacOS/vulcan-terminal"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

MAC_BASE="Vulcan-Terminal-$VERSION-macos"
step "macOS: $MAC_BASE.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/macos/$MAC_BASE.zip"

step "macOS: $MAC_BASE.dmg"
DMG_DIR="$WORK/dmg"
mkdir -p "$DMG_DIR"
ditto "$APP" "$DMG_DIR/Vulcan Terminal.app"
ln -s /Applications "$DMG_DIR/Aplicativos"
cp packaging/LEIA-ME.md "$DMG_DIR/LEIA-ME.md"
hdiutil create -quiet -volname "Vulcan Terminal $VERSION" -srcfolder "$DMG_DIR" -ov -format UDZO "$OUT/macos/$MAC_BASE.dmg"
hdiutil verify -quiet "$OUT/macos/$MAC_BASE.dmg"

# ── Linux ─────────────────────────────────────────────────────────────────
LNX="vulcan-terminal-$VERSION"
STAGE="$WORK/linux/$LNX"
step "Linux: árvore do pacote"
mkdir -p "$STAGE/bin" "$STAGE/lib" "$STAGE/share/applications"
cp packaging/linux/vulcan-terminal packaging/linux/vulcan-terminal-deps "$STAGE/bin/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' --exclude 'ui/' vulcan_terminal "$STAGE/lib/"
cp packaging/linux/vulcan-terminal.desktop "$STAGE/share/applications/"
for pair in 16:icon_16x16 32:icon_32x32 64:icon_32x32@2x 128:icon_128x128 256:icon_256x256 512:icon_512x512; do
  size="${pair%%:*}"; src="${pair#*:}"
  mkdir -p "$STAGE/share/icons/hicolor/${size}x${size}/apps"
  cp "build/icon/$src.png" "$STAGE/share/icons/hicolor/${size}x${size}/apps/vulcan-terminal.png"
done
mkdir -p "$STAGE/share/icons/hicolor/48x48/apps"
sips -z 48 48 "build/icon/icon_32x32@2x.png" --out "$STAGE/share/icons/hicolor/48x48/apps/vulcan-terminal.png" >/dev/null
cp packaging/linux/install.sh packaging/linux/uninstall.sh "$STAGE/"
cp packaging/LEIA-ME.md "$STAGE/LEIA-ME.md"
chmod +x "$STAGE/bin/vulcan-terminal" "$STAGE/bin/vulcan-terminal-deps" "$STAGE/install.sh" "$STAGE/uninstall.sh"

step "Linux: $LNX-linux.tar.gz"
COPYFILE_DISABLE=1 tar --no-mac-metadata -czf "$OUT/linux/$LNX-linux.tar.gz" -C "$WORK/linux" "$LNX"

step "Linux: vulcan-terminal_${VERSION}_all.deb"
DEB="$WORK/deb"
mkdir -p "$DEB/opt/vulcan-terminal" "$DEB/usr/bin" "$DEB/usr/share/applications" "$DEB/usr/share/icons"
cp -R "$STAGE/bin" "$STAGE/lib" "$DEB/opt/vulcan-terminal/"
ln -s /opt/vulcan-terminal/bin/vulcan-terminal "$DEB/usr/bin/vulcan-terminal"
sed "s|@EXEC@|/usr/bin/vulcan-terminal|" packaging/linux/vulcan-terminal.desktop > "$DEB/usr/share/applications/vulcan-terminal.desktop"
cp -R "$STAGE/share/icons/hicolor" "$DEB/usr/share/icons/"
sed "s|@VERSION@|$VERSION|" packaging/linux/deb/control > "$WORK/control"
/usr/bin/python3 scripts/make_deb.py "$DEB" "$WORK/control" packaging/linux/deb/postinst "$OUT/linux/vulcan-terminal_${VERSION}_all.deb"

# ── somas ─────────────────────────────────────────────────────────────────
step "SHA256SUMS"
(cd "$OUT" && shasum -a 256 macos/*.dmg macos/*.zip linux/*.tar.gz linux/*.deb > SHA256SUMS)
cat "$OUT/SHA256SUMS"
ls -lh "$OUT/macos" "$OUT/linux"
echo "PACOTES OK"
