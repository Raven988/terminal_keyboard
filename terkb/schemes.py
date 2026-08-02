"""Цветовые схемы, работа с цветом и выбор шрифта."""

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

# Схема задаёт цвета не только терминалу, но и клавиатуре с панелью: иначе
# тёмный терминал сидит в светлой рамке системной темы и окно выглядит
# склеенным из двух программ. Переключаются кнопкой-циклером по кругу.
#
# fg/bg/cursor/sel — базовые цвета, palette — стандартные 16 ANSI-цветов
# (8 обычных, 8 ярких) в том порядке, в котором их ждёт VTE.
SCHEMES = [
    {
        "id": "system", "name": "Система",
        # Цвета не трогаем вовсе: VTE и клавиатура берут их у темы GTK.
        "fg": None, "bg": None, "cursor": None, "sel": None, "palette": [],
    },
    {
        "id": "dracula", "name": "Dracula",
        "fg": "#f8f8f2", "bg": "#282a36", "cursor": "#f8f8f2", "sel": "#44475a",
        "palette": [
            "#21222c", "#ff5555", "#50fa7b", "#f1fa8c",
            "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
            "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5",
            "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
        ],
    },
    {
        "id": "gruvbox", "name": "Gruvbox",
        "fg": "#ebdbb2", "bg": "#282828", "cursor": "#ebdbb2", "sel": "#504945",
        "palette": [
            "#282828", "#cc241d", "#98971a", "#d79921",
            "#458588", "#b16286", "#689d6a", "#a89984",
            "#928374", "#fb4934", "#b8bb26", "#fabd2f",
            "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
        ],
    },
    {
        "id": "nord", "name": "Nord",
        "fg": "#d8dee9", "bg": "#2e3440", "cursor": "#d8dee9", "sel": "#434c5e",
        "palette": [
            "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b",
            "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
            "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b",
            "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
        ],
    },
    {
        "id": "tokyo", "name": "Tokyo",
        "fg": "#c0caf5", "bg": "#1a1b26", "cursor": "#c0caf5", "sel": "#33467c",
        "palette": [
            "#15161e", "#f7768e", "#9ece6a", "#e0af68",
            "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6",
            "#414868", "#f7768e", "#9ece6a", "#e0af68",
            "#7aa2f7", "#bb9af7", "#7dcfff", "#c0caf5",
        ],
    },
    {
        "id": "mocha", "name": "Mocha",
        "fg": "#cdd6f4", "bg": "#1e1e2e", "cursor": "#f5e0dc", "sel": "#585b70",
        "palette": [
            "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
            "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8",
        ],
    },
    {
        "id": "solar-dark", "name": "Solar ◑",
        "fg": "#93a1a1", "bg": "#002b36", "cursor": "#93a1a1", "sel": "#073642",
        "palette": [
            "#073642", "#dc322f", "#859900", "#b58900",
            "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83",
            "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
    },
    {
        "id": "solar-light", "name": "Solar ◐",
        "fg": "#586e75", "bg": "#fdf6e3", "cursor": "#586e75", "sel": "#eee8d5",
        "palette": [
            "#073642", "#dc322f", "#859900", "#b58900",
            "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83",
            "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
    },
]

DEFAULT_SCHEME = "dracula"

# Кандидаты в шрифты терминала. В системе их обычно стоит два-три, поэтому
# список фильтруется по установленным: циклер не должен листать пустоту.
# «Monospace» — псевдоним, он есть всегда, и с него начинается цикл.
FONT_CHOICES = [
    "Monospace", "JetBrains Mono", "Fira Code", "Cascadia Code", "Hack",
    "Iosevka", "Source Code Pro", "IBM Plex Mono", "Ubuntu Mono",
    "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono",
]

FONT_MIN, FONT_MAX = 6, 40


# --- цвета ----------------------------------------------------------------
def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def mix(a, b, t):
    """Смешать два цвета: t=0 — чистый a, t=1 — чистый b."""
    ca, cb = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(
        int(round(255 * (x + (y - x) * t))) for x, y in zip(ca, cb))


def luma(hex_color):
    r, g, b = rgb(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(scheme):
    return scheme["bg"] is None or luma(scheme["bg"]) < 0.5


def gdk_rgba(hex_color):
    c = Gdk.RGBA()
    c.parse(hex_color)
    return c


def scheme_by_id(ident):
    for s in SCHEMES:
        if s["id"] == ident:
            return s
    return None


def available_fonts():
    """Моноширинные шрифты из FONT_CHOICES, которые есть в системе."""
    try:
        families = {f.get_name() for f
                    in Gtk.Label().get_pango_context().list_families()}
    except Exception:
        return ["Monospace"]
    return [f for f in FONT_CHOICES if f == "Monospace" or f in families]


# Что лежит в settings.json: значение по умолчанию и проверка. Всё, что не
# прошло проверку, заменяется умолчанием — битый или отредактированный руками
# файл не должен ронять запуск и не должен приводить к неработающему окну
# (нулевой клавиатуре, окну в один пиксель).
