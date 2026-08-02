#!/bin/sh
# Ставит terkb в меню приложений текущего пользователя.
# Ничего не трогает вне ~/.local — удаляется через ./install.sh --uninstall
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
# Имя файла ярлыка совпадает с app_id окна: под Wayland оболочка связывает
# окно с ярлыком именно по нему, иначе окно остаётся без имени и без иконки,
# а значок в доке — пустым.
APP_ID="org.terkb.Terminal"
DESKTOP="$APPS/$APP_ID.desktop"
# Иконка ставится в пользовательскую тему hicolor: оттуда её берут и меню, и
# панель задач, и переключатель окон.
ICONS="$HOME/.local/share/icons/hicolor"
# Раньше ярлык и иконка звались просто terkb — подчищаем за прежними версиями.
OLD_DESKTOP="$APPS/terkb.desktop"

remove_icons() {
    for name in "$APP_ID" terkb; do
        rm -f "$ICONS/scalable/apps/$name.svg"
        for size in 16 24 32 48 64 128 256; do
            rm -f "$ICONS/${size}x${size}/apps/$name.png"
        done
    done
}

if [ "$1" = "--uninstall" ]; then
    rm -f "$DESKTOP" "$OLD_DESKTOP"
    remove_icons
    update-desktop-database "$APPS" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true
    echo "Удалено: $DESKTOP и иконки"
    exit 0
fi

chmod +x "$SRC/terkb-run"
mkdir -p "$APPS"
rm -f "$OLD_DESKTOP"

# Векторная иконка — основная; PNG кладутся рядом, если они собраны
# (make-icons.py): не в каждой системе стоит SVG-загрузчик gdk-pixbuf, и без
# растровых копий иконка молча не покажется. Имён два: по app_id её ищет
# оболочка, коротким пользуются меню и запуск из исходников.
mkdir -p "$ICONS/scalable/apps"
for name in "$APP_ID" terkb; do
    cp "$SRC/icons/terkb.svg" "$ICONS/scalable/apps/$name.svg"
done
for png in "$SRC"/icons/terkb-*.png; do
    [ -e "$png" ] || continue
    size="${png##*terkb-}"
    size="${size%.png}"
    mkdir -p "$ICONS/${size}x${size}/apps"
    for name in "$APP_ID" terkb; do
        cp "$png" "$ICONS/${size}x${size}/apps/$name.png"
    done
done
gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

sed "s|^Exec=.*|Exec=$SRC/terkb-run|" "$SRC/$APP_ID.desktop" > "$DESKTOP"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Установлено: $DESKTOP"
echo "Иконки: $ICONS"
echo "Запуск: $SRC/terkb-run  (или «terkb» в меню приложений)"
