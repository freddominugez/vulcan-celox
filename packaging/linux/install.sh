#!/bin/sh
# Installs Vulcan Celox for the current user, without sudo (default ~/.local). PREFIX=/other/place changes the destination.
#   sh install.sh                    installs and asks before installing any missing libraries
#   sh install.sh -y                 installs and authorizes installing the libraries
#   sh install.sh --skip-deps        only copies the program
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
DEST="$PREFIX/opt/vulcan-celox"
DEPS_MODE=""
for arg in "$@"; do
  case "$arg" in
    -y|--sim|--yes) DEPS_MODE="-y" ;;
    --sem-dependencias|--skip-deps) DEPS_MODE="skip" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -d "$DEST" ]; then
  # previous version kept alongside; uninstall.sh or the user decides to delete it
  OLD="$DEST.anterior"
  [ -e "$OLD" ] && mv "$OLD" "$OLD.$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$OLD"
fi
mkdir -p "$DEST" "$PREFIX/bin" "$PREFIX/share/applications"
cp -R "$HERE/bin" "$HERE/lib" "$DEST/"
chmod +x "$DEST/bin/vulcan-celox"
ln -sf "$DEST/bin/vulcan-celox" "$PREFIX/bin/vulcan-celox"

sed "s|@EXEC@|$PREFIX/bin/vulcan-celox|" "$HERE/share/applications/vulcan-celox.desktop" \
  > "$PREFIX/share/applications/vulcan-celox.desktop"
mkdir -p "$PREFIX/share/icons"
cp -R "$HERE/share/icons/hicolor" "$PREFIX/share/icons/"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "Vulcan Celox installed at $DEST"
echo "Open it from the applications menu or run: $PREFIX/bin/vulcan-celox"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Tip: add $PREFIX/bin to your PATH." ;; esac

if [ "$DEPS_MODE" = "skip" ]; then
  echo "Libraries not checked. Later, run: vulcan-celox --install-deps"
else
  echo
  # shellcheck disable=SC2086
  sh "$DEST/bin/vulcan-celox-deps" $DEPS_MODE || echo "Whenever you want: $PREFIX/bin/vulcan-celox --install-deps"
fi
