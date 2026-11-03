#!/bin/sh
# Instala o Vulcan Celox para o usuário atual, sem sudo (padrão ~/.local). PREFIX=/outro/lugar muda o destino.
#   sh install.sh                    instala e pergunta antes de instalar as bibliotecas que faltarem
#   sh install.sh -y                 instala e autoriza a instalação das bibliotecas
#   sh install.sh --sem-dependencias só copia o programa
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
DEST="$PREFIX/opt/vulcan-celox"
DEPS_MODE=""
for arg in "$@"; do
  case "$arg" in
    -y|--sim) DEPS_MODE="-y" ;;
    --sem-dependencias) DEPS_MODE="skip" ;;
    *) echo "opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done

if [ -d "$DEST" ]; then
  # versão anterior guardada ao lado; o uninstall.sh ou o usuário decide apagar
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

echo "Vulcan Celox instalado em $DEST"
echo "Abra pelo menu de aplicativos ou rode: $PREFIX/bin/vulcan-celox"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Dica: adicione $PREFIX/bin ao PATH." ;; esac

if [ "$DEPS_MODE" = "skip" ]; then
  echo "Bibliotecas não verificadas. Depois rode: vulcan-celox --instalar-dependencias"
else
  echo
  # shellcheck disable=SC2086
  sh "$DEST/bin/vulcan-celox-deps" $DEPS_MODE || echo "Quando quiser: $PREFIX/bin/vulcan-celox --instalar-dependencias"
fi
