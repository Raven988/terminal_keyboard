#!/bin/sh
# Ставит terkb в меню приложений текущего пользователя.
# Ничего не трогает вне ~/.local — удаляется через ./install.sh --uninstall
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
DESKTOP="$APPS/terkb.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$DESKTOP"
    update-desktop-database "$APPS" 2>/dev/null || true
    echo "Удалено: $DESKTOP"
    exit 0
fi

chmod +x "$SRC/terkb-run"
mkdir -p "$APPS"
sed "s|^Exec=.*|Exec=$SRC/terkb-run|" "$SRC/terkb.desktop" > "$DESKTOP"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Установлено: $DESKTOP"
echo "Запуск: $SRC/terkb-run  (или «terkb» в меню приложений)"
