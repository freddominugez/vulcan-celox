#!/bin/sh
# Remove o programa instalado pelo install.sh. Os dados (tarefas, post-its, memórias) em
# ~/.local/share/vulcan-celox NÃO são tocados. A pasta do programa vai para a Lixeira quando possível.
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
    echo "Movido para a Lixeira: $dir"
  else
    echo "Apague manualmente a pasta do programa (não contém seus dados): $dir"
  fi
done
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
echo "Vulcan Celox removido. Seus dados continuam em ${XDG_DATA_HOME:-$HOME/.local/share}/vulcan-celox"
