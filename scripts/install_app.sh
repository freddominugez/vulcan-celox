#!/bin/bash
# Instala o bundle em ~/Applications e cria o atalho na Mesa. Sem sudo.
# VULCAN_INSTALL_DEST e VULCAN_DESKTOP permitem instalar em diretórios de teste.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SRC="dist/Vulcan Terminal.app"
DEST_DIR="${VULCAN_INSTALL_DEST:-$HOME/Applications}"
DESKTOP="${VULCAN_DESKTOP:-$HOME/Desktop}"
DEST="$DEST_DIR/Vulcan Terminal.app"
LINK="$DESKTOP/Vulcan Terminal"

[ -d "$SRC" ] || bash scripts/build_app.sh
mkdir -p "$DEST_DIR" "$DESKTOP"

if [ -e "$DEST" ]; then
  # versão anterior vai para a Lixeira (recuperável), nunca é apagada em definitivo
  if ! /usr/bin/osascript -e "tell application \"Finder\" to delete POSIX file \"$DEST\"" >/dev/null 2>&1; then
    BACKUP="$DEST_DIR/Vulcan Terminal (anterior $(date +%Y%m%d-%H%M%S)).app"
    mv "$DEST" "$BACKUP"
    echo "aviso: Finder indisponível; versão anterior guardada em $BACKUP"
  fi
fi
/usr/bin/ditto "$SRC" "$DEST"

if [ -L "$LINK" ]; then
  unlink "$LINK"
elif [ -e "$LINK" ]; then
  echo "erro: $LINK já existe e não é um atalho; nada foi alterado na Mesa" >&2
  exit 1
fi
ln -s "$DEST" "$LINK"

LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$DEST" >/dev/null 2>&1 || true

echo "instalado: $DEST"
echo "atalho:    $LINK"
