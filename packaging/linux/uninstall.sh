#!/bin/sh
# Removes the program installed by install.sh. The data (tasks, sticky notes, memories) in
# ~/.local/share/vulcan-celox is NOT touched. The program folder goes to the Trash when possible.
set -e
PREFIX="${PREFIX:-$HOME/.local}"
DEST="$PREFIX/opt/vulcan-celox"

rm -f "$PREFIX/bin/vulcan-celox" "$PREFIX/share/applications/vulcan-celox.desktop"
for size in 16 32 48 64 128 256 512; do
  rm -f "$PREFIX/share/icons/hicolor/${size}x${size}/apps/vulcan-celox.png"
done
for dir in "$DEST" "$DEST.anterior"; do
  [ -d "$dir" ] || continue
  if command -v gio >/dev/null 2>&1 && gio trash "$dir" 2>/dev/null; then
    echo "Moved to the Trash: $dir"
  else
    echo "Delete the program folder manually (it does not contain your data): $dir"
  fi
done
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
echo "Vulcan Celox removed. Your data is still in ${XDG_DATA_HOME:-$HOME/.local/share}/vulcan-celox"
