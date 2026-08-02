#!/bin/sh
# Ставит terkb в меню приложений текущего пользователя.
# Ничего не трогает вне ~/.local — удаляется через ./install.sh --uninstall
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
DESKTOP="$APPS/terkb.desktop"
# Иконка ставится в пользовательскую тему hicolor: оттуда её берут и меню, и
# панель задач, и переключатель окон.
ICONS="$HOME/.local/share/icons/hicolor"

if [ "$1" = "--uninstall" ]; then
    rm -f "$DESKTOP"
    rm -f "$ICONS/scalable/apps/terkb.svg"
    for size in 16 24 32 48 64 128 256; do
        rm -f "$ICONS/${size}x${size}/apps/terkb.png"
    done
    update-desktop-database "$APPS" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true
    echo "Удалено: $DESKTOP и иконки"
    exit 0
fi

chmod +x "$SRC/terkb-run"
mkdir -p "$APPS"

# Векторная иконка — основная; PNG кладутся рядом, если они собраны
# (make-icons.py): не в каждой системе стоит SVG-загрузчик gdk-pixbuf, и без
# растровых копий иконка молча не покажется.
mkdir -p "$ICONS/scalable/apps"
cp "$SRC/icons/terkb.svg" "$ICONS/scalable/apps/terkb.svg"
for png in "$SRC"/icons/terkb-*.png; do
    [ -e "$png" ] || continue
    size="${png##*terkb-}"
    size="${size%.png}"
    mkdir -p "$ICONS/${size}x${size}/apps"
    cp "$png" "$ICONS/${size}x${size}/apps/terkb.png"
done
gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

sed "s|^Exec=.*|Exec=$SRC/terkb-run|" "$SRC/terkb.desktop" > "$DESKTOP"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Установлено: $DESKTOP"
echo "Иконки: $ICONS"
echo "Запуск: $SRC/terkb-run  (или «terkb» в меню приложений)"
