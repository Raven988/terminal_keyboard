#!/usr/bin/env python3
"""terkb — терминал со сплит-клавиатурой для планшета.

Половины клавиатуры прижаты к краям экрана, терминал между ними: планшет
держат двумя руками и набирают большими пальцами. Над левой половиной —
цифровой блок, над правой — стрелки.

Клавиатура и терминал живут в одном процессе, поэтому ввод отдаётся
VTE-виджету напрямую — без ydotool/uinput и без проблем с инжектом
ввода в Wayland.
"""

import json
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

APP_ID = "org.terkb.Terminal"

# --- геометрия ------------------------------------------------------------
# Всё считается в «четвертях клавиши»: обычная клавиша = 4, Tab = 6, Shift = 9
# и т.д. — как на настоящей раскладке ANSI.
U = 4

# Ширины половин. Правая шире: на неё приходятся Backspace, Enter и правый
# Shift. Окно делится в той же пропорции, поэтому клавиши в обеих половинах
# получаются одного размера.
SPLIT_L_W = 29
SPLIT_R_W = 34

# Во сколько раз клавише разрешено быть выше своей ширины.
KEY_STRETCH = 1.35

MAIN_ROWS = 6            # F-ряд, символы, qwerty, asdf, zxcv, пробел
NUM_ROWS = 4             # цифровой блок над левой половиной

# Стрелки «перевёрнутым Т» — в двух нижних рядах правой половины, под большим
# пальцем. Полторы обычных ширины каждая.
ARROW_W = 6

# Над правой половиной — блок модификаторов: Shift/Ctrl сверху, Alt/RU-EN под
# ними. Клавиши обычного размера: жмут их редко, а место лучше отдать высоте
# основной части.
MOD_W = U                # ширина клавиши блока в четвертях
MOD_H = 1                # высота в рядах

# Тачпад: узкая полоса рядом с блоком модификаторов — в одну клавишу шириной
# и в две высотой. Только перемотка вверх-вниз.
TOUCHPAD_ROWS = 2
TOUCHPAD_W = U

TOP_ROWS = max(2 * MOD_H, TOUCHPAD_ROWS)

SCROLL_SPEED = 1.0       # во сколько раз прокрутка быстрее движения пальца

# --- цельная раскладка (портрет) ------------------------------------------
# Планшет, повёрнутый вертикально, держат иначе: одной рукой снизу или лёжа на
# столе, а печатают указательным пальцем. Раскол под большие пальцы тут только
# мешает — окно узкое, половины сходятся посередине. Поэтому в портрете
# клавиатура становится обычной: сплошная сетка во всю ширину под терминалом.
FULL_W = 60              # ширина в «четвертях клавиши», как у ANSI-раскладки
FULL_ROWS = 7

# Сколько высоты окна цельной клавиатуре разрешено занять. Упрётся — станет
# уже полной ширины и встанет по центру: клавиши лучше мельче, чем терминал
# в три строки.
FULL_MAX_H = 0.55

# Программируемые клавиши: короткое нажатие выполняет команду, долгое —
# открывает строку правки. Сохраняются между запусками.
# Четыре в правой половине и ещё четыре в левой, рядом с цифровым блоком: там
# всё равно пустовало 13 четвертей на четыре ряда. Левые широкие — на них
# помещается имя команды целиком.
PROG_KEYS = 8
PROG_W = 5               # ширина в четвертях
PROG_L_KEYS = 4          # сколько из них в левой половине — по одной на ряд
PROG_L_W = SPLIT_L_W - 4 * U   # ширина клавиш левой половины: вся пустая зона

# Служебные слова, за которыми стоит настоящая команда: подпись на клавише
# должна показывать её, а не «sudo».
CMD_PREFIXES = {"sudo", "env", "nohup", "time", "doas", "exec", "command"}
CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "terkb")
MACRO_FILE = os.path.join(CONFIG_DIR, "macros.json")

# Схема, шрифт и его размер: всё, что правится кнопками панели и должно
# пережить перезапуск.
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Раскладки клавиш. Файла нет — работают встроенные; создать его с текущими
# раскладками умеет сам terkb (--dump-layout).
LAYOUT_FILE = os.path.join(CONFIG_DIR, "layout.json")

# Какую долю ширины окна занимают обе половины вместе. Стартовое значение:
# дальше оно живёт в настройках (ключ kb_fraction) и правится кнопками ⌨−/⌨+
# через множитель kb_scale — руками в коде менять больше не нужно.
KB_FRACTION = 0.68

# Кнопки ⌨−/⌨+ домножают эту долю. Верхняя граница — чтобы половины не
# сошлись посередине, нижняя — чтобы клавиши не стали неприцельными.
KB_SCALE_STEP = 0.1
KB_SCALE_MIN = 0.6
KB_SCALE_MAX = 1.35

# Сколько ширины окна половины не имеют права занимать суммарно: иначе в режиме
# наложения левая и правая наедут друг на друга.
KB_MAX_TOTAL = 0.94

# Зазор со стороны терминала. Окно-ручка GtkPaned шириной 9 px наезжает на
# крайнюю клавишу, и касание уходило на изменение размера, а не на клавишу:
# подсветка не загоралась. Замер показал перекрытие F7 на 4 px.
HANDLE_GUARD = 24

PANE_PAD = 4 + HANDLE_GUARD   # отступы .kb-pane слева и справа вместе

# Через сколько подсветка нажатия снимается сама, если release не пришёл.
HIT_TIMEOUT_MS = 600

# Плотность клавиш в режиме наложения. Меньше — сильнее просвечивает терминал,
# но хуже читаются подписи: под клавишами идёт текст. Правится на лету
# кнопками ◐−/◐+ в пределах GHOST_ALPHA_MIN..MAX.
GHOST_ALPHA = 0.82
GHOST_ALPHA_STEP = 0.08
GHOST_ALPHA_MIN = 0.30
GHOST_ALPHA_MAX = 1.0

# --- оформление -----------------------------------------------------------
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

# --- ссылки в выводе ------------------------------------------------------
# Что считать ссылкой. Хвостовая пунктуация отсекается: адрес в конце
# предложения обычно заканчивается точкой или запятой, и они в URL не входят.
# Второй шаблон ловит адреса без схемы (www.example.org) — к ним потом
# приписывается https://.
LINK_TAIL = r"""[^\s'"<>()\[\]{}«»]*[^\s'"<>()\[\]{}«».,;:!?]"""
LINK_PATTERNS = [
    r"(?:https?|ftp|file)://" + LINK_TAIL,
    r"www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}" + LINK_TAIL,
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
]

# PCRE2_MULTILINE — иначе VTE ругается на шаблон без якорей; значение зашито
# числом, потому что через GI константы PCRE2 не пробрасываются.
LINK_REGEX_FLAGS = 0x00000400


def pad_ratio(cols, rows):
    return cols / (rows * U * KEY_STRETCH)


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
SETTINGS_SPEC = {
    "scheme": (DEFAULT_SCHEME, lambda v: scheme_by_id(str(v)) is not None),
    "font": ("Monospace", lambda v: isinstance(v, str) and bool(v)),
    "font_size": (8, lambda v: isinstance(v, int)
                  and FONT_MIN <= v <= FONT_MAX),
    # Доля ширины окна под обе половины. Раньше правилась только в коде —
    # значит терялась при обновлении.
    "kb_fraction": (KB_FRACTION, lambda v: isinstance(v, (int, float))
                    and 0.2 <= v <= KB_MAX_TOTAL),
    "kb_scale": (1.0, lambda v: isinstance(v, (int, float))
                 and KB_SCALE_MIN <= v <= KB_SCALE_MAX),
    "ghost_alpha": (GHOST_ALPHA, lambda v: isinstance(v, (int, float))
                    and GHOST_ALPHA_MIN <= v <= GHOST_ALPHA_MAX),
    "ghost": (False, lambda v: isinstance(v, bool)),
    "hidden": (False, lambda v: isinstance(v, bool)),
    "fullscreen": (False, lambda v: isinstance(v, bool)),
    "width": (1280, lambda v: isinstance(v, int) and 320 <= v <= 8192),
    "height": (800, lambda v: isinstance(v, int) and 240 <= v <= 8192),
}


def load_settings():
    """Сохранённые настройки. Битый файл не должен ронять запуск."""
    out = {k: default for k, (default, _ok) in SETTINGS_SPEC.items()}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for key, (_default, ok) in SETTINGS_SPEC.items():
        if key in data:
            try:
                if ok(data[key]):
                    out[key] = data[key]
            except (TypeError, ValueError):
                pass
    return out


def save_settings(settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("terkb: не удалось сохранить настройки: %s" % e, file=sys.stderr)

# --- состояния модификаторов ----------------------------------------------
MOD_OFF, MOD_ONCE, MOD_LOCK = 0, 1, 2


def ctrl_code(ch):
    """ASCII-символ -> управляющий код, как его выдаёт настоящий Ctrl."""
    if not ch:
        return None
    c = ch.upper()
    if "A" <= c <= "Z":
        return bytes([ord(c) - 64])
    return {
        "@": b"\x00", " ": b"\x00", "[": b"\x1b", "\\": b"\x1c",
        "]": b"\x1d", "^": b"\x1e", "_": b"\x1f", "?": b"\x7f",
        "/": b"\x1f", "2": b"\x00", "3": b"\x1b", "4": b"\x1c",
        "5": b"\x1d", "6": b"\x1e", "7": b"\x1f", "8": b"\x7f",
    }.get(c)


class Key:
    """Описание одной клавиши.

    kind:
      char    — печатный символ (low/high — без Shift и с Shift)
      key     — специальная клавиша, задаётся keyval'ом GDK
      mod     — модификатор (Ctrl/Alt/Shift/Super), трёхпозиционный
      raw     — фиксированная последовательность байт
      action  — действие приложения (копировать/вставить/...)
    """

    def __init__(self, kind, low, high=None, keyval=None, w=U, h=1,
                 name=None, data=None, css=None, repeat=False):
        self.kind = kind
        self.low = low
        self.high = high if high is not None else low
        self.keyval = keyval
        self.w = w
        self.h = h
        self.name = name
        self.data = data
        self.css = css
        self.repeat = repeat
        self.button = None
        self.label = None
        self.x = self.y = 0       # место в сетке, проставляет KeyPad.add_key

    # -- обмен с файлом раскладки -------------------------------------------
    def to_spec(self):
        """Клавиша в виде словаря для layout.json. Пишем только то, что
        отличается от умолчаний: файл читают и правят руками."""
        spec = {"kind": self.kind, "low": self.low,
                "x": self.x, "y": self.y}
        if self.w != U:
            spec["w"] = self.w
        if self.h != 1:
            spec["h"] = self.h
        if self.kind == "char":
            spec["high"] = self.high
            if getattr(self, "ru", None):
                spec["ru"] = list(self.ru)
        if self.keyval is not None:
            spec["keyval"] = Gdk.keyval_name(self.keyval) or self.keyval
        if self.name is not None:
            spec["name"] = self.name
        if self.data is not None:
            spec["data"] = (self.data.decode("utf-8", "replace")
                            if isinstance(self.data, bytes) else self.data)
        if self.css:
            spec["css"] = self.css
        if self.repeat:
            spec["repeat"] = True
        return spec


def key_from_spec(spec):
    """Клавиша из словаря layout.json. Ошибку описываем словами: файл правят
    руками, и «KeyError» вместо «нет поля low» там не поможет."""
    if not isinstance(spec, dict):
        raise ValueError("клавиша должна быть объектом, а не %s"
                         % type(spec).__name__)
    kind = spec.get("kind")
    if kind not in ("char", "key", "mod", "raw", "action", "macro"):
        raise ValueError("неизвестный вид клавиши: %r" % (kind,))
    low = spec.get("low", "")
    if not isinstance(low, str):
        raise ValueError("подпись low должна быть строкой")

    keyval = spec.get("keyval")
    if isinstance(keyval, str):
        code = Gdk.keyval_from_name(keyval)
        if code == Gdk.KEY_VoidSymbol:
            raise ValueError("нет такой клавиши GDK: %r" % keyval)
        keyval = code
    if kind == "key" and keyval is None:
        raise ValueError("клавише %r нужен keyval" % low)
    if kind == "mod" and spec.get("name") not in ("ctrl", "alt", "shift",
                                                  "super"):
        raise ValueError("модификатор %r: name должен быть ctrl/alt/shift/super"
                         % low)

    data = spec.get("data")
    if kind == "macro":
        if not isinstance(data, int) or not 0 <= data < PROG_KEYS:
            raise ValueError("макросу нужен data от 0 до %d" % (PROG_KEYS - 1))
    elif kind == "raw" and isinstance(data, str):
        data = data.encode("utf-8")

    key = Key(kind, low, spec.get("high"), keyval=keyval,
              w=int(spec.get("w", U)), h=int(spec.get("h", 1)),
              name=spec.get("name"), data=data, css=spec.get("css"),
              repeat=bool(spec.get("repeat", False)))
    if kind == "char":
        ru = spec.get("ru") or [key.low, key.high]
        if len(ru) != 2:
            raise ValueError("ru у клавиши %r: нужны две подписи" % low)
        key.ru = (str(ru[0]), str(ru[1]))
    if key.w < 1 or key.h < 1:
        raise ValueError("клавиша %r: ширина и высота от одной четверти" % low)
    return key


def C(low, high, ru_low=None, ru_high=None, w=U):
    """Печатная клавиша с латинской и русской раскладкой."""
    k = Key("char", low, high, w=w, repeat=True)
    k.ru = (ru_low if ru_low is not None else low,
            ru_high if ru_high is not None else (ru_low or high))
    return k


def K(label, keyval, w=U, h=1, repeat=False, css="special"):
    return Key("key", label, keyval=keyval, w=w, h=h, repeat=repeat, css=css)


def M(label, name, w=U, h=1):
    return Key("mod", label, name=name, w=w, h=h, css="mod")


def R(label, data, w=U, css="special"):
    return Key("raw", label, data=data, w=w, css=css)


def A(label, name, w=U, h=1, css="special"):
    return Key("action", label, name=name, w=w, h=h, css=css)


def P(index, w=PROG_W):
    """Программируемая клавиша: data — её номер."""
    return Key("macro", "M%d" % (index + 1), w=w, data=index, css="macro")


def macro_label(cmd, index):
    """Короткая подпись на клавише макроса.

    Целиком команда не влезает: клавиша шириной чуть больше обычной, и подпись
    обрезалась многоточием на втором-третьем символе — «g…» не говорит ничего.
    Поэтому берём саму команду без пути и аргументов: «git», «htop», «run.sh».
    """
    for word in cmd.split():
        if word in CMD_PREFIXES or "=" in word:
            continue                      # sudo, env, VAR=значение
        name = os.path.basename(word.strip("\"'"))
        if name:
            return name[:12]
        break
    return "M%d" % (index + 1)


def load_macros():
    """Команды программируемых клавиш. Битый файл не должен ронять запуск."""
    try:
        with open(MACRO_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            out = [str(x) for x in data[:PROG_KEYS]]
            return out + [""] * (PROG_KEYS - len(out))
    except (OSError, ValueError):
        pass
    return [""] * PROG_KEYS


def save_macros(macros):
    try:
        os.makedirs(os.path.dirname(MACRO_FILE), exist_ok=True)
        with open(MACRO_FILE, "w", encoding="utf-8") as f:
            json.dump(macros, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("terkb: не удалось сохранить макросы: %s" % e, file=sys.stderr)


class KeyState:
    """Общее состояние обеих половин.

    Половины — разные наборы кнопок, но модификаторы, Caps и язык у них одни:
    нажал Shift слева — подсветились оба Shift и сработало на правой половине.
    """

    def __init__(self, send):
        self.send = send
        self.mods = {"ctrl": MOD_OFF, "alt": MOD_OFF,
                     "shift": MOD_OFF, "super": MOD_OFF}
        self.caps = False
        self.ru = False
        self.all_keys = []
        self.char_keys = []
        self._repeat_id = None
        self.macros = load_macros()
        self.on_macro_edit = None       # ставит окно: открыть строку правки

    # -- автоповтор ---------------------------------------------------------
    def on_press(self, _gesture, _n, _x, _y, key):
        self.press(key)
        self.stop_repeat()
        self._repeat_id = GLib.timeout_add(400, self._start_repeat, key)

    def on_release(self, *_a):
        self.stop_repeat()

    def _start_repeat(self, key):
        self._repeat_id = GLib.timeout_add(45, self._do_repeat, key)
        return False

    def _do_repeat(self, key):
        self.press(key, sticky=True)
        return True

    def stop_repeat(self):
        if self._repeat_id:
            GLib.source_remove(self._repeat_id)
            self._repeat_id = None

    # -- ввод ---------------------------------------------------------------
    def mod_on(self, name):
        return self.mods[name] != MOD_OFF

    def press(self, key, sticky=False):
        if key.kind == "mod":
            self.mods[key.name] = (self.mods[key.name] + 1) % 3
            self.refresh_mods()
            return
        if key.kind == "action":
            self.do_action(key.name)
            return
        if key.kind == "macro":
            cmd = self.macros[key.data]
            if cmd:
                self.send.text(cmd + "\n")
            elif self.on_macro_edit:
                # пустую клавишу логично сразу предложить заполнить
                self.on_macro_edit(key.data)
            return

        ctrl, alt = self.mod_on("ctrl"), self.mod_on("alt")
        shift, sup = self.mod_on("shift"), self.mod_on("super")

        if key.kind == "raw":
            self.send.raw(key.data)
        elif key.kind == "key":
            state = 0
            if ctrl:
                state |= Gdk.ModifierType.CONTROL_MASK
            if alt:
                state |= Gdk.ModifierType.MOD1_MASK
            if shift:
                state |= Gdk.ModifierType.SHIFT_MASK
            if sup:
                state |= Gdk.ModifierType.SUPER_MASK
            keyval = key.keyval
            if keyval == Gdk.KEY_Tab and shift:
                keyval = Gdk.KEY_ISO_Left_Tab
            self.send.keyval(keyval, state)
        else:  # char
            up = shift ^ (self.caps and key.low.isalpha())
            text = self.label_for(key, up)
            if ctrl:
                code = ctrl_code(key.high if shift else key.low)
                if code is None:
                    code = ctrl_code(key.low)
                if code is not None:
                    self.send.raw((b"\x1b" if alt else b"") + code)
                    self._clear_once(sticky)
                    return
            if alt:
                self.send.raw(b"\x1b" + text.encode())
            else:
                self.send.text(text)

        self._clear_once(sticky)

    def _clear_once(self, sticky=False):
        if sticky:
            return
        changed = False
        for name, state in self.mods.items():
            if state == MOD_ONCE:
                self.mods[name] = MOD_OFF
                changed = True
        if changed:
            self.refresh_mods()

    def do_action(self, name):
        if name == "caps":
            self.caps = not self.caps
            self.refresh_mods()
        elif name == "lang":
            self.ru = not self.ru
            self.refresh_labels()
        else:
            self.send.action(name)

    # -- отображение --------------------------------------------------------
    def label_for(self, key, upper):
        if self.ru and hasattr(key, "ru"):
            low, high = key.ru
        else:
            low, high = key.low, key.high
        return high if upper else low

    def set_macro(self, index, cmd):
        self.macros[index] = cmd
        save_macros(self.macros)
        self.refresh_macros()

    def refresh_macros(self):
        for key in self.all_keys:
            if key.kind != "macro":
                continue
            cmd = self.macros[key.data]
            key.label.set_text(macro_label(cmd, key.data))
            key.button.set_tooltip_text(
                "M%d: %s" % (key.data + 1, cmd) if cmd
                else "M%d — долгое нажатие задаёт команду" % (key.data + 1))
            ctx = key.button.get_style_context()
            if cmd:
                ctx.remove_class("kb-macro-empty")
            else:
                ctx.add_class("kb-macro-empty")

    def refresh_labels(self):
        shift = self.mod_on("shift")
        for key in self.char_keys:
            up = shift ^ (self.caps and key.low.isalpha())
            text = self.label_for(key, up)
            key.label.set_text("␣" if text == " " else text)

    def refresh_mods(self):
        # Ctrl/Alt/Shift есть в обеих половинах — красим все сразу.
        for key in self.all_keys:
            if key.kind == "mod":
                state = self.mods[key.name]
            elif key.kind == "action" and key.name == "caps":
                state = MOD_LOCK if self.caps else MOD_OFF
            else:
                continue
            ctx = key.button.get_style_context()
            ctx.remove_class("kb-active")
            ctx.remove_class("kb-locked")
            if state == MOD_ONCE:
                ctx.add_class("kb-active")
            elif state == MOD_LOCK:
                ctx.add_class("kb-locked")
        self.refresh_labels()


_pad_seq = [0]


class KeyPad(Gtk.Grid):
    """Одна половина клавиатуры."""

    def __init__(self, state, cols):
        super().__init__()
        self.state = state
        self.cols = cols
        self.keys = []

        self.set_row_homogeneous(True)
        self.set_column_homogeneous(True)
        # Промежутки делаются CSS-отступом внутри клавиши, а не spacing сетки:
        # при десятках колонок spacing съедал бы заметную долю ширины.
        self.set_row_spacing(0)
        self.set_column_spacing(0)

        # Шрифт пересчитывается под реальный размер клавиш, иначе подписи
        # обрезаются многоточием. Правило скоупится собственным классом:
        # провайдер в GTK3 действует на весь экран, а не на поддерево виджета.
        _pad_seq[0] += 1
        self.css_name = "kb-pad-%d" % _pad_seq[0]
        self.get_style_context().add_class(self.css_name)
        self._font_px = 0
        self._font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self._font_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.connect("size-allocate", self._on_alloc)

    def _on_alloc(self, _w, alloc):
        key_w = alloc.width / max(1, self.cols) * U
        px = max(7, min(34, round(key_w * 0.36)))
        if px != self._font_px:
            self._font_px = px
            GLib.idle_add(self._apply_font, px)

    def _apply_font(self, px):
        self._font_provider.load_from_data(
            (".%s .kb-key { font-size: %dpx; }\n"
             ".%s .kb-special, .%s .kb-mod, .%s .kb-tool { font-size: %dpx; }\n"
             % (self.css_name, px, self.css_name, self.css_name,
                self.css_name, max(6, int(px * 0.72)))).encode())
        return False

    # -- подсветка нажатия ---------------------------------------------------
    def _on_pressed(self, gesture, n, x, y, key):
        self.state.on_press(gesture, n, x, y, key)

    def _on_released(self, _gesture, _n, _x, _y, _key):
        self.state.on_release()

    def _on_cancel(self, _gesture, _sequence, _key):
        self.state.stop_repeat()

    def _on_long_press(self, _gesture, _x, _y, key):
        if self.state.on_macro_edit:
            self.state.on_macro_edit(key.data)

    def _on_state(self, btn, _old_flags):
        """Подсветку ведём от собственного состояния кнопки.

        Не от нашего жеста: он живёт в фазе CAPTURE, и у клавиш рядом с
        терминалом подсветка не загоралась, хотя нажатие срабатывало. Флаг
        ACTIVE ставит сама GtkButton — та же машинерия, что даёт "clicked",
        поэтому загорается везде, где клавиша вообще нажимается.
        """
        self.hit(btn, bool(btn.get_state_flags() & Gtk.StateFlags.ACTIVE))

    def hit(self, btn, on):
        """Подсветить нажатие.

        Своим классом, а не готовым видом состояния: после касания тачскрина
        виджет нередко остаётся в prelight, и подсветка залипала. Плюс
        страховка по таймауту — если ACTIVE почему-то не снимется, подсветка
        уйдёт сама.
        """
        if getattr(btn, "_hit_id", 0):
            GLib.source_remove(btn._hit_id)
            btn._hit_id = 0
        ctx = btn.get_style_context()
        if on:
            ctx.add_class("kb-hit")
            btn._hit_id = GLib.timeout_add(HIT_TIMEOUT_MS, self._hit_expired, btn)
        else:
            ctx.remove_class("kb-hit")

    def _hit_expired(self, btn):
        btn._hit_id = 0
        btn.get_style_context().remove_class("kb-hit")
        return False

    # -- построение ---------------------------------------------------------
    def add_key(self, key, col, row):
        if key is None:
            return
        btn = Gtk.Button()
        btn.set_can_focus(False)          # фокус остаётся в терминале
        lbl = Gtk.Label(label=key.low)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        # Без этого минимальная ширина длинных подписей раздувает всю
        # однородную сетку, и край клавиатуры уезжает за пределы панели.
        lbl.set_width_chars(1)
        lbl.set_max_width_chars(1)
        btn.set_size_request(1, 1)
        btn.add(lbl)
        btn.get_style_context().add_class("kb-key")
        if key.css:
            btn.get_style_context().add_class("kb-" + key.css)
        key.button, key.label = btn, lbl

        # Подсветка — от состояния самой кнопки, независимо от жестов.
        btn.connect("state-flags-changed", self._on_state)

        if key.kind == "macro":
            lp = Gtk.GestureLongPress.new(btn)
            lp.connect("pressed", self._on_long_press, key)
            key._long_press = lp

        if key.repeat:
            # Автоповтор при удержании. Жест в фазе CAPTURE видит события
            # раньше кнопки, поэтому "clicked" для таких клавиш не подключаем.
            g = Gtk.GestureMultiPress.new(btn)
            g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            g.connect("pressed", self._on_pressed, key)
            g.connect("released", self._on_released, key)
            g.connect("cancel", self._on_cancel, key)
            key._gesture = g
        else:
            btn.connect("clicked", lambda _b, k=key: self.state.press(k))

        key.x, key.y = col, row       # понадобится при выгрузке раскладки
        self.attach(btn, col, row, key.w, key.h)
        self.keys.append(key)
        self.state.all_keys.append(key)
        if key.kind == "char":
            self.state.char_keys.append(key)

    def add_widget(self, widget, col, row, w, h):
        """Вставить в сетку не-клавишу (тачпад)."""
        widget.set_size_request(1, 1)
        self.attach(widget, col, row, w, h)

    def row(self, keys, row, x0=0):
        x = x0
        for k in keys:
            if isinstance(k, int):      # число = пустой промежуток
                x += k
                continue
            self.add_key(k, x, row)
            x += k.w

# --- раскладки ------------------------------------------------------------
def build_left(pad):
    """Левая половина: цифровой блок сверху, под ним основная часть.

    Раскол по классическому месту — между T и Y, G и H, B и N. Ширина каждого
    ряда подогнана ровно под SPLIT_L_W.
    """
    E = Gdk
    # цифровой блок, 4 колонки в левом верхнем углу половины
    pad.row([C("7", "7"), C("8", "8"), C("9", "9"), C("/", "/")], 0)
    pad.row([C("4", "4"), C("5", "5"), C("6", "6"), C("*", "*")], 1)
    pad.row([C("1", "1"), C("2", "2"), C("3", "3"), C("-", "-")], 2)
    pad.row([C("0", "0", w=2 * U), C(".", "."), C("+", "+")], 3)

    # Справа от цифрового блока пустовало 13 четвертей на четыре ряда — туда
    # уходит вторая половина программируемых клавиш, по одной на ряд. Они
    # широкие: подпись с именем команды читается целиком.
    for i in range(PROG_L_KEYS):
        pad.add_key(P(PROG_KEYS - PROG_L_KEYS + i, w=PROG_L_W), 4 * U, i)

    r = NUM_ROWS
    pad.row([K("Esc", E.KEY_Escape, w=5),
             K("F1", E.KEY_F1), K("F2", E.KEY_F2), K("F3", E.KEY_F3),
             K("F4", E.KEY_F4), K("F5", E.KEY_F5), K("F6", E.KEY_F6)], r)
    # Цифры с этого ряда убраны — они есть на цифровом блоке. Основными стали
    # символы, цифра осталась под Shift. Сам ряд убрать нельзя: ` ~ ! @ # $ % ^
    # на цифровом блоке отсутствуют, а без них в шелле делать нечего.
    pad.row([C("`", "~", "ё", "Ё", w=5),
             C("!", "1"), C("@", "2", '"', "2"), C("#", "3", "№", "3"),
             C("$", "4", ";", "4"), C("%", "5"),
             C("^", "6", ":", "6")], r + 1)
    pad.row([K("Tab ⇥", E.KEY_Tab, w=9),
             C("q", "Q", "й", "Й"), C("w", "W", "ц", "Ц"), C("e", "E", "у", "У"),
             C("r", "R", "к", "К"), C("t", "T", "е", "Е")], r + 2)
    pad.row([A("Caps", "caps", w=9, css="mod"),
             C("a", "A", "ф", "Ф"), C("s", "S", "ы", "Ы"), C("d", "D", "в", "В"),
             C("f", "F", "а", "А"), C("g", "G", "п", "П")], r + 3)
    pad.row([M("Shift ⇧", "shift", w=9),
             C("z", "Z", "я", "Я"), C("x", "X", "ч", "Ч"), C("c", "C", "с", "С"),
             C("v", "V", "м", "М"), C("b", "B", "и", "И")], r + 4)
    pad.row([M("Ctrl", "ctrl", w=6), M("Super", "super", w=5),
             M("Alt", "alt", w=6), C(" ", " ", " ", " ", w=12)], r + 5)


class Touchpad(Gtk.EventBox):
    """Полоса перемотки справа: палец листает терминал вверх-вниз.

    Кликов не шлём: VTE не реагирует на синтетические события указателя —
    они до него доходят, но внутренние жесты требуют настоящего захвата
    устройства от композитора. Прокрутка же идёт мимо событий, прямо через
    vadjustment, и работает всегда.
    """

    def __init__(self, on_drag):
        super().__init__()
        self.set_above_child(True)
        self.get_style_context().add_class("kb-touchpad")
        lbl = Gtk.Label(label="⇕")
        lbl.get_style_context().add_class("kb-touchpad-hint")
        self.add(lbl)

        self._on_drag = on_drag
        self._last = 0.0
        g = Gtk.GestureDrag.new(self)
        g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        g.connect("drag-begin", self._begin)
        g.connect("drag-update", self._update)
        self._gesture = g

    def _begin(self, _g, _x, _y):
        self._last = 0.0

    def _update(self, _g, _ox, oy):
        dy = oy - self._last
        self._last = oy
        self._on_drag(dy)


def build_right(pad, touchpad=None):
    """Правая половина.

    Стрелки — в двух нижних рядах, под большим пальцем. Модификаторы и смена
    языка подняты наверх, на освободившееся место: они нажимаются раз в
    несколько символов, а стрелками в терминале работают постоянно.
    Copy/Paste оставлены здесь — иначе до буфера обмена на планшете не
    добраться.
    """
    E = Gdk
    # Сверху справа: полоса перемотки прижата к самому краю, блок
    # модификаторов — слева от неё. Место под полосу запоминаем на самой
    # сетке: полоса одна на все раскладки и переезжает между ними.
    tx = SPLIT_R_W - TOUCHPAD_W
    mx = tx - 2 * MOD_W
    pad.touchpad_at = (tx, 0, TOUCHPAD_W, TOUCHPAD_ROWS)
    pad.add_key(M("Shift ⇧", "shift", w=MOD_W, h=MOD_H), mx, 0)
    pad.add_key(M("Ctrl", "ctrl", w=MOD_W, h=MOD_H), mx + MOD_W, 0)
    pad.add_key(M("Alt", "alt", w=MOD_W, h=MOD_H), mx, MOD_H)
    pad.add_key(A("RU/EN", "lang", w=MOD_W, h=MOD_H, css="tool"),
                mx + MOD_W, MOD_H)
    if touchpad is not None:
        pad.add_widget(touchpad, tx, 0, TOUCHPAD_W, TOUCHPAD_ROWS)

    # Слева от них свободно 22 четверти на два ряда: навигация и макросы.
    pad.row([K("Home", E.KEY_Home), K("End", E.KEY_End),
             K("PgUp", E.KEY_Page_Up), K("PgDn", E.KEY_Page_Down),
             K("Del", E.KEY_Delete, repeat=True)], 0)
    # Остальные программируемые клавиши — в левой половине: здесь на них места
    # нет, а там пустует зона рядом с цифровым блоком.
    pad.row([P(i) for i in range(PROG_KEYS - PROG_L_KEYS)], 1)

    r = TOP_ROWS
    pad.row([K("F7", E.KEY_F7), K("F8", E.KEY_F8), K("F9", E.KEY_F9),
             K("F10", E.KEY_F10), K("F11", E.KEY_F11), K("F12", E.KEY_F12),
             A("⧉ Copy", "copy", w=5, css="tool"),
             A("📋 Paste", "paste", w=5, css="tool")], r)
    pad.row([C("&", "7", "?", "7"), C("*", "8"), C("(", "9"), C(")", "0"),
             C("-", "_"), C("=", "+"),
             K("⌫", E.KEY_BackSpace, w=10, repeat=True)], r + 1)
    pad.row([C("y", "Y", "н", "Н"), C("u", "U", "г", "Г"), C("i", "I", "ш", "Ш"),
             C("o", "O", "щ", "Щ"), C("p", "P", "з", "З"),
             C("[", "{", "х", "Х"), C("]", "}", "ъ", "Ъ"),
             C("\\", "|", w=6)], r + 2)
    pad.row([C("h", "H", "р", "Р"), C("j", "J", "о", "О"), C("k", "K", "л", "Л"),
             C("l", "L", "д", "Д"), C(";", ":", "ж", "Ж"),
             C("'", '"', "э", "Э"),
             K("Enter ⏎", E.KEY_Return, w=10, css="accent")], r + 3)
    # ↑ стоит ровно над ↓ — привычное «перевёрнутое Т»
    def arrow(label, keyval):
        return K(label, keyval, w=ARROW_W, repeat=True, css="arrow")

    ax = SPLIT_R_W - 3 * ARROW_W
    pad.row([C("n", "N", "т", "Т"), C("m", "M", "ь", "Ь"),
             C(",", "<", "б", "Б"), C(".", ">", "ю", "Ю"),
             C("/", "?", ".", ",")], r + 4)
    pad.add_key(arrow("↑", E.KEY_Up), ax + ARROW_W, r + 4)
    pad.row([C(" ", " ", " ", " ", w=ax)], r + 5)
    pad.row([arrow("←", E.KEY_Left), arrow("↓", E.KEY_Down),
             arrow("→", E.KEY_Right)], r + 5, ax)


def build_full(pad, touchpad=None):
    """Цельная раскладка для портрета: обычная ANSI-клавиатура во всю ширину.

    Здесь, в отличие от половин, основными в цифровом ряду стоят цифры:
    отдельного цифрового блока нет, а под Shift уходят символы — как на
    настоящей клавиатуре. Всё остальное повторяет сплит, чтобы при повороте
    не пришлось переучиваться: те же макросы, Copy/Paste и полоса перемотки.
    """
    E = Gdk
    # Полоса перемотки — в правом верхнем углу, на два служебных ряда. Шириной
    # в одну клавишу, как в сплите: освободившиеся четверти нужны служебному
    # ряду, где теперь лежат все шесть программируемых клавиш.
    tx = FULL_W - TOUCHPAD_W
    pad.touchpad_at = (tx, 0, TOUCHPAD_W, 2)
    if touchpad is not None:
        pad.add_widget(touchpad, *pad.touchpad_at)

    # Программируемые здесь обычной ширины: их восемь, и служебный ряд иначе
    # не сходится. Навигация ужата до трёх четвертей — по ней попадают реже
    # всего, а прокрутка в портрете и так есть на полосе перемотки.
    pad.row([P(i, w=U) for i in range(PROG_KEYS)]
            + [A("⧉ Copy", "copy", w=6, css="tool"),
               A("📋 Paste", "paste", w=6, css="tool"),
               K("Home", E.KEY_Home, w=3), K("End", E.KEY_End, w=3),
               K("PgUp", E.KEY_Page_Up, w=3),
               K("PgDn", E.KEY_Page_Down, w=3)], 0)
    pad.row([K("Esc", E.KEY_Escape, w=8),
             K("F1", E.KEY_F1), K("F2", E.KEY_F2), K("F3", E.KEY_F3),
             K("F4", E.KEY_F4), K("F5", E.KEY_F5), K("F6", E.KEY_F6),
             K("F7", E.KEY_F7), K("F8", E.KEY_F8), K("F9", E.KEY_F9),
             K("F10", E.KEY_F10), K("F11", E.KEY_F11), K("F12", E.KEY_F12)], 1)
    pad.row([C("`", "~", "ё", "Ё"),
             C("1", "!"), C("2", "@", "2", '"'), C("3", "#", "3", "№"),
             C("4", "$", "4", ";"), C("5", "%"), C("6", "^", "6", ":"),
             C("7", "&", "7", "?"), C("8", "*"), C("9", "("), C("0", ")"),
             C("-", "_"), C("=", "+"),
             K("⌫", E.KEY_BackSpace, w=8, repeat=True)], 2)
    pad.row([K("Tab ⇥", E.KEY_Tab, w=6),
             C("q", "Q", "й", "Й"), C("w", "W", "ц", "Ц"), C("e", "E", "у", "У"),
             C("r", "R", "к", "К"), C("t", "T", "е", "Е"),
             C("y", "Y", "н", "Н"), C("u", "U", "г", "Г"), C("i", "I", "ш", "Ш"),
             C("o", "O", "щ", "Щ"), C("p", "P", "з", "З"),
             C("[", "{", "х", "Х"), C("]", "}", "ъ", "Ъ"),
             C("\\", "|", w=6)], 3)
    pad.row([A("Caps", "caps", w=7, css="mod"),
             C("a", "A", "ф", "Ф"), C("s", "S", "ы", "Ы"), C("d", "D", "в", "В"),
             C("f", "F", "а", "А"), C("g", "G", "п", "П"),
             C("h", "H", "р", "Р"), C("j", "J", "о", "О"), C("k", "K", "л", "Л"),
             C("l", "L", "д", "Д"), C(";", ":", "ж", "Ж"),
             C("'", '"', "э", "Э"),
             K("Enter ⏎", E.KEY_Return, w=9, css="accent")], 4)
    pad.row([M("Shift ⇧", "shift", w=9),
             C("z", "Z", "я", "Я"), C("x", "X", "ч", "Ч"), C("c", "C", "с", "С"),
             C("v", "V", "м", "М"), C("b", "B", "и", "И"),
             C("n", "N", "т", "Т"), C("m", "M", "ь", "Ь"),
             C(",", "<", "б", "Б"), C(".", ">", "ю", "Ю"),
             C("/", "?", ".", ","),
             K("↑", E.KEY_Up, repeat=True, css="arrow"),
             K("Del", E.KEY_Delete, w=7, repeat=True)], 5)
    pad.row([M("Ctrl", "ctrl", w=6), M("Super", "super", w=5),
             M("Alt", "alt", w=5), A("RU/EN", "lang", w=6, css="tool"),
             C(" ", " ", " ", " ", w=26),
             K("←", E.KEY_Left, repeat=True, css="arrow"),
             K("↓", E.KEY_Down, repeat=True, css="arrow"),
             K("→", E.KEY_Right, repeat=True, css="arrow")], 6)


# --- раскладка из файла ---------------------------------------------------
# Три встроенные раскладки: как называются в layout.json, чем собираются и
# сколько в них колонок.
BUILTIN_LAYOUTS = {
    "left": (build_left, SPLIT_L_W),
    "right": (build_right, SPLIT_R_W),
    "full": (build_full, FULL_W),
}


def build_layout(pad, which, touchpad=None, spec=None):
    """Собрать раскладку: из файла, если он есть и цел, иначе встроенную.

    Файл — это возможность переставить клавиши, не трогая Python: добавить
    свои, поменять ширины, сделать вторую пару языков. Ошибку в нём не считаем
    поводом остаться без клавиатуры — говорим, что не так, и собираем
    встроенную.
    """
    builder = BUILTIN_LAYOUTS[which][0]
    if spec is None:
        return builder(pad, touchpad) if touchpad is not None else builder(pad)
    try:
        keys = spec["keys"]
        if not isinstance(keys, list) or not keys:
            raise ValueError("нет ни одной клавиши")
        parsed = [key_from_spec(k) for k in keys]
    except (KeyError, TypeError, ValueError) as e:
        print("terkb: раскладка «%s» из %s не годится (%s), беру встроенную"
              % (which, LAYOUT_FILE, e), file=sys.stderr)
        return builder(pad, touchpad) if touchpad is not None else builder(pad)

    for key, raw in zip(parsed, keys):
        pad.add_key(key, int(raw.get("x", 0)), int(raw.get("y", 0)))
    at = spec.get("touchpad")
    if isinstance(at, list) and len(at) == 4:
        pad.touchpad_at = tuple(int(v) for v in at)
    if touchpad is not None:
        pad.add_widget(touchpad, *pad.touchpad_at)


def load_layouts():
    """Раскладки из ~/.config/terkb/layout.json. Нет файла — нет и правок."""
    if not os.path.exists(LAYOUT_FILE):
        return {}
    try:
        with open(LAYOUT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("в файле должен быть объект")
    except (OSError, ValueError) as e:
        print("terkb: %s не читается (%s), беру встроенные раскладки"
              % (LAYOUT_FILE, e), file=sys.stderr)
        return {}
    return {k: v for k, v in data.items() if k in BUILTIN_LAYOUTS}


def dump_layouts(path=None):
    """Записать встроенные раскладки в файл — чтобы было что править.

    Собираем их во временном KeyState: клавишам нужен приёмник ввода, но
    нажимать их никто не собирается.
    """
    path = path or LAYOUT_FILE
    state = KeyState(None)
    out = {"note": "правьте и перезапустите; удалите файл — вернутся "
                   "встроенные раскладки",
           "keyval": "имена клавиш GDK: Return, BackSpace, Page_Up, F7, Up"}
    for which, (builder, cols) in BUILTIN_LAYOUTS.items():
        pad = KeyPad(state, cols)
        builder(pad)
        out[which] = {
            "cols": cols,
            "touchpad": list(getattr(pad, "touchpad_at", ())) or None,
            "keys": [k.to_spec() for k in pad.keys],
        }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return path


class EntrySink:
    """Приёмник ввода с экранной клавиатуры вместо терминала.

    Модального диалога тут быть не может: он перекрыл бы клавиатуру, которой
    и надо набирать. Поэтому строка правки встроена в окно, а ввод на это
    время подменяется — интерфейс тот же, что у Terminal.
    """

    def __init__(self, entry, accept, cancel):
        self.entry = entry
        self.accept = accept
        self.cancel = cancel

    def text(self, s):
        pos = self.entry.get_position()
        self.entry.insert_text(s, pos)
        self.entry.set_position(pos + len(s))

    def raw(self, data):
        try:
            s = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        if s.isprintable():
            self.text(s)

    def keyval(self, keyval, _state):
        e = self.entry
        pos = e.get_position()
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.accept()
        elif keyval == Gdk.KEY_Escape:
            self.cancel()
        elif keyval == Gdk.KEY_BackSpace:
            if pos > 0:
                e.delete_text(pos - 1, pos)
                e.set_position(pos - 1)
        elif keyval == Gdk.KEY_Delete:
            e.delete_text(pos, pos + 1)
        elif keyval == Gdk.KEY_Left:
            e.set_position(max(0, pos - 1))
        elif keyval == Gdk.KEY_Right:
            e.set_position(pos + 1)
        elif keyval == Gdk.KEY_Home:
            e.set_position(0)
        elif keyval == Gdk.KEY_End:
            e.set_position(-1)
        elif keyval == Gdk.KEY_Tab:
            self.text("    ")

    def action(self, name):
        if name == "paste":
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            txt = clip.wait_for_text()
            if txt:
                self.text(txt)


class Terminal(Gtk.Box):
    """Обёртка над VTE: терминал + вертикальный скроллбар."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.vte = Vte.Terminal()
        self.vte.set_scrollback_lines(50000)
        self.vte.set_mouse_autohide(True)
        self.vte.set_scroll_on_output(False)
        self.vte.set_scroll_on_keystroke(True)
        self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        self.vte.set_cursor_shape(Vte.CursorShape.BLOCK)
        self.font_size = 8
        self.font_family = "Monospace"
        self.apply_font()
        self.setup_links()

        self.pack_start(self.vte, True, True, 0)
        adj = self.vte.get_vadjustment()
        sb = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=adj)
        sb.get_style_context().add_class("term-scroll")
        self.pack_start(sb, False, False, 0)

    # -- ссылки -------------------------------------------------------------
    def setup_links(self):
        """Сделать ссылки в выводе нажимаемыми.

        На планшете ссылку иначе не открыть: выделить её пальцем в VTE толком
        не выходит, а перенабирать вручную — то ещё занятие. Кроме обычного
        поиска по тексту включаем OSC 8: программы вроде ls и gh отдают ссылку
        отдельной последовательностью, и угадывать её по виду не нужно.
        """
        self.link_tags = []
        try:
            self.vte.set_allow_hyperlink(True)
        except AttributeError:
            pass          # VTE старше 0.50
        for pattern in LINK_PATTERNS:
            try:
                regex = Vte.Regex.new_for_match(pattern, -1,
                                                LINK_REGEX_FLAGS)
                tag = self.vte.match_add_regex(regex, 0)
            except (AttributeError, GLib.Error):
                continue  # сборка VTE без PCRE2 — просто останемся без ссылок
            self.vte.match_set_cursor_name(tag, "pointer")
            self.link_tags.append(tag)
        self.vte.connect("button-press-event", self.on_click)

    def link_at(self, event):
        """URL под касанием: сначала OSC 8, потом распознанный по тексту."""
        try:
            uri = self.vte.hyperlink_check_event(event)
        except AttributeError:
            uri = None
        if uri:
            return uri
        match, tag = self.vte.match_check_event(event)
        if not match or tag not in self.link_tags:
            return None
        if "://" in match:
            return match
        # адрес почты открываем почтовиком, всё остальное — как http-адрес
        return ("mailto:" + match) if "@" in match else ("https://" + match)

    def on_click(self, _w, event):
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        uri = self.link_at(event)
        if not uri:
            return False
        try:
            Gtk.show_uri_on_window(self.get_toplevel(), uri, event.time)
        except GLib.Error as e:
            print("terkb: не удалось открыть %s: %s" % (uri, e.message),
                  file=sys.stderr)
        return True

    def apply_font(self):
        self.vte.set_font(Pango.FontDescription(
            "%s %d" % (self.font_family, self.font_size)))

    def zoom(self, delta):
        self.font_size = max(FONT_MIN, min(FONT_MAX, self.font_size + delta))
        self.apply_font()

    def set_font_family(self, family):
        self.font_family = family
        self.apply_font()

    def apply_scheme(self, scheme):
        """Цвета терминала. У «Системы» их нет — сбрасываем в тему GTK.

        set_colors перетирает и курсор с выделением, поэтому их ставим после
        неё, а не до.
        """
        palette = [gdk_rgba(c) for c in scheme["palette"]] or None
        fg = gdk_rgba(scheme["fg"]) if scheme["fg"] else None
        bg = gdk_rgba(scheme["bg"]) if scheme["bg"] else None
        self.vte.set_colors(fg, bg, palette)
        self.vte.set_color_cursor(
            gdk_rgba(scheme["cursor"]) if scheme["cursor"] else None)
        if scheme["sel"]:
            self.vte.set_color_highlight(gdk_rgba(scheme["sel"]))
            self.vte.set_color_highlight_foreground(fg)
        else:
            self.vte.set_color_highlight(None)
            self.vte.set_color_highlight_foreground(None)
        # Курсор-блок закрашивает символ под собой: без контрастного текста
        # под курсором не видно, какая это буква.
        try:
            self.vte.set_color_cursor_foreground(bg)
        except AttributeError:
            pass          # VTE старше 0.44
        try:
            self.vte.set_bold_is_bright(True)
        except AttributeError:
            pass          # VTE старше 0.52

    def spawn(self, on_exit):
        shell = os.environ.get("SHELL") or "/bin/bash"
        env = ["%s=%s" % (k, v) for k, v in os.environ.items()]
        env = [e for e in env if not e.startswith("COLUMNS=")]
        env.append("TERM=xterm-256color")
        self.vte.connect("child-exited", lambda *_a: on_exit())
        self.vte.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.path.expanduser("~"),
            [shell, "-l"],
            env,
            GLib.SpawnFlags.DEFAULT,
            None, None,
            -1, None,
            None, None,
        )

    # -- приём ввода от клавиатуры -----------------------------------------
    def text(self, s):
        self.raw(s.encode("utf-8"))

    def raw(self, data):
        try:
            self.vte.feed_child(data)
        except TypeError:
            self.vte.feed_child(data.decode("utf-8", "replace"), len(data))

    def keyval(self, keyval, state):
        """Синтезируем настоящее событие клавиши.

        Так VTE сам выберет правильную последовательность с учётом режима
        приложения (стрелки в vim/less шлют ESC O A, а не ESC [ A).
        """
        window = self.vte.get_window()
        if window is None:
            return
        display = self.vte.get_display()
        keymap = Gdk.Keymap.get_for_display(display)
        ok, entries = keymap.get_entries_for_keyval(keyval)
        keycode = entries[0].keycode if ok and entries else 0
        group = entries[0].group if ok and entries else 0

        for etype in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
            ev = Gdk.Event.new(etype)
            ev.window = window
            ev.send_event = 1
            ev.time = Gdk.CURRENT_TIME
            ev.state = Gdk.ModifierType(state)
            ev.keyval = keyval
            ev.hardware_keycode = keycode
            ev.group = group
            ev.is_modifier = 0
            self.vte.event(ev)

    def action(self, name):
        if name == "copy":
            if self.vte.get_has_selection():
                self.vte.copy_clipboard_format(Vte.Format.TEXT)
        elif name == "paste":
            self.vte.paste_clipboard()


# Состояния GTK (:hover, :active, :checked) везде перечислены явно. Без этого
# правило темы "button:hover" со специфичностью (0,1,1) перебивает наш
# одноклассовый ".kb-key", а на тачскрине GTK часто не снимает prelight после
# касания: подсветка залипала. Само нажатие показываем своим классом .kb-hit,
# который снимается по отпусканию и по таймауту.
CSS = """
.kb-key, .kb-key:hover, .kb-key:active, .kb-key:checked, .kb-key:focus {
  padding: 0; margin: 1px; min-width: 0; min-height: 0;
  border-radius: 6px;
  background-image: none;
  background-color: @theme_bg_color;
  border: 1px solid alpha(@theme_fg_color, 0.18);
  color: @theme_fg_color;
  text-shadow: none;
}
.kb-special, .kb-special:hover, .kb-special:active,
.kb-mod, .kb-mod:hover, .kb-mod:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.8em;
}
.kb-arrow, .kb-arrow:hover, .kb-arrow:active {
  background-color: alpha(@theme_fg_color, 0.14);
  font-size: 1.2em;
}
.kb-accent, .kb-accent:hover, .kb-accent:active {
  background-color: alpha(@theme_selected_bg_color, 0.45);
}
/* Copy/Paste и RU/EN — такие же, как остальные служебные клавиши: акцентный
   фон читался как «нажато». */
.kb-tool, .kb-tool:hover, .kb-tool:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.8em;
}
.kb-active, .kb-active:hover, .kb-active:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
  border-color: @theme_selected_bg_color;
}
.kb-locked, .kb-locked:hover, .kb-locked:active {
  background-color: #d4801a; color: #ffffff; border-color: #d4801a;
}
.kb-key.kb-hit, .kb-key.kb-hit:hover, .kb-key.kb-hit:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
  border-color: @theme_selected_bg_color;
}
.kb-pane { padding: 4px; }
.kb-macro, .kb-macro:hover, .kb-macro:active {
  background-color: alpha(@theme_fg_color, 0.10);
  font-size: 0.75em;
}
/* незаполненная клавиша не должна выглядеть как рабочая */
.kb-macro-empty, .kb-macro-empty:hover, .kb-macro-empty:active {
  background-color: transparent;
  border-style: dashed;
  color: alpha(@theme_fg_color, 0.45);
}
.kb-editor { padding: 2px 4px; }
.kb-touchpad {
  margin: 1px;
  border-radius: 8px;
  background-color: alpha(@theme_fg_color, 0.07);
  border: 1px dashed alpha(@theme_fg_color, 0.30);
}
.kb-touchpad:active { background-color: alpha(@theme_selected_bg_color, 0.25); }
.kb-touchpad-hint { color: alpha(@theme_fg_color, 0.35); font-size: 1.4em; }
"""

# Зазор подставляется числом, поэтому отдельной таблицей.
GUARD_CSS = """
.kb-pane-left  { padding-right: %(g)dpx; }
.kb-pane-right { padding-left:  %(g)dpx; }
"""

# Перезагружается на лету кнопками ◐−/◐+, поэтому отдельной таблицей.
GHOST_CSS = """
/* Режим наложения: клавиши лежат поверх терминала и просвечивают. Селекторы
   из двух классов, чтобы перебить одноклассовые правила базовой таблицы.
   Плотность подставляется на лету: под клавишами идёт текст терминала, и при
   сильной прозрачности он забивает подписи. */
.kb-ghost .kb-key, .kb-ghost .kb-key:hover, .kb-ghost .kb-key:active,
.kb-ghost .kb-key:checked, .kb-ghost .kb-key:focus {
  background-color: alpha(@theme_bg_color, %(a).2f);
  border-color: alpha(@theme_fg_color, 0.40);
  color: @theme_fg_color;
}
.kb-ghost .kb-special, .kb-ghost .kb-special:hover,
.kb-ghost .kb-special:active,
.kb-ghost .kb-mod, .kb-ghost .kb-mod:hover, .kb-ghost .kb-mod:active,
.kb-ghost .kb-tool, .kb-ghost .kb-tool:hover, .kb-ghost .kb-tool:active {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
}
.kb-ghost .kb-arrow, .kb-ghost .kb-arrow:hover, .kb-ghost .kb-arrow:active {
  background-color: alpha(shade(@theme_bg_color, 1.5), %(a).2f);
}
.kb-ghost .kb-accent, .kb-ghost .kb-accent:hover,
.kb-ghost .kb-accent:active {
  background-color: alpha(@theme_selected_bg_color, 0.62);
}
.kb-ghost .kb-active, .kb-ghost .kb-active:hover,
.kb-ghost .kb-active:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
}
.kb-ghost .kb-locked, .kb-ghost .kb-locked:hover,
.kb-ghost .kb-locked:active {
  background-color: #d4801a; color: #ffffff; border-color: #d4801a;
}
.kb-ghost .kb-key.kb-hit, .kb-ghost .kb-key.kb-hit:hover,
.kb-ghost .kb-key.kb-hit:active {
  background-color: @theme_selected_bg_color; color: #ffffff;
}
.kb-ghost .kb-macro, .kb-ghost .kb-macro:hover, .kb-ghost .kb-macro:active {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
}
.kb-ghost .kb-macro-empty, .kb-ghost .kb-macro-empty:hover {
  background-color: alpha(@theme_bg_color, %(a).2f);
  border-style: dashed;
}
.kb-ghost .kb-touchpad {
  background-color: alpha(shade(@theme_bg_color, 1.35), %(a).2f);
  border-color: alpha(@theme_fg_color, 0.45);
}
"""

# Цветовая схема красит не только терминал: клавиши, панель и строка правки
# берут цвета оттуда же. Иначе тёмный терминал сидит в светлой рамке системной
# темы, и окно выглядит склеенным из двух программ.
#
# Состояния (:hover, :active, ...) перечислены так же, как в базовой таблице:
# у провайдера приоритет выше, но при равной специфичности спорить не о чем.
# Правила для .kb-ghost идут парами к обычным — в наложении отличается только
# плотность фона.
SKIN_CSS = """
window.terkb-win { background-color: %(bg)s; color: %(fg)s; }
.terkb-bar, .kb-pane, .kb-editor {
  background-color: %(panel)s;
  color: %(fg)s;
}
.terkb-bar { border-bottom: 1px solid %(edge)s; }
/* В наложении подложка половин лежит поверх терминала: непрозрачной она
   закрыла бы текст между клавишами. */
.kb-pane.kb-ghost { background-color: transparent; }
.kb-editor label, .terkb-bar label { color: %(fg)s; }
.terkb-bar button, .kb-editor button,
.terkb-bar button:hover, .kb-editor button:hover,
.terkb-bar button:active, .kb-editor button:active,
.terkb-bar button:checked {
  background-image: none;
  background-color: %(special)s;
  border: 1px solid %(edge)s;
  color: %(fg)s;
  text-shadow: none;
}
.terkb-bar button:checked, .terkb-bar button:active, .kb-editor button:active {
  background-color: %(sel)s;
  border-color: %(sel)s;
  color: %(selfg)s;
}
.terkb-bar button:disabled { color: %(dim)s; border-color: %(edge)s; }
.kb-editor entry {
  background-image: none;
  background-color: %(key)s;
  border: 1px solid %(edge)s;
  color: %(fg)s;
}
.term-scroll { background-color: %(bg)s; border: none; }
.term-scroll slider {
  background-color: %(dim)s;
  border: none;
  border-radius: 6px;
  min-width: 8px;
}
.term-scroll slider:hover { background-color: %(sel)s; }

.kb-key, .kb-key:hover, .kb-key:active, .kb-key:checked, .kb-key:focus {
  background-color: %(key)s;
  border-color: %(edge)s;
  color: %(fg)s;
}
.kb-ghost .kb-key, .kb-ghost .kb-key:hover, .kb-ghost .kb-key:active,
.kb-ghost .kb-key:checked, .kb-ghost .kb-key:focus {
  background-color: alpha(%(key)s, %(a).2f);
  border-color: %(edge)s;
  color: %(fg)s;
}
.kb-special, .kb-special:hover, .kb-special:active,
.kb-mod, .kb-mod:hover, .kb-mod:active,
.kb-tool, .kb-tool:hover, .kb-tool:active,
.kb-macro, .kb-macro:hover, .kb-macro:active {
  background-color: %(special)s;
}
.kb-ghost .kb-special, .kb-ghost .kb-special:hover,
.kb-ghost .kb-special:active,
.kb-ghost .kb-mod, .kb-ghost .kb-mod:hover, .kb-ghost .kb-mod:active,
.kb-ghost .kb-tool, .kb-ghost .kb-tool:hover, .kb-ghost .kb-tool:active,
.kb-ghost .kb-macro, .kb-ghost .kb-macro:hover, .kb-ghost .kb-macro:active {
  background-color: alpha(%(special)s, %(a).2f);
}
.kb-arrow, .kb-arrow:hover, .kb-arrow:active {
  background-color: %(arrow)s;
}
.kb-ghost .kb-arrow, .kb-ghost .kb-arrow:hover, .kb-ghost .kb-arrow:active {
  background-color: alpha(%(arrow)s, %(a).2f);
}
.kb-accent, .kb-accent:hover, .kb-accent:active {
  background-color: alpha(%(sel)s, 0.45);
}
.kb-ghost .kb-accent, .kb-ghost .kb-accent:hover,
.kb-ghost .kb-accent:active {
  background-color: alpha(%(sel)s, 0.62);
}
.kb-active, .kb-active:hover, .kb-active:active,
.kb-key.kb-hit, .kb-key.kb-hit:hover, .kb-key.kb-hit:active,
.kb-ghost .kb-active, .kb-ghost .kb-active:hover, .kb-ghost .kb-active:active,
.kb-ghost .kb-key.kb-hit, .kb-ghost .kb-key.kb-hit:hover,
.kb-ghost .kb-key.kb-hit:active {
  background-color: %(sel)s;
  border-color: %(sel)s;
  color: %(selfg)s;
}
.kb-macro-empty, .kb-macro-empty:hover, .kb-macro-empty:active {
  background-color: transparent;
  border-style: dashed;
  color: %(dim)s;
}
.kb-ghost .kb-macro-empty, .kb-ghost .kb-macro-empty:hover {
  background-color: alpha(%(bg)s, %(a).2f);
  border-style: dashed;
}
.kb-touchpad {
  background-color: %(special)s;
  border: 1px dashed %(edge)s;
}
.kb-ghost .kb-touchpad {
  background-color: alpha(%(special)s, %(a).2f);
  border-color: %(edge)s;
}
.kb-touchpad:active, .kb-ghost .kb-touchpad:active {
  background-color: alpha(%(sel)s, 0.25);
}
.kb-touchpad-hint { color: %(dim)s; }
"""


def skin_colors(scheme, alpha):
    """Цвета для SKIN_CSS: от фона схемы к её тексту, ступенями."""
    bg, fg, sel = scheme["bg"], scheme["fg"], scheme["sel"]
    return {
        "a": alpha,
        "bg": bg,
        "fg": fg,
        "sel": sel,
        # текст на акцентном фоне: у светлых схем выделение светлое, и белым
        # по нему не прочитать
        "selfg": bg if luma(sel) > 0.55 else "#ffffff",
        # панель чуть отходит от фона терминала, клавиши — от панели: иначе
        # в светлых схемах всё сливается в одно пятно
        "panel": mix(bg, fg, 0.05),
        "key": mix(bg, fg, 0.14),
        "special": mix(bg, fg, 0.22),
        "arrow": mix(bg, fg, 0.30),
        "edge": mix(bg, fg, 0.34),
        "dim": mix(bg, fg, 0.45),
    }


def aspect(child, ratio):
    # yalign=1.0 — клавиатура прижата вниз, туда, где лежат большие пальцы
    fr = Gtk.AspectFrame(xalign=0.5, yalign=1.0, ratio=ratio, obey_child=False)
    fr.set_shadow_type(Gtk.ShadowType.NONE)
    fr.add(child)
    return fr


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app,
                         title="terkb — терминал со сплит-клавиатурой")
        self.get_style_context().add_class("terkb-win")

        self.settings = load_settings()
        self.set_default_size(self.settings["width"], self.settings["height"])
        self.fonts = available_fonts()
        self.term = Terminal()
        self.term.font_size = self.settings["font_size"]
        self.term.font_family = (self.settings["font"]
                                 if self.settings["font"] in self.fonts
                                 else "Monospace")
        self.term.apply_font()
        # Доля ширины под клавиатуру и её множитель: и то, и другое правится
        # кнопками ⌨−/⌨+ и переживает перезапуск.
        self.kb_fraction = self.settings["kb_fraction"]
        self.kb_scale = self.settings["kb_scale"]
        self.state = KeyState(self.term)
        self.kb = self.state          # для тестов и внешнего кода

        # Раскладки: свои из layout.json, если он есть, иначе встроенные.
        self.layouts = load_layouts()
        self.pad_left = KeyPad(self.state, SPLIT_L_W)
        build_layout(self.pad_left, "left", spec=self.layouts.get("left"))
        self.pad_right = KeyPad(self.state, SPLIT_R_W)
        # Полоса перемотки одна на все раскладки: она переезжает между сетками
        # вместе с переключением режима (mount_keyboard). Место, куда её
        # класть, каждая раскладка запомнила у себя в touchpad_at.
        self.touchpad = Touchpad(self.on_pad_drag)
        build_layout(self.pad_right, "right", self.touchpad,
                     self.layouts.get("right"))

        self.left_frame = aspect(self.pad_left,
                                 pad_ratio(SPLIT_L_W, NUM_ROWS + MAIN_ROWS))
        self.right_frame = aspect(self.pad_right,
                                  pad_ratio(SPLIT_R_W, TOP_ROWS + MAIN_ROWS))

        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.left_box.get_style_context().add_class("kb-pane")
        self.left_box.get_style_context().add_class("kb-pane-left")
        self.left_box.pack_start(self.left_frame, True, True, 0)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_box.get_style_context().add_class("kb-pane")
        self.right_box.get_style_context().add_class("kb-pane-right")
        self.right_box.pack_start(self.right_frame, True, True, 0)

        # Цельная раскладка для портрета. Живёт своим набором клавиш, а не
        # переставленными половинами: у неё другие ширины и другой цифровой
        # ряд. Состояние (модификаторы, Caps, язык, макросы) общее — оно
        # хранится в KeyState, куда клавиши прописываются при сборке.
        self.pad_full = KeyPad(self.state, FULL_W)
        build_layout(self.pad_full, "full", spec=self.layouts.get("full"))

        self.full_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.full_box.get_style_context().add_class("kb-pane")
        self.full_box.pack_start(aspect(self.pad_full,
                                        pad_ratio(FULL_W, FULL_ROWS)),
                                 True, True, 0)
        self.state.refresh_labels()     # после сборки всех трёх раскладок

        self.center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.bar = self.toolbar()
        self.center.pack_start(self.macro_editor(), False, False, 0)
        self.center.pack_start(self.search_bar(), False, False, 0)
        self.center.pack_start(self.term, True, True, 0)
        self.state.on_macro_edit = self.edit_macro

        # Два вложенных Paned: левая половина | (терминал | правая половина)
        # Два вложенных Paned: левая половина | (терминал | правая половина).
        # Оба разделителя перетаскиваются.
        #
        # resize=False у половин, True у терминала: при изменении размера окна
        # клавиатура сохраняет ширину, а слак забирает терминал. Если отдать
        # resize=True обеим сторонам, Paned начинает перераспределять место сам
        # и затирает выставленные позиции.
        self.inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.inner.pack1(self.center, True, False)
        self.inner.pack2(self.right_box, False, False)
        self.outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.outer.pack1(self.left_box, False, False)
        self.outer.pack2(self.inner, True, False)

        # В режиме наложения половины вынимаются из Paned и кладутся поверх
        # терминала: сам терминал при этом занимает всё окно.
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.outer)

        # Панель во всю ширину окна, а не только над терминалом: в центральной
        # колонке кнопки лезли в две строки и жались, а её ширина ещё и
        # меняется вместе с разделителями. Заодно панель оказывается снаружи
        # оверлея — в режиме наложения половины физически не могут перекрыть
        # её своими GdkWindow.
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root.pack_start(self.bar, False, False, 0)
        self.root.pack_start(self.overlay, True, True, 0)
        self.add(self.root)

        self.ghost = False
        self.portrait = False     # ставится по форме окна, см. set_portrait
        self.hidden = False       # клавиатура убрана кнопкой «Скрыть ⌨»
        self.fullscreen_on = False   # своё имя: fullscreen() — метод GTK
        # Цветовая схема и плотность клавиш поверх терминала правятся на лету
        # кнопками панели, поэтому у них свой провайдер: базовую таблицу
        # перезагружать незачем.
        self.ghost_alpha = self.settings["ghost_alpha"]
        self.ghost_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.ghost_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        gset = Gtk.Settings.get_default()
        self._prefer_dark = bool(gset and gset.get_property(
            "gtk-application-prefer-dark-theme"))
        self.set_scheme(self.settings["scheme"], save=False)
        self.set_font(self.term.font_family, save=False)
        for b in self.alpha_btns:
            b.set_sensitive(False)

        self._laid_out = (0, 0)   # размер, под который разложено
        self._retries = 0
        self._bar_h = 0           # высота панели, под которую разложено
        self.connect("size-allocate", self.on_alloc)
        self.bar.connect("size-allocate", self.on_bar_alloc)
        # Размер окна пишем не на каждое изменение, а один раз при закрытии:
        # иначе конфиг переписывался бы на каждый пиксель перетаскивания.
        self.connect("destroy", self.on_destroy)

        # Режимы восстанавливаем последними: кнопки уже собраны, дерево
        # виджетов готово, и обработчики сделают всю работу сами.
        if self.settings["fullscreen"]:
            self.fs_btn.set_active(True)
        if self.settings["hidden"]:
            self.hide_btn.set_active(True)
        elif self.settings["ghost"]:
            self.ghost_btn.set_active(True)

        self.state.refresh_macros()
        self.term.spawn(self.close)
        self.term.vte.grab_focus()

    def on_destroy(self, *_a):
        """Запомнить размер окна. В полном экране и в развёрнутом окне
        сохранять нечего: вернётся оно всё равно в те же границы, а записанный
        размер экрана потом мешал бы окну быть окном."""
        if not self.fullscreen_on and not self.is_maximized():
            w, h = self.get_size()
            self.store(width=w, height=h)

    def toolbar(self):
        # FlowBox, а не Box: минимальная ширина Box'а — это сумма всех кнопок,
        # и она становится полом для ширины терминала. С семью кнопками
        # разделитель переставал двигаться. FlowBox переносит их на вторую
        # строку, и минимум равен ширине одной кнопки.
        bar = Gtk.FlowBox()
        bar.get_style_context().add_class("terkb-bar")
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_min_children_per_line(1)
        bar.set_max_children_per_line(20)
        bar.set_row_spacing(2)
        bar.set_column_spacing(2)
        bar.set_homogeneous(False)

        def place(widget):
            widget.set_can_focus(False)
            bar.add(widget)
            widget.get_parent().set_can_focus(False)   # GtkFlowBoxChild

        def btn(label, cb, tip=None):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda *_a: cb())
            if tip:
                b.set_tooltip_text(tip)
            place(b)
            return b

        btn("A−", lambda: self.zoom_font(-1), "Уменьшить шрифт терминала")
        btn("A+", lambda: self.zoom_font(1), "Увеличить шрифт терминала")

        # Циклеры: на планшете список выбирать пальцем неудобно, а одна кнопка
        # с названием текущего значения и попадается легко, и сама показывает,
        # что сейчас выбрано.
        self.scheme_btn = btn("", self.next_scheme, "")
        self.font_btn = btn("", self.next_font, "")
        if len(self.fonts) < 2:
            self.font_btn.set_sensitive(False)

        self.kb_scale_btns = [
            btn("⌨−", lambda: self.zoom_kb(-KB_SCALE_STEP),
                "Клавиатуру меньше"),
            btn("⌨+", lambda: self.zoom_kb(KB_SCALE_STEP),
                "Клавиатуру больше"),
        ]

        self.alpha_btns = [
            btn("◐−", lambda: self.fade_kb(GHOST_ALPHA_STEP),
                "Клавиши плотнее (меньше прозрачности)"),
            btn("◐+", lambda: self.fade_kb(-GHOST_ALPHA_STEP),
                "Клавиши прозрачнее"),
        ]

        self.ghost_btn = Gtk.ToggleButton(label="Поверх")
        self.ghost_btn.set_tooltip_text(
            "Терминал во всю ширину, клавиши прозрачные поверх него")
        self.ghost_btn.connect("toggled", self.on_ghost)
        place(self.ghost_btn)

        self.hide_btn = Gtk.ToggleButton(label="Скрыть ⌨")
        self.hide_btn.set_tooltip_text(
            "Убрать клавиатуру совсем: терминал на всё окно")
        self.hide_btn.connect("toggled", self.on_hide_kb)
        place(self.hide_btn)

        self.search_btn = Gtk.ToggleButton(label="🔍")
        self.search_btn.set_tooltip_text("Искать по выводу терминала")
        self.search_btn.connect("toggled", self.on_search)
        place(self.search_btn)

        # На 10-дюймовом экране заголовок окна — это полсотни отъеденных
        # пикселей и лишний повод промахнуться мимо верхнего ряда клавиш.
        self.fs_btn = Gtk.ToggleButton(label="⛶")
        self.fs_btn.set_tooltip_text("Во весь экран, без заголовка окна")
        self.fs_btn.connect("toggled", self.on_fullscreen)
        place(self.fs_btn)
        return bar

    def on_fullscreen(self, btn):
        self.set_fullscreen(btn.get_active())
        self.term.vte.grab_focus()

    def set_fullscreen(self, on):
        self.fullscreen_on = on
        if on:
            self.fullscreen()
        else:
            self.unfullscreen()
        self.store(fullscreen=on)

    # -- режим наложения ----------------------------------------------------
    def on_ghost(self, btn):
        self.set_ghost(btn.get_active())
        self.term.vte.grab_focus()

    def set_ghost(self, on):
        self.ghost = on
        for box, halign in ((self.left_box, Gtk.Align.START),
                            (self.right_box, Gtk.Align.END)):
            parent = box.get_parent()
            if parent is not None:
                parent.remove(box)
            ctx = box.get_style_context()
            if on:
                ctx.add_class("kb-ghost")
                box.set_halign(halign)
                # Прижимаем вниз и задаём высоту ровно по клавиатуре: у
                # оверлей-ребёнка своё GdkWindow, и всё, что он накрывает,
                # перестаёт нажиматься. Растянутый на всю высоту, он забирал
                # бы касания у верхних строк терминала.
                box.set_valign(Gtk.Align.END)
                self.overlay.add_overlay(box)
            else:
                ctx.remove_class("kb-ghost")
                box.set_halign(Gtk.Align.FILL)
                box.set_valign(Gtk.Align.FILL)
                box.set_size_request(-1, -1)
        if not on:
            # порядок важен: pack1 у outer, pack2 у inner
            self.outer.pack1(self.left_box, False, False)
            self.inner.pack2(self.right_box, False, False)
        self.left_box.show_all()
        self.right_box.show_all()
        self.update_mode_buttons()
        self.store(ghost=on)
        self._laid_out = (0, 0)   # заставить пересчитать
        self.schedule_layout()

    # -- раскладка окна: поворот и скрытие ----------------------------------
    def mount_keyboard(self):
        """Повесить в дерево ту клавиатуру, которая сейчас нужна.

        Все три раскладки собраны при запуске, поэтому переключение режима —
        это только перевешивание виджетов. Пересобирать нечего: состояние
        (модификаторы, Caps, язык, макросы) общее и живёт в KeyState.
        """
        for box in (self.left_box, self.right_box, self.full_box):
            parent = box.get_parent()
            if parent is not None:
                parent.remove(box)
        if self.hidden:
            return
        if self.portrait:
            self.move_touchpad(self.pad_full)
            self.center.pack_end(self.full_box, False, False, 0)
            self.full_box.show_all()
        else:
            self.move_touchpad(self.pad_right)
            # порядок важен: pack1 у outer, pack2 у inner
            self.outer.pack1(self.left_box, False, False)
            self.inner.pack2(self.right_box, False, False)
            self.left_box.show_all()
            self.right_box.show_all()

    def move_touchpad(self, pad):
        """Перевесить полосу перемотки в нужную раскладку.

        Полоса одна на все три: у неё свой GdkWindow и жест перетаскивания, и
        держать по копии на раскладку — значит держать копии состояния.
        """
        if self.touchpad.get_parent() is pad:
            return
        parent = self.touchpad.get_parent()
        if parent is not None:
            parent.remove(self.touchpad)
        pad.add_widget(self.touchpad, *pad.touchpad_at)
        self.touchpad.show_all()

    def update_mode_buttons(self):
        """Что можно нажать в текущем режиме.

        Без клавиатуры нечего накладывать и нечего масштабировать; в портрете
        размер задан шириной окна, а терминал и так во всю ширину. Прозрачность
        видна только под наложением.
        """
        live = not self.portrait and not self.hidden
        self.ghost_btn.set_sensitive(live)
        for b in self.kb_scale_btns:
            b.set_sensitive(live)
        for b in self.alpha_btns:
            b.set_sensitive(self.ghost and not self.hidden)

    def set_portrait(self, on):
        """Переключить раскладку под форму окна."""
        self.portrait = on
        # Наложение в портрете смысла не имеет: клавиатура и так внизу, а
        # терминал над ней во всю ширину.
        if on and self.ghost:
            self.ghost_btn.set_active(False)          # снимет режим наложения
        self.mount_keyboard()
        self.update_mode_buttons()
        self._laid_out = (0, 0)

    def on_hide_kb(self, btn):
        self.set_hidden(btn.get_active())
        self.term.vte.grab_focus()

    def set_hidden(self, on):
        """Убрать клавиатуру совсем: терминал на всё окно.

        Нужно, когда на планшет подключили настоящую клавиатуру или когда
        надо посмотреть длинный вывод целиком — в отличие от наложения, здесь
        экран не занят даже полупрозрачными клавишами.
        """
        self.hidden = on
        if on and self.ghost:
            self.ghost_btn.set_active(False)
        self.mount_keyboard()
        self.update_mode_buttons()
        self.hide_btn.set_label("Вернуть ⌨" if on else "Скрыть ⌨")
        self.store(hidden=on)
        self._laid_out = (0, 0)
        self.schedule_layout()

    def full_key(self, w, h):
        """Размер клавиши цельной раскладки: по ширине окна, с потолком по
        высоте — иначе на узком экране терминал ужимается в пару строк."""
        key = (w - PANE_PAD) / FULL_W * U
        if h > 50:
            key = min(key, (h * FULL_MAX_H - PANE_PAD) / FULL_ROWS
                      / KEY_STRETCH)
        return max(1.0, key)

    def key_size(self, w, h):
        """Размер клавиши, общий для обеих половин.

        Один размер на обе — иначе клавиши слева и справа разъедутся. По
        высоте тоже ограничиваем, иначе AspectFrame ужмёт половины по-разному.
        """
        cols = SPLIT_L_W + SPLIT_R_W
        key = w * self.kb_fraction * self.kb_scale / cols * U
        # потолок по ширине: половины не должны сойтись посередине
        key = min(key, w * KB_MAX_TOTAL / cols * U)
        if h > 50:
            rows = max(NUM_ROWS, TOP_ROWS) + MAIN_ROWS
            key = min(key, (h - PANE_PAD) / rows / KEY_STRETCH)
        return key

    # -- программируемые клавиши ---------------------------------------------
    def macro_editor(self):
        """Строка правки макроса. Живёт в окне, а не в диалоге: модальное окно
        перекрыло бы клавиатуру, которой и надо набирать."""
        # Подписи короткие и поле узкое намеренно: минимальная ширина Box'а —
        # это сумма детей, и она стала бы полом для центральной колонки,
        # сдвинув разделители (уже наступали на это с панелью инструментов).
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.get_style_context().add_class("kb-editor")
        self.macro_label = Gtk.Label(label="")
        box.pack_start(self.macro_label, False, False, 0)

        self.macro_entry = Gtk.Entry()
        self.macro_entry.set_width_chars(6)
        self.macro_entry.set_placeholder_text("команда, например: ls -la")
        box.pack_start(self.macro_entry, True, True, 0)

        for label, tip, cb in (("✓", "Сохранить", self.macro_accept),
                               ("✕", "Отмена", self.macro_cancel)):
            b = Gtk.Button(label=label)
            b.set_can_focus(False)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            box.pack_start(b, False, False, 0)

        box.set_no_show_all(True)
        self.macro_box = box
        self.macro_index = -1
        return box

    def edit_macro(self, index):
        self.macro_index = index
        self.macro_label.set_text("M%d" % (index + 1))
        self.macro_entry.set_text(self.state.macros[index])
        self.macro_entry.set_position(-1)
        self.macro_box.show()
        for w in self.macro_box.get_children():
            w.show()
        self.macro_entry.grab_focus()
        # ввод с клавиатуры на время правки уходит в поле, а не в терминал
        self.state.send = EntrySink(self.macro_entry, self.macro_accept,
                                    self.macro_cancel)

    def macro_accept(self):
        if self.macro_index >= 0:
            self.state.set_macro(self.macro_index,
                                 self.macro_entry.get_text().strip())
        self.macro_cancel()

    def macro_cancel(self):
        self.macro_index = -1
        self.macro_box.hide()
        self.state.send = self.term          # ввод снова идёт в терминал
        self.term.vte.grab_focus()

    # -- поиск по выводу -----------------------------------------------------
    def search_bar(self):
        """Строка поиска. Устроена как строка правки макроса: встроена в окно,
        а не диалогом, и на время поиска забирает ввод с экранной клавиатуры —
        иначе набирать запрос было бы нечем."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.get_style_context().add_class("kb-editor")
        box.pack_start(Gtk.Label(label="🔍"), False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_width_chars(6)
        self.search_entry.set_placeholder_text("что искать")
        self.search_entry.connect("changed", lambda *_a: self.search_apply())
        box.pack_start(self.search_entry, True, True, 0)

        for label, tip, cb in (("↑", "Раньше в выводе", self.search_prev),
                               ("↓", "Позже в выводе", self.search_next),
                               ("✕", "Закрыть поиск", self.search_close)):
            b = Gtk.Button(label=label)
            b.set_can_focus(False)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            box.pack_start(b, False, False, 0)

        box.set_no_show_all(True)
        self.search_box = box
        return box

    def on_search(self, btn):
        if btn.get_active():
            self.search_open()
        else:
            self.search_close()

    def search_open(self):
        self.search_box.show()
        for w in self.search_box.get_children():
            w.show()
        self.search_entry.grab_focus()
        self.state.send = EntrySink(self.search_entry, self.search_prev,
                                    self.search_close)
        self.search_apply()

    def search_close(self):
        self.search_box.hide()
        self.term.vte.search_set_regex(None, 0)
        self.state.send = self.term          # ввод снова идёт в терминал
        self.search_btn.set_active(False)
        self.term.vte.grab_focus()

    def search_apply(self):
        """Отдать VTE текущий запрос. Ищем как простой текст: регулярное
        выражение на экранной клавиатуре никто набирать не станет."""
        text = self.search_entry.get_text()
        vte = self.term.vte
        if not text:
            vte.search_set_regex(None, 0)
            return
        try:
            regex = Vte.Regex.new_for_search(
                GLib.Regex.escape_string(text, -1), -1, LINK_REGEX_FLAGS)
        except (AttributeError, GLib.Error):
            return
        vte.search_set_regex(regex, 0)
        vte.search_set_wrap_around(True)

    def search_prev(self):
        """Предыдущее совпадение — то есть раньше в выводе, выше по экрану."""
        self.search_apply()
        self.term.vte.search_find_previous()

    def search_next(self):
        self.search_apply()
        self.term.vte.search_find_next()

    # -- тачпад --------------------------------------------------------------
    def on_pad_drag(self, dy):
        """Палец по полосе листает терминал. Как на телефоне: тянешь вниз —
        уходишь к более ранним строкам."""
        self.scroll_lines(-dy * SCROLL_SPEED
                          / max(1.0, self.term.vte.get_char_height()))

    def scroll_lines(self, lines):
        adj = self.term.vte.get_vadjustment()
        top = max(adj.get_lower(), adj.get_upper() - adj.get_page_size())
        adj.set_value(min(top, max(adj.get_lower(), adj.get_value() + lines)))

    # -- оформление ---------------------------------------------------------
    def apply_ghost_css(self):
        """Перезагрузить динамическую таблицу.

        Имя историческое: сначала здесь была только плотность клавиш в режиме
        наложения, теперь оттуда же приходят цвета схемы. У «Системы» своих
        цветов нет — работает прежняя таблица поверх темы GTK.
        """
        if self.scheme["bg"] is None:
            css = GHOST_CSS % {"a": self.ghost_alpha}
        else:
            css = SKIN_CSS % skin_colors(self.scheme, self.ghost_alpha)
        self.ghost_provider.load_from_data(css.encode())

    def set_scheme(self, ident, save=True):
        self.scheme = scheme_by_id(ident) or SCHEMES[0]
        self.term.apply_scheme(self.scheme)
        self.apply_ghost_css()
        # Системные виджеты (выпадашки, тултипы, курсор в поле правки) нашей
        # таблицей не покрыты — им остаётся сказать только, светлая схема или
        # тёмная. У «Системы» возвращаем то, что стояло до запуска.
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property(
                "gtk-application-prefer-dark-theme",
                self._prefer_dark if self.scheme["bg"] is None
                else is_dark(self.scheme))
        self.scheme_btn.set_label(self.scheme["name"])
        self.scheme_btn.set_tooltip_text(
            "Схема: %s. Нажать — следующая" % self.scheme["name"])
        if save:
            self.store(scheme=self.scheme["id"])

    def next_scheme(self):
        ids = [s["id"] for s in SCHEMES]
        self.set_scheme(ids[(ids.index(self.scheme["id"]) + 1) % len(ids)])
        self.term.vte.grab_focus()

    def set_font(self, family, save=True):
        self.term.set_font_family(family)
        # «JetBrains Mono» в кнопку не влезает, а слово Mono у всех одинаковое
        # и ничего не различает.
        short = family.replace(" Sans Mono", "").replace(" Mono", "")
        self.font_btn.set_label(short if short != "Monospace" else "Моно")
        self.font_btn.set_tooltip_text(
            "Шрифт: %s. Нажать — следующий" % family)
        if save:
            self.store(font=family)

    def next_font(self):
        if len(self.fonts) < 2:
            return
        cur = self.term.font_family
        i = self.fonts.index(cur) + 1 if cur in self.fonts else 0
        self.set_font(self.fonts[i % len(self.fonts)])
        self.term.vte.grab_focus()

    def zoom_font(self, delta):
        self.term.zoom(delta)
        self.store(font_size=self.term.font_size)
        self.term.vte.grab_focus()

    def store(self, **kw):
        self.settings.update(kw)
        save_settings(self.settings)

    def fade_kb(self, delta):
        """Изменить плотность клавиш в режиме наложения."""
        a = min(GHOST_ALPHA_MAX, max(GHOST_ALPHA_MIN, self.ghost_alpha + delta))
        if abs(a - self.ghost_alpha) < 1e-9:
            return
        self.ghost_alpha = a
        self.apply_ghost_css()
        self.store(ghost_alpha=a)
        self.term.vte.grab_focus()

    def bar_height(self, w):
        """Высота панели. До первого размещения аллокации ещё нет, а считать
        по ней нельзя: раскладка сойдётся на заниженной высоте панели, клавиши
        получатся крупнее, чем влезает, и половины разъедутся — у левой рядов
        больше, и AspectFrame ужмёт её сильнее правой. Поэтому спрашиваем
        предпочтительную высоту под известную ширину."""
        h = self.bar.get_allocation().height
        if h > 1:
            return h
        return self.bar.get_preferred_height_for_width(max(1, w))[1]

    def avail_height(self, w, h):
        """Высота, доступная клавиатуре.

        h — высота всего окна, а панель лежит над клавиатурой во всю ширину,
        и в обычном режиме, и в наложении.
        """
        return h - self.bar_height(w)

    def on_bar_alloc(self, _w, alloc):
        """Панель переехала на другое число строк — клавиатуре досталось
        больше или меньше высоты, надо пересчитать."""
        if alloc.height != self._bar_h:
            self._bar_h = alloc.height
            self._laid_out = (0, 0)
            self.schedule_layout()

    def zoom_kb(self, delta):
        """Изменить размер клавиатуры.

        В режиме наложения это единственный способ: разделителей там нет.
        В обычном режиме кнопки переставляют разделители — подвинуть их потом
        руками всё равно можно.
        """
        scale = min(KB_SCALE_MAX, max(KB_SCALE_MIN, self.kb_scale + delta))
        if abs(scale - self.kb_scale) < 1e-9:
            return
        a = self.root.get_allocation()
        if a.width > 100 and delta > 0:
            # Клавиатура может упереться в высоту окна раньше, чем масштаб
            # дойдёт до предела. Копить недостижимый масштаб нельзя: иначе
            # ⌨+ жмётся вхолостую, а потом ⌨− несколько раз без реакции.
            h = self.avail_height(a.width, a.height)
            before = self.key_size(a.width, h)
            prev, self.kb_scale = self.kb_scale, scale
            if self.key_size(a.width, h) <= before + 0.01:
                self.kb_scale = prev
                return
        else:
            self.kb_scale = scale
        self.store(kb_scale=self.kb_scale)
        self.schedule_layout()
        self.term.vte.grab_focus()

    def half_widths(self, w, h):
        """Ширины половин: пропорционально числу колонок в каждой."""
        key = self.key_size(w, h)
        return (int(key * SPLIT_L_W / U) + PANE_PAD,
                int(key * SPLIT_R_W / U) + PANE_PAD)

    def half_height(self, key, rows):
        return int(key * rows * KEY_STRETCH) + PANE_PAD

    def targets(self, width=None, height=None):
        """Желаемые размеры половин под текущий режим.

        Размер берётся у root, а не у окна: в тестах дерево виджетов живёт
        в OffscreenWindow, и аллокация самого окна остаётся нулевой.
        """
        a = self.root.get_allocation()
        w = width if width is not None else a.width
        h = height if height is not None else a.height
        if w <= 100:
            return None
        avail = self.avail_height(w, h)
        if self.hidden:
            # клавиатуры в дереве нет, размеры считать не для кого
            return {"w": w, "h": h}
        if self.portrait:
            key = self.full_key(w, avail)
            return {"w": w, "h": h, "fh": self.half_height(key, FULL_ROWS)}
        key = self.key_size(w, avail)
        return {
            "w": w, "h": h,
            "lw": int(key * SPLIT_L_W / U) + PANE_PAD,
            "rw": int(key * SPLIT_R_W / U) + PANE_PAD,
            "lh": self.half_height(key, NUM_ROWS + MAIN_ROWS),
            "rh": self.half_height(key, TOP_ROWS + MAIN_ROWS),
        }

    def relayout(self, width=None, height=None):
        """Применить раскладку. False — размеры ещё не готовы."""
        self.check_orientation(width, height)
        t = self.targets(width, height)
        if t is None:
            return False
        if self.hidden:
            # Пустая сторона Paned всё равно держит позицию разделителя —
            # без этого терминал остался бы прежней ширины с пустотой по краям.
            self.outer.set_position(0)
            self.inner.set_position(t["w"])
        elif self.portrait:
            # Клавиатуре — своя высота, остальное забирает терминал. Ширину не
            # трогаем: цельная раскладка идёт во всю ширину окна.
            self.full_box.set_size_request(-1, t["fh"])
        elif self.ghost:
            self.left_box.set_size_request(t["lw"], t["lh"])
            self.right_box.set_size_request(t["rw"], t["rh"])
        else:
            self.outer.set_position(t["lw"])
            self.inner.set_position(max(120, t["w"] - t["lw"] - t["rw"]))
        return True

    def place_dividers(self, width=None, height=None):
        """Разложить под явный размер и добить асинхронно.

        Нужно тестам и харнессу скриншотов: там окно не показано на экране,
        size-allocate не приходит, и сам по себе schedule_layout не запустится.
        """
        self.relayout(width, height)
        self.schedule_layout()

    def check_orientation(self, width=None, height=None):
        """Портрет или альбом — по форме окна, а не по монитору.

        Композитор поворачивает экран, окно приезжает узким и высоким; тот же
        признак работает и когда окно просто вытянули мышью. Квадрат остаётся
        за альбомом: в нём сплит ещё помещается.
        """
        a = self.root.get_allocation()
        w = width if width is not None else a.width
        h = height if height is not None else a.height
        if w <= 100 or h <= 100:
            return
        want = h > w
        if want != self.portrait:
            self.set_portrait(want)

    def layout_ok(self):
        """Приняло ли GTK выставленные размеры."""
        t = self.targets()
        if t is None:
            return False
        if self.hidden:
            return True
        if self.portrait:
            return abs(self.full_box.get_allocation().height - t["fh"]) <= 2
        return (abs(self.left_box.get_allocation().width - t["lw"]) <= 2
                and abs(self.right_box.get_allocation().width - t["rw"]) <= 2)

    def schedule_layout(self):
        """Разложить, когда GTK досчитает размеры.

        Сразу после смены режима аллокации ещё старые: Paned обрезает позицию
        по прежней ширине, а половина, которой ничего не выставили, схлопы-
        вается в свой минимум. Поэтому пробуем на idle и повторяем, пока не
        сойдётся. Счётчик попыток обнуляется на каждый новый запрос — иначе
        после нескольких переключений он исчерпывался навсегда, и раскладка
        переставала чиниться.
        """
        self._retries = 0
        GLib.idle_add(self._layout_step)

    def _layout_step(self):
        if self._retries >= 15:
            return False
        self._retries += 1
        if not self.relayout():
            GLib.timeout_add(50, self._layout_step)   # окно ещё не размещено
        elif not self.layout_ok():
            GLib.timeout_add(30, self._layout_step)
        return False

    def on_alloc(self, _w, alloc):
        size = (alloc.width, alloc.height)
        if alloc.width > 100 and size != self._laid_out:
            # Раскладываем при смене размера окна. Дальше в обычном режиме
            # разделители — дело пользователя, мы их не трогаем.
            self._laid_out = size
            self.schedule_layout()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
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


def main(argv):
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
