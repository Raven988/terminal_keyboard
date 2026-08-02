"""Точка входа: приложение GTK и разбор командной строки."""

import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .config import LAYOUT_FILE
from .geometry import HANDLE_GUARD
from .layouts import dump_layouts
from .styles import CSS, GUARD_CSS
from .window import Window

APP_ID = "org.terkb.Terminal"

# Иконка: имя в теме — когда приложение установлено, файлы рядом с пакетом —
# когда его запускают прямо из каталога с исходниками.
# Установленная иконка зовётся по app_id — так её ищет оболочка; короткое имя
# остаётся запасным, им пользуются меню и прежние версии.
ICON_NAME = APP_ID
ICON_NAME_SHORT = "terkb"
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "icons")


def set_app_icon():
    """Своя иконка окна. Установленную берём из темы: так её подхватят и
    панель задач, и переключатель окон. Из исходников — прямо из файла, причём
    сначала растровые копии: SVG-загрузчик gdk-pixbuf стоит не везде."""
    theme = Gtk.IconTheme.get_default()
    for name in (ICON_NAME, ICON_NAME_SHORT):
        if theme.has_icon(name):
            Gtk.Window.set_default_icon_name(name)
            return True
    for name in ("terkb-128.png", "terkb-64.png", "terkb.svg"):
        path = os.path.join(ICON_DIR, name)
        if not os.path.exists(path):
            continue
        try:
            Gtk.Window.set_default_icon_from_file(path)
            return True
        except GLib.Error:
            continue          # формат не читается этой сборкой gdk-pixbuf
    return False


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        set_app_icon()
        provider = Gtk.CssProvider()
        provider.load_from_data(
            (CSS + GUARD_CSS % {"g": HANDLE_GUARD}).encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = Window(self)
        win.show_all()


USAGE = """terkb — терминал со сплит-клавиатурой для планшета

  terkb                 запустить
  terkb --dump-layout   записать встроенные раскладки в %s
                        и выйти: дальше файл правится руками
  terkb --help          эта справка
""" % LAYOUT_FILE


def set_app_id():
    """Назваться так же, как называется файл ярлыка.

    Под Wayland оболочка связывает окно с ярлыком по app_id, а GTK берёт его
    из имени программы — то есть «python3», раз запуск идёт через
    «python3 -m terkb». Из-за этого GNOME не находил org.terkb.Terminal.desktop
    и показывал окно без имени и с чужой иконкой, а значок в доке оставался
    пустым. Под X11 за то же отвечает WM_CLASS.
    """
    GLib.set_prgname(APP_ID)
    Gdk.set_program_class(APP_ID)


def main(argv):
    set_app_id()
    if len(argv) > 1:
        if argv[1] in ("-h", "--help"):
            print(USAGE)
            return 0
        if argv[1] == "--dump-layout":
            try:
                print("terkb: раскладки записаны в %s" % dump_layouts())
            except OSError as e:
                print("terkb: не удалось записать раскладки: %s" % e,
                      file=sys.stderr)
                return 1
            return 0
        print(USAGE, file=sys.stderr)
        return 2
    return App().run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
