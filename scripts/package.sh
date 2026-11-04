#!/bin/bash
# Builds the distribution packages in executaveis/: macOS (.dmg and .zip, universal binary) and Linux (.tar.gz and .deb).
# Runs on macOS (needs swiftc, lipo, codesign, hdiutil). The generated packages stay out of git.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(/usr/bin/python3 -c 'import vulcan_celox as v; print(v.__version__)')"
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
APP="dist/Vulcan Celox.app"
lipo -archs "$APP/Contents/MacOS/vulcan-celox"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

MAC_BASE="Vulcan-Celox-$VERSION-macos"
step "macOS: $MAC_BASE.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/macos/$MAC_BASE.zip"

step "macOS: $MAC_BASE.dmg"
DMG_DIR="$WORK/dmg"
mkdir -p "$DMG_DIR"
ditto "$APP" "$DMG_DIR/Vulcan Celox.app"
ln -s /Applications "$DMG_DIR/Aplicativos"
cp packaging/LEIA-ME.md "$DMG_DIR/LEIA-ME.md"
hdiutil create -quiet -volname "Vulcan Celox $VERSION" -srcfolder "$DMG_DIR" -ov -format UDZO "$OUT/macos/$MAC_BASE.dmg"
hdiutil verify -quiet "$OUT/macos/$MAC_BASE.dmg"

# ── Linux ─────────────────────────────────────────────────────────────────
LNX="vulcan-celox-$VERSION"
STAGE="$WORK/linux/$LNX"
step "Linux: árvore do pacote"
mkdir -p "$STAGE/bin" "$STAGE/lib" "$STAGE/share/applications"
cp packaging/linux/vulcan-celox packaging/linux/vulcan-celox-deps "$STAGE/bin/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' --exclude 'ui/' vulcan_celox "$STAGE/lib/"
cp packaging/linux/vulcan-celox.desktop "$STAGE/share/applications/"
mkdir -p "$STAGE/share/icons"
cp -R packaging/linux/icons/hicolor "$STAGE/share/icons/"
cp packaging/linux/install.sh packaging/linux/uninstall.sh "$STAGE/"
cp packaging/LEIA-ME.md "$STAGE/LEIA-ME.md"
chmod +x "$STAGE/bin/vulcan-celox" "$STAGE/bin/vulcan-celox-deps" "$STAGE/install.sh" "$STAGE/uninstall.sh"

step "Linux: $LNX-linux.tar.gz"
COPYFILE_DISABLE=1 tar --no-mac-metadata -czf "$OUT/linux/$LNX-linux.tar.gz" -C "$WORK/linux" "$LNX"

step "Linux: vulcan-celox_${VERSION}_all.deb"
DEB="$WORK/deb"
mkdir -p "$DEB/opt/vulcan-celox" "$DEB/usr/bin" "$DEB/usr/share/applications" "$DEB/usr/share/icons"
cp -R "$STAGE/bin" "$STAGE/lib" "$DEB/opt/vulcan-celox/"
ln -s /opt/vulcan-celox/bin/vulcan-celox "$DEB/usr/bin/vulcan-celox"
sed "s|@EXEC@|/usr/bin/vulcan-celox|" packaging/linux/vulcan-celox.desktop > "$DEB/usr/share/applications/vulcan-celox.desktop"
cp -R "$STAGE/share/icons/hicolor" "$DEB/usr/share/icons/"
sed "s|@VERSION@|$VERSION|" packaging/linux/deb/control > "$WORK/control"
/usr/bin/python3 scripts/make_deb.py "$DEB" "$WORK/control" packaging/linux/deb/postinst "$OUT/linux/vulcan-celox_${VERSION}_all.deb"

# ── checksums ─────────────────────────────────────────────────────────────
step "SHA256SUMS"
(cd "$OUT" && shasum -a 256 macos/*.dmg macos/*.zip linux/*.tar.gz linux/*.deb > SHA256SUMS)
cat "$OUT/SHA256SUMS"
ls -lh "$OUT/macos" "$OUT/linux"
echo "PACOTES OK"

# the build copy is not registered with macOS: it would become one more icon in Launchpad
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREGISTER" ] && "$LSREGISTER" -u "$ROOT/dist/Vulcan Celox.app" >/dev/null 2>&1 || true
