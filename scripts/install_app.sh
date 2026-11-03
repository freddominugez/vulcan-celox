#!/bin/bash
# Instala o bundle em ~/Applications e cria o atalho na Mesa. Sem sudo.
# VULCAN_INSTALL_DEST e VULCAN_DESKTOP permitem instalar em diretórios de teste.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SRC="dist/Vulcan Celox.app"
DEST_DIR="${VULCAN_INSTALL_DEST:-$HOME/Applications}"
DESKTOP="${VULCAN_DESKTOP:-$HOME/Desktop}"
DEST="$DEST_DIR/Vulcan Celox.app"
LINK="$DESKTOP/Vulcan Celox"

[ -d "$SRC" ] || bash scripts/build_app.sh
mkdir -p "$DEST_DIR" "$DESKTOP"

# versão anterior vai para a Lixeira (recuperável), nunca é apagada em definitivo
to_trash() {
  if [ -n "${VULCAN_NO_FINDER:-}" ] || ! /usr/bin/osascript -e "tell application \"Finder\" to delete POSIX file \"$1\"" >/dev/null 2>&1; then
    BACKUP="${1%.app} (anterior $(date +%Y%m%d-%H%M%S)).app"
    mv "$1" "$BACKUP"
    echo "aviso: Finder indisponível; versão anterior guardada em $BACKUP"
  fi
}

if [ -e "$DEST" ]; then to_trash "$DEST"; fi

# o app se chamava Vulcan Terminal: o bundle antigo sai de cena; dados, Keychain e preferências ficam onde estavam
OLD_APP="$DEST_DIR/Vulcan Terminal.app"
OLD_LINK="$DESKTOP/Vulcan Terminal"
if [ -e "$OLD_APP" ]; then
  to_trash "$OLD_APP"
  echo "aviso: o app com o nome antigo (Vulcan Terminal) saiu de $DEST_DIR. Seus dados continuam no mesmo lugar."
fi
if [ -L "$OLD_LINK" ]; then unlink "$OLD_LINK"; fi

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
